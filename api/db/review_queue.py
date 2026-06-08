"""
DuckDB data access module for Review Queue, Reviewer Verdicts, and Calibration History.

Ownership: MiMo (Performance & Optimization Engineer) — Phase 8
"""

from __future__ import annotations

import json
import uuid
from typing import Optional

import duckdb


# ---------------------------------------------------------------------------
# Table initialisation
# ---------------------------------------------------------------------------

def init_review_tables(conn: duckdb.DuckDBPyConnection) -> None:
    """Create review-queue tables and performance indexes if they do not exist.

    Intended to be called once at application startup from the DB init flow.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS review_decisions (
            id          VARCHAR PRIMARY KEY,
            cik         VARCHAR NOT NULL,
            accession   VARCHAR NOT NULL,
            form_type   VARCHAR NOT NULL,
            route       VARCHAR NOT NULL
                        CHECK (route IN ('SAMPLED_REVIEW', 'ESCALATE')),
            confidence  DOUBLE  NOT NULL,
            triggers_fired JSON NOT NULL DEFAULT '[]',
            status      VARCHAR NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'reviewed')),
            created_at  TIMESTAMP DEFAULT current_timestamp
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS reviewer_verdicts (
            id              VARCHAR PRIMARY KEY,
            decision_id     VARCHAR NOT NULL,
            reviewer_agrees BOOLEAN NOT NULL,
            notes           TEXT,
            created_at      TIMESTAMP DEFAULT current_timestamp
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS calibration_history (
            id               VARCHAR PRIMARY KEY,
            run_at           TIMESTAMP DEFAULT current_timestamp,
            verdicts_used    INTEGER NOT NULL,
            high_threshold   DOUBLE,
            medium_threshold DOUBLE,
            agreement_rate   DOUBLE,
            notes            TEXT
        )
    """)

    # Performance index: cover status-filtered queries ordered by creation time
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_rd_status
        ON review_decisions(status, created_at DESC)
    """)


# ---------------------------------------------------------------------------
# Decision CRUD
# ---------------------------------------------------------------------------

def insert_decision(conn: duckdb.DuckDBPyConnection, decision: dict) -> str:
    """Insert a new pending review decision.

    Args:
        conn:     Active DuckDB connection.
        decision: Dict with keys: cik, accession, form_type, route, confidence,
                  triggers_fired (list[str], optional).

    Returns:
        The generated UUID string for the inserted row.
    """
    decision_id = str(uuid.uuid4())
    triggers = json.dumps(decision.get("triggers_fired", []))

    conn.execute(
        """
        INSERT INTO review_decisions
            (id, cik, accession, form_type, route, confidence, triggers_fired)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            decision_id,
            decision["cik"],
            decision["accession"],
            decision["form_type"],
            decision["route"],
            float(decision["confidence"]),
            triggers,
        ],
    )
    return decision_id


