# RAG Workbench — Auditable Filing QA

A financial Q&A system where **every claim traces to source and every number is verified against XBRL** — auditable, not just intelligent.

Built for AI/data roles in banking and financial services. The point: demonstrate you think like the team building compliance-grade AI, not just a demo that looks impressive and produces confidently wrong answers.

---

## The thesis

Most RAG systems retrieve context and trust the LLM to do the rest. This system doesn't:

- **AI retrieves.** The LangGraph pipeline finds the right SEC filing chunks and XBRL-tagged facts.
- **Python calculates.** `financial_calc.py` does all arithmetic — the LLM is never asked to do math.
- **XBRL verifies.** Every numeric answer is cross-checked against the SEC EDGAR companyfacts API before it's returned.
- **The audit trail is the product.** Each answer shows retrieved chunks with EDGAR links, the XBRL fact behind each number, the formula used, and a green/red verification badge.

---

## Architecture

```
Browser
  │
  └── Nginx (port 7860)
        ├── /* ──────────────────── React + Tailwind (static)
        └── /api/* ──────────────── FastAPI (port 8000)
                                        │
                               LangGraph Pipeline
                                        │
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
              Retrieval             XBRL Extraction      Math Node
          (dense + BM25)         (SEC companyfacts)   (financial_calc.py)
                    │                   │                   │
                    └───────────────────┼───────────────────┘
                                        │
                                  Verification
                              (numeric + NLI entailment)
                                        │
                                  Final Answer
                            {answer, sources, xbrl_facts,
                             verification badge, math_steps}
```

Single Docker container (Nginx + Uvicorn + Supervisor). Deploys to Hugging Face Spaces.

---

## Key components

### Backend — `api/`

| File | What it does |
|---|---|
| `services/langgraph_engine.py` | Deterministic DAG: Retrieval → XBRL → Math → Verify → Abstain/Answer |
| `services/financial_calc.py` | All financial arithmetic (gross margin, FCF, CAGR, ratios, identity checks) |
| `services/xbrl_client.py` | SEC EDGAR companyfacts API client — rate-limited (≤10 req/s), LRU-cached |
| `services/verification.py` | Numeric claim extraction + XBRL cross-check (1% tolerance) |
| `services/verifier.py` | NLI CrossEncoder entailment check — independent model from the generator |
| `services/sec_client.py` | EdgarTools + Polars XBRL extraction, LRU-cached per ticker |
| `services/edgar_adapter.py` | Wraps EdgarTools output into canonical `ExtractionResult` type contract |
| `services/rag_engine.py` | Hybrid retrieval: dense embeddings (Gemini) + BM25, RRF merge |
| `services/chat_engine.py` | SQL mode — natural language to DuckDB queries |
| `routes/chat.py` | `/api/chat/sql`, `/api/chat/rag`, `/api/chat/auditable-rag` |
| `routes/review.py` | Phase 8 HITL review queue (5 endpoints) |
| `services/drift_detection.py` | Agreement-rate and concept-spike drift alerts |
| `services/calibration.py` | Routing threshold recalibration from reviewer verdicts |

### Frontend — `frontend/src/`

| File | What it does |
|---|---|
| `App.tsx` | Main shell — chat (SQL/RAG), review queue, sidebar navigation |
| `components/AuditTrail.tsx` | Per-answer sources panel, XBRL facts table, verification badge |
| `components/PipelineFlow.tsx` | Real-time pipeline step visualization |
| `components/DriftAlert.tsx` | Live agreement-rate and concept-spike monitor in sidebar |
| `pages/ReviewQueue.tsx` | HITL reviewer interface — agree/disagree on routed decisions |
| `api/chat.ts` | Typed API client for all chat endpoints |
| `api/review.ts` | Typed API client for review queue endpoints |

### Evaluation — `evals/`

| File | What it does |
|---|---|
| `golden_set.csv` | 25 labelled questions (AAPL, TSLA, GE) across 8 failure modes |
| `run_eval.py` | Deterministic 4-axis scorer: correctness, XBRL verified, has sources, abstention |
| `ragas_eval.py` | LLM-judge metrics: faithfulness, answer relevancy, context precision/recall |

---

## Quickstart

### Prerequisites

- Python 3.11+ (3.14 works but some packages emit deprecation warnings)
- Node 22+
- Docker (for container build)

### Local development

```bash
# 1. Clone and install
git clone https://github.com/evangoh122/Rag_workbench.git
cd Rag_workbench
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env — set at minimum:
#   DEEPSEEK_API_KEY=sk-...         (or any supported provider)
#   GEMINI_API_KEY=...              (for embeddings)
#   EDGAR_USER_AGENT=Your Name your@email.com
#   DB_PATH=./data/rag.duckdb     (or your DuckDB path)

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
  -e DEEPSEEK_API_KEY=sk-... \
  -e GEMINI_API_KEY=... \
  -e EDGAR_USER_AGENT="Your Name your@email.com" \
  -e DB_PATH=/app/data/rag.duckdb \
  -v $(pwd)/data:/app/data \
  rag-workbench
# → http://localhost:7860
```

---

## Supported LLM providers

Set `CHAT_PROVIDER` in `.env`:

| Provider | Value | Notes |
|---|---|---|
| DeepSeek | `deepseek` | Default. Set `DEEPSEEK_API_KEY` |
| Xiaomi MiMo | `mimo` | Set `XIAOMI_API_KEY` |
| OpenAI | `openai` | Set `OPENAI_API_KEY` |
| Anthropic (Claude) | `anthropic` | RAG mode only; SQL mode unsupported |
| Ollama (local) | `ollama` | Set `OLLAMA_BASE_URL` and `OLLAMA_MODEL` |

