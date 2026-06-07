from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
from api.services.chat_engine import chat_sql
from api.services.rag_engine import ask_rag

router = APIRouter(prefix="/api/chat", tags=["chat"])

class ChatRequest(BaseModel):
    message: str
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
