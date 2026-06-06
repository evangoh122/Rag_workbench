from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from .chat_engine import chat_sql
from .rag_engine import ask_rag
from .config import Config

app = FastAPI(title="RAG Workbench API")

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this to the frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
