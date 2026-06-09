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


@app.get("/api/health/full")
async def health_full():
    from api.services.llm_health import get_llm_tracker
    from api.services.drift_detection import check_drift
    from api.db.database import db_manager

    llm = get_llm_tracker().snapshot()

    db_ok = False
    db_error = None
    try:
        conn = db_manager.get_connection()
        conn.execute("SELECT 1")
        conn.close()
        db_ok = True
    except Exception as e:
        db_error = str(e)

    drift = None
    try:
        conn = db_manager.get_review_connection()
        drift_status = check_drift(
            conn,
            agreement_floor=Config.DRIFT_AGREEMENT_FLOOR,
            concept_spike_threshold=Config.DRIFT_CONCEPT_SPIKE_THRESHOLD,
        )
        drift = {
            "agreement_rate": drift_status.agreement_rate,
            "agreement_floor": drift_status.agreement_floor,
            "agreement_alert": drift_status.agreement_alert,
            "unrecognized_concept_count": drift_status.unrecognized_concept_count,
            "concept_spike_threshold": drift_status.concept_spike_threshold,
            "concept_alert": drift_status.concept_alert,
            "window_size": drift_status.window_size,
        }
        conn.close()
    except Exception as e:
        drift = {"error": str(e)}

    return {
        "status": "healthy" if db_ok else "degraded",
        "provider": Config.CHAT_PROVIDER,
        "database": {
            "connected": db_ok,
            "error": db_error,
        },
        "drift": drift,
        "llm": {
            "total_calls": llm["total_calls"],
            "success_rate": round(llm["success_rate"], 4),
            "failed_calls": llm["failed_calls"],
            "last_error": llm["last_error"],
            "last_error_time": llm["last_error_time"],
            "recent_errors": llm["recent_errors"],
        },
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
