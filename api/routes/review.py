import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response

from api.models.review_schemas import (
    CalibrationResultOut,
    DriftStatusOut,
    ReviewDecisionOut,
    VerdictIn,
)
from api.services.drift_detection import DriftStatus, check_drift, log_drift_alert

# MiMo delivers this
try:
    from api.db.review_queue import (
        fetch_review_queue,
        insert_review_decision,
        record_verdict,
        get_decision_by_id,
        get_calibration_data,
        persist_calibration_result,
    )
except ImportError:  # pragma: no cover — MiMo delivers this
    fetch_review_queue = None          # MiMo delivers this
    insert_review_decision = None      # MiMo delivers this
    record_verdict = None              # MiMo delivers this
    get_decision_by_id = None          # MiMo delivers this
    get_calibration_data = None        # MiMo delivers this
    persist_calibration_result = None  # MiMo delivers this

# MiMo delivers this
try:
    from api.services.calibration import recalibrate_thresholds
except ImportError:  # pragma: no cover — MiMo delivers this
    recalibrate_thresholds = None  # MiMo delivers this

from api.db.database import db_manager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration constants (override via env vars or Config if added later)
# ---------------------------------------------------------------------------
AGREEMENT_FLOOR: float = 0.80
CONCEPT_SPIKE_THRESHOLD: int = 20
DRIFT_WINDOW: int = 100


# ---------------------------------------------------------------------------
# DB dependency
# ---------------------------------------------------------------------------

def get_db():
    """FastAPI dependency that yields the shared DuckDB connection."""
    conn = db_manager.get_connection()
    try:
        yield conn
    finally:
        pass  # Connection is managed by DatabaseManager singleton


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/review", tags=["review"])


# 1. GET /queue — list review queue (REQ-RQ-01)
@router.get("/queue", response_model=list[ReviewDecisionOut])
async def list_review_queue(
    status: Optional[str] = None,
    route: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    conn=Depends(get_db),
):
    """
    Returns SAMPLED_REVIEW and ESCALATE decisions from the review queue (REQ-RQ-01).
    """
    if fetch_review_queue is None:
        raise HTTPException(
            status_code=503,
            detail="review_queue DB module not yet available (MiMo delivers this).",
        )
    try:
        rows = fetch_review_queue(
            conn,
            status=status,
            route=route,
            limit=limit,
            offset=offset,
        )
        return rows
    except Exception as exc:
        logger.exception("Failed to fetch review queue")
        raise HTTPException(status_code=500, detail=str(exc))


# 2. POST /queue — pipeline pushes a new routing decision (REQ-RQ-01)
@router.post("/queue", status_code=201)
async def add_review_decision(
    cik: str,
    accession: str,
    form_type: str,
    route: str,
    confidence: float,
    triggers_fired: list[str],
    conn=Depends(get_db),
):
    """
    Pipeline calls this endpoint to register a decision for human review.
    route must be SAMPLED_REVIEW or ESCALATE.
    """
    if route not in ("SAMPLED_REVIEW", "ESCALATE"):
        raise HTTPException(
            status_code=422,
            detail="route must be 'SAMPLED_REVIEW' or 'ESCALATE'.",
        )
    if insert_review_decision is None:
        raise HTTPException(
            status_code=503,
            detail="review_queue DB module not yet available (MiMo delivers this).",
        )
    try:
        decision_id = str(uuid.uuid4())
        insert_review_decision(
            conn,
            id=decision_id,
            cik=cik,
            accession=accession,
            form_type=form_type,
            route=route,
            confidence=confidence,
            triggers_fired=triggers_fired,
        )
        return {"id": decision_id}
    except Exception as exc:
        logger.exception("Failed to insert review decision")
        raise HTTPException(status_code=500, detail=str(exc))


