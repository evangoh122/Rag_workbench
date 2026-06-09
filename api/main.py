import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from loguru import logger

from api.routes import chat
from api.routes.review import router as review_router
from api.config import Config
from api.middleware.rate_limit import rate_limit_middleware
from api.middleware.cors_config import configure_cors
from api.db.database import db_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("RAG Workbench starting up (provider={})", Config.CHAT_PROVIDER)
    if Config.LANGSMITH_TRACING and Config.LANGSMITH_API_KEY:
        logger.info("LangSmith tracing: enabled (project={})", Config.LANGSMITH_PROJECT)
    yield
    logger.info("RAG Workbench shutting down — closing database connections")
    db_manager.close()


app = FastAPI(title="RAG Workbench API", lifespan=lifespan)

app.middleware("http")(rate_limit_middleware)
configure_cors(app)

app.include_router(chat.router)

app.include_router(review_router)

frontend_path = os.path.join(os.getcwd(), "frontend", "dist")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

    @app.exception_handler(404)
    async def not_found_handler(request, exc):
        if not request.url.path.startswith("/api"):
            return FileResponse(os.path.join(frontend_path, "index.html"))
        raise exc

@app.get("/api/health")
async def health():
    return {"status": "ok", "provider": Config.CHAT_PROVIDER}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
