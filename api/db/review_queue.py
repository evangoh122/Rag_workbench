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
            id          VARCHAR, -- Plain VARCHAR to avoid DuckDB 1.0.0 index constraint bugs on UPDATE
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

    # Golden-set evaluation results — one row per suite execution (eval_runs)
    # plus one row per question per run (eval_results). Lives in the persistent
    # review/runtime DB so eval history survives the boot-time overwrite of the
    # main DB (mirrors how audit_runs and calibration_history are stored).
    conn.execute("""
        CREATE TABLE IF NOT EXISTS eval_runs (
            run_id          VARCHAR PRIMARY KEY,
            run_at          TIMESTAMP DEFAULT current_timestamp,
            api_url         VARCHAR,
            git_sha         VARCHAR,
            filter_id       VARCHAR,
            filter_mode     VARCHAR,
            n_questions     INTEGER NOT NULL,
            pass_rate       DOUBLE,
            avg_correctness DOUBLE,
            avg_xbrl        DOUBLE,
            avg_sources     DOUBLE,
            avg_overall     DOUBLE,
            by_failure_mode JSON NOT NULL DEFAULT '{}'
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS eval_results (
            id                 VARCHAR PRIMARY KEY,
            run_id             VARCHAR NOT NULL,
            question_id        VARCHAR,
            ticker             VARCHAR,
            company            VARCHAR,
            failure_mode       VARCHAR,
            difficulty         VARCHAR,
            question           TEXT,
            expected           TEXT,
            answer_snippet     TEXT,
            correctness        DOUBLE,
            correctness_reason TEXT,
            xbrl               DOUBLE,
            xbrl_reason        TEXT,
            sources            DOUBLE,
            sources_reason     TEXT,
            abstention         DOUBLE,
            abstention_reason  TEXT,
            overall            DOUBLE,
            has_error          BOOLEAN DEFAULT FALSE
        )
    """)

    # Performance index: cover status-filtered queries ordered by creation time
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_rd_status
        ON review_decisions(status, created_at DESC)
    """)

    # Index eval_results by run for fast per-run detail lookups.
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_er_run
        ON eval_results(run_id)
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
    contains the string 'unrecognized_concept' (lowercase — matches the trigger
    name registered in confidence_scorer.ALL_TRIGGERS).

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
          AND  triggers_fired::VARCHAR LIKE '%unrecognized_concept%'
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


def persist_eval_run(
    conn: duckdb.DuckDBPyConnection,
    data: dict,
    *,
    api_url: Optional[str] = None,
    git_sha: Optional[str] = None,
    filter_id: Optional[str] = None,
    filter_mode: Optional[str] = None,
) -> str:
    """Persist a golden-set eval run (summary + per-question detail) to DuckDB.

    Args:
        conn:        Active DuckDB connection (review/runtime DB).
        data:        The dict returned by evals.run_eval.run() — must contain
                     ``summary``, ``pass_rate``, ``n``, ``results`` and
                     ``by_failure_mode``.
        api_url:     Base URL the suite ran against (provenance).
        git_sha:     Commit the suite ran on (provenance), if known.
        filter_id:   --id filter used for the run, if any.
        filter_mode: --mode (failure_mode) filter used, if any.

    Returns:
        The generated run_id (UUID string) linking eval_runs ↔ eval_results.
    """
    run_id = str(uuid.uuid4())
    summary = data.get("summary", {}) or {}

    conn.execute("BEGIN")
    try:
        conn.execute(
            """
            INSERT INTO eval_runs
                (run_id, run_at, api_url, git_sha, filter_id, filter_mode,
                 n_questions, pass_rate, avg_correctness, avg_xbrl,
                 avg_sources, avg_overall, by_failure_mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                run_id,
                data.get("run_at"),
                api_url,
                git_sha,
                filter_id,
                filter_mode,
                data.get("n", len(data.get("results", []))),
                data.get("pass_rate"),
                summary.get("correctness"),
                summary.get("xbrl"),
                summary.get("sources"),
                summary.get("overall"),
                json.dumps(data.get("by_failure_mode", {})),
            ],
        )

        for r in data.get("results", []):
            conn.execute(
                """
                INSERT INTO eval_results
                    (id, run_id, question_id, ticker, company, failure_mode,
                     difficulty, question, expected, answer_snippet,
                     correctness, correctness_reason, xbrl, xbrl_reason,
                     sources, sources_reason, abstention, abstention_reason,
                     overall, has_error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    str(uuid.uuid4()),
                    run_id,
                    str(r.get("id")) if r.get("id") is not None else None,
                    r.get("ticker"),
                    r.get("company"),
                    r.get("failure_mode"),
                    r.get("difficulty"),
                    r.get("question"),
                    r.get("expected"),
                    r.get("answer_snippet"),
                    r.get("correctness"),
                    r.get("correctness_reason"),
                    r.get("xbrl"),
                    r.get("xbrl_reason"),
                    r.get("sources"),
                    r.get("sources_reason"),
                    r.get("abstention"),
                    r.get("abstention_reason"),
                    r.get("overall"),
                    bool(r.get("has_error", False)),
                ],
            )

        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    return run_id


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
