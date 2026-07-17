# ROADMAP.md
<!-- RAG Workbench — Multi-Track Roadmap -->
<!-- Eval pipeline phases 1-8 are mandated by CONSTRAINT-011 and must not be reordered. -->
<!-- RAG pipeline phases 9+ are independent and can be built in parallel. -->

Updated: 2026-06-09

---

## Track A: Eval Pipeline (SEC Filing Evaluation & HITL)

- [x] **Phase 1: Data Structures & Reader Adapter** - Define the ExtractionResult contract and wrap EdgarTools output into it
- [x] **Phase 2: Schema Validator** - Implement layer-1 validation (field presence, types, unit sanity)
- [x] **Phase 3: XBRL Cross-Validation & companyfacts Client** - Build the XBRL fact lookup that unlocks semantic validation and honest confidence scoring
- [x] **Phase 4: Semantic Validator** - Implement layer-2 validation (accounting identities, referential integrity, plausibility)
- [x] **Phase 5: Confidence Scoring, Routing & Always-Escalate Triggers** - Wire provenance-based confidence, three-tier routing, and all eight deterministic triggers
- [x] **Phase 6: Shadow Deployment & Calibration** - Run read-only over historical filings; calibrate AUTO/SAMPLED_REVIEW/ESCALATE cut points
- [x] **Phase 7: Metrics Dashboard** - Surface rolling agreement rate, routing distribution, and escalation signals
- [x] **Phase 8: Review Queue, Feedback Loop & Drift Alerts** - Complete the HITL loop with human review, scorer feedback, and drift detection

## Track B: RAG Pipeline (LangGraph + Knowledge Graph)

- [x] **Phase 9: LangGraph Auditable RAG** - Deterministic DAG for SEC filings (retrieval → extraction → math → verify → output/abstention)
- [x] **Phase 10: Knowledge Graph RAG Engine** - Entity extraction → DuckDB graph query → LLM synthesis with `graph_triples`
- [x] **Phase 11: GraphRAG Frontend Integration** - Engine toggle, entity badges, triple visualization in React UI
- [x] **Phase 12: Outstanding Integrations & Fixes** - Implement trigger 8, wire vector retrieval, run shadow deployment, calibrate thresholds, and run RAGAS eval

## Track C: NeMo Guardrails System

- [x] **Phase 13: Input & Dialog Rails** - Implement prompt injection detection, jailbreak prevention, and conversational state tracking
- [x] **Phase 14: Retrieval & Execution Rails** - Implement relevance checking for retrieved context and safe execution boundaries for math/SQL
- [x] **Phase 15: Output Rails** - Implement hallucination detection, formatting checks, and sensitive data masking

---

## Phase Details

### Phase 1: Data Structures & Reader Adapter
**Goal**: The canonical ExtractionResult type contract exists in code and EdgarTools output flows through it
**Depends on**: Nothing (first phase)
**Requirements**: REQ-DS-01, REQ-DS-02, REQ-DS-03, REQ-DS-04
**Success Criteria** (what must be TRUE):
  1. All seven dataclasses (`Provenance`, `ReasonCode`, `Route`, `ExtractedField`, `ExtractionResult`, `ValidationResult`, `Decision`) are importable from a single module with no runtime errors
  2. Given a real SEC filing CIK and accession number, EdgarTools returns data that is successfully wrapped into an `ExtractionResult` without custom parser code
  3. Every `ExtractedField` in the result carries a `provenance` tag (XBRL, STRUCTURED_TABLE, or NARRATIVE_LLM) — no field is untagged
  4. A round-trip test demonstrates that an `ExtractionResult` can be serialised and deserialised without data loss
**Plans**: 2 plans

Plans:
- [ ] 01-PLAN-01.md — Define the seven canonical dataclasses in api/models/eval_types.py and write round-trip + provenance enforcement tests
- [ ] 01-PLAN-02.md — Build the EdgarTools adapter (api/services/edgar_adapter.py) that wraps filing data into ExtractionResult with provenance tags

