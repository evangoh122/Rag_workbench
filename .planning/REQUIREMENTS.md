# REQUIREMENTS.md
<!-- SEC Filing Eval & HITL Framework -->
<!-- Derived from SPEC constraints — no PRD was ingested. Requirements are sourced directly from the spec. -->

Generated: 2026-06-07

---

## Source Note

No PRD documents were ingested. All requirements below are derived from CONSTRAINT-001 through CONSTRAINT-011 in the spec (C:/RAG_workbench/docs/specs/eval-layer-spec.md). Each requirement carries its originating constraint ID.

---

## Requirements

### Data Structures & Reader (REQ-DS)

| ID | Requirement | Source |
|----|-------------|--------|
| REQ-DS-01 | System must define Python dataclasses: `Provenance`, `ReasonCode`, `Route`, `ExtractedField`, `ExtractionResult`, `ValidationResult`, `Decision` exactly as specified | CONSTRAINT-001 |
| REQ-DS-02 | All pipeline components must accept and emit the `ExtractionResult` / `Decision` types — no ad-hoc dicts or parallel schemas | CONSTRAINT-001 |
| REQ-DS-03 | Reader/extraction layer must wrap EdgarTools output into `ExtractionResult`; no custom EDGAR or XBRL parser may be written | CONSTRAINT-009 |
| REQ-DS-04 | Each `ExtractedField` must carry a `provenance` tag (XBRL | STRUCTURED_TABLE | NARRATIVE_LLM) | CONSTRAINT-001, CONSTRAINT-002 |

### Schema Validator — Layer 1 (REQ-SV)

| ID | Requirement | Source |
|----|-------------|--------|
| REQ-SV-01 | Validator must check that all required fields are present per form type (10-K and 10-Q field sets differ from 8-K) | CONSTRAINT-006 |
| REQ-SV-02 | Validator must verify type correctness: dates parse, monetary values are numeric, CIK is 10 digits, accession matches `\d{10}-\d{2}-\d{6}` | CONSTRAINT-006 |
| REQ-SV-03 | Validator must detect unit scale confusion (XBRL thousands vs. actuals) | CONSTRAINT-006 |
| REQ-SV-04 | Validator must emit a `ValidationResult` with `is_valid` bool, `reason_codes` list, and `details` dict | CONSTRAINT-001, CONSTRAINT-006 |

### XBRL Cross-Validation & companyfacts Client (REQ-XV)

| ID | Requirement | Source |
|----|-------------|--------|
| REQ-XV-01 | System must implement a companyfacts API client that fetches prior-period XBRL facts for a given CIK | CONSTRAINT-005, CONSTRAINT-006 |
| REQ-XV-02 | All SEC API calls must include a declared User-Agent header and must not exceed 10 requests per second | CONSTRAINT-005 |
| REQ-XV-03 | If a XBRL-tagged fact exists for a concept and matches the extracted value, confidence for that field must be set to 1.0 | CONSTRAINT-002 |
| REQ-XV-04 | If a XBRL-tagged fact exists for a concept and does not match the extracted value, the field must be flagged `XBRL_MISMATCH` and confidence set to 0.0 (triggering ESCALATE) | CONSTRAINT-002, CONSTRAINT-004 |
| REQ-XV-05 | Ground truth for XBRL-tagged figures must come from companyfacts API or SEC bulk quarterly data sets — hand-labeling of structured figures is prohibited | CONSTRAINT-010 |

### Semantic Validator — Layer 2 (REQ-SEM)

| ID | Requirement | Source |
|----|-------------|--------|
| REQ-SEM-01 | Validator must check accounting identities within tolerance: Assets ≈ Liabilities + StockholdersEquity; GrossProfit ≈ Revenues − CostOfRevenue; cash-flow subtotals tie | CONSTRAINT-006 |
| REQ-SEM-02 | Validator must check referential integrity: CIK ↔ company name; period dates consistent with fiscal period; referenced exhibits exist | CONSTRAINT-006 |
| REQ-SEM-03 | Validator must check plausibility vs. company history using companyfacts API: flag values > N std devs or > X% YoY from company-specific distribution as `OUT_OF_RANGE` | CONSTRAINT-006 |
| REQ-SEM-04 | Balance sheet identity failure (after unit normalization) must be tagged and always-escalated | CONSTRAINT-004 |

### Confidence Scoring, Routing & Triggers (REQ-CR)

