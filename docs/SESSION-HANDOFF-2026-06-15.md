# Session Handoff — 2026-06-15

Handoff so work can resume on another machine. Covers what shipped this session,
what's deployed, known gaps, and how to verify/continue.

## TL;DR

This session shipped (all committed on branch `claude-change-it`, pushed to
`origin/main` → deploys to the HF Space):

1. **Revenue growth-rate fix** — "revenue growth rate over the same period" no
   longer returns the latest revenue level.
2. **Conversation memory** — the chat now remembers previous turns on the main
   (auditable-rag) path.
3. **Knowledge Graph tab** — a dedicated nav tab to browse the whole graph
   (was previously only reachable by clicking a triple inside an answer).

Earlier in the session (already live): peer/competitor comparison, graph
analytics panel + endpoint, UAT notice, recharts charting tool.

## Deploy / ops model (read before pushing)

- **Local `:8000` server serves live `www.evangoh.com`** via proxy. **Do NOT
  stop it.** It holds the local DuckDB write-lock, so a separate local process
  that opens the DB read-write will fail — that's expected.
- **Deploy = push to `origin/main`** → GitHub Actions (`deploy.yml`): sync
  secrets → push to HF Space → await-space → embed-data verify `/api/stats` →
  rag-pipeline. The current working branch is `claude-change-it`; deploy with
  `git push origin claude-change-it:main`.
- During deploy the Space ETL grabs the Space DB write-lock and can transiently
  504 the Space API; it recovers. See memory `ops-duckdb-lock-and-deploy`.
- **DuckDB storage-format trap**: local DuckDB 1.5.3 writes a format the Space
  (`duckdb>=0.10.0,<1.1.0` ≈ 1.0.0) cannot read → `main_connected: false`.
  Build any DB destined for the Space with DuckDB 1.0.0 on Python 3.12
  (`.venv_duck10`). See memory `ops-duckdb-storage-format-mismatch`.

## What shipped this session — details

### 1. Revenue growth-rate metric (commit `459f0aa`)
- **Bug**: numeric path `math_node` (`api/services/langgraph_engine.py`) had no
  revenue-growth route, so "revenue growth rate…" fell through to the bare
  `"revenue"` keyword branch and returned the latest level.