### Phase 2: Schema Validator
**Goal**: Layer-1 validation catches malformed, missing, and mis-scaled fields before any downstream processing
**Depends on**: Phase 1
**Requirements**: REQ-SV-01, REQ-SV-02, REQ-SV-03, REQ-SV-04
**Success Criteria** (what must be TRUE):
  1. Given an `ExtractionResult` with a missing required field for the declared form type, the validator returns `is_valid=False` with the appropriate `MISSING_FIELD` reason code
  2. Given a CIK value that is not 10 digits or an accession number that does not match `\d{10}-\d{2}-\d{6}`, the validator returns `BAD_TYPE`
  3. Given a monetary value that is in thousands where actuals are expected (or vice versa), the validator returns a unit-sanity failure
  4. Given a well-formed `ExtractionResult`, the validator returns `is_valid=True` with an empty `reason_codes` list
**Plans**: TBD

### Phase 3: XBRL Cross-Validation & companyfacts Client
**Goal**: The system can fetch live XBRL facts from SEC and compare them to extracted values, producing field-level confidence scores
**Depends on**: Phase 2
**Requirements**: REQ-XV-01, REQ-XV-02, REQ-XV-03, REQ-XV-04, REQ-XV-05
**Success Criteria** (what must be TRUE):
  1. Given a CIK, the companyfacts client returns prior-period XBRL facts as a structured result without triggering SEC rate-limit errors (all calls include User-Agent; rate stays at or below 10 req/s)
  2. When an extracted field value matches the XBRL-tagged fact for the same concept and period, that field's confidence is set to 1.0
  3. When an extracted field value does not match the XBRL fact, the field is tagged `XBRL_MISMATCH`, confidence is set to 0.0, and the record is routed to ESCALATE
  4. When no XBRL fact exists for a concept, the system falls back to the provenance base score (0.98 / 0.85 / 0.55) without error
**Plans**: TBD

### Phase 4: Semantic Validator
**Goal**: Layer-2 validation catches accounting identity violations, referential inconsistencies, and statistically implausible values
**Depends on**: Phase 3
**Requirements**: REQ-SEM-01, REQ-SEM-02, REQ-SEM-03, REQ-SEM-04
**Success Criteria** (what must be TRUE):
  1. Given a balance sheet where Assets != Liabilities + StockholdersEquity (after unit normalization), the validator returns `IDENTITY_VIOLATION` and the record is flagged for always-escalate
  2. Given a record where CIK does not match the company name known to SEC, the validator returns a `REFERENTIAL` reason code
  3. Given a revenue figure that is more than N standard deviations from that company's historical range (fetched from companyfacts), the validator returns `OUT_OF_RANGE`
  4. Given a record that passes both layers, `ValidationResult.is_valid` is True and `reason_codes` is empty
**Plans**: TBD

### Phase 5: Confidence Scoring, Routing & Always-Escalate Triggers
**Goal**: Every ExtractionResult receives a calibration-ready Decision with a derived confidence score, a routing tier, and a complete list of fired triggers
**Depends on**: Phase 4
**Note on CONSTRAINT-003**: Routing band cut points (HIGH/MEDIUM/LOW) MUST NOT be hard-coded in this phase. Phase 5 wires the routing logic and trigger predicates; actual threshold values are undefined until Phase 6 (shadow deployment) produces calibration data. Use placeholder/configurable values that can be swapped after Phase 6 completes.
**Requirements**: REQ-CR-01, REQ-CR-02, REQ-CR-03, REQ-CR-04, REQ-CR-05, REQ-CR-06
**Success Criteria** (what must be TRUE):
  1. Record-level confidence is computed as the minimum (or configured weighted aggregate) of per-field confidences derived from provenance scores and XBRL cross-check — no LLM self-report value appears anywhere in the computation
  2. All eight always-escalate predicates exist as pure functions; passing an `ExtractionResult` that satisfies any one of them returns ESCALATE regardless of the confidence score, and the trigger name appears in `Decision.triggers_fired`
  3. A record with no triggers fired and high confidence routes to AUTO; medium confidence routes to SAMPLED_REVIEW; low confidence routes to ESCALATE — using the configurable cut points
  4. Routing thresholds are stored in a config file or environment variable, not hard-coded, confirming they can be updated after Phase 6 calibration
