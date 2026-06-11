"""
langgraph_engine.py — Deterministic RAG DAG for SEC filings.

Nodes: Retrieval -> XBRL Extraction -> Math Execution -> Verification -> Output
Conditional edge on Verification failure: -> Abstention
"""
from datetime import datetime, timezone
from typing import TypedDict, List, Dict, Any, Optional, Union
import polars as pl

from langgraph.graph import StateGraph, END
from langchain_core.documents import Document

from api.config import Config
from api.services.sec_client import get_latest_10k_facts, chunk_filing_sections
from api.services.verifier import verifier
from api.services.rag_engine import EDGAREmbeddingsRetriever, PolygonRetriever
from api.services.reranker import rerank as rerank_docs
from api.services.guardrails.retrieval_rails import filter_retrieval
from loguru import logger

# Eval pipeline (Phases 2-5) — wired in as a post-extraction node.
try:
    from api.models.eval_types import ExtractionResult, ExtractedField, Provenance, PolygonData
    from api.services.schema_validator import validate_extraction
    from api.services.confidence_scorer import score_and_route
    _EVAL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _EVAL_AVAILABLE = False
from api.services.financial_calc import (
    FactExtractor, CalcResult,
    gross_margin, operating_margin, net_margin, rd_intensity, current_ratio, debt_to_equity, net_debt, free_cash_flow, check_balance_sheet,
)


# ---------------------------------------------------------------------------
# State Definition
# ---------------------------------------------------------------------------

class GraphState(TypedDict):
    """
    Strict TypedDict state matching the JSON payload expected by the React app.
    """
    query: str
    ticker: str
    retrieved_docs: List[Dict[str, Any]]
    xbrl_facts: List[Dict[str, Any]]
    polygon_data: List[Dict[str, Any]]
    math_result: Optional[Union[float, str]]
    math_steps: List[str]
    verification_status: str # PASS, FAIL, ERROR
    verification_reasoning: str
    final_answer: str
    status: Dict[str, str] # {node_name: 'success' | 'error' | 'pending'}
    # Eval pipeline outputs (populated by eval_node, optional)
    eval_route: Optional[str]           # AUTO | SAMPLED_REVIEW | ESCALATE
    eval_confidence: Optional[float]    # record-level confidence score
    eval_triggers: Optional[List[str]]  # always-escalate triggers that fired
    # Audit lineage (populated by lineage_node, always present in output)
    lineage: Optional[Dict[str, Any]]

# ---------------------------------------------------------------------------
# Node Functions
# ---------------------------------------------------------------------------

def retrieval_node(state: GraphState) -> Dict[str, Any]:
    """
    Node 1: Retrieve relevant text chunks from SEC filings and Polygon data.
    Uses DuckDB vector similarity as primary for filings.
    Uses PolygonRetriever for structured market data.
    """
    logger.info(f"--- RETRIEVAL: {state['ticker']} ---")
    try:
        query = state['query']
        ticker = state['ticker']

        # 1. Retrieve SEC Filing Chunks (Primary: vector similarity)
        docs = []
        try:
            edgar_retriever = EDGAREmbeddingsRetriever(top_k=5, ticker=ticker)
            docs = edgar_retriever.invoke(query)
        except Exception as e:
            logger.warning(f"Vector retrieval failed, falling back to keyword: {e}")

        # Fallback: keyword search on filing sections
        if not docs:
            chunks = chunk_filing_sections(ticker)
            keywords = query.lower().split()
            matched_chunks = [
                c for c in chunks
                if any(k in c['chunk_text'].lower() for k in keywords)
            ][:5]
            docs = [Document(page_content=c["chunk_text"], metadata=c.get("metadata", {})) for c in matched_chunks]

        # Rerank by cross-encoder relevance
        docs = rerank_docs(query, docs, top_k=Config.RERANKER_TOP_K)

        retrieved = [
            {
                "chunk_text": d.page_content,
                "metadata": d.metadata,
                "source": d.metadata.get("source", "edgar_embeddings"),
            }
            for d in docs
        ]

        # Apply retrieval rail — filter irrelevant chunks
        verdict = filter_retrieval(query, retrieved)
        if verdict.dropped_count > 0:
            logger.info(f"Retrieval rail: dropped {verdict.dropped_count}/{verdict.original_count} irrelevant chunks")
        retrieved = verdict.filtered_chunks

        # 2. Retrieve Polygon Data (Structured metadata and prices)
        polygon_data = []
        try:
            poly_retriever = PolygonRetriever()
            poly_results = poly_retriever.invoke(query, ticker=ticker)
            import dataclasses
            polygon_data = [dataclasses.asdict(p) for p in poly_results]
        except Exception as e:
            logger.warning(f"Polygon retrieval failed: {e}")

        return {
            "retrieved_docs": retrieved,
            "polygon_data": polygon_data,
            "status": {**state.get('status', {}), "retrieval": "success"}
        }
    except Exception as e:
        logger.error(f"Retrieval failed: {e}")
        return {"status": {**state.get('status', {}), "retrieval": "error"}}