def list_decisions(
    conn: duckdb.DuckDBPyConnection,
    status: Optional[str] = None,
    route: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List review decisions with optional filtering and pagination.

    Args:
        conn:   Active DuckDB connection.
        status: Filter by status ('pending' | 'reviewed'). None = all.
        route:  Filter by route ('SAMPLED_REVIEW' | 'ESCALATE'). None = all.
        limit:  Maximum rows to return (pagination).
        offset: Row offset for pagination.

    Returns:
        List of dicts representing review_decisions rows.
    """
    conditions: list[str] = []
    params: list = []

    if status is not None:
        conditions.append("status = ?")
        params.append(status)
    if route is not None:
        conditions.append("route = ?")
        params.append(route)

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    params.extend([limit, offset])

    cursor = conn.execute(
        f"""
        SELECT id, cik, accession, form_type, route, confidence,
               triggers_fired, status, created_at
        FROM   review_decisions
        {where_clause}
        ORDER  BY created_at DESC
        LIMIT  ? OFFSET ?
        """,
        params,
    )
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    return [dict(zip(columns, row)) for row in rows]


def get_decision(
    conn: duckdb.DuckDBPyConnection,
    decision_id: str,
) -> Optional[dict]:
    """Fetch a single review decision by its primary key.

    Returns:
        Dict of the row, or None if not found.
    """
    cursor = conn.execute(
        """
        SELECT id, cik, accession, form_type, route, confidence,
               triggers_fired, status, created_at
        FROM   review_decisions
        WHERE  id = ?
        """,
        [decision_id],
    )
    row = cursor.fetchone()
    if row is None:
        return None
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


# ---------------------------------------------------------------------------
# Verdict CRUD
# ---------------------------------------------------------------------------

def insert_verdict(
    conn: duckdb.DuckDBPyConnection,
    decision_id: str,
    reviewer_agrees: bool,
    notes: Optional[str] = None,
) -> str:
    """Record a reviewer verdict and mark the parent decision as reviewed.

    Args:
        conn:            Active DuckDB connection.
        decision_id:     FK reference to review_decisions.id.
        reviewer_agrees: True if reviewer agrees with the system decision.
        notes:           Optional free-text notes from the reviewer.

    Returns:
        The generated UUID string for the inserted verdict row.
    """
    verdict_id = str(uuid.uuid4())

    conn.execute("BEGIN")
    try:
        conn.execute(
            """
            INSERT INTO reviewer_verdicts (id, decision_id, reviewer_agrees, notes)
            VALUES (?, ?, ?, ?)
            """,
            [verdict_id, decision_id, reviewer_agrees, notes],
        )
        conn.execute(
            "UPDATE review_decisions SET status = 'reviewed' WHERE id = ?",
            [decision_id],
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    return verdict_id


# ---------------------------------------------------------------------------
# Aggregate queries (MiMo performance mandate: single-SQL, no Python-side agg)
# ---------------------------------------------------------------------------

def compute_agreement_rate(
    conn: duckdb.DuckDBPyConnection,
    window: int = 100,
) -> float:
    """Compute the rolling reviewer-agreement rate over the last *window* verdicts.

    Uses a single SQL query — no Python-side aggregation.

    Args:
        conn:   Active DuckDB connection.
        window: Number of most-recent verdicts to consider.

    Returns:
        Float in [0.0, 1.0].  Returns 0.0 when no verdicts exist.
    """
    cursor = conn.execute(
        """
        WITH recent AS (
            SELECT reviewer_agrees
            FROM   reviewer_verdicts
            ORDER  BY created_at DESC
            LIMIT  ?
        )
        SELECT
            CASE
                WHEN COUNT(*) = 0 THEN 0.0
                ELSE SUM(CASE WHEN reviewer_agrees THEN 1 ELSE 0 END)::DOUBLE
                     / COUNT(*)::DOUBLE
            END AS agreement_rate
        FROM recent
        """,
        [window],
    )
    row = cursor.fetchone()
    if row is None or row[0] is None:
        return 0.0
    return float(row[0])


def count_unrecognized_concepts(
    conn: duckdb.DuckDBPyConnection,
    window_hours: int = 24,
) -> int:
    """Count decisions in the last *window_hours* hours where triggers_fired
    contains the string 'UNRECOGNIZED_CONCEPT'.

    Args:
        conn:         Active DuckDB connection.
        window_hours: Look-back period in hours.

    Returns:
        Integer count; 0 if none found.
    """
    cursor = conn.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM   review_decisions
        WHERE  created_at >= current_timestamp - INTERVAL (?) HOUR
          AND  triggers_fired::VARCHAR LIKE '%UNRECOGNIZED_CONCEPT%'
        """,
        [window_hours],
    )
    row = cursor.fetchone()
    if row is None or row[0] is None:
        return 0
    return int(row[0])


def get_calibration_data(
    conn: duckdb.DuckDBPyConnection,
) -> list[dict]:
    """Return all reviewer verdicts joined with decision confidence and route.

    Used by the calibration service to recalculate routing thresholds.

    Returns:
        List of dicts with keys: confidence (float), reviewer_agrees (bool),
        route (str).
    """
    cursor = conn.execute(
        """
        SELECT rd.confidence,
               rv.reviewer_agrees,
               rd.route
        FROM   reviewer_verdicts rv
        JOIN   review_decisions  rd ON rd.id = rv.decision_id
        ORDER  BY rv.created_at ASC
        """
    )
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    return [dict(zip(columns, row)) for row in rows]


def persist_calibration_result(
    conn: duckdb.DuckDBPyConnection,
    result: dict,
) -> None:
    """Persist a calibration run result to calibration_history.

    Args:
        conn:   Active DuckDB connection.
        result: Dict returned by recalibrate_thresholds().
    """
    conn.execute(
        """
        INSERT INTO calibration_history
            (id, verdicts_used, high_threshold, medium_threshold, agreement_rate, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            str(uuid.uuid4()),
            result.get("verdicts_used", 0),
            result.get("high_threshold"),
            result.get("medium_threshold"),
            result.get("projected_agreement_rate"),
            result.get("error"),
        ],
    )
