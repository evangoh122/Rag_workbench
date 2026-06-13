from fastapi import APIRouter
from api.config import Config
from api.db.database import db_manager
from api.services.llm_health import get_llm_tracker

router = APIRouter(prefix="/api")


def _count(conn, sql: str) -> int | None:
    try:
        row = conn.execute(sql).fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return None


@router.get("/stats")
async def get_stats():
    llm = get_llm_tracker().snapshot()

    data: dict = {}
    db_main_ok = False
    try:
        conn = db_manager.get_connection()
        db_main_ok = True
        data["filing_chunks"]         = _count(conn, "SELECT COUNT(*) FROM edgar_embeddings")
        data["companies_with_chunks"] = _count(conn, "SELECT COUNT(DISTINCT ticker) FROM edgar_embeddings")
        data["xbrl_facts"]            = _count(conn, "SELECT COUNT(*) FROM xbrl_facts")
        data["companies_with_xbrl"]   = _count(conn, "SELECT COUNT(DISTINCT ticker) FROM xbrl_facts")
        data["graph_triples"]         = _count(conn, "SELECT COUNT(*) FROM graph_triples")
        data["ticker_embeddings"]     = _count(conn, "SELECT COUNT(*) FROM ticker_embeddings")
        # Aggregate stored dimensions so CI can reject partially re-embedded
        # corpora containing a mix of vectors from old and new models.
        try:
            row = conn.execute(
                """SELECT MIN(len(embedding)), MAX(len(embedding)),
                          COUNT(DISTINCT len(embedding))
                   FROM edgar_embeddings
                   WHERE embedding IS NOT NULL"""
            ).fetchone()
            data["embedding_dim_min"] = int(row[0]) if row and row[0] is not None else None
            data["embedding_dim_max"] = int(row[1]) if row and row[1] is not None else None
            data["embedding_dim_variants"] = int(row[2]) if row and row[2] is not None else 0
        except Exception:
            data["embedding_dim_min"] = None
            data["embedding_dim_max"] = None
            data["embedding_dim_variants"] = 0
        # ticker coverage list
        try:
            rows = conn.execute(
                "SELECT DISTINCT ticker FROM edgar_embeddings ORDER BY ticker"
            ).fetchall()
            data["tickers_embedded"] = [r[0] for r in rows]
        except Exception:
            data["tickers_embedded"] = []
    except Exception as exc:
        data["error"] = str(exc)

    review: dict = {}
    db_review_ok = False
    try:
        rconn = db_manager.get_review_connection()
        db_review_ok = True
        review["total_decisions"] = _count(rconn, "SELECT COUNT(*) FROM review_decisions")
        review["total_verdicts"]  = _count(rconn, "SELECT COUNT(*) FROM reviewer_verdicts")
        review["pending"]         = _count(rconn, "SELECT COUNT(*) FROM review_decisions WHERE status='pending'")
        review["escalated"]       = _count(rconn, "SELECT COUNT(*) FROM review_decisions WHERE route='ESCALATE'")
    except Exception as exc:
        review["error"] = str(exc)

    return {
        "data": data,
        "review": review,
        "llm": {
            "total_calls":    llm["total_calls"],
            "failed_calls":   llm["failed_calls"],
            "success_rate":   round(llm["success_rate"], 4),
            "last_error":     llm.get("last_error"),
            "last_error_time": llm.get("last_error_time"),
            "recent_errors":  llm.get("recent_errors", [])[-5:],
        },
        "config": {
            "provider":          Config.CHAT_PROVIDER,
            "embedding_provider": Config.EMBEDDING_PROVIDER,
            "embedding_model":   Config.ACTIVE_EMBEDDING_MODEL,
            "embedding_dim":     Config.EMBEDDING_DIM,
        },
        "database": {
            "main_connected":   db_main_ok,
            "review_connected": db_review_ok,
        },
    }
