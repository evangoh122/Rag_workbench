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

**Current phase**: Not started
**Current plan**: None
**Status**: Awaiting Phase 1 kickoff
**Open questions blocking start**: OQ-1 (reader output mode), OQ-2 (downstream actions), OQ-3 (in-scope form types), OQ-4 (reviewer availability) — see PROJECT.md

```
Progress: [........] 0/8 phases complete
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
2026-06-07: Initial planning pass. PROJECT.md, REQUIREMENTS.md, ROADMAP.md, STATE.md created from spec ingest. 35 requirements derived from 11 constraints. 8-phase roadmap mirrors mandated build order (CONSTRAINT-011). Four open questions surfaced in PROJECT.md awaiting user resolution before Phase 1 can begin.

### Next Session Start Point
1. Resolve open questions OQ-1 through OQ-4 with user
2. Run `/gsd-plan-phase 1` to decompose Phase 1 (Data Structures & Reader Adapter) into executable plans
3. Phase 1 entry point: define the seven dataclasses in a single module, then build the EdgarTools adapter

### Handoff Notes
- CONSTRAINT-003 routing thresholds are intentionally undefined. Do not hard-code them in Phase 5. They will be derived from Phase 6 shadow run output.
- Phases 7 and 8 have UI components (dashboard, review queue). Flag for `/gsd-ui-phase` when those phases begin.
- No ADRs exist yet. When the EdgarTools choice is formalised as an ADR, re-run ingest to get conflict coverage on future spec changes.
