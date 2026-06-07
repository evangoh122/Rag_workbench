"""
tests/test_calibrator.py — unit tests for api/services/calibrator.py

No EDGAR calls, no real filesystem I/O beyond tmp_path.
"""
from __future__ import annotations

import json
import math

import pytest

from api.services.calibrator import (
    build_histogram,
    calibrate_thresholds,
    generate_report,
    load_run_records,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(
    confidence: float,
    is_valid: bool,
    route: str = "auto",
    triggers_fired: list | None = None,
) -> dict:
    return {
        "cik": "0000320193",
        "accession": "0000320193-23-000064",
        "form_type": "10-K",
        "confidence": confidence,
        "route": route,
        "triggers_fired": triggers_fired if triggers_fired is not None else [],
        "is_valid": is_valid,
        "reason_codes": [],
        "xbrl_backed": True,
    }


def _write_jsonl(tmp_path, records: list[dict], filename: str = "run.jsonl") -> str:
    path = tmp_path / filename
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")
    return str(path)


# ---------------------------------------------------------------------------
# Test 1: calibration selects threshold meeting 95% bar
# ---------------------------------------------------------------------------

def test_calibration_selects_threshold_meeting_95_bar(tmp_path):
    """10 high-confidence valid records + 2 low-confidence invalid records.

    The calibrator should find a high_threshold <= 0.97 that achieves >= 95%
    agreement on the AUTO tier and set meets_production_bar=True.
    """
    records = (
        [_make_record(confidence=0.97, is_valid=True, route="auto") for _ in range(10)]
        + [_make_record(confidence=0.50, is_valid=False, route="escalate") for _ in range(2)]
    )
    path = _write_jsonl(tmp_path, records)
    report = generate_report(path)

    assert report.recommended_high_threshold <= 0.97
    assert report.meets_production_bar is True
    assert report.auto_tier_agreement_rate is not None
    assert report.auto_tier_agreement_rate >= 0.95


# ---------------------------------------------------------------------------
# Test 2: calibration reports best candidate when bar not met
# ---------------------------------------------------------------------------

def test_calibration_reports_best_when_bar_not_met(tmp_path):
    """All records have is_valid=False — no threshold can reach 95% agreement."""
    records = [
        _make_record(confidence=0.95, is_valid=False, route="auto")
        for _ in range(10)
    ]
    path = _write_jsonl(tmp_path, records)
    report = generate_report(path)

    # meets_production_bar must be False
    assert report.meets_production_bar is False
    # But we still get a recommendation (no exception raised)
    assert isinstance(report.recommended_high_threshold, float)
    assert isinstance(report.recommended_low_threshold, float)


# ---------------------------------------------------------------------------
# Test 3: histogram buckets all records
# ---------------------------------------------------------------------------

def test_histogram_buckets_all_records():
    """20 records at various confidences — histogram sum must equal 20."""
    records = (
        [_make_record(0.55, True) for _ in range(3)]
        + [_make_record(0.72, True) for _ in range(5)]
        + [_make_record(0.85, True) for _ in range(4)]
        + [_make_record(0.92, True) for _ in range(5)]
        + [_make_record(0.98, True) for _ in range(3)]
    )
    assert len(records) == 20

    histogram = build_histogram(records)
    total = sum(histogram.values())
    assert total == 20, f"Expected 20 records in histogram, got {total}: {histogram}"


# ---------------------------------------------------------------------------
# Test 4: routing distribution matches records
# ---------------------------------------------------------------------------

def test_routing_distribution_matches_records(tmp_path):
    """10 AUTO + 4 SAMPLED_REVIEW + 3 ESCALATE — routing_distribution counts must match."""
    records = (
        [_make_record(0.97, True, route="auto") for _ in range(10)]
        + [_make_record(0.75, True, route="sampled_review") for _ in range(4)]
        + [_make_record(0.50, False, route="escalate") for _ in range(3)]
    )
    path = _write_jsonl(tmp_path, records)
    report = generate_report(path)

    dist = report.routing_distribution
    assert dist.auto_count == 10, f"Expected auto=10, got {dist.auto_count}"
    assert dist.sampled_review_count == 4, f"Expected sampled=4, got {dist.sampled_review_count}"
    assert dist.escalate_count == 3, f"Expected escalate=3, got {dist.escalate_count}"
    assert dist.total == 17


# ---------------------------------------------------------------------------
# Test 5: auto-tier agreement rate computation
# ---------------------------------------------------------------------------

def test_auto_tier_agreement_rate_computation(tmp_path):
    """8 AUTO records: 6 is_valid=True, 2 is_valid=False → agreement rate ≈ 0.75."""
    records = (
        [_make_record(0.97, is_valid=True, route="auto") for _ in range(6)]
        + [_make_record(0.92, is_valid=False, route="auto") for _ in range(2)]
    )
    path = _write_jsonl(tmp_path, records)
    report = generate_report(path)

    assert report.auto_tier_agreement_rate is not None
    assert math.isclose(report.auto_tier_agreement_rate, 0.75, rel_tol=1e-9), (
        f"Expected 0.75, got {report.auto_tier_agreement_rate}"
    )
    # With 75% agreement, production bar (95%) should NOT be met
    assert report.meets_production_bar is False
