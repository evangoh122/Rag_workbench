---
title: Auditable Filing QA
emoji: 💹
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# RAG Workbench — Auditable Filing QA

A financial Q&A system over SEC filings where **every claim traces to source and every number is verified against XBRL** — auditable, not just intelligent.

Built for AI/data roles in banking and financial services. The point: demonstrate you think like the team building compliance-grade AI, not just a demo that looks impressive and produces confidently wrong answers.

---

## The thesis

Most RAG systems retrieve context and trust the LLM to do the rest. This system splits the work along trust lines:

- **AI retrieves and explains.** A LangGraph pipeline finds the right SEC filing chunks and XBRL-tagged facts, then writes the prose.
- **Python calculates.** `financial_calc.py` does all arithmetic — the LLM is never asked to do math.
- **XBRL verifies.** Every numeric answer is cross-checked against the SEC EDGAR companyfacts API before it's returned, with an independent NLI model checking that the prose is entailed by the sources.
- **The pipeline can abstain.** If verification fails or no GAAP-equivalent fact exists, the system declines rather than guesses.
- **The audit trail is the product.** Each answer shows retrieved chunks with EDGAR links, the XBRL fact behind each number, the formula used, a green/red verification badge, and full lineage.

---

## Architecture

Single Docker container (Nginx + Uvicorn + Supervisor), deployed to Hugging Face Spaces.

```
Browser
  │
  └── Nginx (port 7860)
        ├── /* ──────────────────── React + Vite + Tailwind (static build)
        └── /api/* ──────────────── FastAPI (port 8000)
```

The flagship answer path is the **auditable RAG** LangGraph DAG (`POST /api/chat/auditable-rag`):

```
                          retrieval (dense + BM25 + rerank)
                                   │
                              classifier ── numeric vs qualitative?
                          ┌────────┴─────────────┐
               numeric    │                      │   qualitative
                          ▼                      ▼
                     extraction            qualitative_output
                  (SEC companyfacts)      (LLM over retrieved docs)
                          │                      │
                       eval (validation layer)   │
                          │                      │
                        math (financial_calc.py) │
                          │                      │
                     verification                │
                  (numeric XBRL + NLI entailment)│
                   ┌──────┴──────┐               │
                   ▼             ▼               │
                output       abstention          │
                   └──────┬──────┴───────────────┘
                          ▼
                    build_lineage
                          │
                          ▼
   { answer, sources, xbrl_facts, relevant_xbrl, verification badge,
     math_steps, what_it_means, follow_ups, confidence, lineage, chart }
```

Every request additionally passes through **guardrails** — input rails (injection / safety), dialog rails (on-topic enforcement) before the pipeline, and output rails (PII masking) on the response.

Alternative answer paths share the same retrieval and audit layer:
- **`/api/chat/graph-rag`** — knowledge-graph retrieval over extracted filing triples.
- **`/api/chat/rag`** — plain hybrid RAG (no math/verify spine).
- **`/api/chat/sql`** — natural language → DuckDB query.

---

## Key components

### Backend — `api/`

**Orchestration & retrieval**

| File | What it does |
|---|---|
| `services/langgraph_engine.py` | The auditable DAG: retrieval → classifier → extraction → eval → math → verification → output/abstain → lineage |
| `services/graph_rag_engine.py` | Graph RAG: entity search + triple extraction over the knowledge graph |
| `services/rag_engine.py` | Hybrid retrieval: dense embeddings + BM25, RRF merge |
| `services/hybrid_retriever.py` | Dense + sparse fusion retriever |
| `services/reranker.py` | CrossEncoder reranking of retrieved chunks (`ms-marco-MiniLM-L-6-v2`) |
| `services/metric_router.py` | Routes a question to the right metric / calculator |
| `services/chat_engine.py` | SQL mode — natural language to DuckDB queries |
| `services/embeddings.py` | Embedding provider abstraction (local sentence-transformers default) |

**Calculation & verification spine**

| File | What it does |
|---|---|
| `services/financial_calc.py` | All financial arithmetic (margins, FCF, CAGR, ratios, accounting-identity checks) — the LLM never does math |
| `services/xbrl_client.py` | SEC EDGAR companyfacts API client — rate-limited (≤10 req/s), LRU-cached |
| `services/sec_client.py` | EdgarTools + Polars XBRL extraction, LRU-cached per ticker |
| `services/edgar_adapter.py` | Wraps EdgarTools output into the canonical `ExtractionResult` type contract |
| `services/verification.py` | Numeric claim extraction + XBRL cross-check (1% tolerance) |
| `services/verifier.py` | NLI CrossEncoder entailment check — independent model from the generator |
| `services/xbrl_cross_validator.py` | Cross-validates extracted facts across filings/frames |
| `services/polygon_verifier.py` | Optional market-data cross-check via Polygon |
| `services/confidence_scorer.py` | Per-answer confidence scoring feeding the routing decision |
| `services/schema_validator.py` / `semantic_validator.py` | Structural + semantic validation of extracted facts |