def extraction_node(state: GraphState) -> Dict[str, Any]:
    """
    Node 2: Extract structured XBRL facts using Polars.
    """
    logger.info(f"--- EXTRACTION: {state['ticker']} ---")
    try:
        df = get_latest_10k_facts(state['ticker'])
        if df.is_empty():
            return {
                "xbrl_facts": [],
                "status": {**state.get('status', {}), "extraction": "success"}
            }
        
        # Convert Polars DF to list of dicts for the state
        facts = df.to_dicts()
        return {
            "xbrl_facts": facts,
            "status": {**state.get('status', {}), "extraction": "success"}
        }
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        return {"status": {**state.get('status', {}), "extraction": "error"}}

def math_node(state: GraphState) -> Dict[str, Any]:
    """
    Node 3: Route to the right Polars financial calculator based on query intent.

    AI identifies the question type. Python does ALL arithmetic via financial_calc.
    See docs/FINANCIAL_CALC_INSTRUCTIONS.md for the full instruction set.
    """
    logger.info("--- MATH EXECUTION (financial_calc) ---")
    try:
        facts_list = state['xbrl_facts']
        query      = state['query'].lower()
        steps:  list[str] = []
        result: Optional[Union[float, str]] = None
        calc: Optional[CalcResult] = None

        if not facts_list:
            return {
                "math_result": "ABSTAIN: No XBRL facts available for this filing.",
                "math_steps": ["Extraction returned 0 facts."],
                "status": {**state.get('status', {}), "math": "success"},
            }

        # Build Polars DataFrame from the list-of-dicts state
        xbrl_df = pl.DataFrame(facts_list)
        extractor = FactExtractor(xbrl_df)
        periods   = extractor.periods()
        latest    = periods[-1] if periods else ""
        # Fix #5: warn if period strings are non-ISO (affects sort correctness)
        if latest and not latest[:4].isdigit():
            logger.warning(f"Non-ISO period format detected: {latest!r} — sort order may be wrong")
        steps.append(f"Available periods: {periods}  | using: {latest}")

        # ── Route by question intent ────────────────────────────────────────
        # Fix #2: all guards use explicit `is not None` to handle zero-valued facts
        # Gross margin
        if any(k in query for k in ("gross margin", "gross profit margin")):
            rev  = extractor.get("revenues",      period=latest)
            cogs = extractor.get("costofrevenue",  period=latest)
            if rev is not None and cogs is not None:
                calc = gross_margin(rev, cogs, period=latest)

        # Operating margin
        elif any(k in query for k in ("operating margin", "operating income margin")):
            rev  = extractor.get("revenues",           period=latest)
            oi   = extractor.get("operatingincomeloss", period=latest)
            if rev is not None and oi is not None:
                calc = operating_margin(rev, oi, period=latest)

        # Net margin
        elif any(k in query for k in ("net margin", "profit margin", "net income margin")):
            rev = extractor.get("revenues",     period=latest)
            ni  = extractor.get("netincomeloss", period=latest)
            if rev is not None and ni is not None:
                calc = net_margin(rev, ni, period=latest)

        # Free cash flow / FCF
        elif any(k in query for k in ("free cash flow", "fcf")):
            ocf   = extractor.get("netcashoperating",    period=latest)
            capex = extractor.get("capitalexpenditures",  period=latest)
            if ocf is not None and capex is not None:
                calc = free_cash_flow(ocf, capex, period=latest)

        # Current ratio / liquidity
        elif any(k in query for k in ("current ratio", "liquidity ratio")):
            ca = extractor.get("currentassets",     period=latest)
            cl = extractor.get("currentliabilities", period=latest)
            if ca is not None and cl is not None:
                calc = current_ratio(ca, cl, period=latest)

        # Fix #7: removed bare "leverage" keyword — too broad (matches operating leverage etc.)
        elif any(k in query for k in ("debt to equity", "debt-to-equity", "d/e ratio")):
            debt   = extractor.get("longtermdebt",       period=latest)
            equity = extractor.get("stockholdersequity",  period=latest)
            if debt is not None and equity is not None:
                calc = debt_to_equity(debt, equity, period=latest)

        # Net debt
        elif any(k in query for k in ("net debt", "net cash position")):
            debt = extractor.get("longtermdebt",      period=latest)
            cash = extractor.get("cashandequivalents", period=latest)
            if debt is not None and cash is not None:
                calc = net_debt(debt, cash, period=latest)

        # R&D intensity
        elif any(k in query for k in ("r&d", "research and development", "rd intensity")):
            rev = extractor.get("revenues",               period=latest)
            rd  = extractor.get("researchanddevelopment",  period=latest)
            if rev is not None and rd is not None:
                calc = rd_intensity(rev, rd, period=latest)

        # Revenue standalone fallback
        elif any(k in query for k in ("revenue", "net sales", "total revenue")):
            rev = extractor.get("revenues", period=latest)
            if rev is not None:
                result = rev
                steps.append(f"Revenue ({latest}): ${rev:,.0f}")

        # Net income standalone fallback
        elif any(k in query for k in ("net income", "net earnings")):
            ni = extractor.get("netincomeloss", period=latest)
            if ni is not None:
                result = ni
                steps.append(f"Net Income ({latest}): ${ni:,.0f}")

        # If a CalcResult was produced, record it
        if calc is not None:
            result = calc.value
            steps.append(calc.display())
            # Run accounting identity check as a bonus verification signal
            try:
                assets = extractor.get("assets",      period=latest)
                liabs  = extractor.get("liabilities",  period=latest)
                eq     = extractor.get("stockholdersequity", period=latest)
                if assets and liabs and eq:
                    identity = check_balance_sheet(assets, liabs, eq, period=latest)
                    steps.append(f"Balance sheet identity: {identity.verdict} "
                                 f"(delta {identity.delta_pct:.2f}%)")
            except Exception:
                pass

        if result is None:
            result = "ABSTAIN: Could not determine the appropriate calculation for this query."
            steps.append("No matching calculation route found.")

        return {
            "math_result": result,
            "math_steps": steps,
            "status": {**state.get('status', {}), "math": "success"},
        }
    except Exception as e:
        logger.error(f"Math node failed: {e}")
        return {
            "math_result": f"ABSTAIN: Math node error — {e}",
            "math_steps": [str(e)],
            "status": {**state.get('status', {}), "math": "error"},
        }

