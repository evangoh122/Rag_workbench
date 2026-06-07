# PROJECT.md
<!-- SEC Filing Eval & HITL Framework -->

Generated: 2026-06-07

---

## Core Value

Build an evaluation and human-in-the-loop (HITL) framework that makes it safe to trust automated SEC filing extractions. The central insight: autonomy is an evaluation problem, not an automation problem. Confidence is derived from provenance and XBRL cross-validation — never from LLM self-report — and routing decisions are calibrated from real shadow-deployment data before any tier is trusted in production.

Target success metric: human-agreement rate > 95% on the AUTO tier (CONSTRAINT-007).

---

## Positioning

This project is a worked example demonstrating an AI governance and evaluation methodology. The differentiated contribution is:

1. Domain-specific ground truth (XBRL facts + accounting identities) as the calibration substrate — no hand-labeling of structured figures
2. Honest confidence derivation from provenance + cross-check (not LLM self-report)
3. Multi-source integrity model spanning EDGAR extraction under a single risk-tiered routing layer

The project is not architecturally novel; its value is synthesis, EDGAR-specific ground-truth leverage, and a replicable governance methodology suitable for AI PM / AI governance portfolio contexts.

---

## Regulatory Alignment

- **US — SR 11-7** (Federal Reserve / OCC Model Risk Management): validation layer (§4.1) + metrics (§4.4) + drift detection (§4.5) + routing and escalate triggers (§4.2–4.3)
- **Singapore — MAS Proposed AI Risk Management Guidelines**: consultation closed Jan 2026, finalisation expected 2026 with 12-month transition. Covers all FIs including GenAI agents. This project is positioned ahead of the curve: risk materiality (§4.2), life-cycle controls (§4.1/§4.2–4.3), meaningful human oversight (§4.3/§4.4), pre- and post-deployment monitoring (§6/§4.5), auditability via per-field provenance.
- **EU AI Act**: August 2026 human-oversight requirements — demonstrable human oversight of automated decisions is a compliance requirement for enterprises; this framework provides that capability.

---

## Hard Constraints

| ID | Constraint | Impact |
|----|-----------|--------|
| CONSTRAINT-001 | ExtractionResult schema is the canonical contract — all pipeline components must accept/emit these Python dataclasses | Defines the type surface for the entire project |
| CONSTRAINT-002 | LLM self-reported confidence MUST NOT be used as a routing signal | Confidence is derived only from provenance base scores + XBRL cross-check result |
| CONSTRAINT-003 | Routing band cut points MUST be calibrated from shadow deployment data (Phase 6) — do not hard-code | Thresholds are undefined until Phase 6 completes |
| CONSTRAINT-004 | Eight deterministic always-escalate conditions are non-bypassable regardless of confidence score | Implemented as pure predicate functions over ExtractionResult |
| CONSTRAINT-005 | All SEC API calls must include a User-Agent header and respect <= 10 req/s | Applies to companyfacts and bulk XBRL data set calls |
| CONSTRAINT-006 | Validation must produce a ValidationResult with both layers evaluated (schema + semantic) | No single-layer shortcut is acceptable |
| CONSTRAINT-007 | AUTO tier requires > 95% human-agreement rate before production use | Acceptance bar for Phase 6 / Phase 7 calibration |
| CONSTRAINT-008 | Drift monitoring must use human-agreement rate as primary alarm; escalation rate is secondary and ambiguous | Do not use escalation rate as a sole alert trigger |
| **CONSTRAINT-009** | **Reader/extraction layer MUST be built on EdgarTools (dgunning/edgartools, MIT). Writing a custom EDGAR/XBRL parser is explicitly out of scope.** | EdgarTools already provides XBRL facts as DataFrames — use this as ground truth. Acceptable alternative: edgar-crawler for section JSON extraction. |
| CONSTRAINT-010 | XBRL-tagged figures use companyfacts API (auto labels). Hand-label only narrative hard cases (50–100 records). | Do not hand-label structured financial figures |
| CONSTRAINT-011 | Build order is mandated (8 phases); phases must not be reordered | See ROADMAP.md |

---

## Open Questions (Unresolved — Must Be Answered Before Phase 1 Begins)

These four questions are unresolved as of 2026-06-07. Each affects the scope and shape of at least one phase.

> **OQ-1: Reader output mode**
> Does the reader output structured field extractions, summaries/Q&A, or both?
> Impact: Determines the shape of the §4.1 validator — field-level validation vs. claim-against-source-span validation. If both, the validator must handle two modes.

> **OQ-2: Downstream actions**
> What downstream actions can an extraction trigger?
> Impact: Defines the highest-stakes entries in the always-escalate trigger list (CONSTRAINT-004, condition 8: "any extraction feeding a user-facing financial figure, alert, or downstream action").

> **OQ-3: In-scope form types**
> Which form types are in scope first — 10-K/10-Q, 8-K, or both?
> Impact: 10-K/10-Q lean heavily on XBRL and need minimal hand-labeling; 8-K is narrative-heavy and requires more hand-labeling effort (CONSTRAINT-010).

> **OQ-4: Reviewer availability**
> Is a human reviewer available for the sampled review queue, or will the builder act as reviewer initially?
> Impact: Determines whether Phase 8 (review queue + feedback loop) can be fully exercised or must be built for future use.

---

## Runtime

Python. All data structures defined as Python dataclasses (CONSTRAINT-001). EdgarTools is the reader layer (CONSTRAINT-009).

---

## Honest Limitations

This is a personal PoC with no real users or measured ROI. Recommended mitigation before any portfolio presentation: run one shadow-deployment slice (Phase 6) and cite a real result (threshold X → false-escalation Y%, agreement Z%). If a full shadow run is not feasible, frame the deliverable explicitly as a reusable governance methodology.