**Guardrails — `services/guardrails/`**

| File | What it does |
|---|---|
| `input_rails.py` | Blocks prompt injection / unsafe input |
| `dialog_rails.py` | Refuses off-topic (non-filing) questions |
| `output_rails.py` | Masks PII before returning the answer |
| `retrieval_rails.py` / `execution_rails.py` | Retrieval-grounding and execution-safety checks |

**Qualitative analysis**

| File | What it does |
|---|---|
| `services/sentiment.py` | Loughran-McDonald lexicon sentiment/tone scoring (dict in `data/sentiment_dict/`) |
| `services/sec_analyzer.py` | Section-level filing analysis |
| `services/peer_comparison.py` | Cross-company peer comparison |
| `services/chart_tool.py` | Builds chart specs returned to the frontend |

**Governance & ops**

| File | What it does |
|---|---|
| `services/drift_detection.py` | Agreement-rate and concept-spike drift alerts |
| `services/calibration.py` | Routing-threshold recalibration from reviewer verdicts |
| `services/shadow_runner.py` | Shadow-deployment runner for offline comparison |
| `services/runtime_snapshot.py` | Parquet snapshot of the runtime/review DB to the HF dataset |
| `services/llm_health.py` | LLM call success/failure telemetry |
| `db/database.py` / `db/review_queue.py` | DuckDB access (main corpus + review/audit DB) |

### API surface

| Router | Endpoints |
|---|---|
| `routes/chat.py` | `POST /api/chat/{sql,rag,graph-rag,auditable-rag,sec-analyzer,feedback}` |
| `routes/review.py` | `GET /api/review/{queue,metrics,drift}`, `POST /api/review/{queue,decisions/{id}/verdict,calibrate}` |
| `routes/graph.py` | `GET /api/graph/{analytics,triples,evidence}` |
| `routes/sentiment.py` | `GET /api/sentiment/{ticker}`, `/{ticker}/{compare,history,tone-shift}` |
| `routes/audit.py` | `GET /api/audit`, `/api/audit/{run_id}`, `/api/audit/summary/stats` |
| `routes/analytics.py` | `POST /api/analytics/track`, `GET /api/analytics/{summary,posthog}` |
| `routes/admin.py` | `POST /api/admin/{refresh-data,snapshot,embed-data}` |
| `routes/stats.py` | `GET /api/stats` |
| `main.py` | `GET /api/health`, `/api/health/full` (DB + drift + LLM telemetry) |

### Frontend — `frontend/src/`

React + TypeScript + Vite + Tailwind. Routed shell: `/` portfolio home, `/rag-overview`, `/rag/*` workbench.

| Area | Files |
|---|---|
| Views | `views/ChatView.tsx` (SQL / RAG / auditable / graph chat), `views/TraceabilityView.tsx` |
| Audit & pipeline | `components/AuditTrail.tsx` (sources + XBRL facts table + verification badge), `components/PipelineFlow.tsx` (live step viz), `components/DriftAlert.tsx` |
| Knowledge graph | `components/KnowledgeGraph.tsx`, `GraphExplorer.tsx`, `GraphAnalytics.tsx` |
| Charts & tone | `components/FinancialChart.tsx`, `ChartView.tsx`, `ToneAnalysis.tsx` |
| Pages | `pages/ReviewQueue.tsx`, `MetricsDashboard.tsx`, `SystemDashboard.tsx`, `AuditLog.tsx`, `Methodology.tsx`, `ProductAnalytics.tsx`, `PortfolioHome.tsx`, `RagOverview.tsx`, `StocksList.tsx` |
| API clients | `api/{client,chat,review,graph,analytics}.ts` |

### Evaluation — `evals/`

| File | What it does |
|---|---|
| `golden_set.csv` | 50 labelled semiconductor questions across 8 failure modes |
| `run_eval.py` | Deterministic 4-axis scorer: correctness, XBRL verified, has sources, abstention |
| `ragas_eval.py` | LLM-judge metrics: faithfulness, answer relevancy, context precision/recall |

---

## Quickstart

### Prerequisites

- Python 3.11+ (the Docker image pins 3.11)
- Node 22+
- Docker (for the container build)

### Local development

