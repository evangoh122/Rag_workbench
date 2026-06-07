# STATE.md
<!-- SEC Filing Eval & HITL Framework — project memory -->
<!-- Updated by Claude at the end of each work session. -->

Last updated: 2026-06-07

---

## Project Reference

**Project**: SEC Filing Eval & HITL Framework
**Core value**: Provenance-derived confidence scoring + risk-tiered routing that makes it safe to trust automated SEC filing extractions. Autonomy is an evaluation problem.
**Runtime**: Python
**Success metric**: Human-agreement rate > 95% on the AUTO tier (CONSTRAINT-007)
**Reader constraint**: EdgarTools only — no custom parser (CONSTRAINT-009)

---

## Current Position

**Current phase**: Phase 1 — Data Structures & Reader Adapter
**Current plan**: 01-PLAN-01 (Wave 1), 01-PLAN-02 (Wave 2)
**Status**: Ready to execute
**Open questions blocking start**: Resolved — planning complete from spec

```
Progress: [●.......] 0/8 phases complete (Phase 1 planned, not yet executed)
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
(None yet — no ADRs exist. First decisions will be made when open questions OQ-1 through OQ-4 are answered.)

### Key Constraints to Carry Forward
- Confidence derivation: provenance base scores only (XBRL=0.98, TABLE=0.85, LLM=0.55); no self-report
- XBRL match → confidence 1.0; XBRL mismatch → confidence 0.0 + ESCALATE
- Routing thresholds: configurable, not hard-coded; populate after Phase 6
- Always-escalate triggers: 8 deterministic predicates, non-bypassable
- SEC API: User-Agent header required; <= 10 req/s

### TODOs Before Phase 1
- [ ] Answer OQ-1: confirm reader output mode (structured fields / summaries+Q&A / both)
- [ ] Answer OQ-2: enumerate downstream actions that extractions can trigger
- [ ] Answer OQ-3: decide initial in-scope form types (10-K/10-Q vs 8-K)
- [ ] Answer OQ-4: confirm reviewer availability for Phase 8 queue

### Blockers
None (no code written yet)

---

## Session Continuity

### Last Session Summary
2026-06-07: Phase 1 planned. Two PLAN.md files created in .planning/phases/01-data-structures-reader-adapter/. Verification passed (0 blockers, 0 warnings). Multi-runtime ownership confirmed: Claude owns Phases 1–6 (eval layer), MiMo owns Phase 3 retriever/caching layer, Gemini owns Phases 7–8 UI.

### Next Session Start Point
1. Execute Phase 1: `/gsd-execute-phase 1`
   - Wave 1: 01-PLAN-01 — define seven dataclasses in api/models/eval_types.py
   - Wave 2: 01-PLAN-02 — build EdgarTools adapter in api/services/edgar_adapter.py
2. After Phase 1 complete: plan Phase 2 (Schema Validator)

### Handoff Notes
- CONSTRAINT-003 routing thresholds are intentionally undefined. Do not hard-code them in Phase 5. They will be derived from Phase 6 shadow run output.
- Phases 7 and 8 have UI components (dashboard, review queue). Flag for `/gsd-ui-phase` when those phases begin.
- No ADRs exist yet. When the EdgarTools choice is formalised as an ADR, re-run ingest to get conflict coverage on future spec changes.
