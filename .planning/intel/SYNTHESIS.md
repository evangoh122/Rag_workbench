# Synthesis Summary
<!-- entry point for gsd-roadmapper — do not hand-edit -->

Generated: 2026-06-07
Mode: new
Synthesizer: gsd-doc-synthesizer

---

## Doc counts by type

| Type | Count | Source paths |
|------|-------|--------------|
| SPEC | 1     | C:/RAG_workbench/docs/specs/eval-layer-spec.md |
| ADR  | 0     | — |
| PRD  | 0     | — |
| DOC  | 0     | — |
| UNKNOWN (low confidence) | 0 | — |

Total docs ingested: 1

---

## Decisions locked

Count: 0

No ADR documents were ingested. No locked decisions exist in this intel set.

---

## Requirements extracted

Count: 0

No PRD documents were ingested. No formal requirements with IDs exist in this intel set. Constraints extracted from the SPEC (below) serve as the implementation requirements for this pass.

---

## Constraints extracted

Count: 11 (from 1 SPEC document)

| ID | Type | Summary |
|----|------|---------|
| CONSTRAINT-001 | schema | ExtractionResult data structure contract (Python dataclasses) |
| CONSTRAINT-002 | nfr | Confidence scoring derivation rule — no LLM self-report |
| CONSTRAINT-003 | nfr | Routing band thresholds — calibrated from shadow deployment |
| CONSTRAINT-004 | protocol | Always-escalate trigger list (8 deterministic conditions) |
| CONSTRAINT-005 | protocol | SEC API access rules (User-Agent + <= 10 req/s) |
| CONSTRAINT-006 | schema | Validation two-layer structure (schema + semantic) |
| CONSTRAINT-007 | nfr | Human-agreement rate acceptance bar: > 95% on AUTO tier |
| CONSTRAINT-008 | nfr | Drift alarm triggers — agreement rate primary, escalation rate secondary only |
| CONSTRAINT-009 | api-contract | Use EdgarTools as reader layer; do not write a custom parser |
| CONSTRAINT-010 | nfr | Ground truth sourcing strategy (XBRL auto-labels; hand-label only narrative hard cases) |
| CONSTRAINT-011 | protocol | Mandated build order (8 phases, must not be reordered) |

Detail: C:/RAG_workbench/.planning/intel/constraints.md

---

## Context topics extracted

Count: 4

1. Project positioning and business framing
2. Regulatory alignment (SR 11-7, MAS, EU AI Act)
3. Open questions requiring resolution before build
4. Prior art and honest gap / limitations

Detail: C:/RAG_workbench/.planning/intel/context.md

---

## Conflicts

Blockers: 0
Competing variants: 0
Auto-resolved: 0

Detail: C:/RAG_workbench/.planning/INGEST-CONFLICTS.md

---

## Intel files

- Constraints: C:/RAG_workbench/.planning/intel/constraints.md
- Context: C:/RAG_workbench/.planning/intel/context.md
- Decisions: (not generated — no ADRs ingested)
- Requirements: (not generated — no PRDs ingested)

---

## Notes for gsd-roadmapper

1. Four open questions in context.md (reader output mode, downstream actions, in-scope form types, reviewer availability) are unresolved and should be surfaced in PROJECT.md for user resolution before the build order in CONSTRAINT-011 is executed.
2. Routing band cut points in CONSTRAINT-003 are intentionally undefined — they depend on shadow deployment output (CONSTRAINT-011 phase 6). ROADMAP.md should gate the confidence thresholds task on completion of the shadow run.
3. No ADRs exist yet. When ADRs are added (e.g., formalising the EdgarTools decision in CONSTRAINT-009), re-run ingest to get conflict coverage.