- **Fix**: added a dedicated route *before* the plain-revenue branch that
  computes **YoY growth + full-period CAGR** from a clean annual series
  (reuses `chart_tool._annual_series` + `_REVENUE_CONCEPTS`, so multi-year "over
  the same period" questions get real annual data, not quarterly noise).
  Uses `financial_calc.yoy_growth` and `financial_calc.cagr`.

### 2. Conversation memory (commit `459f0aa`)
- **Bug**: the app's main path `sendAuditableRagMessage` posted only
  `{message, ticker}`; `run_auditable_rag` ignored history → follow-ups had no
  context beyond the persisted ticker.
- **Fix (end-to-end)**:
  - `frontend/src/App.tsx` passes `history` to `sendAuditableRagMessage`.
  - `frontend/src/api/chat.ts` sends `history` in the POST body.
  - `api/routes/chat.py` → `run_auditable_rag(req.message, req.ticker, history=req.history)`.
  - `langgraph_engine.py`: `GraphState` gains `history`; `run_auditable_rag`
    accepts it; `qualitative_output_node` injects the last 6 user/assistant
    turns before the grounded context message.
- Numeric `output_node` is template-based (no LLM), so it doesn't need history;
  numeric answers are deterministic per resolved ticker.

### 3. Knowledge Graph tab (commit `1a097d1`)
- **New endpoint** `GET /api/graph/triples?ticker=&limit=` (`api/routes/graph.py`)
  — returns triples, optional per-company, capped (default 300), ordered by
  confidence.
- **Frontend**: `getGraphTriples()` (`frontend/src/api/graph.ts`);
  new `GraphExplorer.tsx` (company filter, force graph + analytics overlay via
  the existing `KnowledgeGraph` component, and a click-to-source evidence side
  panel using `getGraphEvidence`); wired as `AppView 'graph'` with a nav button
  (`Network` icon) in `App.tsx`.

## ⚠️ Open grounding concern — competitor taxonomy "not from the sources"

The detailed NVIDIA competitor taxonomy (AMD/Intel/Qualcomm **plus** AWS
Trainium, Google TPU, Microsoft Maia, Meta MTIA, Cerebras, Groq, SambaNova) is
**NOT filing-grounded**. Our auditable competitor data comes from only two
places (`api/services/peer_comparison.py`):

1. **Filing-derived** `COMPETES_WITH` triples in `graph_triples`
   (`_graph_competitors`) — auditable.
2. **Curated** `_PEER_GROUPS` — a hardcoded **semiconductor** peer list
   (AMD, INTC, QCOM, AVGO, MRVL, TXN, ADI, MCHP, MU, AMAT, LRCX, KLAC).

Hyperscalers and AI startups are in **neither**, and they're not covered tickers
(no XBRL), so they can't be compared numerically. If that taxonomy appeared in a
product answer, it came from the LLM's general knowledge, not the filings —
which violates the auditability promise.

**Decision needed next session**: either (a) add a guardrail so competitor
answers only cite filing-named / curated peers and clearly label any
general-knowledge names as "not from filings", or (b) deliberately ingest those
entities as graph nodes (labelled non-XBRL) if we want them shown.

> **RESOLVED (2026-06-15, commit `8bcea97`)** via option (a). The
> `qualitative_output_node` system prompt (`api/services/langgraph_engine.py`)
> now restricts competitor/peer/company names to those present in the retrieved
> filing context and tells the model to say the filings don't enumerate specific
> competitors rather than filling the gap from general knowledge. Covered by
> `TestQualitativeGrounding`. **Caveat**: this is a prompt-level (non-deterministic)
> guard, not a post-hoc NER filter — if leakage recurs, escalate to a hard
> post-processing check or option (b).

> **Memory cross-ref**: this concern is also saved as the local Claude memory
> `competitor-grounding-gap.md` (in `~/.claude/.../memory/`, this machine only —
> it does not travel with the repo, so this section is the cross-machine record).
> Related memories: `evidence-graph-feature-brief`, `product-philosophy-answer-framework`.

## Known data gaps (pre-existing)
- **ADI / INTC / KLAC** are 1-chunk stubs with incomplete XBRL → `n/a` in some
  peer comparisons and charts. Fix = the deferred re-ingest (blocked while the
  local DB is locked by the live server).
- Some peers (AMD, INTC, AVGO) lack a current revenue XBRL tag → `n/a` in
  numeric comparisons. `peer_comparison` has a Rev=GP+COGS identity fallback
  that recovers a few cases (e.g. TXN gross margin).

## How to verify (after a deploy completes)
- Space health: `GET /api/stats` → `main_connected: true`.
- Growth fix: ask "What was NVIDIA's revenue growth rate over the same period?"
  → expect a YoY% + CAGR, not a single latest-revenue figure.
- Memory: ask an NVDA question, then a follow-up like "what about its net
  income?" → should stay on NVDA with prior context.
- Graph tab: open **Knowledge Graph** in the nav → graph renders; company
  filter works; clicking an edge/node shows the source excerpt + EDGAR link.
- Graph triples API: `GET /api/graph/triples?ticker=NVDA&limit=50`.

## Test status
- `pytest tests/test_langgraph_engine.py tests/test_peer_comparison.py
  tests/test_xbrl_relevance.py` → 54 passed, **1 pre-existing failure**
  (`test_eval_node` patches `score_and_route`, a lazy in-function import that is
  never a module attribute — predates this session, unrelated).
- Frontend `tsc --noEmit` clean; `npm run build` clean.
- The new `math_node` revenue-growth route and `/graph/triples` read the DB, so
  they were **not** unit-tested locally (live server holds the DB lock) — verify
  against the Space after deploy.

## Key files touched this session
- `api/services/langgraph_engine.py` — growth route, history threading, GraphState.
- `api/routes/chat.py` — pass history to `run_auditable_rag`.
- `api/routes/graph.py` — new `/triples` endpoint.
- `frontend/src/App.tsx` — history pass-through, graph nav tab + view.
- `frontend/src/api/chat.ts` — history in auditable-rag POST.
- `frontend/src/api/graph.ts` — `getGraphTriples`.
- `frontend/src/components/GraphExplorer.tsx` — new graph tab (created).

## Branch / commits
Branch `claude-change-it` (pushed to `origin/claude-change-it` and to
`origin/main` for deploy). This session's commits:
- `459f0aa` fix(qa): revenue growth-rate metric + conversation memory
- `1a097d1` feat(graph): dedicated Knowledge Graph tab
