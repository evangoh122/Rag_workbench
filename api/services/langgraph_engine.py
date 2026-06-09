"""
langgraph_engine.py — Deterministic RAG DAG for SEC filings.

Nodes: Retrieval -> XBRL Extraction -> Math Execution -> Verification -> Output
Conditional edge on Verification failure: -> Abstention
"""
import os
import logging
from typing import TypedDict, List, Dict, Any, Optional, Union
import polars as pl

from langgraph.graph import StateGraph, END
from api.services.sec_client import get_latest_10k_facts, chunk_filing_sections
from api.services.verifier import verify_numeric, verify_entailment

logger = logging.getLogger(__name__)

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
    Node 3: Execute math or reasoning based on extracted facts.
    """
    logger.info("--- MATH EXECUTION ---")
    # For this scaffold, we'll implement a simple keyword-based extractor
    # that looks for specific values in the XBRL facts.
    try:
        facts = state['xbrl_facts']
        query = state['query'].lower()
        
        result = None
        steps = []
        
        # Trivial logic: find the first fact that matches a concept in the query
        for fact in facts:
            concept = fact.get('concept', '').lower()
            if concept in query or query in concept:
                result = fact.get('value')
                steps.append(f"Found value for {concept}: {result}")
                break
        
        if result is None:
            result = "Data not found in XBRL financials."
            steps.append("Failed to find matching XBRL concept.")

        return {
            "math_result": result,
            "math_steps": steps,
            "status": {**state.get('status', {}), "math": "success"}
        }
    except Exception as e:
        logger.error(f"Math node failed: {e}")
        return {"status": {**state.get('status', {}), "math": "error"}}

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