def verification_node(state: GraphState) -> Dict[str, Any]:
    """
    Node 4: Verify the math result against the source text (retrieved docs).
    """
    logger.info("--- VERIFICATION ---")
    try:
        if not state['retrieved_docs'] or isinstance(state['math_result'], str):
            return {
                "verification_status": "FAIL",
                "verification_reasoning": "Insufficient source text or non-numeric result to verify.",
                "status": {**state.get('status', {}), "verification": "success"}
            }
        
        # Trivial numeric verification against itself (placeholder)
        # In a real app, verify against a different source or rule
        claim = f"The value is {state['math_result']}"
        source = " ".join([d['chunk_text'] for d in state['retrieved_docs']])
        
        status, reasoning = verifier.verify_entailment(claim, source)
        
        return {
            "verification_status": status,
            "verification_reasoning": reasoning,
            "status": {**state.get('status', {}), "verification": "success"}
        }
    except Exception as e:
        logger.error(f"Verification node failed: {e}")
        return {
            "verification_status": "ERROR",
            "verification_reasoning": str(e),
            "status": {**state.get('status', {}), "verification": "error"}
        }

def eval_node(state: GraphState) -> Dict[str, Any]:
    """Eval Node (Phase 2-5): Run schema + confidence scoring over extracted XBRL facts.

    Converts the raw xbrl_facts list into an ExtractionResult and passes it
    through the eval pipeline.  The routing decision and confidence score are
    stored in the state for the audit trail but do NOT block the pipeline —
    escalation is surfaced to the caller, not used as a hard gate here so that
    the existing abstention logic is preserved.
    """
    logger.info("--- EVAL ---")
    if not _EVAL_AVAILABLE:
        return {"status": {**state.get('status', {}), "eval": "skipped"}}

    try:
        ticker = state.get("ticker", "")
        facts  = state.get("xbrl_facts", [])

        # Build a minimal ExtractionResult from the XBRL facts in state.
        # We use CIK=ticker as a placeholder when the real CIK is not in state.
        fields: List[ExtractedField] = []
        for fact in facts:
            name  = str(fact.get("concept", fact.get("label", "")))
            value = fact.get("value") or fact.get("val")
            if name and value is not None:
                try:
                    fields.append(ExtractedField(
                        name=name,
                        value=float(value),
                        provenance=Provenance.XBRL,
                        concept=name,
                    ))
                except (TypeError, ValueError):
                    pass

        if not fields:
            logger.info("Eval: no XBRL fields extracted — skipping scorer (no_data)")
            return {
                "eval_route":      None,
                "eval_confidence": None,
                "eval_triggers":   ["no_data"],
                "status": {**state.get('status', {}), "eval": "no_data"},
            }

        extraction = ExtractionResult(
            cik=ticker,
            accession="0000000000-00-000000",  # placeholder — real accession not in state
            form_type="10-K",
            period=None,
            fields=fields,
        )

        schema_result = validate_extraction(extraction)
        decision      = score_and_route(extraction, ticker=ticker)

        logger.info(
            "Eval: route=%s conf=%.2f triggers=%s schema_valid=%s",
            decision.route.value, decision.confidence,
            decision.triggers_fired, schema_result.is_valid,
        )

        return {
            "eval_route":      decision.route.value,
            "eval_confidence": round(decision.confidence, 4),
            "eval_triggers":   decision.triggers_fired,
            "status": {**state.get('status', {}), "eval": "success"},
        }
    except Exception as exc:
        logger.warning("Eval node error (non-fatal): {}", exc)
        return {"status": {**state.get('status', {}), "eval": "error"}}