```bash
# 1. Clone and install
git clone https://github.com/evangoh122/Rag_workbench.git
cd Rag_workbench
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env — set at minimum:
#   CHAT_PROVIDER=deepseek
#   DEEPSEEK_API_KEY=sk-...          (or another supported provider's key)
#   EDGAR_USER_AGENT=Your Name your@email.com
#   DB_PATH=./data/rag.duckdb
# Embeddings default to a local sentence-transformers model (no API key
# needed). Override with EMBEDDING_PROVIDER / ST_EMBEDDING_MODEL if desired.

# 3. Start the backend
uvicorn api.main:app --reload --port 8000

# 4. Start the frontend (separate terminal)
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

### Docker (single container)

```bash
docker build -t rag-workbench .
docker run -p 7860:7860 \
  -e CHAT_PROVIDER=deepseek \
  -e DEEPSEEK_API_KEY=sk-... \
  -e EDGAR_USER_AGENT="Your Name your@email.com" \
  -e DB_PATH=/app/data/rag.duckdb \
  -v $(pwd)/data:/app/data \
  rag-workbench
# → http://localhost:7860
```

---

## Supported LLM providers

Set `CHAT_PROVIDER` in `.env`:

| Provider | Value | Default model | Notes |
|---|---|---|---|
| DeepSeek | `deepseek` | `deepseek-chat` | Default. Set `DEEPSEEK_API_KEY` |
| Xiaomi MiMo | `mimo` | `mimo-v2.5-pro` | Set `MIMO_API_KEY` / `XIAOMI_API_KEY` |
| OpenAI | `openai` | `gpt-4o` | Set `OPENAI_API_KEY` |
| Anthropic | `anthropic` | `claude-sonnet-4-6` | Set `ANTHROPIC_API_KEY` |
| Ollama (local) | `ollama` | `llama3.2` | Set `OLLAMA_BASE_URL` / `OLLAMA_MODEL` |

### Embeddings & reranking

Embeddings are **provider-pluggable** via `EMBEDDING_PROVIDER`:

| Provider | Model | Dim |
|---|---|---|
| `sentence-transformers` (default in prod) | `Qwen/Qwen3-Embedding-0.6B` — runs in-process, no API | 1024 |
| `huggingface` | `Qwen/Qwen3-Embedding-8B` | 4096 |
| `ollama` | `nomic-embed-text` | 768 |

Retrieval is reranked by a CrossEncoder (`RERANKER_MODEL`, default `cross-encoder/ms-marco-MiniLM-L-6-v2`, top-K = 5).

---

## Ingest real filings

```bash
# Ingest the semiconductor ticker universe (10-K, latest available)
python -m scripts.embed_edgar

# Or specific tickers
EMBED_TICKERS=NVDA,AMD python -m scripts.embed_edgar
```

Each chunk is stored with `ticker`, `accession`, `cik`, `section_id`, `form_type`, `period_of_report`, `chunk_index`. The retriever uses this metadata to build the audit trail. The ticker universe (see `api/config.py` `TICKER_TO_CIK`) covers ~33 semiconductor names — chip designers (NVDA, AMD, QCOM, AVGO, INTC, MU, TXN, …) and equipment/materials (AMAT, LRCX, KLAC, ENTG, …).

Related scripts: `extract_xbrl_facts.py`, `extract_graph_triples.py`, `backfill_xbrl_coverage.py`, `reembed_qwen06.py`.

---

## Run the eval suite

```bash
# Start the API first, then:

# 1. Deterministic scoring (fast, free)
python evals/run_eval.py

# 2. LLM-judge scoring (uses your configured provider)
python evals/ragas_eval.py

# Debug a single question
python evals/run_eval.py --id 5
python evals/ragas_eval.py --id 5 --metrics faithfulness,answer_relevancy

# Filter by failure mode
python evals/run_eval.py --mode gaap_vs_nongaap
```

### Golden set failure modes

| Mode | Description | Example |
|---|---|---|
| `baseline` | Clean GAAP number, direct XBRL match | NVDA revenue |
| `period_mismatch` | Question asks for year X, model pulls year X+1 | QCOM 2023 vs 2024 |
| `gaap_vs_nongaap` | GAAP and non-GAAP differ materially | AMD non-GAAP gross margin |
| `segment` | Revenue must come from a specific segment only | QCOM QCT vs QTL revenue |
| `derived_calculation` | Requires arithmetic, not a direct XBRL tag | NVDA gross margin % |
| `restatement` | Company restated prior financials | INTC restatement |
| `segment_reorg` | Segment structure changed between filings | AVGO segment reorg |
| `abstention_failure` | No GAAP equivalent exists — model must decline | Non-GAAP metrics |

---

## Financial calculation library

`api/services/financial_calc.py` implements every common metric as a deterministic Python function. The LLM never does arithmetic — it identifies which function to call and extracts the inputs from XBRL.

```python
from api.services.financial_calc import gross_margin, FactExtractor

