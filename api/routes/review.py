from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from api.config import Config
from api.db.database import db_manager
from api.models.review_schemas import (
    CalibrationResultOut,
    DriftStatusOut,
    ReviewDecisionIn,
    ReviewDecisionOut,
    VerdictIn,
)
from api.services.drift_detection import DriftStatus, check_drift, log_drift_alert

try:
    from api.db.review_queue import (
        list_decisions,
        insert_decision,
        get_decision,
        insert_verdict,
        get_calibration_data,
        persist_calibration_result,
    )
    from api.db.review_queue import compute_agreement_rate
    from api.db.review_queue import count_unrecognized_concepts
except ImportError:  # pragma: no cover
    list_decisions = None
    insert_decision = None
    get_decision = None
    insert_verdict = None
    get_calibration_data = None
    persist_calibration_result = None
    compute_agreement_rate = None
    count_unrecognized_concepts = None

from loguru import logger
try:
    from api.services.calibration import recalibrate_thresholds
except ImportError:  # pragma: no cover
    recalibrate_thresholds = None


from api.middleware.auth import get_write_api_key

async def get_review_conn(_=Depends(get_write_api_key)):
    return db_manager.get_review_connection()

async def get_review_conn_public():
    return db_manager.get_review_connection()


router = APIRouter(prefix="/api/review", tags=["review"])


@router.get("/queue", response_model=list[ReviewDecisionOut])
async def list_review_queue(
    status: Optional[str] = None,
    route: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    conn=Depends(get_review_conn),
):
    if list_decisions is None:
        raise HTTPException(status_code=503, detail="Review queue module unavailable")
    try:
        return list_decisions(conn, status=status, route=route, limit=limit, offset=offset)
    except Exception:
        logger.exception("Failed to fetch review queue")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/queue", status_code=201)
async def add_review_decision(
    body: ReviewDecisionIn,
    conn=Depends(get_review_conn),
):
    if insert_decision is None:
        raise HTTPException(status_code=503, detail="Review queue module unavailable")
    try:
        decision_id = insert_decision(conn, {
            "cik": body.cik,
            "accession": body.accession,
            "form_type": body.form_type,
            "route": body.route,
            "confidence": body.confidence,
            "triggers_fired": body.triggers_fired,
        })
        return {"id": decision_id}
    except Exception:
        logger.exception("Failed to insert review decision")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/decisions/{decision_id}/verdict", status_code=204)
async def record_reviewer_verdict(
    decision_id: str,
    verdict: VerdictIn,
    conn=Depends(get_review_conn),
):
    if get_decision is None or insert_verdict is None:
        raise HTTPException(status_code=503, detail="Review queue module unavailable")

    try:
        decision = get_decision(conn, decision_id)
    except Exception:
        logger.exception("DB error looking up decision {}", decision_id)
        raise HTTPException(status_code=500, detail="Internal server error")

    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    if decision.get("status") == "reviewed":
        raise HTTPException(status_code=409, detail="Decision already reviewed")

    try:
        insert_verdict(
            conn,
            decision_id=decision_id,
            reviewer_agrees=verdict.reviewer_agrees,
            notes=verdict.notes,
        )
    except Exception:
        logger.exception("Failed to record verdict for decision {}", decision_id)
        raise HTTPException(status_code=500, detail="Internal server error")

    return Response(status_code=204)


@router.get("/metrics")
async def get_pipeline_metrics(conn=Depends(get_review_conn)):
    try:
        agreement_rate = 0.0
        if compute_agreement_rate is not None:
            agreement_rate = compute_agreement_rate(conn, window=100)

        routes_query = """
            SELECT route, COUNT(*) as cnt
            FROM review_decisions
            GROUP BY route
        """
        cursor = conn.execute(routes_query)
        routing = {"auto": 0, "sampled_review": 0, "escalate": 0}
        total = 0
        for row in cursor.fetchall():
            r = row[0]
            cnt = row[1]
            if r in routing:
                routing[r] = cnt
            total += cnt

        escalation_rate = 0.0
        if total > 0:
            escalation_rate = routing["escalate"] / total

        return {
            "agreement_rate": agreement_rate,
            "routing_distribution": routing,
            "escalation_rate": round(escalation_rate, 4),
            "total_decisions": total,
        }
    except Exception:
        logger.exception("Failed to compute metrics")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/drift", response_model=DriftStatusOut)
async def get_drift_status(conn=Depends(get_review_conn_public)):
    try:
        status: DriftStatus = check_drift(
            conn,
            agreement_floor=Config.DRIFT_AGREEMENT_FLOOR,
            concept_spike_threshold=Config.DRIFT_CONCEPT_SPIKE_THRESHOLD,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception:
        logger.exception("Failed to compute drift status")
        raise HTTPException(status_code=500, detail="Internal server error")

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


@router.post("/calibrate", response_model=CalibrationResultOut)
async def run_calibration(conn=Depends(get_review_conn)):
    if get_calibration_data is None or persist_calibration_result is None:
        raise HTTPException(status_code=503, detail="Review queue module unavailable")
    if recalibrate_thresholds is None:
        raise HTTPException(status_code=503, detail="Calibration service unavailable")

    try:
        cal_data = get_calibration_data(conn)
    except Exception:
        logger.exception("Failed to fetch calibration data")
        raise HTTPException(status_code=500, detail="Internal server error")

    try:
        result = recalibrate_thresholds(cal_data)
    except Exception:
        logger.exception("Calibration computation failed")
        raise HTTPException(status_code=500, detail="Internal server error")

    try:
        persist_calibration_result(conn, result)
    except Exception:
        logger.exception("Failed to persist calibration result")
        raise HTTPException(status_code=500, detail="Internal server error")

    return CalibrationResultOut(
        message=result.get("message", result.get("error", "Calibration complete.")),
        verdicts_used=result.get("verdicts_used", 0),
        high_threshold=result.get("high_threshold"),
        medium_threshold=result.get("medium_threshold"),
        projected_agreement_rate=result.get("projected_agreement_rate"),
    )
