"""Choice-based conjoint analysis of the answer experience.

Users are shown a series of choice tasks, each pairing two *profiles* — random
bundles of four binary answer-experience attributes — and pick the one they'd
prefer. At the end they rate how useful the application is. Everything persists
to the durable runtime DB (REVIEW_DB_PATH, the same volume that backs
`analytics_events`), so the study survives Space restarts.

Two payoffs:
  1. Aggregate analysis (`GET /results`) — count-based part-worth utilities and
     attribute importance across every completed response.
  2. Live personalization — `POST /complete` returns the level each respondent
     preferred (from their own choices), which the frontend applies to the chat.

The four attributes (each with two levels) are the single source of truth for
both the backend and the frontend, exposed via `GET /attributes`.
"""
from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from api.db.database import db_manager

router = APIRouter(prefix="/api/conjoint", tags=["conjoint"])

# ── Attribute design (single source of truth) ────────────────────────────────
# Each attribute has exactly two levels. Level index 0 is the default chosen on
# a tie when deriving a respondent's personalization preferences.
ATTRIBUTES: list[dict[str, Any]] = [
    {
        "key": "answer_basis",
        "label": "Answers",
        "levels": [
            {"key": "role_based", "label": "Role-based"},
            {"key": "standard", "label": "Standard"},
        ],
    },
    {
        "key": "answer_style",
        "label": "Style",
        "levels": [
            {"key": "direct", "label": "Direct answer"},
            {"key": "explained", "label": "With explanation"},
        ],
    },
    {
        "key": "prompts",
        "label": "Prompts",
        "levels": [
            {"key": "guided", "label": "Guided prompts"},
            {"key": "suggested", "label": "Suggested prompts"},
        ],
    },
    {
        "key": "evidence",
        "label": "Evidence",
        "levels": [
            {"key": "text_only", "label": "Text only"},
            {"key": "graph_metrics", "label": "KG + metrics"},
        ],
    },
]

_ATTR_KEYS = [a["key"] for a in ATTRIBUTES]
_LEVELS_BY_ATTR = {a["key"]: [lv["key"] for lv in a["levels"]] for a in ATTRIBUTES}

# ── Respondent roles (the four professional personas) ─────────────────────────
# Each respondent self-identifies as one of these. When the `answer_basis` level
# is "role_based", answers are tailored to this role using `answer_guidance`.
# The JTBD fields (situation/motivation/outcome/emotional_job/social_job) document
# what each role is hiring the product to do and segment the aggregate analysis.
ROLES: list[dict[str, str]] = [
    {
        "key": "compliance_officer",
        "name": "Compliance Officer",
        "persona": "Mary M.",
        "situation": "Post-deployment audit of an AI answer",
        "motivation": "Ensure regulatory traceability",
        "outcome": "Full evidence trail for regulators",
        "emotional_job": "Confidence that the AI won't create liability",
        "social_job": "Seen as a responsible AI steward",
        "answer_guidance": (
            "Emphasize a complete, auditable evidence trail: cite every source filing "
            "and section, surface verification status, and flag any uncertainty "
            "explicitly. Prioritize traceability and defensibility over brevity."
        ),
    },
    {
        "key": "equity_research_analyst",
        "name": "Equity Research Analyst",
        "persona": "Derek T.",
        "situation": "Researching a filing under deadline",
        "motivation": "Find relevant disclosures quickly",
        "outcome": "Cited, evidence-backed answers",
        "emotional_job": "Trust in AI-surfaced insights",
        "social_job": "Credible analysis for colleagues",
        "answer_guidance": (
            "Lead with the key disclosure, cite the exact filing section, and stay "
            "fast and signal-dense. The reader is time-pressed and needs cited insight."
        ),
    },
    {
        "key": "credit_analyst",
        "name": "Credit Analyst",
        "persona": "Nayara N.",
        "situation": "Assessing default risk on a borrower",
        "motivation": "Validate reported financial figures",
        "outcome": "Verified numbers with confidence",
        "emotional_job": "Certainty that numbers aren't hallucinated",
        "social_job": "Defensible credit recommendation",
        "answer_guidance": (
            "Foreground verified financial figures with their source and verification "
            "status. Never present an unverified number without a caveat; certainty "
            "that figures aren't hallucinated is the priority."
        ),
    },
    {
        "key": "relationship_manager",
        "name": "Relationship Manager",
        "persona": "Robert Q.",
        "situation": "Prepping for a client meeting",
        "motivation": "Quickly surface key risks",
        "outcome": "Clean summary with actionable takeaways",
        "emotional_job": "Feeling prepared, not overwhelmed",
        "social_job": "Professional, informed client presence",
        "answer_guidance": (
            "Give a concise, client-ready summary of key risks and actionable "
            "takeaways. Minimize jargon; favor a clean, prepared narrative over an "
            "exhaustive dump."
        ),
    },
]

