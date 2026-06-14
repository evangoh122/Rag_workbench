"""Product analytics.

Two data sources:
  1. Self-capture — the frontend mirrors every PostHog event to POST /track,
     which persists it to `analytics_events` in the durable runtime DB
     (REVIEW_DB_PATH on the persistent volume). The summary endpoint aggregates
     from this owned dataset, so the analytics page works with no external keys.
  2. PostHog API — /posthog proxies PostHog's Query API for richer aggregates
     when POSTHOG_API_KEY + POSTHOG_PROJECT_ID are configured; otherwise it
     reports `configured: false` and the page hides that section.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

import requests
from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

from api.config import Config
from api.db.database import db_manager

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _ensure_table(conn) -> None:
    conn.execute("CREATE SEQUENCE IF NOT EXISTS analytics_events_seq START 1")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analytics_events (
            id          INTEGER PRIMARY KEY DEFAULT(nextval('analytics_events_seq')),
            event       VARCHAR NOT NULL,
            distinct_id VARCHAR,
            view        VARCHAR,
            properties  JSON,
            ts          VARCHAR NOT NULL
        )
    """)


class TrackIn(BaseModel):
    event: str
    properties: dict[str, Any] = {}
    distinct_id: Optional[str] = None


@router.post("/track")
def track(body: TrackIn):
    """Persist one client analytics event. Never fails the caller's UX."""
    if not body.event or len(body.event) > 200:
        raise HTTPException(status_code=400, detail="invalid event name")
    try:
        conn = db_manager.get_review_connection()
        _ensure_table(conn)
        props = body.properties if isinstance(body.properties, dict) else {}
        view = props.get("view")
        conn.execute(
            "INSERT INTO analytics_events (event, distinct_id, view, properties, ts) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                body.event[:200],
                (body.distinct_id or None),
                (str(view)[:100] if view else None),
                json.dumps(props, default=str),
                datetime.now(timezone.utc).isoformat(),
            ],
        )
        return {"ok": True}
    except Exception:
        logger.exception("analytics track failed")
        return {"ok": False}


@router.get("/summary")
def summary(days: int = 14):
    """Aggregate the self-captured events for the Product Analytics page."""
    days = max(1, min(days, 90))
    try:
        conn = db_manager.get_review_connection()
        _ensure_table(conn)
        total = conn.execute("SELECT COUNT(*) FROM analytics_events").fetchone()[0]
        uniq = conn.execute(
            "SELECT COUNT(DISTINCT distinct_id) FROM analytics_events "
            "WHERE distinct_id IS NOT NULL"
        ).fetchone()[0]
        by_event = conn.execute(
            "SELECT event, COUNT(*) c FROM analytics_events "
            "GROUP BY event ORDER BY c DESC LIMIT 15"
        ).fetchall()
        by_view = conn.execute(
            "SELECT view, COUNT(*) c FROM analytics_events "
            "WHERE event = '$pageview' AND view IS NOT NULL "
            "GROUP BY view ORDER BY c DESC LIMIT 15"
        ).fetchall()
        daily = conn.execute(
            "SELECT substr(ts, 1, 10) d, COUNT(*) c FROM analytics_events "
            f"GROUP BY d ORDER BY d DESC LIMIT {days}"
        ).fetchall()
        recent = conn.execute(
            "SELECT event, view, ts FROM analytics_events ORDER BY id DESC LIMIT 25"
        ).fetchall()
        return {
            "total_events": total,
            "unique_visitors": uniq,
            "by_event": [{"event": e, "count": c} for e, c in by_event],
            "by_view": [{"view": v, "count": c} for v, c in by_view],
            "daily": [{"date": d, "count": c} for d, c in reversed(daily)],
            "recent": [{"event": e, "view": v, "ts": t} for e, v, t in recent],
        }
    except Exception:
        logger.exception("analytics summary failed")
        raise HTTPException(status_code=500, detail="analytics summary failed")


def _hogql(host: str, project: str, key: str, query: str) -> list:
    r = requests.post(
        f"{host}/api/projects/{project}/query/",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"query": {"kind": "HogQLQuery", "query": query}},
        timeout=20,
    )
    r.raise_for_status()
    return r.json().get("results", []) or []


@router.get("/posthog")
def posthog_summary():
    """Richer aggregates pulled from PostHog's Query API (if configured)."""
    key = Config.POSTHOG_API_KEY
    project = Config.POSTHOG_PROJECT_ID
    if not key or not project:
        return {"configured": False}
    host = Config.POSTHOG_API_HOST
    try:
        total = _hogql(
            host, project, key,
            "SELECT count() FROM events WHERE timestamp > now() - INTERVAL 7 DAY",
        )
        top = _hogql(
            host, project, key,
            "SELECT event, count() c FROM events WHERE timestamp > now() - INTERVAL 7 DAY "
            "GROUP BY event ORDER BY c DESC LIMIT 10",
        )
        return {
            "configured": True,
            "events_7d": (total[0][0] if total and total[0] else 0),
            "top_events": [{"event": row[0], "count": row[1]} for row in top],
        }
    except Exception as e:
        logger.warning("PostHog query failed: {}", e)
        return {"configured": True, "error": "PostHog query failed — check key/project."}
