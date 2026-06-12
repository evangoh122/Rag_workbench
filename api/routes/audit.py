"""Audit log endpoints — regulatory read access to pipeline run history."""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pydantic import BaseModel

from api.db.database import db_manager

router = APIRouter(prefix="/api/audit", tags=["audit"])

_VALID_TICKER = re.compile(r"^[A-Z0-9]{1,10}$")
_VALID_ROUTES = {"AUTO", "SAMPLED_REVIEW", "ESCALATE"}


class AuditRunOut(BaseModel):
    run_id: str
    timestamp: str
    ticker: Optional[str] = None
    question: Optional[str] = None
    query_type: Optional[str] = None
    answer: Optional[str] = None
    eval_route: Optional[str] = None
    confidence: Optional[float] = None
    verification_status: Optional[str] = None
    model_used: Optional[str] = None
    source_docs: list[str] = []
    chunk_ids: list[str] = []
    xbrl_facts_cited: list[dict] = []
    math_result: Optional[str] = None
    math_steps: list[str] = []
    eval_triggers: list[str] = []
    review_id: Optional[str] = None


def _parse_json_col(val: Any, default):
    if val is None:
        return default
    if isinstance(val, (list, dict)):
        return val
    try:
        return json.loads(val)
    except Exception:
        return default


def _row_to_run(row) -> AuditRunOut:
    return AuditRunOut(
        run_id=row[0],
        timestamp=row[1],
        ticker=row[2],
        question=row[3],
        query_type=row[4],
        answer=row[5],
        eval_route=row[6],
        confidence=row[7],
        verification_status=row[8],
        model_used=row[9],
        source_docs=_parse_json_col(row[10], []),
        chunk_ids=_parse_json_col(row[11], []),
        xbrl_facts_cited=_parse_json_col(row[12], []),
        math_result=row[13],
        math_steps=_parse_json_col(row[14], []),
        eval_triggers=_parse_json_col(row[15], []),
        review_id=row[16],
    )


def _ensure_audit_table(conn) -> None:
    """Idempotent — safe to call on every read; only creates the table if missing."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_runs (
            run_id              VARCHAR PRIMARY KEY,
            timestamp           VARCHAR NOT NULL,
            ticker              VARCHAR,
            question            TEXT,
            query_type          VARCHAR,
            answer              TEXT,
            eval_route          VARCHAR,
            confidence          DOUBLE,
            verification_status VARCHAR,
            model_used          VARCHAR,
            source_docs         JSON,
            chunk_ids           JSON,
            xbrl_facts_cited    JSON,
            math_result         VARCHAR,
            math_steps          JSON,
            eval_triggers       JSON,
            review_id           VARCHAR
        )
    """)


# NOTE: /summary/stats MUST be declared before /{run_id} so FastAPI's static
# path takes precedence over the parameterised one.
@router.get("/summary/stats")
def audit_summary():
    """Aggregate stats over all runs — useful for a regulator dashboard."""
    try:
        conn = db_manager.get_connection()
        _ensure_audit_table(conn)

        stats = conn.execute("""
            SELECT
                COUNT(*)                                                        AS total_runs,
                COUNT(DISTINCT ticker)                                          AS unique_tickers,
                AVG(confidence)                                                 AS avg_confidence,
                SUM(CASE WHEN eval_route = 'ESCALATE'      THEN 1 ELSE 0 END) AS escalated,
                SUM(CASE WHEN eval_route = 'SAMPLED_REVIEW' THEN 1 ELSE 0 END) AS sampled_review,
                SUM(CASE WHEN eval_route = 'AUTO'           THEN 1 ELSE 0 END) AS auto_approved,
                MIN(timestamp)                                                  AS first_run,
                MAX(timestamp)                                                  AS last_run
            FROM audit_runs
        """).fetchone()

        return {
            "total_runs":     stats[0],
            "unique_tickers": stats[1],
            "avg_confidence": round(stats[2], 4) if stats[2] is not None else None,
            "escalated":      stats[3],
            "sampled_review": stats[4],
            "auto_approved":  stats[5],
            "first_run":      stats[6],
            "last_run":       stats[7],
        }
    except Exception as e:
        logger.error(f"audit summary failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=list[AuditRunOut])
def list_audit_runs(
    ticker: Optional[str] = None,
    eval_route: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List pipeline runs. Filter by ticker or eval_route (AUTO/SAMPLED_REVIEW/ESCALATE)."""
    if ticker:
        ticker = ticker.upper()
        if not _VALID_TICKER.match(ticker):
            raise HTTPException(status_code=422, detail="Invalid ticker format")
    if eval_route:
        eval_route = eval_route.upper()
        if eval_route not in _VALID_ROUTES:
            raise HTTPException(
                status_code=422,
                detail=f"eval_route must be one of {sorted(_VALID_ROUTES)}",
            )

    try:
        conn = db_manager.get_connection()
        _ensure_audit_table(conn)

        # Build query with explicit branches — no f-string interpolation of user input
        if ticker and eval_route:
            sql = """
                SELECT run_id, timestamp, ticker, question, query_type, answer,
                       eval_route, confidence, verification_status, model_used,
                       source_docs, chunk_ids, xbrl_facts_cited, math_result,
                       math_steps, eval_triggers, review_id
                FROM audit_runs
                WHERE ticker = ? AND eval_route = ?
                ORDER BY timestamp DESC LIMIT ? OFFSET ?
            """
            params: list[Any] = [ticker, eval_route, limit, offset]
        elif ticker:
            sql = """
                SELECT run_id, timestamp, ticker, question, query_type, answer,
                       eval_route, confidence, verification_status, model_used,
                       source_docs, chunk_ids, xbrl_facts_cited, math_result,
                       math_steps, eval_triggers, review_id
                FROM audit_runs
                WHERE ticker = ?
                ORDER BY timestamp DESC LIMIT ? OFFSET ?
            """
            params = [ticker, limit, offset]
        elif eval_route:
            sql = """
                SELECT run_id, timestamp, ticker, question, query_type, answer,
                       eval_route, confidence, verification_status, model_used,
                       source_docs, chunk_ids, xbrl_facts_cited, math_result,
                       math_steps, eval_triggers, review_id
                FROM audit_runs
                WHERE eval_route = ?
                ORDER BY timestamp DESC LIMIT ? OFFSET ?
            """
            params = [eval_route, limit, offset]
        else:
            sql = """
                SELECT run_id, timestamp, ticker, question, query_type, answer,
                       eval_route, confidence, verification_status, model_used,
                       source_docs, chunk_ids, xbrl_facts_cited, math_result,
                       math_steps, eval_triggers, review_id
                FROM audit_runs
                ORDER BY timestamp DESC LIMIT ? OFFSET ?
            """
            params = [limit, offset]

        rows = conn.execute(sql, params).fetchall()
        return [_row_to_run(r) for r in rows]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"audit list failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{run_id}", response_model=AuditRunOut)
def get_audit_run(run_id: str):
    """Fetch a single run by ID."""
    try:
        conn = db_manager.get_connection()
        _ensure_audit_table(conn)

        rows = conn.execute("""
            SELECT run_id, timestamp, ticker, question, query_type, answer,
                   eval_route, confidence, verification_status, model_used,
                   source_docs, chunk_ids, xbrl_facts_cited, math_result,
                   math_steps, eval_triggers, review_id
            FROM audit_runs WHERE run_id = ?
        """, [run_id]).fetchall()

        if not rows:
            raise HTTPException(status_code=404, detail="Run not found")
        return _row_to_run(rows[0])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"audit get failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
