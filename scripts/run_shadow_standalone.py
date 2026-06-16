"""
run_shadow_standalone.py — Standalone shadow deployment that avoids heavy imports.

Directly implements the eval pipeline (schema + XBRL cross-validation + confidence
scoring) without importing the full api.services chain (which triggers model downloads).
"""
import json
import os
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import duckdb
from loguru import logger

# Minimal eval_types (avoid importing from api.models which triggers the full chain)
from enum import Enum

class Provenance(Enum):
    XBRL = "XBRL"
    STRUCTURED_TABLE = "STRUCTURED_TABLE"
    NARRATIVE_LLM = "NARRATIVE_LLM"

class ReasonCode(Enum):
    OK = "OK"
    XBRL_MISMATCH = "XBRL_MISMATCH"
    MISSING_FIELD = "MISSING_FIELD"
    IDENTITY_VIOLATION = "IDENTITY_VIOLATION"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    REFERENTIAL = "REFERENTIAL"
    BAD_TYPE = "BAD_TYPE"
    NO_DATA = "NO_DATA"
    UNKNOWN_CONCEPT = "UNKNOWN_CONCEPT"

class Route(Enum):
    AUTO = "AUTO"
    SAMPLED_REVIEW = "SAMPLED_REVIEW"
    ESCALATE = "ESCALATE"

@dataclass
class ExtractedField:
    name: str
    value: float
    provenance: Provenance
    concept: str = ""
    unit: str = "USD"

@dataclass
class ExtractionResult:
    cik: str
    accession: str
    form_type: str
    period: str
    fields: list

@dataclass
class ValidationResult:
    is_valid: bool = True
    reason_codes: list = field(default_factory=list)
    details: dict = field(default_factory=dict)

@dataclass
class Decision:
    route: Route
    confidence: float
    validation: ValidationResult
    triggers_fired: list = field(default_factory=list)

# --- Confidence scoring (simplified, standalone) ---
PROVENANCE_BASE_SCORE = {
    Provenance.XBRL: 0.98,
    Provenance.STRUCTURED_TABLE: 0.85,
    Provenance.NARRATIVE_LLM: 0.55,
}

ROUTING_THRESHOLDS = {
    "high": float(os.getenv("ROUTING_THRESHOLD_HIGH", "0.85")),
    "medium": float(os.getenv("ROUTING_THRESHOLD_MEDIUM", "0.55")),
}

def _validate_schema(result: ExtractionResult) -> ValidationResult:
    """Schema-level validation."""
    codes = []
    if not result.accession:
        codes.append(ReasonCode.MISSING_FIELD)
    if not result.form_type:
        codes.append(ReasonCode.MISSING_FIELD)
    if not result.fields:
        codes.append(ReasonCode.NO_DATA)
    return ValidationResult(is_valid=len(codes) == 0, reason_codes=codes)

def _check_xbrl_match(field_val: float, concept: str, ticker: str, conn) -> Optional[float]:
    """Check field value against XBRL facts in DB. Returns 1.0 if match, 0.0 if mismatch, None if no fact."""
    try:
        row = conn.execute(
            "SELECT value FROM xbrl_facts WHERE ticker = ? AND concept = ? ORDER BY period_end DESC LIMIT 1",
            [ticker, concept]
        ).fetchone()
        if row is None or row[0] is None:
            return None
        xbrl_val = float(row[0])
        if xbrl_val == 0:
            return 1.0 if field_val == 0 else 0.0
        diff = abs(field_val - xbrl_val) / abs(xbrl_val)
        return 1.0 if diff < 0.005 else 0.0  # 0.5% tolerance
    except Exception:
        return None

def score_and_route(result: ExtractionResult, ticker: str, conn) -> Decision:
    """Score extraction and route to AUTO/SAMPLED_REVIEW/ESCALATE."""
    schema = _validate_schema(result)

    # Compute per-field confidence
    field_confs = []
    xbrl_mismatch = False
    unknown_concept = False

    for f in result.fields:
        xbrl_match = _check_xbrl_match(f.value, f.concept or f.name, ticker, conn)
        if xbrl_match == 1.0:
            field_confs.append(1.0)
        elif xbrl_match == 0.0:
            field_confs.append(0.0)
            xbrl_mismatch = True
        else:
            # No XBRL fact — use provenance base score
            field_confs.append(PROVENANCE_BASE_SCORE.get(f.provenance, 0.55))
            unknown_concept = True

    record_conf = min(field_confs) if field_confs else 0.0

    # Trigger checks
    triggers = []
    if xbrl_mismatch:
        triggers.append("xbrl_mismatch")
    if unknown_concept:
        triggers.append("unrecognized_concept")

    # Route
    if triggers:
        route = Route.ESCALATE
    elif record_conf >= ROUTING_THRESHOLDS["high"]:
        route = Route.AUTO
    elif record_conf >= ROUTING_THRESHOLDS["medium"]:
        route = Route.SAMPLED_REVIEW
    else:
        route = Route.ESCALATE

    return Decision(
        route=route,
        confidence=record_conf,
        validation=schema,
        triggers_fired=triggers,
    )