**Plans**: TBD

### Phase 6: Shadow Deployment & Calibration
**Goal**: The full pipeline runs read-only over a batch of real historical filings and produces the calibration data needed to set production routing thresholds
**Depends on**: Phase 5
**Requirements**: REQ-SD-01, REQ-SD-02, REQ-SD-03
**Success Criteria** (what must be TRUE):
  1. The pipeline processes a batch of historical filings without triggering any downstream actions — every decision is logged only, no external writes or alerts fire
  2. The calibration run produces a distribution report: confidence score histogram per routing tier, escalation rate, agreement-rate proxy (where ground truth is available from XBRL)
  3. Based on the distribution report, explicit numeric values for the HIGH/MEDIUM/LOW cut points are chosen and written into the config (satisfying REQ-CR-04)
  4. The resulting AUTO-tier subset has an agreement rate (XBRL-backed validation vs. extraction) that meets or approaches the > 95% bar from CONSTRAINT-007, or the cut points are tightened until it does
**Plans**: TBD

### Phase 7: Metrics Dashboard
**Goal**: A developer-facing dashboard shows the current health of the pipeline — agreement rate, routing distribution, and escalation signals — so the AUTO tier can be certified for production use
**Depends on**: Phase 6
**Requirements**: REQ-MD-01, REQ-MD-02, REQ-MD-03
**Success Criteria** (what must be TRUE):
  1. The dashboard displays a rolling human-agreement rate for the AUTO tier that updates as new review decisions are logged
  2. The dashboard shows escalation rate, routing-tier distribution (count and %) and unrecognized-concept count in the current window
  3. When the agreement rate is below 95%, the dashboard shows a clear indicator that AUTO tier is not certified for production use
**Plans**: TBD
**UI hint**: yes

### Phase 8: Review Queue, Feedback Loop & Drift Alerts
**Goal**: The HITL loop is fully closed — human reviewers see queued decisions, their feedback recalibrates the scorer, and drift in extraction quality triggers alerts automatically
**Depends on**: Phase 7
**Requirements**: REQ-RQ-01, REQ-RQ-02, REQ-RQ-03, REQ-RQ-04, REQ-RQ-05, REQ-RQ-06
**Success Criteria** (what must be TRUE):
  1. SAMPLED_REVIEW and ESCALATE decisions appear in the review queue; a reviewer can record agree/disagree and that outcome is persisted
  2. After a batch of reviewer decisions is logged, the calibration pipeline can be re-run and updated cut points can be derived from the enriched dataset
  3. When the rolling agreement rate drops below the configured floor, a drift alert fires (log entry, notification, or equivalent) — no false silence
  4. When the unrecognized-concept count spikes above threshold, a separate drift alert fires indicating a potential new us-gaap taxonomy season
  5. Escalation-rate movement alone does not trigger any alert (no false alarm on expected workflow variation)
**Plans**: TBD
**UI hint**: yes

### Phase 9: LangGraph Auditable RAG
**Goal**: Deterministic LangGraph DAG retrieves SEC filing chunks, extracts XBRL facts via Polars, executes financial math, verifies against source, and routes to output or abstention
**Depends on**: Phase 1 (EvalPipeline dataclasses)
**Owner**: Claude (engine), MiMo (math), DeepSeek (review)
**Success Criteria** (what must be TRUE):
  1. Given a ticker and financial query, the DAG executes all 6 nodes (retrieval, extraction, math, verification, output/abstention) without error
  2. Financial calculators (gross/operating/net margin, FCF, ratios, EBITDA) produce correct numeric results from XBRL facts
  3. Accounting identity checks (balance sheet, gross profit, FCF) run automatically and appear in math_steps
  4. Failed verification routes to abstention node with explicit reasoning