# 3. POST /decisions/{decision_id}/verdict — reviewer records verdict (REQ-RQ-02)
@router.post("/decisions/{decision_id}/verdict", status_code=204)
async def record_reviewer_verdict(
    decision_id: str,
    verdict: VerdictIn,
    conn=Depends(get_db),
):
    """
    Records a reviewer verdict. Feeds agreement signal back into calibration (REQ-RQ-02).
    Returns 204 No Content on success, 404 if not found, 409 if already reviewed.
    """
    if get_decision_by_id is None or record_verdict is None:
        raise HTTPException(
            status_code=503,
            detail="review_queue DB module not yet available (MiMo delivers this).",
        )
    try:
        decision = get_decision_by_id(conn, decision_id)
    except Exception as exc:
        logger.exception("DB error looking up decision %s", decision_id)
        raise HTTPException(status_code=500, detail=str(exc))

    if decision is None:
        raise HTTPException(status_code=404, detail=f"Decision '{decision_id}' not found.")

    if decision.get("status") == "reviewed":
        raise HTTPException(
            status_code=409, detail=f"Decision '{decision_id}' has already been reviewed."
        )

    try:
        record_verdict(
            conn,
            decision_id=decision_id,
            reviewer_agrees=verdict.reviewer_agrees,
            notes=verdict.notes,
        )
    except Exception as exc:
        logger.exception("Failed to record verdict for decision %s", decision_id)
        raise HTTPException(status_code=500, detail=str(exc))

    return Response(status_code=204)


# 4. GET /drift — current drift status (REQ-RQ-03/04/05)
@router.get("/drift", response_model=DriftStatusOut)
async def get_drift_status(conn=Depends(get_db)):
    """
    Returns the current drift status based on:
      - human-agreement rate (primary signal, REQ-RQ-03)
      - unrecognized concept count (REQ-RQ-04)
    Escalation rate is intentionally excluded (REQ-RQ-05).
    """
    try:
        status: DriftStatus = check_drift(
            conn,
            agreement_floor=AGREEMENT_FLOOR,
            concept_spike_threshold=CONCEPT_SPIKE_THRESHOLD,
            window=DRIFT_WINDOW,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Failed to compute drift status")
        raise HTTPException(status_code=500, detail=str(exc))

    if status.agreement_alert or status.concept_alert:
        log_drift_alert(status)

    return DriftStatusOut(
        agreement_rate=status.agreement_rate,
        agreement_floor=status.agreement_floor,
        agreement_alert=status.agreement_alert,
        unrecognized_concept_count=status.unrecognized_concept_count,
        concept_spike_threshold=status.concept_spike_threshold,
        concept_alert=status.concept_alert,
        window_size=status.window_size,
        last_updated=status.last_updated,
    )


# 5. POST /calibrate — trigger calibration recalculation (REQ-RQ-02/06)
@router.post("/calibrate", response_model=CalibrationResultOut)
async def run_calibration(conn=Depends(get_db)):
    """
    Triggers a full calibration pass using recently labeled verdicts.
    Scoped to 50-100 records (REQ-RQ-06). Persists results to calibration_history.
    """
    if get_calibration_data is None or persist_calibration_result is None:
        raise HTTPException(
            status_code=503,
            detail="review_queue DB module not yet available (MiMo delivers this).",
        )
    if recalibrate_thresholds is None:
        raise HTTPException(
            status_code=503,
            detail="calibration service not yet available (MiMo delivers this).",
        )

    try:
        cal_data = get_calibration_data(conn)
    except Exception as exc:
        logger.exception("Failed to fetch calibration data")
        raise HTTPException(status_code=500, detail=str(exc))

    try:
        result = recalibrate_thresholds(cal_data)
    except Exception as exc:
        logger.exception("Calibration computation failed")
        raise HTTPException(status_code=500, detail=str(exc))

    try:
        persist_calibration_result(conn, result)
    except Exception as exc:
        logger.exception("Failed to persist calibration result")
        raise HTTPException(status_code=500, detail=str(exc))

    return CalibrationResultOut(
        message=result.get("message", "Calibration complete."),
        verdicts_used=result.get("verdicts_used", 0),
        high_threshold=result.get("high_threshold"),
        medium_threshold=result.get("medium_threshold"),
        projected_agreement_rate=result.get("projected_agreement_rate"),
    )
