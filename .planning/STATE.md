# STATE.md
<!-- SEC Filing Eval & HITL Framework — project memory -->
<!-- Updated by Claude at the end of each work session. -->

Last updated: 2026-06-15

---

## Project Reference

**Project**: SEC Filing Eval & HITL Framework
**Core value**: Provenance-derived confidence scoring + risk-tiered routing that makes it safe to trust automated SEC filing extractions. Autonomy is an evaluation problem.
**Runtime**: Python
**Success metric**: Human-agreement rate > 95% on the AUTO tier (CONSTRAINT-007)
**Reader constraint**: EdgarTools only — no custom parser (CONSTRAINT-009)

---

## Current Position

**Current phase**: Phases 1–11 complete and **deployed to production** (HF Space
`egoh33/Auditable-Filing-QA`, serving `www.evangoh.com`). Roadmap phases 12–15
(guardrail rails / outstanding integrations) remain; Phase 16 (UAT Feedback) is
in **Discussion**.

**Status**: Live. Since the roadmap was last marked, additional product work has
shipped on top of Phase 11:
- Revenue growth-rate metric fix (YoY + CAGR) and conversation memory on the
  auditable-RAG path.
- Dedicated **Knowledge Graph** nav tab (`/api/graph/triples`).
- Competitor/peer grounding guardrail (prompt-level) — restricts named
  competitors to filing context.
- **Eval persistence**: `eval_runs` / `eval_results` tables + `run_eval.py`
  writes each golden-set run to DuckDB.
- **Runtime durability (in progress)**: the Space has no persistent volume, so
  the review/runtime DB (audit_runs, HITL decisions, calibration, eval_*) is now
  persisted as a DuckDB container to the **private HF dataset `egoh33/app_data`**,
  extracted+saved **daily by a CI/CD cron** (`.github/workflows/snapshot.yml` →
  `POST /api/admin/snapshot`) and restored on boot.

```
Progress: [●●●●●●●○○○] 11/15 roadmap phases complete (+ Phase 16 in discussion)
```

**Open questions blocking start**: None for shipped work. The runtime-snapshot
feature is awaiting a Space secret (see Blockers).

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
- **ADR-004 (2026-06-15)**: Persist runtime/review data (audit, HITL, calibration,
  eval_*) to the **private HF dataset `egoh33/app_data`** as a single DuckDB
  container, NOT to HF Space persistent storage. Rationale: the Space is
  `cpu-basic` with `storage: None`, and the account is HF Pro but `canPay: false`
  (Pro does not include Space storage). The container is rebuilt from a Parquet
  export so it's written in the runtime's own DuckDB format (sidesteps the
  1.0↔1.5 storage-format mismatch). Daily extract via CI/CD cron; restore on boot.
  Uses a dedicated write token secret **`APP_DATA_HF_TOKEN`** (falls back to
  `HF_TOKEN`).

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
- **Runtime snapshot needs a Space secret**: set **`APP_DATA_HF_TOKEN`** on the
  Space (`egoh33/Auditable-Filing-QA`) to an HF token with **write** access to
  `egoh33/app_data`. Until then, the daily extract / boot-restore no-op (the app
  runs fine, but runtime data stays ephemeral). User is provisioning this token.

---

## Session Continuity

### Last Session Summary
2026-06-15: Shipped runtime-durability work. Created `eval_runs`/`eval_results`
tables + `persist_eval_run()` (`api/db/review_queue.py`) and wired `run_eval.py`
to persist each golden-set run. Built `api/services/runtime_snapshot.py`
(extract review DB → DuckDB container → `egoh33/app_data`; restore on boot),
`POST /api/admin/snapshot` (`api/routes/admin.py`), `scripts/restore_review_db.py`
+ Dockerfile boot step, and `.github/workflows/snapshot.yml` (daily cron). Verified
the live Space recovered from a 502 after deploy (`main_connected: true`, model
Qwen3-Embedding-0.6B, 14 companies, 979 graph triples). Backed up the live corpus
locally before any changes. Cleaned up two interim datasets (deleted
`egoh33/rag-workbench-runtime`; removed misplaced `runtime/` parquet from the
public `egoh33/Rag-workbench`).

### Next Session Start Point
1. **Set `APP_DATA_HF_TOKEN`** on the Space, then trigger the snapshot workflow
   (manual `workflow_dispatch`) to confirm the daily extract writes
   `review_queue.duckdb` to `egoh33/app_data`, and confirm boot-restore repopulates.
2. Commit + deploy the latest `runtime_snapshot.py` (app_data + container) and
   `main.py` (shutdown-only snapshot) changes — currently edited/tested locally,
   on branch `feat/runtime-snapshot-persistence`, not yet committed.
3. Outstanding corpus merge (option A): fold ADI/INTC/KLAC stub fixes + ON/STM
   into production — planned, not started.
4. Roadmap phases 12–15 (guardrail rails); Phase 16 (UAT) discussion.

### Handoff Notes
- **Deploy = `git push origin <branch>:main`** → rebuilds the live HF Space.
  `claude-change-it` is identical to `origin/main`; the working branch is
  `feat/runtime-snapshot-persistence`.
- The `embed-data` verify step in `deploy.yml` is **flaky** (`bash -e` kills the
  retry loop on the first empty `/api/stats` poll while the model warms), so the
  deploy job often shows "failure" even when the Space ends up healthy — verify
  the Space directly via `/api/stats` rather than trusting the job status.
- Build any DB destined for the Space with DuckDB 1.0.0 (`.venv_duck10`) — the
  Space can't read the 1.5.x format (CONSTRAINT: storage-format mismatch).
- `egoh33/Rag-workbench` (corpus) is **public**; `egoh33/app_data` (runtime) is
  **private**.