---

## Ingest real filings

```bash
# Ingest AAPL, TSLA, GE (10-K, latest available)
python scripts/run_ingestion.py

# Or specific tickers
EMBED_TICKERS=AAPL,MSFT python scripts/embed_edgar.py
```

Each chunk is stored with: `ticker`, `accession`, `cik`, `section_id`, `form_type`, `period_of_report`, `chunk_index`. The retriever uses this metadata for the audit trail.

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
| `baseline` | Clean GAAP number, direct XBRL match | AAPL revenue |
| `period_mismatch` | Question asks for year X, model pulls year X+1 | TSLA 2021 vs 2022 |
| `gaap_vs_nongaap` | GAAP and non-GAAP differ materially | TSLA net income |
| `segment` | Revenue must come from a specific segment only | AAPL iPhone revenue |
| `derived_calculation` | Requires arithmetic, not a direct XBRL tag | AAPL gross margin % |
| `restatement` | Company restated prior financials | GE 2018 restatement |
| `segment_reorg` | Segment structure changed between filings | GE Healthcare spinoff |
| `abstention_failure` | No GAAP equivalent exists — model must decline | Non-GAAP EBITDA margin |

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

## Deploy to Hugging Face Spaces

CI/CD is already configured in `.github/workflows/deploy.yml`. It:
- Pushes to your HF Space on every merge to `main`
- Pings the health endpoint every 20 minutes to prevent sleep

**Setup:**
1. Create a Space (Docker type) at huggingface.co
2. Add GitHub secrets: `HF_TOKEN`, `HF_USERNAME`
3. Add HF Space secrets: `DEEPSEEK_API_KEY`, `GEMINI_API_KEY`, `EDGAR_USER_AGENT`, `DB_PATH`
4. Push to `main` — the Action deploys automatically

---

## HITL governance (Phase 8)

The project includes a full human-in-the-loop review framework beyond what most demos provide:

- **Review queue**: SAMPLED_REVIEW and ESCALATE decisions surface to a reviewer UI
- **Verdict recording**: agree/disagree stored with full transaction safety
- **Calibration**: reviewer verdicts recalibrate the routing confidence thresholds
- **Drift detection**: alerts when human-agreement rate drops below floor (default 95%) or unrecognized XBRL concepts spike
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

Every chat call, RAG retrieval, and LangGraph node run produces a trace in your LangSmith dashboard.

---

## Regulatory alignment

| Framework | How this project maps |
|---|---|
| **US SR 11-7** (Model Risk Management) | Validation layer, metrics dashboard, drift detection, routing and escalation triggers |
| **MAS AI Risk Management** | Risk materiality, lifecycle controls, meaningful human oversight, pre/post-deployment monitoring |
| **EU AI Act** (Aug 2026) | Demonstrable human oversight of automated decisions via HITL review queue |

---

## Multi-agent build

This project was built by a team of AI agents with cross-validation before every merge:

| Agent | Role | Owned files |
|---|---|---|
| **Claude** | Software architect — routes, data structures, orchestration | `api/routes/`, `api/models/`, `financial_calc.py` |
| **Gemini** | Security + frontend | `frontend/src/`, `Dockerfile`, `nginx.conf` |
| **MiMo** | Performance + data | `api/retrievers/`, `api/db/`, `scripts/` |
| **DeepSeek** | API engineering | `api/routes/review.py`, `api/services/drift_detection.py` |

Three rounds of peer review were completed before merging to `main`. Review reports are in `.claude/`, `.gemini/`, `.mimo/` directories.

---

## Project structure

```
.
├── api/
│   ├── db/              # DuckDB access layer (main + review queue)
│   ├── middleware/      # Rate limiting, auth
│   ├── models/          # Pydantic schemas, eval_types dataclasses
│   ├── retrievers/      # Hybrid dense+BM25 retrieval
│   ├── routes/          # FastAPI routers (chat, review)
│   └── services/        # Business logic (langgraph, financial_calc, xbrl, verifier...)
├── docs/
│   └── FINANCIAL_CALC_INSTRUCTIONS.md   # LangGraph math node instruction set
├── evals/
│   ├── golden_set.csv   # 25-question labelled eval set
│   ├── run_eval.py      # Deterministic 4-axis scorer
│   └── ragas_eval.py    # LLM-judge RAGAS-equivalent metrics
├── frontend/
│   └── src/
│       ├── api/         # Typed API clients
│       ├── components/  # AuditTrail, DriftAlert, PipelineFlow
│       └── pages/       # ReviewQueue
├── scripts/
│   ├── embed_edgar.py   # 10-K ingestion with provenance metadata
│   └── run_ingestion.py # One-shot ingest for AAPL, TSLA, GE
├── tests/               # Unit tests (eval_types, edgar_adapter, verifier)
├── Dockerfile           # Multi-stage: Node → Python → Nginx+Supervisor
├── nginx.conf           # Port 7860, /api/ proxied to FastAPI
└── supervisord.conf     # Process manager: nginx + uvicorn
```

---

## Honest limitations

- No production users or measured ROI — this is a portfolio PoC
- Phases 2–7 of the validation pipeline (schema validator, XBRL cross-validation, semantic validator, confidence scoring, shadow deployment, metrics dashboard) are designed and planned but not yet implemented
- The golden set covers 25 of a target 40–50 questions — domain-specific questions for the remaining slots require banking judgment to write
- Before any portfolio presentation: run Phase 6 shadow deployment and cite a real result (threshold X → false-escalation Y%, agreement Z%)