_ROLE_KEYS = {r["key"] for r in ROLES}
_ROLE_BY_KEY = {r["key"]: r for r in ROLES}


def role_guidance_for(role_key: Optional[str]) -> Optional[str]:
    """Answer-tailoring guidance for a role key, or None if unknown/blank.

    Composes the role's full jobs-to-be-done context (who they are, their
    situation, what they're trying to achieve, and the emotional/social job)
    together with the distilled `answer_guidance`, so the answering model knows
    the persona's needs and wants — not just a one-line tone hint.

    Imported by the chat route to drive `role_based` personalization.
    """
    role = _ROLE_BY_KEY.get((role_key or "").strip())
    if not role:
        return None
    return (
        f"The reader is a {role['name']} ({role['persona']}). "
        f"Situation: {role['situation']}. "
        f"What they're trying to do: {role['motivation']}. "
        f"What a good answer gives them: {role['outcome']}. "
        f"They need to feel: {role['emotional_job']}; "
        f"and to be seen as: {role['social_job']}. "
        f"{role['answer_guidance']}"
    )

_MIN_TASKS = 4
_MAX_TASKS = 12
_DEFAULT_TASKS = 6

# Experiment arms. `control` = standard app (no role, no conjoint tasks — just the
# usefulness vote). `treatment` = role-based personalization + conjoint tasks.
# Assignment is self-selected by the user (not randomized), so downstream analysis
# should treat the arm comparison as observational, not a clean RCT.
_ARMS = {"control", "treatment"}


# ── Schema / persistence ──────────────────────────────────────────────────────
def _ensure_tables(conn) -> None:
    conn.execute("CREATE SEQUENCE IF NOT EXISTS conjoint_responses_seq START 1")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conjoint_sessions (
            session_id          VARCHAR PRIMARY KEY,
            distinct_id         VARCHAR,
            arm                 VARCHAR,
            role                VARCHAR,
            started_at          VARCHAR NOT NULL,
            completed_at        VARCHAR,
            usefulness          INTEGER,
            usefulness_comment  VARCHAR,
            applied_prefs       JSON
        )
    """)
    # Idempotent migrations for DBs created before these columns existed.
    for _stmt in (
        "ALTER TABLE conjoint_sessions ADD COLUMN IF NOT EXISTS role VARCHAR",
        "ALTER TABLE conjoint_sessions ADD COLUMN IF NOT EXISTS arm VARCHAR",
    ):
        try:
            conn.execute(_stmt)
        except Exception as e:  # benign if column already exists; log for visibility
            logger.warning("conjoint migration skipped ({}): {}", _stmt[:48], e)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conjoint_responses (
            id          INTEGER PRIMARY KEY DEFAULT(nextval('conjoint_responses_seq')),
            session_id  VARCHAR NOT NULL,
            task_index  INTEGER NOT NULL,
            profile_a   JSON NOT NULL,
            profile_b   JSON NOT NULL,
            chosen      VARCHAR NOT NULL,
            ts          VARCHAR NOT NULL
        )
    """)
    # Point-lookup on session_id (/complete) and the /results scan benefit from an
    # index as responses accumulate (MiMo review finding).
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_conjoint_responses_session "
        "ON conjoint_responses (session_id)"
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _random_profile() -> dict[str, str]:
    return {k: random.choice(_LEVELS_BY_ATTR[k]) for k in _ATTR_KEYS}


