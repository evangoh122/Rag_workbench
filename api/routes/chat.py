from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
from api.services.chat_engine import chat_sql
from api.services.rag_engine import ask_rag
from api.services.langgraph_engine import run_auditable_rag

router = APIRouter(prefix="/api/chat", tags=["chat"])

class ChatRequest(BaseModel):
    message: str
    ticker: Optional[str] = "AAPL"
    history: Optional[List[Dict[str, str]]] = None

@router.post("/sql")
async def chat_sql_endpoint(req: ChatRequest):
    try:
        result = chat_sql(req.message, req.history)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/rag")
async def chat_rag_endpoint(req: ChatRequest):
    try:
        answer = ask_rag(req.message)
        return {"type": "text", "answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/auditable-rag")
async def chat_auditable_rag_endpoint(req: ChatRequest):
    try:
        result = run_auditable_rag(req.message, req.ticker)
        # Map LangGraph state to the frontend response schema
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
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