**Files**: `api/services/langgraph_engine.py`, `api/services/financial_calc.py`, `api/services/sec_client.py`, `api/services/verifier.py`

### Phase 10: Knowledge Graph RAG Engine
**Goal**: LLM extracts 1-3 search entities from query, DuckDB `graph_triples` table is queried with ILIKE matching, and a second LLM call synthesizes the final answer from retrieved triples
**Depends on**: Nothing (standalone module)
**Owner**: MiMo (engine), DeepSeek (review)
**Success Criteria** (what must be TRUE):
  1. `EntitiesOutput` Pydantic model constrains LLM to return 1-3 entity strings
  2. DuckDB queries use parameterized `?` placeholders — no SQL injection
  3. `with_structured_output` produces typed entity list or empty on parse failure
  4. Empty entity extraction returns "no relevant knowledge graph data found" without error
**Files**: `api/services/graph_rag_engine.py`, `api/db/database.py`

### Phase 11: GraphRAG Frontend Integration
**Goal**: React UI exposes Graph RAG mode with engine toggle, ticker selector, entity badges, triple visualization (subject → predicate → object), and graph-specific suggested queries
**Depends on**: Phase 10
**Owner**: Claude
**Success Criteria** (what must be TRUE):
  1. Graph RAG button appears in engine toggle alongside SQL, Basic RAG, Auditable RAG
  2. Ticker selector visible for both Graph and Auditable modes
  3. Entities render as indigo badges; triples render as styled subject→predicate→object rows
  4. Frontend TypeScript compiles with 0 errors (`tsc -b && vite build`)
  5. Backend tests all pass (32 passed, 3 skipped)
**Files**: `frontend/src/App.tsx`, `frontend/src/api/chat.ts`, `api/routes/chat.py`

### Phase 12: Outstanding Integrations & Fixes
**Goal**: Complete all unexecuted requirements from Track A and Track B to achieve a true end-to-end working system.
**Depends on**: Phases 1-11
**Owner**: MiMo / DeepSeek
**Success Criteria** (what must be TRUE):
  1. Trigger 8 ("downstream action") is implemented via a context flag and added to `ALL_TRIGGERS`.
  2. `retrieval_node` in `langgraph_engine.py` uses proper vector/hybrid retrieval against DuckDB, replacing naive keyword search.
  3. A shadow deployment script (`scripts/run_shadow.py`) exists and has been executed over historical filings.
  4. Calibration endpoint has been run on shadow data to replace default `ROUTING_THRESHOLD` env vars with real derived cut points.
  5. RAGAS evaluation script (`evals/ragas_eval.py`) has been run against the live system and results stored.
**Files**: `api/services/confidence_scorer.py`, `api/services/langgraph_engine.py`, `scripts/run_shadow.py`, `evals/ragas_eval.py`

### Phase 13: Input & Dialog Rails
**Goal**: Protect the system from malicious inputs and maintain coherent, on-topic conversational state.
**Depends on**: Phase 12
**Requirements**: REQ-GR-01, REQ-GR-02
**Owner**: MiMo / DeepSeek
**Success Criteria** (what must be TRUE):
  1. Input rail blocks known prompt injection and jailbreak patterns before they reach the main LLM.
  2. Dialog rail detects off-topic queries (e.g., non-financial questions) and gracefully refuses to answer.
  3. Rails are implemented using a standard framework pattern (like NeMo Guardrails or equivalent LangGraph nodes).
**Files**: `api/services/guardrails/input_rails.py`, `api/services/guardrails/dialog_rails.py`

### Phase 14: Retrieval & Execution Rails
**Goal**: Ensure retrieved context is relevant and execution environments (math/SQL) operate within safe boundaries.
**Depends on**: Phase 13
**Requirements**: REQ-GR-03, REQ-GR-04
**Owner**: MiMo / DeepSeek
**Success Criteria** (what must be TRUE):
  1. Retrieval rail evaluates retrieved chunks against the query and drops irrelevant context before generation.
  2. Execution rail enforces read-only access for SQL mode and bounds math execution to prevent resource exhaustion or arbitrary code execution.