def _make_tasks(n: int) -> list[dict[str, Any]]:
    """Generate `n` choice tasks. Each task pairs two distinct random profiles.

    A random full-profile design keeps the implementation simple while still
    giving every level balanced exposure over enough tasks; we only reject the
    degenerate case where both profiles are identical.
    """
    tasks: list[dict[str, Any]] = []
    for i in range(n):
        a = _random_profile()
        b = _random_profile()
        # Ensure the pair differs on at least one attribute (avoid a no-op task).
        while b == a:
            b = _random_profile()
        tasks.append({"index": i, "profile_a": a, "profile_b": b})
    return tasks


def _valid_profile(p: Any) -> bool:
    if not isinstance(p, dict):
        return False
    # Reject extra/unknown keys, not just missing ones (DeepSeek review finding).
    if set(p.keys()) != set(_ATTR_KEYS):
        return False
    for k in _ATTR_KEYS:
        if p.get(k) not in _LEVELS_BY_ATTR[k]:
            return False
    return True


# ── Count-based conjoint analysis ─────────────────────────────────────────────
def _counting_analysis(rows: list[tuple]) -> dict[str, Any]:
    """Classic count-based conjoint over (profile_a, profile_b, chosen) rows.

    For each attribute level, utility = (# chosen profiles carrying the level) /
    (# presented profiles carrying the level) — i.e. its win-rate when present.
    Attribute importance = (max level utility - min level utility), normalised
    across attributes to sum to 100%.
    """
    appear: dict[str, int] = {}
    won: dict[str, int] = {}

    def _level_key(attr: str, level: str) -> str:
        return f"{attr}::{level}"

    n_choices = 0
    for profile_a, profile_b, chosen in rows:
        a = profile_a if isinstance(profile_a, dict) else json.loads(profile_a)
        b = profile_b if isinstance(profile_b, dict) else json.loads(profile_b)
        if chosen not in ("A", "B"):
            continue
        n_choices += 1
        chosen_profile = a if chosen == "A" else b
        for profile in (a, b):
            for attr in _ATTR_KEYS:
                lv = profile.get(attr)
                if lv is None:
                    continue
                appear[_level_key(attr, lv)] = appear.get(_level_key(attr, lv), 0) + 1
        for attr in _ATTR_KEYS:
            lv = chosen_profile.get(attr)
            if lv is not None:
                won[_level_key(attr, lv)] = won.get(_level_key(attr, lv), 0) + 1

    attributes: list[dict[str, Any]] = []
    raw_importance: dict[str, float] = {}
    for attr in ATTRIBUTES:
        akey = attr["key"]
        levels_out = []
        utils = []
        for lv in attr["levels"]:
            lk = _level_key(akey, lv["key"])
            ap = appear.get(lk, 0)
            wn = won.get(lk, 0)
            util = (wn / ap) if ap else 0.0
            utils.append(util)
            levels_out.append({
                "key": lv["key"],
                "label": lv["label"],
                "utility": round(util, 4),
                "appearances": ap,
                "wins": wn,
            })
        rng = (max(utils) - min(utils)) if utils else 0.0
        raw_importance[akey] = rng
        attributes.append({
            "key": akey,
            "label": attr["label"],
            "levels": levels_out,
            "_range": rng,
        })

    total_range = sum(raw_importance.values())
    for a in attributes:
        a["importance"] = round((a.pop("_range") / total_range) * 100, 2) if total_range else 0.0

    return {"n_choices": n_choices, "attributes": attributes}


