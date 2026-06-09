from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional, Dict
from api.services.chat_engine import chat_sql
from api.services.rag_engine import ask_rag
from api.services.langgraph_engine import run_auditable_rag
from api.services.graph_rag_engine import run_graph_rag
from api.middleware.auth import get_api_key
from api.models.schemas import ChatRequest

router = APIRouter(prefix="/api/chat", tags=["chat"])

@router.post("/sql")
async def chat_sql_endpoint(req: ChatRequest, _=Depends(get_api_key)):
    try:
        result = chat_sql(req.message, req.history)
        return result
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/rag")
async def chat_rag_endpoint(req: ChatRequest, _=Depends(get_api_key)):
    try:
        answer = ask_rag(req.message)
        return {"type": "text", "answer": answer}
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/graph-rag")
async def chat_graph_rag_endpoint(req: ChatRequest, _=Depends(get_api_key)):
    try:
        if not req.ticker:
            raise HTTPException(status_code=400, detail="Ticker is required for Graph RAG")
        result = run_graph_rag(req.message, req.ticker)
        return {
            "type": "text",
            "answer": result["final_answer"],
            "entities": result["search_entities"],
            "triples": result["extracted_triples"]
        }
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/auditable-rag")
async def chat_auditable_rag_endpoint(req: ChatRequest, _=Depends(get_api_key)):
    try:
        result = run_auditable_rag(req.message, req.ticker)
        return {
            "type": "text",
            "answer": result["final_answer"],
            "sources": [{"content": d["chunk_text"], "metadata": d["metadata"]} for d in result["retrieved_docs"]],
            "xbrl_facts": result["xbrl_facts"],
            "verification": {
                "status": result["verification_status"],
                "reasoning": result["verification_reasoning"]
            },
            "math_steps": result["math_steps"],
            "pipeline_status": result["status"]
        }
    except Exception:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")
