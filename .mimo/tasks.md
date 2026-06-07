# Orchestrator Task — 2026-06-07
Feature: Phase 1 — Execute PLAN-01 (Data Structures)
Status: pending

## Context
The SEC Filing Eval & HITL Framework project has started. Phase 1 defines the
canonical Python dataclasses used by every downstream component. Your job is to
execute Wave 1 of Phase 1: write the seven dataclasses and their tests.

Full plan is at: `.planning/phases/01-data-structures-reader-adapter/01-PLAN-01.md`
Read that file first — it has the verbatim code and exact acceptance criteria.

## Your Tasks

- [ ] Create `api/models/eval_types.py` with the seven dataclasses exactly as specified
      (Provenance, ReasonCode, Route, ExtractedField, ExtractionResult, ValidationResult, Decision)
- [ ] Create `tests/test_eval_types.py` with 8 unit tests (round-trip, provenance enforcement, mutable-default isolation)
- [ ] Update `api/models/__init__.py` to re-export the seven new types alongside the existing Pydantic models

## Files
- api/models/eval_types.py       (create)
- tests/test_eval_types.py       (create)
- api/models/__init__.py         (update — append eval_types imports, do NOT remove existing exports)

## Acceptance Criteria
- `python -c "from api.models.eval_types import Provenance, ReasonCode, Route, ExtractedField, ExtractionResult, ValidationResult, Decision; print('OK')"` exits 0
- `python -m pytest tests/test_eval_types.py -v` passes with 0 failures
- `python -c "from api.models import ExtractionResult, Decision; print('re-export OK')"` exits 0
- `Provenance.XBRL == "xbrl"` evaluates True (str-enum behaviour)

## Key constraint
Do NOT modify any existing file except appending to `api/models/__init__.py`.
The existing `ChatRequest`, `ChatResponse`, `HealthResponse` exports must remain untouched.

## After completion
Commit with message: `feat(phase-1): define eval_types dataclasses (PLAN-01)`
Push to main.
Wave 2 (PLAN-02) is assigned to Gemini and unblocks after your commit is on main.
