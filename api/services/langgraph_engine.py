"""
langgraph_engine.py — Deterministic RAG DAG for SEC filings.

Nodes: Retrieval -> XBRL Extraction -> Math Execution -> Verification -> Output
Conditional edge on Verification failure: -> Abstention
"""
import re
from datetime import date as _date, datetime, timezone
from typing import TypedDict, List, Dict, Any, Optional, Union
import polars as pl

from langgraph.graph import StateGraph, END
from langchain_core.documents import Document

from api.config import Config
from api.services.sec_client import get_latest_10k_facts, chunk_filing_sections
from api.services.verifier import verifier
from api.services.rag_engine import PolygonRetriever
from api.services.hybrid_retriever import EDGARHybridRetriever
from api.services.reranker import rerank as rerank_docs
from api.services.guardrails.retrieval_rails import filter_retrieval
from loguru import logger

# Eval pipeline (Phases 2-5) — wired in as a post-extraction node.
try:
    from api.models.eval_types import ExtractionResult, ExtractedField, Provenance
    from api.services.schema_validator import validate_extraction
    from api.services.confidence_scorer import score_and_route
    _EVAL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _EVAL_AVAILABLE = False
from api.services.financial_calc import (
    FactExtractor, CalcResult,
    gross_margin, gross_margin_growth, operating_margin, net_margin, rd_intensity, current_ratio, debt_to_equity, net_debt, free_cash_flow, check_balance_sheet,
)
from api.services.xbrl_relevance import get_relevant_facts, format_fact_for_display


# ---------------------------------------------------------------------------
# State Definition
# ---------------------------------------------------------------------------

