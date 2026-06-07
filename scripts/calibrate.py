"""
calibrate.py — Phase 6 calibration CLI wrapper.

Usage:
    python scripts/calibrate.py --run data/shadow/run_20260608_123456.jsonl
    python scripts/calibrate.py --run data/shadow/run_20260608_123456.jsonl \
        --errors data/shadow/run_20260608_123456_errors.jsonl

Reads a shadow-run JSONL file, generates a CalibrationReport, prints a
formatted report to stdout, and — if the auto-tier agreement rate meets the
>= 95% production bar — writes ROUTING_HIGH_THRESHOLD and
ROUTING_LOW_THRESHOLD to .env.calibration in the repo root.

CONSTRAINT-003: thresholds go into .env.calibration only, never hard-coded.
CONSTRAINT-007: .env.calibration is only written when agreement_rate >= 0.95.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _count_errors_file(errors_path: str) -> int:
    """Count the number of lines in an errors JSONL file."""
    try:
        with open(errors_path, encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())
    except FileNotFoundError:
        return 0


def _format_report(report) -> str:
    """Build the formatted calibration report string."""
    lines = []
    lines.append("=== Phase 6 Calibration Report ===")

    total_attempted = report.total_processed + report.failed
    lines.append(
        f"Total processed:   {report.total_processed} / {total_attempted}"
        f" ({report.failed} failed)"
    )

    lines.append("")
    lines.append("Confidence histogram:")
    for bucket, count in sorted(report.confidence_histogram.items()):
        lines.append(f"  {bucket}: {count:2d} records")

    dist = report.routing_distribution
    total = dist.total or 1  # guard against zero division in formatting
    lines.append("")
    lines.append("Routing distribution (at recommended thresholds):")

    auto_pct = 100.0 * dist.auto_count / total
    sampled_pct = 100.0 * dist.sampled_review_count / total
    escalate_pct = 100.0 * dist.escalate_count / total

    lines.append(f"  AUTO:           {dist.auto_count:3d}  ({auto_pct:.1f}%)")
    lines.append(f"  SAMPLED_REVIEW: {dist.sampled_review_count:3d}  ({sampled_pct:.1f}%)")
    lines.append(f"  ESCALATE:       {dist.escalate_count:3d}  ({escalate_pct:.1f}%)")

    lines.append("")
    if report.auto_tier_agreement_rate is not None:
        rate_pct = 100.0 * report.auto_tier_agreement_rate
        lines.append(f"Auto-tier agreement rate: {rate_pct:.1f}%")
    else:
        lines.append("Auto-tier agreement rate: N/A (no AUTO records)")

    lines.append(f"Recommended HIGH threshold: {report.recommended_high_threshold:.2f}")
    lines.append(f"Recommended LOW threshold:  {report.recommended_low_threshold:.2f}")

    bar_str = "YES" if report.meets_production_bar else "NO"
    lines.append(f"Meets production bar (>=95%): {bar_str}")

    return "\n".join(lines)


def _write_env_calibration(
    high: float,
    low: float,
    repo_root: Path,
) -> None:
    """Write threshold values to .env.calibration in the repo root."""
    env_path = repo_root / ".env.calibration"
    content = (
        f"ROUTING_HIGH_THRESHOLD={high:.4f}\n"
        f"ROUTING_LOW_THRESHOLD={low:.4f}\n"
    )
    env_path.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 6 calibration CLI — reads a shadow-run JSONL and outputs a calibration report."
    )
    parser.add_argument(
        "--run",
        required=True,
        metavar="JSONL",
        help="Path to the shadow-run output JSONL (e.g. data/shadow/run_20260608_123456.jsonl)",
    )
    parser.add_argument(
        "--errors",
        default=None,
        metavar="JSONL",
        help="Path to the shadow-run errors JSONL (optional; used to report failed count)",
    )
    args = parser.parse_args()

    # Count failures from the errors file (if provided)
    failed_count = 0
    if args.errors:
        failed_count = _count_errors_file(args.errors)

    # Import here so env-var problems surface at runtime, not import time
    from api.services.calibrator import generate_report

    report = generate_report(args.run, failed=failed_count)

    # Print the formatted report
    print(_format_report(report))

    # Determine repo root (parent of scripts/)
    repo_root = Path(__file__).resolve().parent.parent

    if report.meets_production_bar:
        _write_env_calibration(
            report.recommended_high_threshold,
            report.recommended_low_threshold,
            repo_root,
        )
        print("\nThresholds written to .env.calibration")
    else:
        rate_str = (
            f"{report.auto_tier_agreement_rate * 100:.1f}%"
            if report.auto_tier_agreement_rate is not None
            else "N/A"
        )
        print(
            f"\nWARNING: Production bar NOT met (auto-tier agreement = {rate_str}, "
            "required >= 95%). Thresholds NOT written to .env.calibration."
        )


if __name__ == "__main__":
    main()