def output_node(state: GraphState) -> Dict[str, Any]:
    """
    Final Node: Format the successful answer.
    """
    logger.info("--- OUTPUT ---")
    answer = f"Based on the SEC filing for {state['ticker']}, the answer is {state['math_result']}."
    if state['verification_status'] == "PASS":
        answer += f" (Verified: {state['verification_reasoning']})"
    elif state['verification_status'] == "SKIPPED":
        answer += " (Note: NLI verification was skipped — model not available)"
    # Surface eval routing decision in the answer when escalation is triggered.
    if state.get("eval_route") == "ESCALATE" and state.get("eval_triggers"):
        answer += (
            f" [Eval: ESCALATE — triggers: {', '.join(state['eval_triggers'])}]"
        )
    return {
        "final_answer": answer,
        "status": {**state.get('status', {}), "output": "success"}
    }

def abstention_node(state: GraphState) -> Dict[str, Any]:
    """
    Fallback Node: Handle verification failures or missing data.
    """
    logger.info("--- ABSTENTION ---")
    return {
        "final_answer": "I cannot answer this question with sufficient confidence based on the available SEC filing data.",
        "status": {**state.get('status', {}), "output": "success"}
    }


def lineage_node(state: GraphState) -> Dict[str, Any]:
    """
    Lineage Node: Build the audit lineage record for every response.

    Collects source document identifiers and chunk IDs from retrieved docs,
    tags the model used, and auto-inserts a review queue entry when the eval
    pipeline routes to SAMPLED_REVIEW or ESCALATE.
    """
    logger.info("--- LINEAGE ---")
    import duckdb
    from api.db.review_queue import init_review_tables, insert_decision

    chunk_ids: List[str] = []
    source_docs: List[str] = []
    for doc in state.get("retrieved_docs", []):
        meta = doc.get("metadata", {})
        cid = meta.get("chunk_id") or meta.get("accession_number") or meta.get("chunk_index")
        if cid is not None:
            chunk_ids.append(str(cid))
        src = str(meta.get("accession_number") or meta.get("source", ""))
        if src and src not in source_docs:
            source_docs.append(src)

    cfg = Config.get_provider_config()
    eval_route = state.get("eval_route")
    review_id: Optional[str] = None

    if eval_route in ("SAMPLED_REVIEW", "ESCALATE"):
        try:
            db_path = Config.REVIEW_DB_PATH
            with duckdb.connect(db_path) as conn:
                init_review_tables(conn)
                review_id = insert_decision(conn, {
                    "cik": state.get("ticker", ""),
                    "accession": source_docs[0] if source_docs else "unknown",
                    "form_type": "10-K",
                    "route": eval_route,
                    "confidence": state.get("eval_confidence") if state.get("eval_confidence") is not None else 0.0,
                    "triggers_fired": state.get("eval_triggers") if state.get("eval_triggers") is not None else [],
                })
            logger.info(f"Review queue entry created: {review_id} (route={eval_route})")
        except Exception as exc:
            logger.warning(f"Review queue insert failed (non-fatal): {exc}")

    lineage: Dict[str, Any] = {
        "source_docs": source_docs,
        "chunk_ids": chunk_ids,
        "model": cfg["model"],
        "confidence": state.get("eval_confidence"),
        "eval_route": eval_route,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "review_id": review_id,
    }

    return {
        "lineage": lineage,
        "status": {**state.get("status", {}), "lineage": "success"},
    }