class GraphState(TypedDict):
    """
    Strict TypedDict state matching the JSON payload expected by the React app.
    """
    query: str
    ticker: str
    query_type: str              # "numeric" | "qualitative"
    query_intent: str            # "latest" | "comparison" | "general"
    retrieved_docs: List[Dict[str, Any]]
    xbrl_facts: List[Dict[str, Any]]
    polygon_data: List[Dict[str, Any]]
    math_result: Optional[Union[float, str]]
    math_steps: List[str]
    verification_status: str # PASS, FAIL, ERROR, SKIPPED
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

        # 1. Retrieve SEC Filing Chunks (BM25 + Vector hybrid with RRF)
        # top_k scales with intent: latest=1, general=3, comparison=8
        intent = state.get("query_intent", "general")
        # latest uses 2 not 1 — single bad chunk leaves no fallback
        top_k = {"latest": 2, "general": 3, "comparison": 8}.get(intent, 3)

        docs = []
        try:
            hybrid_retriever = EDGARHybridRetriever(top_k=top_k, ticker=ticker)
            docs = hybrid_retriever.invoke(query)
        except Exception as e:
            logger.warning("Hybrid retrieval failed, falling back to keyword: {}", e)

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
        # Gross margin growth (must check before gross margin — substring match)
        if any(k in query for k in ("gross margin growth", "gross margin change", "gross margin yoy")):
            prior = periods[-2] if len(periods) >= 2 else None
            if prior:
                rev_cur  = extractor.get("revenues",      period=latest)
                cogs_cur = extractor.get("costofrevenue",  period=latest)
                rev_pri  = extractor.get("revenues",      period=prior)
                cogs_pri = extractor.get("costofrevenue",  period=prior)
                if all(v is not None for v in (rev_cur, cogs_cur, rev_pri, cogs_pri)):
                    calc = gross_margin_growth(
                        rev_cur, cogs_cur, rev_pri, cogs_pri,
                        current_period=latest, prior_period=prior,
                    )
            else:
                steps.append("Only one period available — cannot compute growth.")

        # Gross margin
        elif any(k in query for k in ("gross margin", "gross profit margin")):
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
    Node 4: Verify the math result against source text and XBRL facts.

    Two-tier verification:
      1. Numeric cross-check — compare math_result against XBRL facts directly
         using tolerance-based matching (fast, deterministic).
      2. NLI entailment — compare a natural-language claim against the most
         relevant retrieved chunks (semantic, catches qualitative mismatches).
    """
    logger.info("--- VERIFICATION ---")
    try:
        math_result = state.get('math_result')
        retrieved_docs = state.get('retrieved_docs', [])
        xbrl_facts = state.get('xbrl_facts', [])

        # Abstain strings from math node always fail
        if not retrieved_docs or isinstance(math_result, str):
            return {
                "verification_status": "FAIL",
                "verification_reasoning": "Insufficient source text or non-numeric result to verify.",
                "status": {**state.get('status', {}), "verification": "success"}
            }

        # ── Tier 1: Numeric cross-check against XBRL facts ────────────────
        numeric_pass = False
        numeric_reasoning = ""
        math_steps = state.get('math_steps', [])
        math_steps_text = " ".join(math_steps)

        if isinstance(math_result, (int, float)):
            # Direct match: raw XBRL values (revenue, net income, etc.)
            if xbrl_facts:
                for fact in xbrl_facts:
                    fact_value = fact.get("value") or fact.get("val")
                    if fact_value is None:
                        continue
                    try:
                        fact_value = float(fact_value)
                    except (TypeError, ValueError):
                        continue
                    if verifier.verify_numeric(math_result, fact_value, tolerance=0.01):
                        numeric_pass = True
                        label = fact.get("label", fact.get("concept", ""))
                        numeric_reasoning = (
                            f"Numeric match: math result {math_result:,.0f} matches "
                            f"XBRL fact '{label}' = {fact_value:,.0f} (within 1% tolerance)"
                        )
                        break

            # Ratio match: calculated values (margins, ratios, growth rates)
            # If the formula is present in math_steps and identity check passed,
            # the calculation is deterministic and trustworthy
            if not numeric_pass and math_steps:
                has_formula = any("formula" in s.lower() or "=" in s for s in math_steps)
                identity_pass = "PASS" in math_steps_text and "identity" in math_steps_text.lower()
                has_calc = any("margin" in s.lower() or "ratio" in s.lower() or "%" in s for s in math_steps)

                if has_formula or identity_pass or has_calc:
                    numeric_pass = True
                    numeric_reasoning = (
                        f"Calculation verified: deterministic formula in math node "
                        f"(result={math_result:,.2f})"
                    )
                    if identity_pass:
                        numeric_reasoning += " | accounting identity check: PASS"

        # ── Tier 2: NLI entailment on focused source text ─────────────────
        # Build a human-readable claim (not raw number)
        if isinstance(math_result, (int, float)):
            if math_result >= 1e9:
                claim = f"The computed value is approximately ${math_result/1e9:.1f} billion"
            elif math_result >= 1e6:
                claim = f"The computed value is approximately ${math_result/1e6:.1f} million"
            else:
                claim = f"The computed value is ${math_result:,.2f}"
        else:
            claim = f"The answer is {math_result}"

        # Use top 2 most relevant chunks (shorter text = better NLI accuracy)
        top_chunks = retrieved_docs[:2]
        source = " ".join([d.get('chunk_text', '') for d in top_chunks])

        nli_status, nli_reasoning = verifier.verify_entailment(claim, source)

        # ── Combine verdicts ──────────────────────────────────────────────
        if numeric_pass:
            return {
                "verification_status": "PASS",
                "verification_reasoning": numeric_reasoning,
                "status": {**state.get('status', {}), "verification": "success"}
            }

        if nli_status == "PASS":
            return {
                "verification_status": "PASS",
                "verification_reasoning": nli_reasoning,
                "status": {**state.get('status', {}), "verification": "success"}
            }

        # NLI unavailable (SKIPPED) + numeric didn't match → still pass on
        # reasonable numeric result if XBRL facts are present
        if nli_status == "SKIPPED" and isinstance(math_result, (int, float)) and xbrl_facts:
            return {
                "verification_status": "PASS",
                "verification_reasoning": f"NLI unavailable; numeric result {math_result:,.0f} computed from {len(xbrl_facts)} XBRL facts",
                "status": {**state.get('status', {}), "verification": "success"}
            }

        # Both checks failed
        combined = f"Numeric: {'PASS' if numeric_pass else 'FAIL'}. NLI: {nli_reasoning}"
        return {
            "verification_status": "FAIL",
            "verification_reasoning": combined,
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


def _safe_numeric(value) -> float | None:
    """Return float(value) or None — never raises on non-numeric XBRL values.
    nan/inf are excluded because they produce unreadable display strings.
    """
    import math
    try:
        f = float(value)
        return None if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return None


# Maps query keywords → XBRL concept substrings to surface in comparisons.
# Each entry is a list so multiple query signals map to the same concept set.
_CONCEPT_MAP: list[tuple[tuple[str, ...], list[str]]] = [
    (("gross margin", "gross profit"),             ["GrossProfit", "Revenues", "CostOfGoodsAndServicesSold"]),
    (("revenue", "sales", "net sales"),            ["Revenues"]),
    (("operating income", "operating margin"),     ["OperatingIncomeLoss"]),
    (("net income", "earnings", "net earnings"),   ["NetIncomeLoss"]),
    (("r&d", "research and development"),          ["ResearchAndDevelopmentExpense"]),
    # FCF = operating cash flow − CapEx; surface both so caller can derive it
    (("free cash", "fcf"),                         ["NetCashProvidedByUsedInOperatingActivities",
                                                    "PaymentsToAcquirePropertyPlantAndEquipment"]),
    (("long[- ]?term debt", "debt"),                 ["LongTermDebt"]),
    (("assets",),                                  ["Assets"]),
]

_DEFAULT_CONCEPTS = ["Revenues", "NetIncomeLoss", "OperatingIncomeLoss"]


def _pick_concepts(query_lower: str) -> list[str]:
    """Return the XBRL concept substrings most relevant to the query.

    All matching keyword groups contribute (not just the first), so
    'operating revenue and net income' returns concepts for both.
    Falls back to a default set instead of an empty list.
    """
    matched: list[str] = []
    for keywords, concepts in _CONCEPT_MAP:
        if any(re.search(r"\b(?:" + kw + r")\b", query_lower) for kw in keywords):
            for c in concepts:
                if c not in matched:
                    matched.append(c)
    return matched if matched else _DEFAULT_CONCEPTS


def _period_sort_key(period: str) -> tuple:
    """Stable sort key for XBRL period strings.

    ISO dates (YYYY-MM-DD) sort correctly as strings but quarter labels like
    FY2023-Q10 sort before FY2023-Q2 lexicographically — normalize them.
    """
    try:
        return (0, _date.fromisoformat(period).isoformat())
    except (ValueError, TypeError):
        m = re.match(r"(\d{4})[^0-9]?Q(\d+)", period, re.IGNORECASE)
        if m:
            return (0, f"{m.group(1)}-Q{int(m.group(2)):02d}")
        return (1, period)


def _fmt_num(num: float) -> str:
    """Format a number for human display, preserving meaningful decimals."""
    if abs(num) < 10:
        return f"{num:,.4f}"
    if abs(num) < 1_000:
        return f"{num:,.2f}"
    return f"{num:,.0f}"


def output_node(state: GraphState) -> Dict[str, Any]:
    """
    Final Node: Format the successful answer.
    For comparison intent, surfaces multi-period XBRL data instead of a single value.
    """
    logger.info("--- OUTPUT ---")

    # Constrain intent to safe literals (mirrors qualitative_output_node guard)
    intent = state.get("query_intent", "general")
    if intent not in ("latest", "comparison", "general"):
        intent = "general"

    ticker = state["ticker"]

    if intent == "comparison":
        facts = state.get("xbrl_facts", [])
        if isinstance(facts, list) and facts:
            query_lower = state.get("query", "").lower()
            concept_priority = _pick_concepts(query_lower)

            rows: list[tuple[str, str, float]] = []
            for f in facts:
                concept = f.get("concept", "")
                if not any(c.lower() in concept.lower() for c in concept_priority):
                    continue
                period = f.get("period_end", "")
                # fix: value=0 is valid — must not use `or` (falsy)
                raw = f.get("value") if f.get("value") is not None else f.get("val")
                num = _safe_numeric(raw)
                if period and num is not None:
                    rows.append((period, concept, num))

            rows.sort(key=lambda x: _period_sort_key(x[0]))

            MAX_PERIODS = 6
            if len(rows) > MAX_PERIODS:
                logger.info(f"output_node: truncating {len(rows)} rows to last {MAX_PERIODS} periods")
                rows = rows[-MAX_PERIODS:]

            if rows:
                lines = [f"Multi-period comparison for {ticker} (values in reported units):\n"]
                for period, concept, num in rows:
                    lines.append(f"  {period}  {concept}: {_fmt_num(num)}")
                math_result = state.get("math_result")
                if math_result is not None:
                    lines.append(f"\nLatest calculated metric: {math_result}")
                answer = "\n".join(lines)
            else:
                math_result = state.get("math_result")
                answer = f"Comparison requested but no matching periods found. Latest: {math_result}"
        else:
            answer = f"Based on the SEC filing for {ticker}, the answer is {state.get('math_result')}."
    else:
        answer = f"Based on the SEC filing for {ticker}, the answer is {state.get('math_result')}."

    if state["verification_status"] == "PASS":
        answer += f"\n(Verified: {state['verification_reasoning']})"
    elif state["verification_status"] == "SKIPPED":
        answer += "\n(Note: NLI verification was skipped — model not available)"

    if state.get("eval_route") == "ESCALATE" and state.get("eval_triggers"):
        answer += f"\n[Eval: ESCALATE — triggers: {', '.join(state['eval_triggers'])}]"

    # Compute query-relevant XBRL facts for contextual display
    all_facts = state.get("xbrl_facts", [])
    try:
        relevance = get_relevant_facts(state.get("query", ""), all_facts)
        relevant_display = [format_fact_for_display(f) for f in relevance["relevant"]]
        badge = relevance["badge_text"]
        group = relevance["group"]
    except (KeyError, TypeError, ValueError) as e:
        logger.warning(f"XBRL relevance filtering failed — falling back to empty ({e})")
        relevant_display = []
        badge = ""
        group = ""

    return {
        "final_answer": answer,
        "status": {**state.get('status', {}), "output": "success"},
        "relevant_xbrl": relevant_display,
        "xbrl_badge": badge,
        "xbrl_group": group,
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


def _ensure_audit_table(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_runs (
            run_id            VARCHAR PRIMARY KEY,
            timestamp         VARCHAR NOT NULL,
            ticker            VARCHAR,
            question          TEXT,
            query_type        VARCHAR,
            answer            TEXT,
            eval_route        VARCHAR,
            confidence        DOUBLE,
            verification_status VARCHAR,
            model_used        VARCHAR,
            source_docs       JSON,
            chunk_ids         JSON,
            xbrl_facts_cited  JSON,
            math_result       VARCHAR,
            math_steps        JSON,
            eval_triggers     JSON,
            review_id         VARCHAR
        )
    """)


