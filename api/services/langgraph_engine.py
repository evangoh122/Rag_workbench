"""
langgraph_engine.py — Deterministic RAG DAG for SEC filings.

Nodes: Retrieval -> XBRL Extraction -> Math Execution -> Verification -> Output
Conditional edge on Verification failure: -> Abstention
"""
import os
from typing import TypedDict, List, Dict, Any, Optional, Union
import polars as pl

from langgraph.graph import StateGraph, END
from api.services.sec_client import get_latest_10k_facts, chunk_filing_sections
from api.services.verifier import verify_numeric, verify_entailment
from loguru import logger
from api.services.financial_calc import (
    FactExtractor, CalcResult,
    gross_margin, operating_margin, net_margin, ebitda, ebitda_margin,
    rd_intensity, sga_intensity, yoy_growth, cagr,
    current_ratio, quick_ratio, debt_to_equity, net_debt, working_capital,
    free_cash_flow, fcf_margin, fcf_conversion, capex_intensity,
    check_balance_sheet, check_gross_profit, check_fcf_identity,
    normalize_to_usd,
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
    math_result: Optional[Union[float, str]]
    math_steps: List[str]
    verification_status: str # PASS, FAIL, ERROR
    verification_reasoning: str
    final_answer: str
    status: Dict[str, str] # {node_name: 'success' | 'error' | 'pending'}

# ---------------------------------------------------------------------------
# Node Functions
# ---------------------------------------------------------------------------

def retrieval_node(state: GraphState) -> Dict[str, Any]:
    """
    Node 1: Retrieve relevant text chunks from the SEC filing.
    """
    logger.info(f"--- RETRIEVAL: {state['ticker']} ---")
    try:
        # Mocking for now, in a real app this would query the vector store
        # or use chunk_filing_sections
        chunks = chunk_filing_sections(state['ticker'])
        # Simple keyword search as a placeholder for actual vector retrieval
        keywords = state['query'].lower().split()
        retrieved = [
            c for c in chunks 
            if any(k in c['chunk_text'].lower() for k in keywords)
        ][:5]
        
        return {
            "retrieved_docs": retrieved,
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
        
        status, reasoning = verify_entailment(claim, source)
        
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

def output_node(state: GraphState) -> Dict[str, Any]:
    """
    Final Node: Format the successful answer.
    """
    logger.info("--- OUTPUT ---")
    answer = f"Based on the SEC filing for {state['ticker']}, the answer is {state['math_result']}."
    if state['verification_status'] == "PASS":
        answer += f" (Verified: {state['verification_reasoning']})"
    
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

# ---------------------------------------------------------------------------
# Graph Definition
# ---------------------------------------------------------------------------

def decide_next_step(state: GraphState) -> str:
    """
    Deterministic routing based on verification result.
    """
    if state['verification_status'] == "PASS":
        return "output"
    else:
        return "abstention"

# Initialize graph
workflow = StateGraph(GraphState)

# Add nodes
workflow.add_node("retrieval", retrieval_node)
workflow.add_node("extraction", extraction_node)
workflow.add_node("math", math_node)
workflow.add_node("verification", verification_node)
workflow.add_node("output", output_node)
workflow.add_node("abstention", abstention_node)

# Set entry point
workflow.set_entry_point("retrieval")

# Add deterministic edges
workflow.add_edge("retrieval", "extraction")
workflow.add_edge("extraction", "math")
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

# End edges
workflow.add_edge("output", END)
workflow.add_edge("abstention", END)

# Compile
app = workflow.compile()

def run_auditable_rag(query: str, ticker: str) -> Dict[str, Any]:
    """
    Run the LangGraph DAG for a given query and ticker.
    """
    inputs = {
        "query": query,
        "ticker": ticker,
        "status": {
            "input": "success",
            "retrieval": "pending",
            "extraction": "pending",
            "math": "pending",
            "verification": "pending",
            "output": "pending"
        }
    }
    return app.invoke(inputs)
