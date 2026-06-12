# STATE.md
<!-- SEC Filing Eval & HITL Framework — project memory -->
<!-- Updated by Claude at the end of each work session. -->

Last updated: 2026-06-12

---

## Project Reference

**Project**: SEC Filing Eval & HITL Framework
**Core value**: Provenance-derived confidence scoring + risk-tiered routing that makes it safe to trust automated SEC filing extractions. Autonomy is an evaluation problem.
**Runtime**: Python
**Success metric**: Human-agreement rate > 95% on the AUTO tier (CONSTRAINT-007)
**Reader constraint**: EdgarTools only — no custom parser (CONSTRAINT-009)

---

## Current Position

**Current phase**: Phase 11 — GraphRAG Frontend Integration (Gemini)
**Status**: Frontend responsiveness and ticker constraints implemented.
**Open questions blocking start**: Resolved.

```
Progress: [●●●●●●●●] 11/15 phases complete
```

---

## Performance Metrics

| Metric | Target | Current |
|--------|--------|---------|
| AUTO tier human-agreement rate | > 95% | Not measured |
| Routing band cut points | Calibrated from Phase 6 | Undefined |
| Shadow run batch size | TBD | Not run |
| Escalation rate | TBD after calibration | Not measured |

---

## Accumulated Context

### Decisions Made
- **ADR-001**: Use EdgarTools for all SEC filings extraction (CONSTRAINT-009).
- **ADR-002**: Use Polars for handling XBRL fact DataFrames (Performance).
- **ADR-003**: Use CrossEncoder (deberta-v3-small) for semantic entailment verification.

### Key Constraints to Carry Forward
- Confidence derivation: provenance base scores only (XBRL=0.98, TABLE=0.85, LLM=0.55); no self-report
- XBRL match → confidence 1.0; XBRL mismatch → confidence 0.0 + ESCALATE
- Routing thresholds: configurable, not hard-coded; populate after Phase 6
- Always-escalate triggers: 8 deterministic predicates, non-bypassable
- SEC API: User-Agent header required; <= 10 req/s

### TODOs Before Phase 2
- [x] Answer OQ-1: confirm reader output mode (structured fields / summaries+Q&A / both) -> Both supported via edgar_adapter and verifier.
- [x] Answer OQ-2: enumerate downstream actions that extractions can trigger
- [x] Answer OQ-3: decide initial in-scope form types (10-K/10-Q)
- [x] Answer OQ-4: confirm reviewer availability for Phase 8 queue

### Blockers
None

---

## Session Continuity

### Last Session Summary
2026-06-09: Phase 1 executed. `api/models/eval_types.py` and `api/services/edgar_adapter.py` created. Additional verifier logic (`api/services/verifier.py`) and ingestion logic (`api/services/sec_client.py`) implemented. Frontend updated with `PipelineFlow` component.

### Next Session Start Point
1. Plan Phase 2 (Schema Validator)
2. Integrate `sec_client` into the main RAG flow.

### Handoff Notes
- CONSTRAINT-003 routing thresholds are intentionally undefined. Do not hard-code them in Phase 5. They will be derived from Phase 6 shadow run output.
- Phases 7 and 8 have UI components (dashboard, review queue). Flag for `/gsd-ui-phase` when those phases begin.
- No ADRs exist yet. When the EdgarTools choice is formalised as an ADR, re-run ingest to get conflict coverage on future spec changes.
