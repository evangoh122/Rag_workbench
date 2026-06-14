# Implementation Plan: Product Philosophy + Evidence Graph

> Status: **proposed (no code yet)** — awaiting go-ahead. Authored 2026-06-14.
> Sources: "Product Philosophy" brief (3-layer answer framework) + "Evidence Graph for Auditable Filing-QA" feature brief.

## Gap analysis (grounded in current code)

### Product Philosophy — 3-layer answer framework
| Requirement | Status |
|---|---|
| **Layer 1**: direct answer + citations + XBRL verification | ✅ Exists (auditable RAG, citation chips, XBRL badge) |
| **Layer 2**: "What This Means" (plain-English translation) | ❌ Not in any prompt |
| **Layer 3**: "Suggested follow-up questions" | ❌ Not in any prompt |
| "How to Interpret This" info bubbles (revenue, margin, risk…) | ❌ Not implemented |
| Limitations disclosure | 🟡 Partial (abstention exists; no explicit "filings ≠ investment advice" reminder) |

### Evidence Graph brief
| Requirement | Status |
|---|---|
| "Show Evidence Graph" per answer → React Flow modal (zoom/pan) | ✅ Exists (`data.triples` → `KnowledgeGraph.tsx`) |
| DuckDB storage, no graph DB | ✅ `graph_triples` table w/ `source_file`/`source_loc`/`confidence` |
| **Click edge/node → source text** (the brief's core auditability rule) | ❌ `KnowledgeGraph.tsx` renders labels only; source refs never reach the UI |
| Typed nodes (Company/Segment/Risk/Executive/Metric/XBRL) | 🟡 Generic subject/predicate/object, untyped |
| Filing-derived triples | ❌ Table currently holds **code-graph** triples (`main.py L47`), `ticker=''` — not filing entities |

**Bottom line:** the scaffolding (graph modal, citations, XBRL, audit schema) is built; the substance both briefs are about is missing — (a) the educational answer layers, and (b) graph auditability (click→evidence) backed by actual filing-derived triples.

---

## Sequencing rationale
Phase A is self-contained and the highest user-facing impact. Phase B (real triples) is the foundation the graph needs — auditability (Phase C) is meaningless until the graph holds real filing-derived triples with source refs. So **A → B → C**.

## Phase A — Standard Response Framework *(independent, highest impact, ~M)*
**Goal:** every auditable-RAG answer is rendered in the canonical 5-section structure, educating the user rather than just answering.

### Canonical sections (per the "Standard Response Framework" spec)
| # | Section | Current state |
|---|---|---|
| 1 | **Direct Answer** — concise answer | ✅ Exists |
| 2 | **Source / Citation** — filing type, date, section, supporting excerpt, XBRL status | 🟡 Citations exist; need to surface filing type/date/section + excerpt in this labeled block |
| 3 | **What This Means** — plain-English translation | ❌ New (prompt field) |
| 4 | **How to Interpret This** — educational context, assume no finance background | ❌ New (prompt field + reusable metric explainers) |
| 5 | **Suggested Follow-Up Questions** | ❌ New (prompt field → clickable chips) |

### Optional components
| Component | Current state |
|---|---|
| **XBRL Verification Badge** — "✓ Verified against XBRL" vs "⚠ Derived from filing text only" | ✅ **Already built** — this is exactly the `xbrl_badge` / text-grounded decoration from the SpaceX text-grounded work in `langgraph_engine.py`. Just needs the two-state label wired into the new layout. |
| **Evidence Graph** | 🟡 Modal exists (Phase C makes it auditable) |
| **Trend Chart** — time series when numeric data spans periods | 🟡 `FinancialChart.tsx` + recharts exist; trigger when XBRL has multi-period values |

### Changes
| Area | Change |
|---|---|
| `api/services/langgraph_engine.py` | Extend answer prompt to emit structured `{answer, source{filing_type,filing_date,section,excerpt,xbrl_status}, what_it_means, how_to_interpret, follow_ups[]}`. Reuse existing `xbrl_badge` for `xbrl_status`. |
| Response schema / `api/routes` | Add the new fields to the chat response model (keep `answer` for back-compat). |
| Frontend `App.tsx` chat bubble | Render the 5 labeled sections; follow-ups as clickable chips (click re-asks); "How to Interpret This" collapsible `ⓘ`. |
| Guardrails | Standing limitations footer ("filings ≠ investment advice/valuation/market sentiment") — reuse abstention infra. |

**Design principle (from spec):** never stop at answering — help the user understand the answer, why it matters, how to think about it, and what to investigate next. Success = user understanding, not answer generation.

**Risk:** must NOT weaken auditability — sections 3–5 are clearly separated from the cited section 1–2, and explanation text is labeled "educational, not from the filing".

### Phase A — Code-grounded implementation detail

**Current data path (verified):**
- `api/services/langgraph_engine.py::run_auditable_rag(query, ticker)` (L1494) → `app.invoke(inputs)` returns the full `GraphState` dict.
- Answer is produced by `qualitative_output_node` (L1024) or the numeric `output_node` (~L685); both set `final_answer`, `verification_status`, `verification_reasoning`, `math_steps`, and (where relevant) `xbrl_badge`, `relevant_xbrl`, `xbrl_group`.
- `api/routes/chat.py` (L197) calls `run_auditable_rag`, applies output rails (L198), dedupes XBRL facts, maps `retrieved_docs`→`SourceItem`, and returns `ChatResponse` (L248).
- `api/models/schemas.py::ChatResponse` (L41) is the response model. `frontend/src/api/chat.ts::ChatResponse` (L38) is the TS mirror; `frontend/src/App.tsx` renders the chat bubble (`Message` type, `triples`/`sources`/`xbrl_badge` already rendered).
- Refusal/abstention detection already exists: `_REFUSAL_MARKERS` (L951); `abstention_node` returns a fixed "cannot answer" string.

**Design: additive post-answer "educational layers" (does NOT touch the audited answer).**
Keep section 1 (answer) and section 2 (sources/citation/XBRL badge) exactly as generated today — preserves citations, verification, abstention. Generate sections 3–5 in a **separate, best-effort LLM call** that receives the *already-produced* answer and is explicitly forbidden from introducing new facts/numbers. This matches the brief's "educational, not from the filing" separation.

**New function** `_generate_educational_layers(query: str, answer: str, ticker: str) -> dict` in `langgraph_engine.py` (or new `api/services/answer_framework.py`):
- Returns `{"what_it_means": str, "how_to_interpret": str, "follow_ups": list[str]}`; `{}`-safe on any failure.
- Uses `Config.get_provider_config()` + `OpenAI` client (same as `qualitative_output_node`), short `timeout`, low `max_tokens`.
- Prompt rules: plain English, assume no finance/accounting background; **do not state any number or fact not already in the provided answer**; "What This Means" = translate; "How to Interpret This" = generic educational context for the metric/topic; 3–4 concrete follow-up questions. Request strict JSON; parse with try/except → `{}` on error.
- **Guard:** return `{}` immediately if `answer` is empty or `any(m in answer.lower() for m in _REFUSAL_MARKERS)` (no point explaining an abstention).
- **Best-effort:** entire body wrapped so a failure never affects the answer. Gate behind `Config.ANSWER_FRAMEWORK_ENABLED` (new, default `True`) for instant disable.

**Wiring:** in `run_auditable_rag`, after `result = app.invoke(inputs)`:
```python
ans = result.get("final_answer", "")
layers = _generate_educational_layers(query, ans, ticker)  # {} on guard/fail
result["what_it_means"]    = layers.get("what_it_means", "")
result["how_to_interpret"] = layers.get("how_to_interpret", "")
result["follow_ups"]       = layers.get("follow_ups", [])
return result
```
(Single chokepoint; graph nodes untouched. The audit-log writer is unaffected — these are display-only fields.)

**Schema** (`api/models/schemas.py::ChatResponse`): add
```python
what_it_means: str = ""
how_to_interpret: str = ""
follow_ups: List[str] = Field(default_factory=list)
```
**Route** (`api/routes/chat.py`, the `ChatResponse(...)` at L248): pass
`what_it_means=result.get("what_it_means",""), how_to_interpret=result.get("how_to_interpret",""), follow_ups=result.get("follow_ups",[])`.

**Frontend:**
- `frontend/src/api/chat.ts::ChatResponse`: add the 3 optional fields; thread into `App.tsx` `Message` type.
- `App.tsx` chat bubble — render the 5 labeled sections in order:
  1. **Answer** (existing `answer`/markdown).
  2. **Source / Citation** — relabel existing sources block; show filing/section/excerpt + the XBRL badge.
  3. **What This Means** — muted card, only if `what_it_means`.
  4. **How to Interpret This** — collapsible `ⓘ`, only if `how_to_interpret`.
  5. **Suggested Follow-Up Questions** — `follow_ups` as clickable chips that set the input + send (reuse existing send handler; emit a PostHog `follow_up_click`).
- **XBRL badge two-state** (spec §"XBRL Verification Badge"): render `✓ Verified against XBRL` when `xbrl_badge` denotes XBRL coverage; render `⚠ Derived from filing text only` when `xbrl_badge === "From filing text • not XBRL-verified"` (the existing text-grounded badge). Pure presentational mapping.
- **Limitations footer:** static one-liner under section 5 ("SEC filings don't provide investment advice, valuation, or market sentiment — combine with other sources"). Reuse/extend existing disclaimer rendering.

**Trend Chart (optional component):** `FinancialChart.tsx` already renders recharts from XBRL. Trigger it when `relevant_xbrl`/`xbrl_facts` contain ≥2 periods for the queried concept (comparison intent already detected in `classifier_node`). No new data needed — gate the existing chart on multi-period presence.

**Perf/risk:** +1 LLM call per answer (best-effort, disableable). No new facts (prompt-constrained + visually separated from cited answer). Abstention path skips layers. Back-compat: all new fields default empty, so older frontend ignores them.

**Tests:** extend `tests/` — assert `run_auditable_rag` populates the 3 fields on a normal answer and leaves them empty on an abstention/refusal; assert `_generate_educational_layers` returns `{}` for a refusal string and parses valid JSON otherwise (mock the client).

## Phase B — Real Filing-Derived Triples *(foundation, ~L)*
> Status: **code-complete (2026-06-14)** — `scripts/extract_graph_triples.py` + schema migration + tests landed. The extraction *run* is deferred until the embed ETL finishes (single-writer DuckDB + cost), then triples ship in the dataset rebuild.

**Goal:** replace the code-graph triples with Company/Segment/Risk/Executive/Metric/XBRL triples extracted from filings, each carrying source refs.

**As built:**
- `scripts/extract_graph_triples.py::run_extract_graph_triples(tickers, db_path=, client=, model=)` — reads narrative chunks from `edgar_embeddings` (skips `content_type='table'`, longest-first, capped `MAX_CHUNKS_PER_FILING`), LLM-extracts strict-JSON typed triples, validates against `NODE_TYPES` (Company/Segment/Risk/Executive/Metric/XBRL/Product/Geography), normalises predicates to `UPPER_SNAKE`, floors at `MIN_CONFIDENCE` (0.5), caps `MAX_TRIPLES_PER_CHUNK` (8). Best-effort per chunk (failure → 0 triples, never raises). Knobs via env (`GRAPH_MIN_CONFIDENCE`, `GRAPH_MAX_TRIPLES_PER_CHUNK`, `GRAPH_MAX_CHUNKS_PER_FILING`).
- **Idempotent:** `triple_id = sha1(ticker, subject, predicate, object, chunk_id)` (case-insensitive) + `INSERT OR IGNORE` → re-runs are no-ops.
- **chunk_id** = `f"{ticker}:{accession}:{chunk_index}"` (stable; Phase C's evidence route parses it back, since `edgar_embeddings` has no surrogate key). Stored alongside `source_file` (accession) and `source_loc` (section_id).
- **XBRL linking:** `link_xbrl_metrics()` adds `Metric -VERIFIED_BY-> XBRL` edges by matching extracted Metric labels to `xbrl_facts.concept` (alphanumeric-stem substring), confidence 1.0.
- **Schema:** `subject_type`/`object_type`/`chunk_id` added to `graph_triples` via idempotent `ALTER ... IF NOT EXISTS` — both in the script's `ensure_schema()` and in `api/db/database.py` (so the running app/Phase C see the columns on existing DBs).
- **CLI:** `python -m scripts.extract_graph_triples --tickers NVDA,MU` or `EXTRACT_TICKERS=...`.
- **Tests:** `tests/test_extract_graph_triples.py` (18 passing) — helpers, vocab gate, confidence floor, cap, fence tolerance, idempotency, XBRL linking, end-to-end orchestrator with mocked client.

**Still to wire (carried into Phase C / dataset run):** retrieval-side filtering of triples by ticker + cited chunks (so the graph reflects *this* answer's evidence).

| Area | Change |
|---|---|
| New `scripts/extract_graph_triples.py` (or extend `api/services/graph_rag_engine.py`) | During/after ingestion, LLM-extract `(subject, predicate, object, node_types, source_file, source_loc, chunk_id, confidence)` per chunk. Constrain to the brief's node/edge vocabulary. |
| `graph_triples` table | Already has `source_file`/`source_loc`/`confidence`. Add `subject_type`/`object_type`/`chunk_id` columns. Populate per-ticker (fix `ticker=''`). |
| Link XBRL | Add `Metric →VERIFIED_BY→ XBRL Fact` edges by joining extracted metrics to `xbrl_facts`. |
| Retrieval | `graph_rag_engine` returns the answer's triples filtered by ticker + cited chunks (so the graph reflects *this* answer's evidence). |

**Risk:** LLM extraction cost/noise → cap per filing, dedupe, confidence-threshold.

## Phase C — Evidence-Graph Auditability *(depends on B, ~M)*
**Goal:** click an edge/node → see the source text; type the nodes.

| Area | Change |
|---|---|
| Chat response triples | Plumb `source_file`/`source_loc`/`chunk_id`/`types` through to `data.triples` (currently dropped). |
| `KnowledgeGraph.tsx` | Color/icon nodes by type; add `onClick` on edges/nodes → side panel showing source excerpt (fetch chunk text by `chunk_id`), filing, section. |
| New route `GET /api/graph/evidence?chunk_id=` | Returns the chunk's source text + filing metadata for the panel. |

**Risk:** low — mostly wiring existing data to UI.

---

## Effort summary
A (~M) → B (~L) → C (~M). A delivers visible value immediately; B+C together realize the auditable Evidence Graph.

## Relevant files
- `api/services/langgraph_engine.py` — answer nodes / `run_auditable_rag`
- `api/services/chat_engine.py` — prompts
- `api/services/graph_rag_engine.py`, `scripts/init_graph_triples.py` — graph construction
- `frontend/src/components/KnowledgeGraph.tsx` — React Flow render
- `frontend/src/App.tsx` — `graphModalOpen` / `activeTriples`, chat bubble
- `graph_triples` DuckDB table — `id, ticker, subject, predicate, object, confidence, source_file, source_loc`
