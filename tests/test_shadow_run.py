"""
tests/test_shadow_run.py — unit tests for scripts/shadow_run.py

Uses unittest.mock to stub all external I/O (EDGAR, validators, router).
No real SEC API calls are made.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure the repo root is on sys.path so both 'api' and 'scripts' are importable
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FILINGS = [
    {"cik": "0000320193", "accession": "0000320193-23-000064", "form_type": "10-K"},
    {"cik": "0000789019", "accession": "0000789019-23-000010", "form_type": "10-K"},
    {"cik": "0001652044", "accession": "0001652044-23-000016", "form_type": "10-K"},
]


def _write_input_csv(tmp_path: Path, filings: list[dict]) -> str:
    csv_path = tmp_path / "input.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["cik", "accession", "form_type"])
        writer.writeheader()
        writer.writerows(filings)
    return str(csv_path)


def _make_mock_pipeline_record(cik, accession, form_type="10-K"):
    """Build the dict that _run_pipeline would return for a successful filing."""
    return {
        "cik": cik,
        "accession": accession,
        "form_type": form_type,
        "confidence": 0.97,
        "route": "auto",
        "triggers_fired": [],
        "is_valid": True,
        "reason_codes": [],
        "xbrl_backed": True,
    }


# ---------------------------------------------------------------------------
# Test 1: all filings succeed → output JSONL has 3 lines
# ---------------------------------------------------------------------------

def test_shadow_run_writes_jsonl_per_filing(tmp_path, monkeypatch):
    """3 mock filings all succeed — output JSONL must contain exactly 3 lines."""
    monkeypatch.setenv("EDGAR_USER_AGENT", "Test Runner test@example.com")

    input_csv = _write_input_csv(tmp_path, _FILINGS)
    output_dir = str(tmp_path / "output")

    # Patch _run_pipeline so no real EDGAR call is made
    def fake_run_pipeline(cik, accession):
        filing = next(f for f in _FILINGS if f["cik"] == cik)
        return _make_mock_pipeline_record(cik, accession, filing["form_type"])

    from scripts import shadow_run
    monkeypatch.setattr(shadow_run, "_run_pipeline", fake_run_pipeline)

    shadow_run.run(input_csv, output_dir)

    # Find the run JSONL (not errors)
    run_files = list(Path(output_dir).glob("run_*.jsonl"))
    run_files = [f for f in run_files if "_errors" not in f.name]
    assert len(run_files) == 1, f"Expected 1 run JSONL, found: {run_files}"

    lines = run_files[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3, f"Expected 3 lines in JSONL, got {len(lines)}"

    for line in lines:
        record = json.loads(line)
        assert "cik" in record
        assert "route" in record


# ---------------------------------------------------------------------------
# Test 2: middle filing fails → 2 lines in output JSONL, 1 line in errors JSONL
# ---------------------------------------------------------------------------

def test_shadow_run_skips_failed_filing(tmp_path, monkeypatch):
    """Middle filing raises an exception — output has 2 records, errors has 1."""
    monkeypatch.setenv("EDGAR_USER_AGENT", "Test Runner test@example.com")

    input_csv = _write_input_csv(tmp_path, _FILINGS)
    output_dir = str(tmp_path / "output")

    def fake_run_pipeline(cik, accession):
        if cik == "0000789019":
            raise RuntimeError("Simulated EDGAR fetch failure")
        filing = next(f for f in _FILINGS if f["cik"] == cik)
        return _make_mock_pipeline_record(cik, accession, filing["form_type"])

    from scripts import shadow_run
    monkeypatch.setattr(shadow_run, "_run_pipeline", fake_run_pipeline)

    shadow_run.run(input_csv, output_dir)

    out_path = Path(output_dir)

    run_files = [f for f in out_path.glob("run_*.jsonl") if "_errors" not in f.name]
    assert len(run_files) == 1
    run_lines = run_files[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(run_lines) == 2, f"Expected 2 success lines, got {len(run_lines)}"

    err_files = list(out_path.glob("run_*_errors.jsonl"))
    assert len(err_files) == 1
    err_lines = err_files[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(err_lines) == 1, f"Expected 1 error line, got {len(err_lines)}"

    error_record = json.loads(err_lines[0])
    assert error_record["cik"] == "0000789019"
    assert "error" in error_record


# ---------------------------------------------------------------------------
# Test 3: missing EDGAR_USER_AGENT → SystemExit raised before any processing
# ---------------------------------------------------------------------------

def test_shadow_run_no_edgar_user_agent(tmp_path, monkeypatch):
    """Unset EDGAR_USER_AGENT — runner must raise SystemExit before touching filings."""
    # Remove the env var if it exists
    monkeypatch.delenv("EDGAR_USER_AGENT", raising=False)

    input_csv = _write_input_csv(tmp_path, _FILINGS)
    output_dir = str(tmp_path / "output")

    from scripts import shadow_run

    # Track whether _run_pipeline was ever called
    called = []

    def fake_run_pipeline(cik, accession):
        called.append(cik)
        return _make_mock_pipeline_record(cik, accession)

    monkeypatch.setattr(shadow_run, "_run_pipeline", fake_run_pipeline)

    with pytest.raises((SystemExit, EnvironmentError)):
        shadow_run.run(input_csv, output_dir)

    assert called == [], f"_run_pipeline was called despite missing env var: {called}"
