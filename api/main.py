import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.responses import Response as StarletteResponse
from loguru import logger

from api.routes import chat
from api.routes.review import router as review_router
from api.routes.stats import router as stats_router
from api.routes.admin import router as admin_router
from api.routes.audit import router as audit_router
from api.routes.analytics import router as analytics_router
from api.routes.graph import router as graph_router
from api.config import config, Config
from api.middleware.rate_limit import rate_limit_middleware
from api.middleware.cors_config import configure_cors
from api.db.database import db_manager
from api.services.llm_health import get_llm_tracker
from api.services.drift_detection import check_drift


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.validate_startup()
    config.init_langsmith()
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
app.include_router(stats_router)
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
app.include_router(audit_router)
app.include_router(analytics_router)
app.include_router(graph_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "provider": Config.CHAT_PROVIDER}


@app.get("/api/health/full")
async def health_full():
    llm = get_llm_tracker().snapshot()

    db_ok = False
    db_error = None
    try:
        conn = db_manager.get_connection()
        conn.execute("SELECT 1")
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

frontend_path = os.path.join(os.getcwd(), "frontend", "dist")
if os.path.exists(frontend_path):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_path, "assets")), name="assets")

    async def _not_found(req: Request, exc: Exception):
        if not req.url.path.startswith("/api"):
            return FileResponse(os.path.join(frontend_path, "index.html"))
        return StarletteResponse(content='{"detail":"Not Found"}', status_code=404, media_type="application/json")

    app.add_exception_handler(404, _not_found)

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str, request: Request):
        file_path = os.path.join(frontend_path, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_path, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
