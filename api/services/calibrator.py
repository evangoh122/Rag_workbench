"""
calibrator.py — Phase 6 threshold calibration from a shadow-run JSONL file.

Reads a completed shadow-run output, builds a confidence histogram, sweeps
thresholds to find the lowest HIGH_THRESHOLD that still achieves >= 95%
auto-tier agreement, and produces a CalibrationReport.

CONSTRAINT-003: thresholds are never hard-coded here — they are written to
               .env.calibration by the CLI wrapper (scripts/calibrate.py).
CONSTRAINT-007: .env.calibration is only written when agreement_rate >= 0.95.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from api.models.eval_types import Decision, Route, ValidationResult
from api.services.eval_metrics import RoutingMetrics, compute_routing_metrics

# Production readiness bar (mirrors CONSTRAINT-007 / eval_metrics.PRODUCTION_AGREEMENT_BAR)
PRODUCTION_AGREEMENT_BAR = 0.95

# Histogram bucket width
_BUCKET_WIDTH = 0.05

# Histogram lower bound (anything below this goes in the lowest bucket)
_HISTOGRAM_MIN = 0.50

# Threshold sweep range
_SWEEP_HIGH = 0.97
_SWEEP_LOW = 0.70
_SWEEP_STEP = 0.01


@dataclass
class CalibrationReport:
    """Full calibration report produced from a single shadow-run JSONL file."""

    total_processed: int
    failed: int
    confidence_histogram: dict[str, int]
    routing_distribution: RoutingMetrics
    auto_tier_agreement_rate: Optional[float]
    recommended_high_threshold: float
    recommended_low_threshold: float
    meets_production_bar: bool


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def load_run_records(jsonl_path: str) -> list[dict]:
    """Read a shadow-run JSONL file and return a list of record dicts."""
    records = []
    with open(jsonl_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def build_histogram(records: list[dict]) -> dict[str, int]:
    """Bucket confidence scores into 0.05-wide bands.

    Buckets span [0.50, 1.00] in 0.05 increments.  Scores below 0.50 are
    placed in the "0.50-0.55" bucket (treated as the floor).  Scores of
    exactly 1.0 go into the "0.95-1.00" bucket.
    """
    # Build ordered bucket labels
    buckets: dict[str, int] = {}
    lo = _HISTOGRAM_MIN
    while lo < 1.0 - 1e-9:
        hi = round(lo + _BUCKET_WIDTH, 10)
        label = f"{lo:.2f}-{hi:.2f}"
        buckets[label] = 0
        lo = hi

    bucket_labels = list(buckets.keys())
    bucket_lows = [float(lbl.split("-")[0]) for lbl in bucket_labels]

    for rec in records:
        confidence = float(rec.get("confidence", 0.0))
        # Clamp to histogram range
        confidence = max(_HISTOGRAM_MIN, min(confidence, 1.0))

        # Find the appropriate bucket (last bucket whose lower bound <= confidence)
        chosen = bucket_labels[0]
        for lbl, low in zip(bucket_labels, bucket_lows):
            if confidence >= low:
                chosen = lbl

        buckets[chosen] += 1

    # Remove empty buckets so the report is readable
    return {lbl: cnt for lbl, cnt in buckets.items() if cnt > 0}


def calibrate_thresholds(
    records: list[dict],
    threshold_gap: float = 0.15,
) -> tuple[float, float]:
    """Sweep high-threshold candidates and return (high, low) thresholds.

    Strategy:
    - Sweep high_candidate from 0.97 down to 0.70 in 0.01 steps.
    - At each step, compute the AUTO set: records with
      confidence >= high_candidate AND triggers_fired == [].
    - Agreement rate = fraction of that AUTO set with is_valid == True.
    - Select the LOWEST high_candidate where agreement_rate >= 0.95.
    - low_threshold = max(0.0, high_threshold - threshold_gap).
    - If no candidate reaches 0.95, return the candidate with the best
      agreement rate (to avoid returning None).
    """
    best_candidate: float = _SWEEP_HIGH
    best_agreement: float = 0.0

    # Build list of candidates: 0.97, 0.96, ..., 0.70
    n_steps = round((_SWEEP_HIGH - _SWEEP_LOW) / _SWEEP_STEP)
    candidates = [round(_SWEEP_HIGH - i * _SWEEP_STEP, 10) for i in range(n_steps + 1)]

    # Track lowest candidate that meets the bar (we iterate high → low, so the
    # last one that meets the bar when iterating is the lowest)
    chosen_high: Optional[float] = None

    for cand in candidates:
        auto_set = [
            r for r in records
            if float(r.get("confidence", 0.0)) >= cand
            and r.get("triggers_fired", []) == []
        ]
        if not auto_set:
            agreement = 0.0
        else:
            agreed = sum(1 for r in auto_set if r.get("is_valid", False))
            agreement = agreed / len(auto_set)

        if agreement > best_agreement:
            best_agreement = agreement
            best_candidate = cand

        if agreement >= PRODUCTION_AGREEMENT_BAR:
            # Keep overwriting — last (lowest) candidate that meets bar wins
            chosen_high = cand

    high_threshold = chosen_high if chosen_high is not None else best_candidate
    low_threshold = max(0.0, round(high_threshold - threshold_gap, 10))

    return high_threshold, low_threshold


def generate_report(jsonl_path: str, failed: int = 0) -> CalibrationReport:
    """Orchestrate all calibration steps and return a CalibrationReport.

    Args:
        jsonl_path: Path to the shadow-run JSONL output file.
        failed: Number of filings that failed during the shadow run
                (from the errors JSONL, counted externally).
    """
    records = load_run_records(jsonl_path)
    total_processed = len(records)

    histogram = build_histogram(records)

    # Reconstruct Decision objects for compute_routing_metrics
    decisions: list[Decision] = []
    for rec in records:
        route_str = rec.get("route", "escalate")
        try:
            route = Route(route_str)
        except ValueError:
            route = Route.ESCALATE
        dummy_vs = ValidationResult(is_valid=rec.get("is_valid", False))
        decisions.append(
            Decision(
                route=route,
                confidence=float(rec.get("confidence", 0.0)),
                validation=dummy_vs,
                triggers_fired=rec.get("triggers_fired", []),
            )
        )

    routing_distribution = compute_routing_metrics(decisions)

    # Auto-tier agreement rate: fraction of AUTO records with is_valid == True
    auto_records = [
        r for r in records
        if r.get("route", "") == Route.AUTO.value
    ]
    if auto_records:
        agreed = sum(1 for r in auto_records if r.get("is_valid", False))
        auto_tier_agreement_rate: Optional[float] = agreed / len(auto_records)
    else:
        auto_tier_agreement_rate = None

    high_threshold, low_threshold = calibrate_thresholds(records)

    meets_bar = (
        auto_tier_agreement_rate is not None
        and auto_tier_agreement_rate >= PRODUCTION_AGREEMENT_BAR
    )

    return CalibrationReport(
        total_processed=total_processed,
        failed=failed,
        confidence_histogram=histogram,
        routing_distribution=routing_distribution,
        auto_tier_agreement_rate=auto_tier_agreement_rate,
        recommended_high_threshold=high_threshold,
        recommended_low_threshold=low_threshold,
        meets_production_bar=meets_bar,
    )
