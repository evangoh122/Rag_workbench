"""
Calibration recalculation service for routing confidence thresholds.

Ownership: MiMo (Performance & Optimization Engineer) — Phase 8

Strategy:
    - Uses reviewer verdicts (confidence, reviewer_agrees) to find optimal
      HIGH and MEDIUM confidence cut-points for the AUTO routing tier.
    - Pure-Python math only — no external ML libraries.
    - HIGH threshold: highest confidence below which the agreement rate on
      retained decisions would cross 0.95.
    - MEDIUM threshold: highest confidence below which the agreement rate
      would cross 0.75.
    - Returns None dict with 'error' key when < 10 verdicts are available.
"""

from __future__ import annotations

from typing import Optional


# Target agreement rates for each tier boundary
_HIGH_AGREEMENT_TARGET: float = 0.95
_MEDIUM_AGREEMENT_TARGET: float = 0.75
_MIN_VERDICTS: int = 10


def recalibrate_thresholds(
    calibration_data: list[dict],
) -> dict:
    """Find optimal HIGH and MEDIUM confidence thresholds from reviewer verdicts.

    Args:
        calibration_data: List of dicts, each with keys:
            - confidence (float): System confidence score [0.0, 1.0]
            - reviewer_agrees (bool): Whether the reviewer agreed with the decision
            - route (str): The routing decision ('SAMPLED_REVIEW' | 'ESCALATE')

    Returns:
        On success::

            {
                'high_threshold': float,
                'medium_threshold': float,
                'projected_agreement_rate': float,
                'verdicts_used': int,
            }

        On insufficient data::

            {
                'error': str,
                'high_threshold': None,
                'medium_threshold': None,
                'projected_agreement_rate': None,
                'verdicts_used': int,
            }
    """
    verdicts_used = len(calibration_data)

    if verdicts_used < _MIN_VERDICTS:
        return {
            "error": (
                "Insufficient data for calibration — need at least 10 reviewer verdicts"
            ),
            "high_threshold": None,
            "medium_threshold": None,
            "projected_agreement_rate": None,
            "verdicts_used": verdicts_used,
        }

    # Sort by confidence descending so we evaluate from most-confident downward.
    # Each prefix (top-k by confidence) represents "what if we set the HIGH
    # threshold at this confidence level".
    sorted_data = sorted(
        calibration_data,
        key=lambda r: float(r["confidence"]),
        reverse=True,
    )

    high_threshold: Optional[float] = None
    medium_threshold: Optional[float] = None

    # Scan prefix windows to find where agreement rate crosses each target
    agrees_so_far: int = 0
    for i, record in enumerate(sorted_data):
        if record["reviewer_agrees"]:
            agrees_so_far += 1
        count_so_far: int = i + 1
        rate: float = agrees_so_far / count_so_far

        confidence: float = float(record["confidence"])

        # HIGH threshold: last confidence at which a 0.95 rate is still met
        if rate >= _HIGH_AGREEMENT_TARGET:
            high_threshold = confidence

        # MEDIUM threshold: last confidence at which a 0.75 rate is still met
        if rate >= _MEDIUM_AGREEMENT_TARGET:
            medium_threshold = confidence

    # Overall projected agreement rate across all verdicts
    total_agrees: int = sum(1 for r in calibration_data if r["reviewer_agrees"])
    projected_agreement_rate: float = total_agrees / verdicts_used

    # Fallback: if thresholds could not be found, use conservative defaults
    if high_threshold is None:
        high_threshold = 0.85
    if medium_threshold is None:
        medium_threshold = 0.65

    # Ensure ordering invariant: high > medium
    if medium_threshold >= high_threshold:
        # Nudge medium just below high to maintain valid ordering
        medium_threshold = max(0.0, high_threshold - 0.05)

    return {
        "high_threshold": round(high_threshold, 4),
        "medium_threshold": round(medium_threshold, 4),
        "projected_agreement_rate": round(projected_agreement_rate, 4),
        "verdicts_used": verdicts_used,
    }