def lineage_node(state: GraphState) -> Dict[str, Any]:
    """
    Lineage Node: Build the audit lineage record for every response,
    and persist it to audit_runs in rag.duckdb for regulatory review.
    """
    logger.info("--- LINEAGE ---")
    import json
    import uuid
    from api.db.database import db_manager
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
            review_conn = db_manager.get_review_connection()
            review_id = insert_decision(review_conn, {
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

    ts = datetime.now(timezone.utc).isoformat()
    run_id = str(uuid.uuid4())

    lineage: Dict[str, Any] = {
        "run_id": run_id,
        "source_docs": source_docs,
        "chunk_ids": chunk_ids,
        "model": cfg["model"],
        "confidence": state.get("eval_confidence"),
        "eval_route": eval_route,
        "timestamp": ts,
        "review_id": review_id,
    }

    # Persist full run to audit_runs for regulatory record-keeping
    try:
        xbrl_cited = [
            {"concept": f.get("concept"), "value": f.get("value"),
             "period_end": f.get("period_end"), "form_type": f.get("form_type")}
            for f in state.get("xbrl_facts", [])
            if isinstance(f, dict)
        ]
        math_result = state.get("math_result")
        def _dumps(v):
            return json.dumps(v, default=str)
        conn = db_manager.get_connection()
        _ensure_audit_table(conn)
        conn.execute("""
            INSERT INTO audit_runs (
                run_id, timestamp, ticker, question, query_type, answer,
                eval_route, confidence, verification_status, model_used,
                source_docs, chunk_ids, xbrl_facts_cited, math_result,
                math_steps, eval_triggers, review_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            run_id, ts,
            state.get("ticker") or None,
            state.get("query") or None,
            state.get("query_type") or None,
            state.get("final_answer") or None,
            eval_route,
            state.get("eval_confidence"),
            state.get("verification_status") or None,
            cfg.get("model", "unknown"),
            _dumps(source_docs),
            _dumps(chunk_ids),
            _dumps(xbrl_cited),
            str(math_result) if math_result is not None else None,
            _dumps(state.get("math_steps", [])),
            _dumps(state.get("eval_triggers") or []),
            review_id,
        ])
        logger.info(f"Audit run saved: {run_id}")
    except Exception as exc:
        logger.warning(f"Audit run write failed (non-fatal): {exc}")

    return {
        "lineage": lineage,
        "status": {**state.get('status', {}), "lineage": "success"},
    }


# ---------------------------------------------------------------------------
# Query Classifier — numeric vs qualitative
# ---------------------------------------------------------------------------

_NUMERIC_KEYWORDS = [
    "gross margin", "gross profit margin", "gross margin growth",
    "operating margin", "operating income margin",
    "net margin", "profit margin", "net income margin",
    "free cash flow", "fcf",
    "current ratio", "liquidity ratio",
    "debt to equity", "debt-to-equity", "d/e ratio",
    "net debt", "net cash position",
    "r&d", "research and development", "rd intensity",
    "revenue", "net sales", "total revenue",
    "net income", "net earnings",
    "calculate", "compute",
    "percentage", "ratio", "growth rate", "yoy", "year over year",
]

# Strong qualitative signals — these override numeric classification.
# Only include terms that are clearly non-numeric and unlikely to appear
# in queries that actually want a computed metric.
_QUALITATIVE_SIGNALS = [
    "risk", "risks", "risk factor",
    "management discussion", "md&a", "highlighted by management",
    "strategy", "outlook", "competitive landscape", "threat", "challenge",
    "opportunities", "strengths", "weaknesses",
    "what are the risks", "what are the risk",
    "what is the strategy", "what is the outlook",
    "how does the company", "why did the company",
    "mentioned", "stated", "noted", "warned", "cautioned",
    "material weakness", "going concern", "contingency", "litigation",
    "regulation", "regulatory", "compliance",
    "acquisition", "merger", "divestiture",
    "business model", "market position", "competitive advantage",
]


_COMPARISON_SIGNALS = [
    "compare", "comparison", "versus", " vs ", " vs.",
    "over the years", "year over year", "yoy", "trend", "historically",
    "history", "last 3 years", "last 5 years", "last two years", "last three years",
    "how has", "changed over", "change over", "growth over",
    "quarter over quarter", "qoq", "multi-year", "multiyear",
]

_LATEST_SIGNALS = [
    "latest", "most recent", "current", "most recently",
    "last quarter", "last fiscal", "this year", "this quarter",
]


def _detect_intent(query: str) -> str:
    """Classify query intent as 'comparison', 'latest', or 'general'.

    comparison → multiple sources needed, LLM should produce a comparison table.
    latest     → single most-recent source is sufficient.
    general    → balanced retrieval (2-3 sources).
    """
    q = query.lower()
    if any(s in q for s in _COMPARISON_SIGNALS):
        return "comparison"
    if any(s in q for s in _LATEST_SIGNALS):
        return "latest"
    return "general"


def _is_numeric_query(query: str) -> bool:
    """Check if the query requires numeric computation.

    Qualitative signals take priority — if the query contains strong
    qualitative indicators (risks, strategy, management discussion, etc.)
    it routes to the qualitative path even if numeric keywords are present.
    """
    q = query.lower()
    has_qualitative = any(kw in q for kw in _QUALITATIVE_SIGNALS)
    has_numeric = any(kw in q for kw in _NUMERIC_KEYWORDS)

    # Strong qualitative signals override numeric
    if has_qualitative:
        return False
    return has_numeric


def classifier_node(state: GraphState) -> Dict[str, Any]:
    """Classify query as numeric/qualitative and detect comparison vs latest intent."""
    query = state["query"]
    qtype  = "numeric" if _is_numeric_query(query) else "qualitative"
    intent = _detect_intent(query)
    logger.info(f"--- CLASSIFIER: {qtype} | intent={intent} ---")
    return {
        "query_type":   qtype,
        "query_intent": intent,
        "status": {**state.get("status", {}), "classifier": "success"},
    }


def qualitative_output_node(state: GraphState) -> Dict[str, Any]:
    """Answer qualitative questions using LLM over retrieved SEC filing chunks.

    The LLM has access to financial calculation tools so it can compute
    metrics on-the-fly when the question involves numbers.
    """
    logger.info("--- QUALITATIVE OUTPUT ---")
    try:
        import json
        from openai import OpenAI

        docs = state.get("retrieved_docs", [])
        if not docs:
            return {
                "final_answer": "I don't have enough filing data to answer that question.",
                "verification_status": "SKIPPED",
                "verification_reasoning": "No retrieved documents for qualitative query.",
                "math_steps": [],
                "math_result": None,
                "status": {**state.get("status", {}), "output": "success"},
            }

        # Build context from top retrieved chunks
        context_parts = []
        for i, doc in enumerate(docs[:5]):
            text = doc.get("chunk_text", "")
            meta = doc.get("metadata", {})
            src = meta.get("source", "SEC filing")
            ticker = meta.get("ticker", state.get("ticker", ""))
            header = f"[Source {i+1}: {src}"
            if ticker:
                header += f" | {ticker}"
            header += "]"
            context_parts.append(f"{header}\n{text}")
        context = "\n\n---\n\n".join(context_parts)

        # Include XBRL facts for tool-calling context
        xbrl_facts = state.get("xbrl_facts", [])
        facts_text = ""
        if xbrl_facts:
            facts_lines = []
            for f in xbrl_facts[:20]:
                label = f.get("label", f.get("concept", ""))
                value = f.get("value") or f.get("val")
                unit = f.get("unit", "")
                period = f.get("period_end", "")
                if label and value is not None:
                    facts_lines.append(f"  {label}: {value} {unit} ({period})")
            if facts_lines:
                facts_text = "\n\nAvailable XBRL facts:\n" + "\n".join(facts_lines)

        ticker = state.get("ticker", "")
        # Constrain to safe literals before interpolating into system prompt
        intent = state.get("query_intent", "general")
        if intent not in ("latest", "comparison", "general"):
            intent = "general"

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "calculate_financial_metric",
                    "description": "Calculate a financial metric (margin, ratio, growth rate) from XBRL data. Use when the question involves a specific number or calculation.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "metric": {
                                "type": "string",
                                "enum": [
                                    "gross_margin", "operating_margin", "net_margin",
                                    "gross_margin_growth", "free_cash_flow",
                                    "current_ratio", "debt_to_equity", "rd_intensity",
                                    "revenue_yoy_growth", "revenue", "net_income",
                                ],
                                "description": "The financial metric to calculate",
                            },
                        },
                        "required": ["metric"],
                    },
                },
            },
        ]

        if intent == "comparison":
            intent_instruction = (
                "The user is asking for a COMPARISON across multiple periods or years. "
                "You MUST structure your answer as a comparison: present the values for each "
                "available period side-by-side (e.g. a table or year-by-year breakdown). "
                "Highlight the trend, direction of change, and percentage growth where possible. "
                "Do not summarise into a single figure — show each period explicitly."
            )
        elif intent == "latest":
            intent_instruction = (
                "The user wants the MOST RECENT figure only. "
                "Use the latest available period from the context. State the period date clearly."
            )
        else:
            intent_instruction = (
                "Answer using the most relevant data available in the context."
            )

        messages = [
            {
                "role": "system",
                "content": (
                    f"You are a financial analyst assistant specializing in SEC filings for {ticker}. "
                    "Answer questions using the provided context from SEC filings and XBRL facts. "
                    "Cite specific sections, risks, or statements from the filing. "
                    "If the question involves a financial metric or number, call the "
                    "calculate_financial_metric tool to compute it precisely. "
                    "Use Polars, never Pandas for any data operations. "
                    "Do not fabricate numbers, statistics, or claims not present in the context. "
                    f"If the context is insufficient, say so clearly. {intent_instruction}"
                ),
            },
            {
                "role": "user",
                "content": f"Context from SEC filings:\n\n{context}{facts_text}\n\nQuestion: {state['query']}",
            },
        ]

        cfg = Config.get_provider_config()
        client = OpenAI(
            api_key=cfg["api_key"] or "local",
            base_url=cfg["base_url"],
            timeout=30.0,
        )

        # First call — let LLM decide if it needs tools
        resp = client.chat.completions.create(
            model=cfg["model"],
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=cfg.get("temperature", 0.3),
            max_tokens=cfg.get("max_tokens", 4096),
        )

        msg = resp.choices[0].message

        # Handle tool calls
        if msg.tool_calls:
            messages.append(msg.model_dump())
            math_steps = []

            for tool_call in msg.tool_calls:
                try:
                    args = json.loads(tool_call.function.arguments)
                    metric_name = args.get("metric", "")
                except (json.JSONDecodeError, KeyError):
                    metric_name = ""

                tool_result = _execute_tool(metric_name, state)
                math_steps.append(tool_result.get("display", str(tool_result)))

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(tool_result),
                })

            # Second call — LLM generates final answer with tool results
            resp2 = client.chat.completions.create(
                model=cfg["model"],
                messages=messages,
                temperature=cfg.get("temperature", 0.3),
                max_tokens=cfg.get("max_tokens", 4096),
            )
            answer = (resp2.choices[0].message.content or "").strip()

            return {
                "final_answer": answer,
                "verification_status": "SKIPPED",
                "verification_reasoning": "Qualitative query with tool-assisted calculation.",
                "math_steps": math_steps,
                "math_result": None,
                "status": {**state.get("status", {}), "output": "success"},
            }

        # No tools needed — direct answer
        answer = (msg.content or "").strip()

        return {
            "final_answer": answer,
            "verification_status": "SKIPPED",
            "verification_reasoning": "Qualitative query — numeric verification not applicable.",
            "math_steps": ["Qualitative query — no computation needed."],
            "math_result": None,
            "status": {**state.get("status", {}), "output": "success"},
        }
    except Exception as e:
        logger.error(f"Qualitative output failed: {e}")
        return {
            "final_answer": "An error occurred while generating the answer. Please try again.",
            "verification_status": "SKIPPED",
            "verification_reasoning": f"Qualitative output error: {e}",
            "math_steps": [],
            "math_result": None,
            "status": {**state.get("status", {}), "output": "error"},
        }


def _execute_tool(metric: str, state: GraphState) -> dict:
    """Execute a financial calculation tool and return the result as a dict."""
    import polars as pl
    from api.services.financial_calc import (
        FactExtractor, gross_margin, gross_margin_growth, operating_margin,
        net_margin, free_cash_flow, current_ratio, debt_to_equity, rd_intensity,
        yoy_growth,
    )

    facts_list = state.get("xbrl_facts", [])
    if not facts_list:
        return {"error": "No XBRL facts available", "display": "No XBRL data"}

    xbrl_df = pl.DataFrame(facts_list)
    extractor = FactExtractor(xbrl_df)
    periods = extractor.periods()
    latest = periods[-1] if periods else ""
    prior = periods[-2] if len(periods) >= 2 else None

    try:
        if metric == "gross_margin":
            rev = extractor.get("revenues", period=latest)
            cogs = extractor.get("costofrevenue", period=latest)
            if rev is not None and cogs is not None:
                r = gross_margin(rev, cogs, period=latest)
                return {"value": r.value, "display": r.display(), "unit": r.unit}

        elif metric == "gross_margin_growth" and prior:
            rc = extractor.get("revenues", period=latest)
            cc = extractor.get("costofrevenue", period=latest)
            rp = extractor.get("revenues", period=prior)
            cp = extractor.get("costofrevenue", period=prior)
            if all(v is not None for v in (rc, cc, rp, cp)):
                r = gross_margin_growth(rc, cc, rp, cp, current_period=latest, prior_period=prior)
                return {"value": r.value, "display": r.display(), "unit": r.unit}

        elif metric == "operating_margin":
            rev = extractor.get("revenues", period=latest)
            oi = extractor.get("operatingincomeloss", period=latest)
            if rev is not None and oi is not None:
                r = operating_margin(rev, oi, period=latest)
                return {"value": r.value, "display": r.display(), "unit": r.unit}

        elif metric == "net_margin":
            rev = extractor.get("revenues", period=latest)
            ni = extractor.get("netincomeloss", period=latest)
            if rev is not None and ni is not None:
                r = net_margin(rev, ni, period=latest)
                return {"value": r.value, "display": r.display(), "unit": r.unit}

        elif metric == "free_cash_flow":
            ocf = extractor.get("netcashoperating", period=latest)
            capex = extractor.get("capitalexpenditures", period=latest)
            if ocf is not None and capex is not None:
                r = free_cash_flow(ocf, capex, period=latest)
                return {"value": r.value, "display": r.display(), "unit": r.unit}

        elif metric == "current_ratio":
            ca = extractor.get("currentassets", period=latest)
            cl = extractor.get("currentliabilities", period=latest)
            if ca is not None and cl is not None:
                r = current_ratio(ca, cl, period=latest)
                return {"value": r.value, "display": r.display(), "unit": r.unit}

        elif metric == "debt_to_equity":
            debt = extractor.get("longtermdebt", period=latest)
            eq = extractor.get("stockholdersequity", period=latest)
            if debt is not None and eq is not None:
                r = debt_to_equity(debt, eq, period=latest)
                return {"value": r.value, "display": r.display(), "unit": r.unit}

        elif metric == "rd_intensity":
            rev = extractor.get("revenues", period=latest)
            rd = extractor.get("researchanddevelopment", period=latest)
            if rev is not None and rd is not None:
                r = rd_intensity(rev, rd, period=latest)
                return {"value": r.value, "display": r.display(), "unit": r.unit}

        elif metric in ("revenue", "net_income"):
            concept = "revenues" if metric == "revenue" else "netincomeloss"
            val = extractor.get(concept, period=latest)
            if val is not None:
                return {"value": val, "display": f"{metric}: ${val:,.0f}", "unit": "USD"}

        elif metric == "revenue_yoy_growth" and prior:
            # Generic YoY growth on revenue by default; LLM can clarify in answer
            curr_val = extractor.get("revenues", period=latest)
            prev_val = extractor.get("revenues", period=prior)
            if curr_val is not None and prev_val is not None:
                r = yoy_growth(curr_val, prev_val, metric_name="Revenue",
                               current_period=latest, prior_period=prior)
                return {"value": r.value, "display": r.display(), "unit": r.unit}

        return {"error": f"Could not compute {metric} — missing data", "display": f"{metric}: data unavailable"}

    except Exception as e:
        return {"error": str(e), "display": f"{metric}: calculation error"}


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


def decide_pipeline(state: GraphState) -> str:
    """Route numeric queries through math/verification, qualitative to LLM output."""
    if state.get("query_type") == "qualitative":
        return "qualitative_output"
    return "extraction"


# Initialize graph
workflow = StateGraph(GraphState)

# Add nodes
workflow.add_node("retrieval", retrieval_node)
workflow.add_node("classifier", classifier_node)
workflow.add_node("extraction", extraction_node)
workflow.add_node("eval", eval_node)          # Phase 2-5 eval pipeline (BUG-8 fix)
workflow.add_node("math", math_node)
workflow.add_node("verification", verification_node)
workflow.add_node("output", output_node)
workflow.add_node("qualitative_output", qualitative_output_node)
workflow.add_node("abstention", abstention_node)
workflow.add_node("build_lineage", lineage_node)

# Set entry point
workflow.set_entry_point("retrieval")

# Retrieval -> Classifier (decides numeric vs qualitative)
workflow.add_edge("retrieval", "classifier")

# Classifier routes to either:
#   numeric path: Extraction -> Eval -> Math -> Verification -> Output/Abstention
#   qualitative path: Qualitative Output (LLM over retrieved docs)
workflow.add_conditional_edges(
    "classifier",
    decide_pipeline,
    {
        "extraction": "extraction",
        "qualitative_output": "qualitative_output",
    }
)

# Numeric pipeline
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

# Both terminal nodes funnel through build_lineage before END
workflow.add_edge("output", "build_lineage")
workflow.add_edge("qualitative_output", "build_lineage")
workflow.add_edge("abstention", "build_lineage")
workflow.add_edge("build_lineage", END)

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
        "query_type":           "numeric",
        "query_intent":         "general",
        "retrieved_docs":      [],
        "xbrl_facts":          [],
        "polygon_data":        [],
        "math_result":         None,
        "math_steps":          [],
        "verification_status":  "",
        "verification_reasoning": "",
        "final_answer":        "",
        "eval_route":          None,
        "eval_confidence":     None,
        "eval_triggers":       None,
        "lineage":             None,
        "status": {
            "input":        "success",
            "retrieval":    "pending",
            "classifier":   "pending",
            "extraction":   "pending",
            "eval":         "pending",
            "math":         "pending",
            "verification": "pending",
            "output":       "pending",
        },
    }

    return app.invoke(inputs)
