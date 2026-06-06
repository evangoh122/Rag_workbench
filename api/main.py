import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from loguru import logger

from .chat_engine import chat_sql
from .rag_engine import ask_rag
from .config import Config

app = FastAPI(title="RAG Workbench API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def validate_config():
    if Config.CHAT_PROVIDER == "anthropic":
        logger.error(
            "CHAT_PROVIDER=anthropic: SQL chat mode is unsupported. "
            "RAG mode will work. Switch to deepseek, openai, or ollama for SQL mode."
        )

class ChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, str]]] = None

@app.get("/api/health")
async def health():
    return {"status": "ok", "provider": Config.CHAT_PROVIDER}

@app.post("/api/chat/sql")
async def chat_sql_endpoint(req: ChatRequest):
    try:
        result = chat_sql(req.message, req.history)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat/rag")
async def chat_rag_endpoint(req: ChatRequest):
    try:
        answer = ask_rag(req.message)
        return {"type": "text", "answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