| ID | Requirement | Source |
|----|-------------|--------|
| REQ-CR-01 | Confidence must be derived from provenance base scores: XBRL=0.98, STRUCTURED_TABLE=0.85, NARRATIVE_LLM=0.55; LLM self-reported confidence must not be used | CONSTRAINT-002 |
| REQ-CR-02 | Record-level confidence must be the minimum (or weighted aggregate) of per-field confidences | CONSTRAINT-002 |
| REQ-CR-03 | Routing must produce one of three tiers: AUTO (high confidence), SAMPLED_REVIEW (medium), ESCALATE (low or always-escalate trigger) | CONSTRAINT-003 |
| REQ-CR-04 | Routing band cut points (HIGH/MEDIUM/LOW thresholds) must not be hard-coded — they must be calibrated from shadow deployment data after Phase 6 completes | CONSTRAINT-003 |
| REQ-CR-05 | All eight always-escalate conditions must be implemented as pure predicate functions over `ExtractionResult`; fired trigger names must be collected in `Decision.triggers_fired` | CONSTRAINT-004 |
| REQ-CR-06 | Always-escalate triggers: (1) balance sheet identity failure, (2) amended filing or restatement signal, (3) 8-K items 1.03/4.02/4.01, (4) going-concern language, (5) XBRL_MISMATCH, (6) unrecognized us-gaap concept or new taxonomy, (7) value outside historical range, (8) extraction feeding user-facing financial figure or downstream action | CONSTRAINT-004 |

### Shadow Deployment & Calibration (REQ-SD)

| ID | Requirement | Source |
|----|-------------|--------|
| REQ-SD-01 | Shadow deployment must run over historical filings in read-only mode — no downstream actions may be triggered | CONSTRAINT-011 |
| REQ-SD-02 | Shadow run output must be used to calibrate AUTO/SAMPLED_REVIEW/ESCALATE cut points (i.e., populate REQ-CR-04) | CONSTRAINT-003, CONSTRAINT-011 |
| REQ-SD-03 | Shadow run must be complete before the system is considered trustworthy for any use; Phases 1–6 are the minimum trustworthy baseline | CONSTRAINT-011 |

### Metrics Dashboard (REQ-MD)

| ID | Requirement | Source |
|----|-------------|--------|
| REQ-MD-01 | Dashboard must display rolling human-agreement rate for the AUTO tier | CONSTRAINT-007 |
| REQ-MD-02 | Dashboard must display escalation rate, routing distribution, and unrecognized-concept count | CONSTRAINT-008 |
| REQ-MD-03 | System must not promote AUTO tier to production use until agreement rate exceeds 95% | CONSTRAINT-007 |

### Review Queue, Feedback Loop & Drift Alerts (REQ-RQ)

| ID | Requirement | Source |
|----|-------------|--------|
| REQ-RQ-01 | Review queue must present SAMPLED_REVIEW and ESCALATE decisions to a human reviewer | CONSTRAINT-004 |
| REQ-RQ-02 | Reviewer decisions must feed back into scorer calibration | CONSTRAINT-010 |
| REQ-RQ-03 | Drift monitoring must use human-agreement rate as the primary alarm signal | CONSTRAINT-008 |
| REQ-RQ-04 | Drift alerts must fire when: agreement rate drops below the defined floor; OR unrecognized-concept count spikes (new us-gaap taxonomy season) | CONSTRAINT-008 |
| REQ-RQ-05 | Escalation-rate movement must not be used as a sole alert trigger | CONSTRAINT-008 |
| REQ-RQ-06 | Hand-labeling for narrative fields (no XBRL equivalent) must be scoped to 50–100 edge-case records | CONSTRAINT-010 |

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| REQ-DS-01 | Phase 1 | Pending |
| REQ-DS-02 | Phase 1 | Pending |
| REQ-DS-03 | Phase 1 | Pending |
| REQ-DS-04 | Phase 1 | Pending |
| REQ-SV-01 | Phase 2 | Pending |
| REQ-SV-02 | Phase 2 | Pending |
| REQ-SV-03 | Phase 2 | Pending |
| REQ-SV-04 | Phase 2 | Pending |
| REQ-XV-01 | Phase 3 | Pending |
| REQ-XV-02 | Phase 3 | Pending |
| REQ-XV-03 | Phase 3 | Pending |
| REQ-XV-04 | Phase 3 | Pending |
| REQ-XV-05 | Phase 3 | Pending |
| REQ-SEM-01 | Phase 4 | Pending |
| REQ-SEM-02 | Phase 4 | Pending |
| REQ-SEM-03 | Phase 4 | Pending |
| REQ-SEM-04 | Phase 4 | Pending |
| REQ-CR-01 | Phase 5 | Pending |
| REQ-CR-02 | Phase 5 | Pending |
| REQ-CR-03 | Phase 5 | Pending |
| REQ-CR-04 | Phase 5 | Pending |
| REQ-CR-05 | Phase 5 | Pending |
| REQ-CR-06 | Phase 5 | Pending |
| REQ-SD-01 | Phase 6 | Pending |
| REQ-SD-02 | Phase 6 | Pending |
| REQ-SD-03 | Phase 6 | Pending |
| REQ-MD-01 | Phase 7 | Pending |
| REQ-MD-02 | Phase 7 | Pending |
| REQ-MD-03 | Phase 7 | Pending |
| REQ-RQ-01 | Phase 8 | Pending |
| REQ-RQ-02 | Phase 8 | Pending |
| REQ-RQ-03 | Phase 8 | Pending |
| REQ-RQ-04 | Phase 8 | Pending |
| REQ-RQ-05 | Phase 8 | Pending |
| REQ-RQ-06 | Phase 8 | Pending |