# --- Shadow pipeline ---

@dataclass
class CalibrationReport:
    total_processed: int = 0
    errors: int = 0
    auto_count: int = 0
    sampled_review_count: int = 0
    escalation_count: int = 0
    confidence_histogram: dict = field(default_factory=dict)
    trigger_counts: dict = field(default_factory=dict)
    recommendations: dict = field(default_factory=dict)

def confidence_bucket(conf: float) -> str:
    if conf >= 0.95: return "0.95-1.00"
    if conf >= 0.85: return "0.85-0.94"
    if conf >= 0.70: return "0.70-0.84"
    if conf >= 0.55: return "0.55-0.69"
    return "0.00-0.54"

def load_extractions(conn, tickers: list[str]) -> list[tuple[str, ExtractionResult]]:
    """Load XBRL facts from DuckDB and group into ExtractionResult objects.
    Returns list of (ticker, ExtractionResult) tuples."""
    if not tickers:
        rows = conn.execute("SELECT DISTINCT ticker FROM xbrl_facts").fetchall()
        tickers = [r[0] for r in rows]

    extractions = []
    for ticker in tickers:
        periods = conn.execute("""
            SELECT DISTINCT period_end, accession, form_type
            FROM xbrl_facts WHERE ticker = ?
            ORDER BY period_end DESC LIMIT 3
        """, [ticker]).fetchall()

        for period_end, accession, form_type in periods:
            facts = conn.execute("""
                SELECT concept, value, unit
                FROM xbrl_facts WHERE ticker = ? AND period_end = ?
            """, [ticker, period_end]).fetchall()

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
                extractions.append((ticker, ExtractionResult(
                    cik="",
                    accession=accession or "0000000000-00-000000",
                    form_type=form_type or "10-K",
                    period=period_end,
                    fields=fields,
                )))

    return extractions

def run_shadow(conn, extractions: list[tuple[str, ExtractionResult]]) -> CalibrationReport:
    report = CalibrationReport()
    report.total_processed = len(extractions)

    for ticker, result in extractions:
        try:
            decision = score_and_route(result, ticker, conn)

            if decision.route == Route.AUTO:
                report.auto_count += 1
            elif decision.route == Route.SAMPLED_REVIEW:
                report.sampled_review_count += 1
            else:
                report.escalation_count += 1

            bucket = confidence_bucket(decision.confidence)
            report.confidence_histogram[bucket] = report.confidence_histogram.get(bucket, 0) + 1

            for trigger in decision.triggers_fired:
                report.trigger_counts[trigger] = report.trigger_counts.get(trigger, 0) + 1

        except Exception as e:
            report.errors += 1
            logger.warning(f"Shadow pipeline error: {e}")

    # Derive recommendations from distribution
    if report.total_processed > 0:
        escalation_rate = report.escalation_count / report.total_processed
        auto_rate = report.auto_count / report.total_processed
        report.recommendations = {
            "suggested_high_threshold": ROUTING_THRESHOLDS["high"],
            "suggested_medium_threshold": ROUTING_THRESHOLDS["medium"],
            "escalation_rate": round(escalation_rate, 4),
            "auto_rate": round(auto_rate, 4),
            "note": "Thresholds are defaults (0.85/0.55). Calibrate from reviewer verdicts after shadow data is reviewed."
        }

    return report

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run shadow deployment (standalone)")
    parser.add_argument("--tickers", default="", help="Comma-separated tickers (empty=all)")
    parser.add_argument("--db-path", default="./data/test_rag.duckdb", help="DuckDB path (test DB from create_test_db.py)")
    parser.add_argument("--output", default="./data/shadow_report.json", help="Report output path")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()] if args.tickers else []

    conn = duckdb.connect(args.db_path, read_only=True)
    extractions = load_extractions(conn, tickers)
    logger.info(f"Loaded {len(extractions)} extractions for shadow run")

    if not extractions:
        logger.error("No extractions found.")
        conn.close()
        return

    report = run_shadow(conn, extractions)
    conn.close()

    os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(asdict(report), f, indent=2, default=str)

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
    print(f"\nRecommendations:")
    for k, v in report.recommendations.items():
        print(f"  {k}: {v}")
    print(f"\nReport saved to: {args.output}")

if __name__ == "__main__":
    main()