# Extract from XBRL DataFrame
extractor = FactExtractor(xbrl_df)
revenue = extractor.get("revenues",     period="2023-09-30")
cogs    = extractor.get("costofrevenue", period="2023-09-30")

# Calculate
result = gross_margin(revenue, cogs, period="FY2023")
print(result.display())
# → Gross Margin (FY2023): 44.1% | formula: (383.285B - 214.137B) / 383.285B = 44.13%
```

See `docs/FINANCIAL_CALC_INSTRUCTIONS.md` for the full instruction set used by the LangGraph engine.

**Available calculators:**
- Income statement: `gross_margin`, `operating_margin`, `net_margin`, `ebitda`, `ebitda_margin`, `rd_intensity`, `sga_intensity`, `yoy_growth`, `cagr`
- Balance sheet: `current_ratio`, `quick_ratio`, `debt_to_equity`, `net_debt`, `net_debt_to_ebitda`, `working_capital`, `book_value_per_share`
- Cash flow: `free_cash_flow`, `fcf_margin`, `fcf_conversion`, `capex_intensity`
- Accounting identity checks: `check_balance_sheet`, `check_gross_profit`, `check_fcf_identity`

---

## Data & persistence

| DB | Purpose | Lifecycle |
|---|---|---|
| `data/rag.duckdb` | Corpus: filing chunks + embeddings + XBRL facts + graph triples | Built offline, restored fresh from the HF dataset each boot |
| `data/review_queue.duckdb` | Runtime: audit log, HITL decisions, eval results | Must survive restarts — persisted via Parquet snapshots |

The HF Space has **no persistent volume**, so runtime state survives restarts through a daily Parquet snapshot (`runtime_snapshot.py`, driven by `.github/workflows/snapshot.yml` → `POST /api/admin/snapshot`) to a private HF dataset, restored on boot by `scripts/restore_review_db.py`. The main corpus DB is fetched by `scripts/fetch_db_from_dataset.py` before Uvicorn opens its connection. `DB_PATH` is validated against an allowlist to prevent path traversal.

---

## Deploy to Hugging Face Spaces

CI/CD is configured in `.github/workflows/`:
- `deploy.yml` — pushes to your HF Space on every merge to `main`
- `keep-awake.yml` — pings the health endpoint to prevent the free Space from sleeping
- `snapshot.yml` — triggers the daily runtime-DB Parquet snapshot

**Setup:**
1. Create a Space (Docker type) at huggingface.co
2. Add GitHub secrets: `HF_TOKEN`, `HF_USERNAME` (and `APP_DATA_HF_TOKEN` for the snapshot dataset)
3. Add HF Space secrets: `CHAT_PROVIDER`, the matching provider API key, `EDGAR_USER_AGENT`, `DB_PATH`
4. Push to `main` — the Action deploys automatically

---

## HITL governance

A full human-in-the-loop review framework beyond what most demos provide:

- **Review queue**: `SAMPLED_REVIEW` and `ESCALATE` decisions surface to a reviewer UI
- **Verdict recording**: agree/disagree stored with full transaction safety
- **Calibration**: reviewer verdicts recalibrate the routing confidence thresholds
- **Drift detection**: alerts when human-agreement rate drops below floor (default 95%, `DRIFT_AGREEMENT_FLOOR`) or unrecognized XBRL concepts spike (`DRIFT_CONCEPT_SPIKE_THRESHOLD`)
- **Pipeline monitoring**: live `DriftAlert` widget in the sidebar

Endpoints: `GET /api/review/queue`, `POST /api/review/decisions/{id}/verdict`, `GET /api/review/drift`, `POST /api/review/calibrate`

---

## Observability

LangSmith tracing is built in. Set in `.env`:

```
LANGSMITH_API_KEY=ls__...
LANGSMITH_PROJECT=rag-workbench
LANGSMITH_TRACING=true
```

Every chat call, RAG retrieval, and LangGraph node run produces a trace. Product analytics flow to PostHog (`VITE_POSTHOG_KEY` at build time; server-side read via `POSTHOG_API_KEY` for the analytics page). LLM call health is tracked in-process and surfaced at `/api/health/full`.

---

## Regulatory alignment

| Framework | How this project maps |
|---|---|
| **US SR 11-7** (Model Risk Management) | Validation layer, metrics dashboard, drift detection, routing and escalation triggers |
| **MAS AI Risk Management** | Risk materiality, lifecycle controls, meaningful human oversight, pre/post-deployment monitoring |
| **EU AI Act** | Demonstrable human oversight of automated decisions via the HITL review queue |

---

## How this is built — multi-agent workflow

This project is built by a team of specialist AI agents, each on its own branch, with mandatory cross-review before anything reaches `main`. The roles and ownership are defined in [`AGENTS.md`](AGENTS.md); each agent's mandate lives in `.<agent>/ROLE.md`.

| Agent | Branch | Focus | Owns |
|---|---|---|---|
| 🏛 **Claude** | `claude` | Software architecture — structure, separation of concerns, core pipeline | `api/routes/`, `api/config.py`, `main.py`, `langgraph_engine.py`, `graph_rag_engine.py` |
| 🔒 **Gemini** | `gemini` | Security + frontend — auth, rate limiting, hardened ingestion, React UI | `api/middleware/`, `scripts/embed_*.py`, `frontend/src/` |
| ⚡ **MiMo** | `mimo` | Performance + data — caching, latency, DuckDB query/index tuning, startup | retrieval/caching paths in `api/services/`, `data/`, `run.py` |
| 🔌 **DeepSeek** | `deepseek` | API engineering — routes, services, Pydantic schemas | `api/routes/review.py`, `api/services/drift_detection.py`, `api/models/review_schemas.py` |

### Merge workflow

1. **Branch per specialist.** Commits go to the named branch only — never directly to `main`.
2. **Peer review is required.** Before a branch merges, another specialist reviews it. No self-review.
3. **Round-robin reviewers:** `claude` → reviewed by **MiMo**; `mimo` → reviewed by **Gemini**; `gemini` → reviewed by **Claude**. Reviews are recorded as `.<agent>/REVIEW-*.md`.
4. **Verdict:** reviewer returns `APPROVED` or `CHANGES NEEDED`; the author fixes on-branch and requests re-review.
5. **Integration:** only approved branches merge to `main`. Conflicts are resolved by domain — architecture (Claude), security/perf (Gemini), optimization (MiMo).
6. **Worktree isolation:** agents dispatched with `isolation: "worktree"` must branch from `main` (not a stale specialist branch) — verified with `git log --oneline <branch> | head -3` before review.

> The `Owner`/`Path` table in `AGENTS.md` still references an `api/retrievers/` package and "MySQL"; the current implementation keeps all retrieval in `api/services/` (`hybrid_retriever.py`, `reranker.py`, `rag_engine.py`) and the datastore is DuckDB. Treat `api/services/` as the home for retrieval ownership.

---

## Project structure

```
.
├── api/
│   ├── db/              # DuckDB access (main corpus + review/audit DB)
│   ├── middleware/      # Rate limiting, auth, CORS
│   ├── models/          # Pydantic schemas, eval_types dataclasses
│   ├── routes/          # FastAPI routers (chat, review, graph, sentiment, audit, analytics, admin, stats)
│   └── services/        # Engines, calc/verify spine, guardrails/, governance
├── data/
│   └── sentiment_dict/  # Loughran-McDonald word lists
├── docs/
│   └── FINANCIAL_CALC_INSTRUCTIONS.md   # LangGraph math-node instruction set
├── evals/
│   ├── golden_set.csv   # 50-question labelled eval set
│   ├── run_eval.py      # Deterministic 4-axis scorer
│   └── ragas_eval.py    # LLM-judge metrics
├── frontend/
│   └── src/
│       ├── api/         # Typed API clients
│       ├── components/  # AuditTrail, PipelineFlow, KnowledgeGraph, charts, tone
│       ├── pages/       # ReviewQueue, dashboards, audit log, methodology
│       └── views/       # ChatView, TraceabilityView
├── scripts/             # Ingestion, XBRL/graph extraction, DB fetch/restore, shadow runs
├── tests/               # Unit tests
├── Dockerfile           # 3-stage: Node build → Python deps → Nginx + Supervisor runtime
├── nginx.conf           # Port 7860, /api/ proxied to FastAPI
└── supervisord.conf     # Process manager: nginx + uvicorn
```

---

## Honest limitations

- No production users or measured ROI — this is a portfolio PoC.
- Some validation phases (parts of the shadow-deployment and metrics tooling) are scaffolded ahead of full wiring; the README's architecture reflects what is implemented in `api/services/`.
- The golden set covers 50 questions; expanding the domain-specific slots requires banking judgment to write.
- Before any portfolio presentation: run a shadow-deployment pass and cite a real result (threshold X → false-escalation Y%, agreement Z%).
