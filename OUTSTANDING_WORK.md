# Outstanding Work — Rag_workbench

## Status After `fix/audit-corrections` Branch

All 11 roadmap phases are marked "Completed" in ROADMAP.md, but several items remain **functionally incomplete or never executed**. The code is written but the system has never been run end-to-end.

---

## Category A: Must-Fix (Code Gaps)

| # | Item | Requirement | Current State | Work Needed |
|---|------|-------------|---------------|-------------|
| A1 | Trigger 8: "downstream action" | REQ-CR-06 | Not implemented — 0 references in confidence_scorer.py | Implement as a context flag (caller passes `is_downstream=True` when extraction feeds a user-facing figure); add to ALL_TRIGGERS |
| A2 | Retrieval node uses keyword search | Phase 9 success criteria | `retrieval_node` does naive keyword matching on `chunk_filing_sections` output — no vector similarity | Wire DuckDB VSS or embed-based retrieval from `rag_engine.py` into `langgraph_engine.py` |
| A3 | No DuckDB data (empty) | All RAG modes | `data/` dir is empty — no embeddings, no ticker data, no XBRL facts ingested | Run `main.py --job embed-edgar` or create a bootstrap script that populates the DB for at least 3-5 tickers |
| A4 | `graph_triples` table empty | Phase 10 | Table is created (BUG-10 fix) but never populated | Run `scripts/init_graph_triples.py` to load graphify-out data |
| A5 | Shadow run never executed | REQ-SD-01, REQ-SD-02, REQ-SD-03 | STATE.md says "Not run" | Create `scripts/run_shadow.py` CLI that fetches N historical filings, runs them through the eval pipeline, and produces a CalibrationReport |
| A6 | Routing thresholds still defaults | CONSTRAINT-003 | Env vars `ROUTING_THRESHOLD_HIGH=0.85`, `ROUTING_THRESHOLD_MEDIUM=0.55` are placeholders | After shadow run, invoke `/api/review/calibrate` to derive real thresholds |

---

## Category B: Integration & Polish

| # | Item | Requirement | Current State | Work Needed |
|---|------|-------------|---------------|-------------|
| B1 | RAGAS eval never run against live system | Eval quality | `evals/ragas_eval.py` exists with golden_set.csv (9 questions) but no results file | Run eval, store results, add to CI or README |
| B2 | STATE.md outdated | Project hygiene | Still says "Phase 1" and all metrics "Not measured" | Update to reflect actual state |
| B3 | REQUIREMENTS.md traceability all "Pending" | Project hygiene | All 35 requirements listed as "Pending" despite code existing | Update status column |
| B4 | No end-to-end integration test | Test coverage | Unit tests pass but no test exercises the full LangGraph DAG | Add `tests/test_integration.py` with a mocked SEC API call |
| B5 | MetricsDashboard not connected to real data | REQ-MD-01/02/03 | Dashboard renders but `/api/review/metrics` returns zeros because no decisions exist in DB | Seed review_queue with shadow run output |
| B6 | Hand-labeling dataset for narrative fields | REQ-RQ-06 | No annotation file exists | Create `evals/narrative_labels.csv` with 50-100 edge-case records (can be seeded from golden_set) |

---

## Category C: Nice-to-Have / Future

| # | Item | Notes |
|---|------|-------|
| C1 | Docker build & HF Spaces deploy test | Dockerfile exists but never built/tested in this session |
| C2 | CI/CD pipeline (GitHub Actions) | No `.github/workflows/` directory |
| C3 | README update with setup instructions | Current README may be outdated |
| C4 | Multi-ticker shadow run with real SEC data | Requires network access to SEC EDGAR API |

---

## Recommended Implementation Order

1. **A3** — Bootstrap DuckDB with XBRL data for semiconductor tickers (NVDA, AMD, QCOM)
2. **A4** — Populate graph_triples from graphify-out
3. **A2** — Wire vector/hybrid retrieval into langgraph_engine
4. **A1** — Implement trigger 8 (downstream action context flag)
5. **A5** — Create and run shadow deployment script
6. **A6** — Run calibration to derive real thresholds
7. **B1** — Run RAGAS eval and store results
8. **B4** — Add integration test
9. **B2/B3** — Update planning docs
10. **B5/B6** — Seed dashboard data and narrative labels
