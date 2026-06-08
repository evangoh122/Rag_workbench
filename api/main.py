import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from api.routes import chat, metrics
from api.config import Config
from api.middleware.rate_limit import rate_limit_middleware
from api.db.database import db_manager

@asynccontextmanager
async def lifespan(app):
    # Startup
    if Config.CHAT_PROVIDER == "anthropic":
        logger.warning(
            "CHAT_PROVIDER=anthropic: SQL chat mode is unsupported. "
            "RAG mode will work. Switch to deepseek, openai, or ollama for SQL mode."
        )
    yield
    # Shutdown
    db_manager.close()

app = FastAPI(title="RAG Workbench API", lifespan=lifespan)

# Ownership: Gemini (Security)
app.middleware("http")(rate_limit_middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8501").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ownership: Claude (Architecture)
app.include_router(chat.router)
app.include_router(metrics.router)

@app.get("/api/health")
async def health():
    return {"status": "ok", "provider": Config.CHAT_PROVIDER}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
