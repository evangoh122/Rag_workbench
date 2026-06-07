"""
shadow_run.py — Phase 6 read-only batch runner for historical SEC filings.

Usage:
    python scripts/shadow_run.py --input data/shadow/input_filings.csv --output data/shadow/

Reads a CSV of (cik, accession, form_type), runs the full eval pipeline for
each filing, and writes per-record results to a JSONL file.  On per-filing
failures the record is written to a separate errors JSONL; processing
continues (fail-fast only applies to missing EDGAR_USER_AGENT).

CONSTRAINT-009: all EDGAR access goes through fetch_filing() only.
CONSTRAINT-011: shadow run is read-only — no downstream actions.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Ensure repo root is on sys.path so `api` package is importable when the
# script is invoked directly (python scripts/shadow_run.py)
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# Use UTF-8 for stdout so the arrow character renders on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

logger = logging.getLogger(__name__)


def _check_edgar_user_agent() -> None:
    """Fail fast with a clear error if EDGAR_USER_AGENT is not set (CONSTRAINT-009)."""
    if not os.environ.get("EDGAR_USER_AGENT"):
        sys.stderr.write(
            "ERROR: EDGAR_USER_AGENT environment variable is not set.\n"
            "Set it to 'Your Name your@email.com' before running the shadow pipeline.\n"
            "Example: export EDGAR_USER_AGENT='Acme Corp acme@example.com'\n"
        )
        sys.exit(1)


def _load_filings(input_path: str) -> list[dict]:
    """Read the input CSV and return a list of filing dicts."""
    filings = []
    with open(input_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            filings.append({
                "cik": row["cik"].strip(),
                "accession": row["accession"].strip(),
                "form_type": row["form_type"].strip(),
            })
    return filings


def _run_pipeline(cik: str, accession: str) -> dict:
    """Run the full eval pipeline for a single filing and return a result dict.

    Imports are deferred so that the env-var check fires before any import
    that might trigger EdgarTools initialization.
    """
    from api.services.edgar_adapter import fetch_filing
    from api.services.schema_validator import SchemaValidator
    from api.services.xbrl_validator import XbrlCrossValidator
    from api.services.semantic_validator import SemanticValidator
    from api.services.router import ConfidenceRouter

    result = fetch_filing(cik, accession)

    vs = SchemaValidator.validate(result)

    xbrl_validator = XbrlCrossValidator()
    xbrl_validator.validate(result, vs)

    semantic_validator = SemanticValidator()
    semantic_validator.validate(result, vs)

    router = ConfidenceRouter()
    decision = router.route(result, vs)

    # Determine xbrl_backed: enrichment_manifest has at least one entry
    enrichment_manifest = vs.details.get("enrichment_manifest", {})
    xbrl_backed = len(enrichment_manifest) > 0

    return {
        "cik": cik,
        "accession": accession,
        "form_type": result.form_type,
        "confidence": decision.confidence,
        "route": decision.route.value,
        "triggers_fired": decision.triggers_fired,
        "is_valid": decision.validation.is_valid,
        "reason_codes": [rc.value for rc in decision.validation.reason_codes],
        "xbrl_backed": xbrl_backed,
    }


def run(input_path: str, output_dir: str) -> None:
    """Main entry point for the shadow batch runner."""
    _check_edgar_user_agent()

    filings = _load_filings(input_path)
    total = len(filings)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    run_file = out_dir / f"run_{timestamp}.jsonl"
    errors_file = out_dir / f"run_{timestamp}_errors.jsonl"

    processed = 0
    failed = 0

    with open(run_file, "w", encoding="utf-8") as run_fh, \
         open(errors_file, "w", encoding="utf-8") as err_fh:

        for idx, filing in enumerate(filings, start=1):
            cik = filing["cik"]
            accession = filing["accession"]
            form_type = filing["form_type"]
            label = f"{cik}/{accession}"

            try:
                record = _run_pipeline(cik, accession)
                run_fh.write(json.dumps(record) + "\n")
                run_fh.flush()

                route = record["route"]
                confidence = record["confidence"]
                print(f"[{idx}/{total}] {label} → {route} ({confidence:.2f})")
                processed += 1

            except Exception as exc:
                failed += 1
                logger.error("[%d/%d] FAILED %s: %s", idx, total, label, exc)
                error_record = {
                    "cik": cik,
                    "accession": accession,
                    "form_type": form_type,
                    "error": str(exc),
                }
                err_fh.write(json.dumps(error_record) + "\n")
                err_fh.flush()
                print(f"[{idx}/{total}] {label} → ERROR: {exc}")

    print()
    print(f"Summary: {processed} processed, {failed} failed")
    print(f"Results written to: {run_file}")
    if failed:
        print(f"Errors written to: {errors_file}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 6 shadow batch runner — read-only pipeline evaluation."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to input CSV (columns: cik, accession, form_type)",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Directory to write run_<timestamp>.jsonl and error files",
    )
    args = parser.parse_args()
    run(args.input, args.output)


if __name__ == "__main__":
    main()