def _preferred_levels(rows: list[tuple]) -> dict[str, str]:
    """Derive a respondent's preferred level per attribute from their choices.

    Ties (or no signal) fall back to level index 0, the canonical default.
    """
    analysis = _counting_analysis(rows)
    prefs: dict[str, str] = {}
    by_key = {a["key"]: a for a in analysis["attributes"]}
    for attr in ATTRIBUTES:
        levels = by_key[attr["key"]]["levels"]
        best = max(levels, key=lambda lv: lv["utility"])
        # On a tie keep the canonical default (index 0).
        if levels[0]["utility"] >= best["utility"]:
            prefs[attr["key"]] = levels[0]["key"]
        else:
            prefs[attr["key"]] = best["key"]
    return prefs


# ── Request models ─────────────────────────────────────────────────────────────
class SessionStartIn(BaseModel):
    distinct_id: Optional[str] = None
    arm: Optional[str] = None  # "control" | "treatment"
    role: Optional[str] = None
    tasks: int = Field(default=_DEFAULT_TASKS, ge=_MIN_TASKS, le=_MAX_TASKS)


class ResponseIn(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    task_index: int = Field(ge=0, le=_MAX_TASKS)
    profile_a: dict[str, str]
    profile_b: dict[str, str]
    chosen: str = Field(pattern="^[AB]$")


class CompleteIn(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    usefulness: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=2000)


# ── Endpoints ───────────────────────────────────────────────────────────────────
@router.get("/attributes")
def get_attributes():
    """The attribute/level design + roles — frontend renders labels from this."""
    return {"attributes": ATTRIBUTES, "roles": ROLES}


@router.post("/session")
def start_session(body: SessionStartIn):
    """Create a respondent session and return its generated choice tasks."""
    arm = body.arm if body.arm in _ARMS else "treatment"
    # Control = standard app: no role, no conjoint choice tasks (vote only).
    role = body.role if (arm == "treatment" and body.role in _ROLE_KEYS) else None
    n = max(_MIN_TASKS, min(int(body.tasks or _DEFAULT_TASKS), _MAX_TASKS))
    tasks = _make_tasks(n) if arm == "treatment" else []
    session_id = str(uuid.uuid4())
    try:
        conn = db_manager.get_review_connection()
        _ensure_tables(conn)
        conn.execute(
            "INSERT INTO conjoint_sessions (session_id, distinct_id, arm, role, started_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [session_id, (body.distinct_id or None), arm, role, _now()],
        )
    except Exception:
        logger.exception("conjoint session start failed")
        raise HTTPException(status_code=500, detail="Failed to start conjoint session")
    return {
        "session_id": session_id,
        "arm": arm,
        "role": role,
        "tasks": tasks,
        "attributes": ATTRIBUTES,
        "roles": ROLES,
    }


@router.post("/response", status_code=204)
def record_response(body: ResponseIn):
    """Persist one choice. Never blocks the survey UX on a soft failure."""
    if not (_valid_profile(body.profile_a) and _valid_profile(body.profile_b)):
        raise HTTPException(status_code=400, detail="Invalid profile in response")
    try:
        conn = db_manager.get_review_connection()
        _ensure_tables(conn)
        # Reject choices for unknown sessions so fabricated session_ids can't
        # pollute the aggregate results (review hardening).
        if not conn.execute(
            "SELECT 1 FROM conjoint_sessions WHERE session_id = ?", [body.session_id]
        ).fetchone():
            raise HTTPException(status_code=404, detail="Session not found")
        conn.execute(
            "INSERT INTO conjoint_responses (session_id, task_index, profile_a, profile_b, chosen, ts) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                body.session_id,
                body.task_index,
                json.dumps(body.profile_a),
                json.dumps(body.profile_b),
                body.chosen,
                _now(),
            ],
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("conjoint response record failed")
        raise HTTPException(status_code=500, detail="Failed to record response")


@router.post("/complete")
def complete_session(body: CompleteIn):
    """Record the usefulness vote and return the respondent's preferred levels.

    The returned `applied_prefs` drive live personalization of the chat for the
    rest of the session.
    """
    try:
        conn = db_manager.get_review_connection()
        _ensure_tables(conn)
        # Verify the session exists and isn't already finalized — prevents
        # completing unknown sessions and double-submits that skew aggregates.
        existing = conn.execute(
            "SELECT completed_at, arm FROM conjoint_sessions WHERE session_id = ?",
            [body.session_id],
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Session not found")
        if existing[0] is not None:
            raise HTTPException(status_code=409, detail="Session already completed")
        # Only treatment sessions have choices to derive preferences from.
        # Control = standard app: persist NO applied_prefs, so the frontend keeps
        # the default (standard) rendering. Deriving _preferred_levels([]) for
        # control would yield index-0 defaults (direct / text_only) and wrongly
        # strip evidence + explanation for standard users.
        if existing[1] == "treatment":
            rows = conn.execute(
                "SELECT profile_a, profile_b, chosen FROM conjoint_responses WHERE session_id = ?",
                [body.session_id],
            ).fetchall()
            prefs = _preferred_levels(rows)
        else:
            prefs = {}
        conn.execute(
            "UPDATE conjoint_sessions SET completed_at = ?, usefulness = ?, "
            "usefulness_comment = ?, applied_prefs = ? WHERE session_id = ?",
            [_now(), body.usefulness, (body.comment or None), json.dumps(prefs), body.session_id],
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("conjoint complete failed")
        raise HTTPException(status_code=500, detail="Failed to complete session")
    return {"applied_prefs": prefs}


@router.get("/results")
def results():
    """Aggregate count-based utilities, importance, and usefulness stats."""
    try:
        conn = db_manager.get_review_connection()
        _ensure_tables(conn)
        rows = conn.execute(
            "SELECT profile_a, profile_b, chosen FROM conjoint_responses"
        ).fetchall()
        analysis = _counting_analysis(rows)

        sess_row = conn.execute(
            "SELECT COUNT(*) FROM conjoint_sessions WHERE completed_at IS NOT NULL"
        ).fetchone()
        n_sessions = sess_row[0] if sess_row else 0
        useful = conn.execute(
            "SELECT AVG(usefulness), COUNT(usefulness) FROM conjoint_sessions WHERE usefulness IS NOT NULL"
        ).fetchone()
        dist = conn.execute(
            "SELECT usefulness, COUNT(*) FROM conjoint_sessions "
            "WHERE usefulness IS NOT NULL GROUP BY usefulness ORDER BY usefulness"
        ).fetchall()
        # Test-vs-control comparison of the usefulness outcome by arm.
        by_arm = conn.execute(
            "SELECT COALESCE(arm, 'unknown') arm, AVG(usefulness) avg_useful, COUNT(*) n "
            "FROM conjoint_sessions WHERE usefulness IS NOT NULL "
            "GROUP BY COALESCE(arm, 'unknown') ORDER BY 1"
        ).fetchall()
    except Exception:
        logger.exception("conjoint results failed")
        raise HTTPException(status_code=500, detail="Failed to compute results")

    avg = useful[0] if useful else None
    return {
        "n_sessions_completed": n_sessions,
        "n_choices": analysis["n_choices"],
        "attributes": analysis["attributes"],
        "usefulness": {
            "average": round(avg, 2) if avg is not None else None,
            "count": (useful[1] if useful else 0),
            "distribution": [{"score": s, "count": c} for s, c in dist],
        },
        "by_arm": [
            {"arm": a, "avg_usefulness": round(av, 2) if av is not None else None, "n": n_}
            for a, av, n_ in by_arm
        ],
        "assignment": "self_selected",
    }
