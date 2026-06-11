"""
run_shadow.py — Shadow deployment script (Phase 6).

Fetches XBRL facts from DuckDB, groups them by ticker/period,
and runs the eval pipeline (schema + XBRL cross-validation + semantic +
confidence scoring) to produce a CalibrationReport.

Usage:
    python scripts/run_shadow.py [--tickers NVDA,AMD,QCOM] [--db-path ./data/rag.duckdb]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import duckdb
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.models.eval_types import ExtractionResult, ExtractedField, Provenance
from api.services.shadow_runner import run_shadow_pipeline, report_to_json


def load_extractions(conn: duckdb.DuckDBPyConnection, tickers: list[str]) -> list[ExtractionResult]:
    """Load XBRL facts from DuckDB and group into ExtractionResult objects."""
    if not tickers:
        rows = conn.execute(
            "SELECT DISTINCT ticker FROM xbrl_facts"
        ).fetchall()
        tickers = [r[0] for r in rows]

    extractions = []
    for ticker in tickers:
        # Get the latest filing period for each ticker
        periods = conn.execute("""
            SELECT DISTINCT period_end, accession, form_type
            FROM xbrl_facts
            WHERE ticker = ?
            ORDER BY period_end DESC
            LIMIT 3
        """, [ticker]).fetchall()

        for period_end, accession, form_type in periods:
            facts = conn.execute("""
                SELECT concept, value, unit
                FROM xbrl_facts
                WHERE ticker = ? AND period_end = ?
            """, [ticker, period_end]).fetchall()

            if not facts:
                continue

            fields = []
            for concept, value, unit in facts:
                if value is not None:
                    fields.append(ExtractedField(
                        name=concept,
                        value=float(value),
                        provenance=Provenance.XBRL,
                        concept=concept,
                    ))

            if fields:
                extractions.append(ExtractionResult(
                    cik="",
                    accession=accession or "0000000000-00-000000",
                    form_type=form_type or "10-K",
                    period=period_end,
                    fields=fields,
                ))

    return extractions


def main():
    parser = argparse.ArgumentParser(description="Run shadow deployment over historical filings")
    parser.add_argument("--tickers", default="", help="Comma-separated tickers (empty = all)")
    parser.add_argument("--db-path", default="./data/rag.duckdb", help="DuckDB path")
    parser.add_argument("--output", default="./data/shadow_report.json", help="Report output path")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()] if args.tickers else []

    conn = duckdb.connect(args.db_path, read_only=True)
    extractions = load_extractions(conn, tickers)
    conn.close()

    if not extractions:
        logger.error("No extractions found. Run bootstrap_db.py first.")
        return

    logger.info("Running shadow pipeline over %d extractions...", len(extractions))
    report = run_shadow_pipeline(extractions, ticker=tickers[0] if len(tickers) == 1 else "")

    # Save report
    os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(report_to_json(report))

    # Print summary
    print("\n=== Shadow Deployment Report ===")
    print(f"Total processed:  {report.total_processed}")
    print(f"Errors:           {report.errors}")
    print(f"AUTO:             {report.auto_count}")
    print(f"SAMPLED_REVIEW:   {report.sampled_review_count}")
    print(f"ESCALATE:         {report.escalation_count}")
    print(f"\nConfidence histogram:")
    for bucket, count in sorted(report.confidence_histogram.items()):
        print(f"  {bucket}: {count}")
    if report.trigger_counts:
        print(f"\nTrigger counts:")
        for trigger, count in sorted(report.trigger_counts.items(), key=lambda x: -x[1]):
            print(f"  {trigger}: {count}")
    print(f"\nReport saved to: {args.output}")


if __name__ == "__main__":
    main()