# ---------------------------------------------------------------------------
# Graph Definition
# ---------------------------------------------------------------------------

def decide_next_step(state: GraphState) -> str:
    """
    Deterministic routing based on verification result.
    PASS or SKIPPED (NLI unavailable) -> output.
    FAIL or ERROR -> abstention.
    """
    if state['verification_status'] in ("PASS", "SKIPPED"):
        return "output"
    else:
        return "abstention"

# Initialize graph
workflow = StateGraph(GraphState)

# Add nodes
workflow.add_node("retrieval", retrieval_node)
workflow.add_node("extraction", extraction_node)
workflow.add_node("eval", eval_node)          # Phase 2-5 eval pipeline (BUG-8 fix)
workflow.add_node("math", math_node)
workflow.add_node("verification", verification_node)
workflow.add_node("output", output_node)
workflow.add_node("abstention", abstention_node)
workflow.add_node("lineage", lineage_node)

# Set entry point
workflow.set_entry_point("retrieval")

# Add deterministic edges
# Pipeline: Retrieval -> Extraction -> Eval (schema+confidence) -> Math -> Verification
workflow.add_edge("retrieval", "extraction")
workflow.add_edge("extraction", "eval")
workflow.add_edge("eval", "math")
workflow.add_edge("math", "verification")

# Add conditional edge from verification
workflow.add_conditional_edges(
    "verification",
    decide_next_step,
    {
        "output": "output",
        "abstention": "abstention"
    }
)

# Both terminal nodes funnel through lineage before END
workflow.add_edge("output", "lineage")
workflow.add_edge("abstention", "lineage")
workflow.add_edge("lineage", END)

_app = None

def get_app():
    global _app
    if _app is None:
        _app = workflow.compile()
    return _app

def run_auditable_rag(query: str, ticker: str) -> Dict[str, Any]:
    """
    Run the LangGraph DAG for a given query and ticker.
    """
    app = get_app()
    inputs = {
        "query": query,
        "ticker": ticker,
        "retrieved_docs":  [],
        "xbrl_facts":      [],
        "polygon_data":    [],
        "eval_route":      None,
        "eval_confidence": None,
        "eval_triggers":   None,
        "lineage":         None,
        "status": {
            "input":        "success",
            "retrieval":    "pending",
            "extraction":   "pending",
            "eval":         "pending",
            "math":         "pending",
            "verification": "pending",
            "output":       "pending",
        },
    }

    return app.invoke(inputs)
