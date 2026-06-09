from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional, Dict
from api.services.chat_engine import chat_sql
from api.services.rag_engine import ask_rag
from api.services.langgraph_engine import run_auditable_rag
from api.services.graph_rag_engine import run_graph_rag
from api.middleware.auth import get_api_key
from api.models.schemas import ChatRequest
from api.services.guardrails.input_rails import check_input
from api.services.guardrails.dialog_rails import check_dialog
from api.services.guardrails.output_rails import check_output
from api.services.llm_health import get_llm_tracker

router = APIRouter(prefix="/api/chat", tags=["chat"])

_tracker = get_llm_tracker()


def _apply_input_rails(message: str) -> None:
    """Apply input + dialog rails. Raises 400 if blocked."""
    input_verdict = check_input(message)
    if input_verdict.blocked:
        raise HTTPException(status_code=400, detail=input_verdict.reason)
    dialog_verdict = check_dialog(message)
    if dialog_verdict.off_topic:
        raise HTTPException(status_code=400, detail=dialog_verdict.refusal_message)


def _apply_output_rails(answer: str, context: str = "") -> str:
    """Apply output rails. Returns masked answer if PII detected."""
    verdict = check_output(answer, context)
    if verdict.masked_answer:
        return verdict.masked_answer
    return answer


@router.post("/sql")
async def chat_sql_endpoint(req: ChatRequest, _=Depends(get_api_key)):
    _apply_input_rails(req.message)
    try:
        result = chat_sql(req.message, req.history)
        if "answer" in result:
            result["answer"] = _apply_output_rails(result["answer"])
        _tracker.record_success()
        return result
    except HTTPException:
        raise
    except Exception as e:
        _tracker.record_failure(str(e), context="chat/sql")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/rag")
async def chat_rag_endpoint(req: ChatRequest, _=Depends(get_api_key)):
    _apply_input_rails(req.message)
    try:
        answer = ask_rag(req.message)
        answer = _apply_output_rails(answer)
        _tracker.record_success()
        return {"type": "text", "answer": answer}
    except HTTPException:
        raise
    except Exception as e:
        _tracker.record_failure(str(e), context="chat/rag")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/graph-rag")
async def chat_graph_rag_endpoint(req: ChatRequest, _=Depends(get_api_key)):
    _apply_input_rails(req.message)
    try:
        if not req.ticker:
            raise HTTPException(status_code=400, detail="Ticker is required for Graph RAG")
        result = run_graph_rag(req.message, req.ticker)
        answer = _apply_output_rails(result["final_answer"])
        _tracker.record_success()
        return {
            "type": "text",
            "answer": answer,
            "entities": result["search_entities"],
            "triples": result["extracted_triples"]
        }
    except HTTPException:
        raise
    except Exception as e:
        _tracker.record_failure(str(e), context="chat/graph-rag")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/auditable-rag")
async def chat_auditable_rag_endpoint(req: ChatRequest, _=Depends(get_api_key)):
    _apply_input_rails(req.message)
    try:
        result = run_auditable_rag(req.message, req.ticker)
        answer = _apply_output_rails(result["final_answer"])
        _tracker.record_success()
        return {
            "type": "text",
            "answer": answer,
            "sources": [{"content": d["chunk_text"], "metadata": d["metadata"]} for d in result["retrieved_docs"]],
            "xbrl_facts": result["xbrl_facts"],
            "verification": {
                "status": result["verification_status"],
                "reasoning": result["verification_reasoning"]
            },
            "math_steps": result["math_steps"],
            "pipeline_status": result["status"]
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        _tracker.record_failure(str(e), context="chat/auditable-rag")
        raise HTTPException(status_code=500, detail="Internal server error")