**Files**: `api/services/guardrails/retrieval_rails.py`, `api/services/guardrails/execution_rails.py`

### Phase 15: Output Rails
**Goal**: Prevent the system from emitting hallucinations, malformed data, or sensitive PII.
**Depends on**: Phase 14
**Requirements**: REQ-GR-05, REQ-GR-06
**Owner**: MiMo / DeepSeek
**Success Criteria** (what must be TRUE):
  1. Output rail performs a final check (e.g., SelfCheckGPT or entailment) to block ungrounded claims.
  2. Output rail ensures responses do not contain leaked system prompts or unauthorized PII.
**Files**: `api/services/guardrails/output_rails.py`

---

## Progress Table

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Data Structures & Reader Adapter | 2/2 | Completed | 2026-06-09 |
| 2. Schema Validator | 1/1 | Completed | 2026-06-09 |
| 3. XBRL Cross-Validation & companyfacts Client | 1/1 | Completed | 2026-06-09 |
| 4. Semantic Validator | 1/1 | Completed | 2026-06-09 |
| 5. Confidence Scoring, Routing & Triggers | 1/1 | Completed | 2026-06-09 |
| 6. Shadow Deployment & Calibration | 1/1 | Completed | 2026-06-09 |
| 7. Metrics Dashboard | 1/1 | Completed | 2026-06-09 |
| 8. Review Queue, Feedback Loop & Drift Alerts | 1/1 | Completed | 2026-06-09 |
| 9. LangGraph Auditable RAG | 1/1 | Completed | 2026-06-07 |
| 10. Knowledge Graph RAG Engine | 1/1 | Completed | 2026-06-07 |
| 11. GraphRAG Frontend Integration | 1/1 | Completed | 2026-06-09 |
| 12. Outstanding Integrations & Fixes | 0/5 | In Progress | — |
| 13. Input & Dialog Rails | 1/1 | Completed | 2026-06-09 |
| 14. Retrieval & Execution Rails | 1/1 | Completed | 2026-06-09 |
| 15. Output Rails | 1/1 | Completed | 2026-06-09 |

---

## Coverage

**Total requirements**: 35 (eval) + 6 (guardrails) = 41
**Mapped to phases**: 41/41

| Phase | Requirements / Artifacts |
|-------|-------------|
| 1 | REQ-DS-01, REQ-DS-02, REQ-DS-03, REQ-DS-04 |
| 2 | REQ-SV-01, REQ-SV-02, REQ-SV-03, REQ-SV-04 |
| 3 | REQ-XV-01, REQ-XV-02, REQ-XV-03, REQ-XV-04, REQ-XV-05 |
| 4 | REQ-SEM-01, REQ-SEM-02, REQ-SEM-03, REQ-SEM-04 |
| 5 | REQ-CR-01, REQ-CR-02, REQ-CR-03, REQ-CR-04, REQ-CR-05, REQ-CR-06 |
| 6 | REQ-SD-01, REQ-SD-02, REQ-SD-03 |
| 7 | REQ-MD-01, REQ-MD-02, REQ-MD-03 |
| 8 | REQ-RQ-01, REQ-RQ-02, REQ-RQ-03, REQ-RQ-04, REQ-RQ-05, REQ-RQ-06 |
| 9 | `api/services/langgraph_engine.py`, `api/services/financial_calc.py`, `api/services/verifier.py` |
| 10 | `api/services/graph_rag_engine.py`, `api/db/database.py` (graph_triples queries) |
| 11 | `api/routes/chat.py` (/graph-rag endpoint), `frontend/src/App.tsx`, `frontend/src/api/chat.ts` |
| 12 | Outstanding fixes for Phase 5, 6, 9 |
| 13 | REQ-GR-01, REQ-GR-02 |
| 14 | REQ-GR-03, REQ-GR-04 |
| 15 | REQ-GR-05, REQ-GR-06 |
