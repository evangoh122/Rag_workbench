import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from loguru import logger

from api.routes import chat
from api.routes.review import router as review_router
from api.config import Config
from api.middleware.rate_limit import rate_limit_middleware

app = FastAPI(title="RAG Workbench API")

# Ownership: Gemini (Security)
app.middleware("http")(rate_limit_middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ownership: Claude (Architecture)
app.include_router(chat.router)

# Ownership: DeepSeek (API Engineering) — Phase 8
app.include_router(review_router)

# Mount static files for production (Phase 7/8)
frontend_path = os.path.join(os.getcwd(), "frontend", "dist")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

    @app.exception_handler(404)
    async def not_found_handler(request, exc):
        if not request.url.path.startswith("/api"):
            return FileResponse(os.path.join(frontend_path, "index.html"))
        raise exc

@app.on_event("startup")
async def validate_config():
    if Config.CHAT_PROVIDER == "anthropic":
        logger.warning(
            "CHAT_PROVIDER=anthropic: SQL chat mode is unsupported. "
            "RAG mode will work. Switch to deepseek, openai, or ollama for SQL mode."
        )
    if Config.LANGSMITH_TRACING and Config.LANGSMITH_API_KEY:
        logger.info("LangSmith tracing: enabled (project=%s)", Config.LANGSMITH_PROJECT)
    else:
        logger.info("LangSmith tracing: disabled")

@app.get("/api/health")
async def health():
    return {"status": "ok", "provider": Config.CHAT_PROVIDER}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
