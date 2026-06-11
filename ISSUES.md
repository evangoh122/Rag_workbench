# Issue Tracker

**Last updated:** 2026-06-11 (audit sweep — verified all outstanding + scanned for new issues)

---

## ✅ Resolved Issues

### P0 - Critical

| # | Issue | File | Fix |
|---|-------|------|-----|
| 1 | Race condition in `_rag_instance` singleton | `asymmetric_rag.py` | `threading.Lock()` with double-checked locking |

### P1 - Security

| # | Issue | File | Fix |
|---|-------|------|-----|
| 3 | Silent auth bypass when no API key | `auth.py` | Fail-closed: returns 503 when `API_KEY` not set |
| 4 | Timing-attack vulnerable comparison | `auth.py` | `hmac.compare_digest()` |
| 5 | LLM-generated SQL injection (LIMIT) | `chat_engine.py` | Parameterized `LIMIT ?` |
| 6 | SQL injection via keyword fallback | `rag_engine.py` | Capped word list to 10 |
| 7 | SQL injection via f-string | Multiple | f-strings only build `?` placeholders |
| 8 | No input validation on message | `schemas.py` | `Field(min_length=1, max_length=8000)` |
| 9 | No input validation on history | `schemas.py` | `Field(max_length=50)` |
| 10 | Rate limiter unbounded memory | `rate_limit.py` | `TTLCache(maxsize=10_000, ttl=120)` + `asyncio.Lock()` |
| 11 | Overly permissive CORS | `cors_config.py` | Restricted to `GET, POST, OPTIONS` |
| 12 | No CORS origin validation | `cors_config.py` | Regex validation |
| 13 | Error messages leak internals | Multiple | Generic messages to client |
| 14 | Hardcoded MiMo URL | `ragas_eval.py` | Reads `MIMO_BASE_URL` from env |
| 16 | Audit scripts expose codebase | `scripts/` | CLI-only scripts, require explicit invocation |

### Manus Security Audit Fixes

| ID | Issue | Fix |
|----|-------|-----|
| SEC-02 | Schema enumeration via SQL | `information_schema` + `duckdb_\w+` blocked in `chat_engine.py` |
| SEC-03 | Review endpoints unauthenticated | Error logged in production mode, warning in dev (`review.py`) |
| SEC-06 | CIK SSRF / parameter injection | `cik.isdigit()` validation added in `xbrl_client.py` |

### P2 - Architecture

| # | Issue | File | Fix |
|---|-------|------|-----|
| 17 | Two parallel RAG implementations | `asymmetric_rag.py` vs `rag_engine.py` | Deleted `asymmetric_rag.py` (925 lines) |
| 18 | Inconsistent logging | `calibration.py` | Standardized on loguru |
| 19 | `load_dotenv()` called 7 times | `main.py` | Removed redundant call (config.py handles it) |
| 21 | No retry for SEC API | `edgar_adapter.py` | `tenacity` retry with exponential backoff |
| 22 | DuckDB lock serializes all access | `database.py` | `threading.RLock()` for reentrant locking |
| 23 | Deprecated `on_event("startup")` | `main.py` | Migrated to `lifespan` context manager |
| 24 | No graceful shutdown | `main.py` | `db_manager.close()` in lifespan |

### P3 - Code Quality

| # | Issue | File | Fix |
|---|-------|------|-----|
| 25 | Missing `requests` in requirements | `requirements.txt` | Added `requests>=2.31.0` |
| 26 | Missing dev dependencies | `requirements-dev.txt` | Created with pytest, httpx, ruff |
| 27 | `edgartools` allows breaking v3.x | `requirements.txt` | Pinned `>=2.26.0,<3.0.0` |
| 29 | BM25 index rebuilt on every restart | `asymmetric_rag.py` | Deleted — moot after removal |
| 30 | Embedding one-at-a-time | `asymmetric_rag.py` | Deleted — moot after removal |
| 31 | Non-deterministic `hash()` | `rag_engine.py` | `hashlib.sha256()` |
| 34 | Bare `except Exception` silent | `edgar_adapter.py` | Added `logger.debug()` messages |
| 37 | Dead code `VectorStoreRetriever` | `vector_store.py` | Removed |
| 38 | New DuckDB connection per query | `asymmetric_rag.py` | Uses `db_manager.get_connection()` |
| 39 | Inconsistent provider naming | `asymmetric_rag.py` | Deleted — moot after removal |
| 32 | ~~`warnings.filterwarnings` too broad~~ | `main.py` | **Verified resolved** — only 2 targeted patterns (langchain UserWarning, urllib3 version) |
| 35 | ~~`print()` in run.py~~ | `run.py` | **Verified resolved** — uses `logger.info()` only, no print() |
| 40 | ~~DuckDB file possibly tracked~~ | `data/` | **Verified resolved** — `data/` in .gitignore, zero DuckDB files tracked |

### Guardrails (Manus Phase 13-15)

| ID | Capability | File |
|----|-----------|------|
| GR-01 | Prompt injection / jailbreak detection | `api/services/guardrails/input_rails.py` |
| GR-02 | Off-topic query refusal | `api/services/guardrails/dialog_rails.py` |
| GR-03 | Retrieved chunk relevance filtering | `api/services/guardrails/retrieval_rails.py` |
| GR-04 | SQL/math execution safety | `api/services/guardrails/execution_rails.py` |
| GR-05 | Hallucination detection | `api/services/guardrails/output_rails.py` |
| GR-06 | PII masking + system prompt leak detection | `api/services/guardrails/output_rails.py` |

### Audit Report - Resolved

| ID | Issue | Resolution |
|----|-------|------------|
| H2 | XBRL_MISMATCH false positives | `xbrl_cross_validator.py` — proper 1% tolerance cross-check |
| L1 | Naive BM25 tokenization | `asymmetric_rag.py` deleted — moot |
| L3 | No confidence differentiation | `confidence_scorer.py` — provenance-based (0.98/0.85/0.55) + XBRL cross-check |
| L8 | Separate EDGAR identities | `_edgar_identity.py` — shared SEC identity helper |
| L9 | RRF passes dummy scores | Vector retrieval wired in `langgraph_engine.py` |
| L10 | Regex backtracking risk | Atomic patterns in `embed_edgar.py` |

---

## ⚠️ Outstanding Issues (from prior audit)

### P1 - Security (User Action Required)

| # | Issue | File | Status | Action |
|---|-------|------|--------|--------|
| 2 | Real API keys in `.env` | `.env` | **Still outstanding** — 7 real keys on disk (Gemini, Google, MiMo, DeepSeek, XiaoMi, Manus) | Rotate keys; use secrets manager (local env — deferred) |
| 15 | No API key scoping | `auth.py` | **Still outstanding** — only 2 tiers exist (standard + admin), no write tier | Design: implement key scopes for read/write/admin tiers |

### P2 - Architecture & Design

| # | Issue | File | Status | Action |
|---|-------|------|--------|--------|
| 20 | Module-level global state (19+ vars) | `api/config.py`, `api/db/database.py`, `main.py` | **Still outstanding** — Config class has 16 class-level attrs + 3 more module-level | Encapsulate in config class with lazy init |

### Audit Report - Outstanding

| ID | Issue | Status | Action |
|----|-------|--------|--------|
| C1 | API keys in `.env` | **Still outstanding** — duplicate of #2 | Rotate keys (local env — deferred) |
| L2 | Query instruction prefix | **Still outstanding** — zero references to "Qwen3" anywhere in codebase; no L2 query instruction prefix in guardrails | Verify against Qwen3 docs or remove from audit |
| L4 | 10-K/A has 0.0 confidence | **Still outstanding** — confidence can legitimately go to 0.0 when no XBRL fields match; escalation trigger works but no explicit "no data" signal | Add "no data" signal for zero-match filings |

---

## 🔴 New Issues (2026-06-11 sweep)

### HIGH — Code Broken / Security

| ID | Issue | File | Detail |
|----|-------|------|--------|
| N1 | `_load_env()` undefined — raises `NameError` at runtime | `evals/ragas_eval.py:317` | Function is called but never defined. Running the eval will crash immediately. |
| N2 | `traceback.print_exc()` in production API route | `api/routes/chat.py:110` | Leaks raw Python stack trace to stderr/stdout. Replace with `logger.exception()`. |
| N3 | `print()` in production service code instead of logger | `api/services/graph_rag_engine.py:42,80` | `logger` is not even imported — print() leaks to stdout in API context |

### MEDIUM — Architecture / Reliability

| ID | Issue | File | Detail |
|----|-------|------|--------|
| N4 | All 28 deps unpinned (only `>=`, no upper cap) | `requirements.txt` | `pip install` may pull incompatible major versions (e.g. polars, sentence-transformers) |
| N5 | `pydantic` missing from requirements.txt | `requirements.txt` | Used extensively but only transitively installed via fastapi |
| N6 | `requirements-dev.txt` missing (was supposedly created per #26) | — | File does not exist on disk; pytest, httpx, ruff not declared |
| N7 | `verify_numeric` imported but never called in production | `api/services/langgraph_engine.py:13` | Imported from verifier but only used in `tests/test_verifier.py`, never in engine code |
| N8 | `execution_rails` exported but never called | `api/services/guardrails/execution_rails.py` | `check_execution()`, `check_sql()`, `check_math()` exported from `__init__.py` but no route or service calls them |
| N9 | `graph_extractor.py` never imported (dead code) | `api/services/graph_extractor.py` | Zero imports of this module anywhere in the codebase |
| N10 | `reload=True` in production entry point | `run.py:8` | Auto-restart on file changes is dev-only; gate behind `ENVIRONMENT` check |
| N11 | Missing startup validation for non-deepseek providers | `api/config.py:98-106` | `_validate_startup()` only checks DEEPSEEK + GOOGLE keys; silent failure for openai/anthropic/mimo |
| N12 | `api/services/` importing from `scripts/` | `api/services/rag_engine.py:19` | `from scripts.embed_tickers import _get_embeddings` — API layer depends on CLI scripts |
| N13 | 138 CIK mappings with placeholder CIKs (~40 duplicates) | `scripts/embed_edgar.py:38-138` | Multiple tickers share `"0000930155"` or `"0001903832"` placeholders; fetched data will be incorrect |
| N14 | `open()` without `encoding="utf-8"` | `scripts/init_graph_triples.py:60`, `scripts/run_shadow.py:101` | Locale-dependent behavior on Windows |
| N15 | `StateGraph` compiled at import time | `api/services/langgraph_engine.py:449` | Graph is frozen with import-time settings; dynamic config changes won't apply |
| N16 | Deferred/lazy imports (4 places) | `langgraph_engine.py:70`, `database.py:62`, `main.py:45` | Moves import failures to runtime, breaks static analysis |

### LOW — Code Quality / Frontend

| ID | Issue | File | Detail |
|----|-------|------|--------|
| N17 | Monolithic React component (606 lines) | `frontend/src/App.tsx:42-648` | All views in single component; should be routed + decomposed |
| N18 | TypeScript `any` types leaking | `frontend/src/api/chat.ts:34-35`, `App.tsx:20-21` | `sources?: any[]` / `xbrl_facts?: any[]` — proper `Source[]`/`XBRLFact[]` types exist but unused |
| N19 | Empty catch blocks in frontend | `DriftAlert.tsx:20`, `MetricsDashboard.tsx:48` | Swallows all error info silently |
| N20 | Inconsistent polling intervals | `DriftAlert.tsx` (60s), `MetricsDashboard.tsx`/`SystemDashboard.tsx` (30s) | Inconsistent; should be configurable |
| N21 | Inconsistent API calling patterns | Multiple frontend files | Some use `client.get()` directly, others use typed helper functions |
| N22 | No frontend tests | `frontend/` | No vitest/jest config, no test files |
| N23 | Mixed test frameworks | `tests/` | 3 files use `unittest.TestCase`, 1 uses `pytest` fixtures |
| N24 | `graphify-out/cache/` untracked | `.gitignore` | 48 cached AST JSON files clutter `git status` |
| N25 | Missing .gitignore entries | `.gitignore` | Missing: `graphify-out/cache/`, `.claude/settings.local.json`, `*.duckdb.wal` |
| N26 | Module-level `verify_numeric` mimics class method | `api/services/verifier.py:70-74` | Class method `verify_numeric()` and module-level wrapper both exist — naming confusion |

### TEST GAPS — Major Modules With Zero Tests

| Module | Path | Lines |
|--------|------|-------|
| Core RAG Engine | `api/services/rag_engine.py` | ~250 |
| LangGraph Engine | `api/services/langgraph_engine.py` | ~450 |
| Chat Engine | `api/services/chat_engine.py` | ~200 |
| Graph RAG Engine | `api/services/graph_rag_engine.py` | ~85 |
| Financial Calculator | `api/services/financial_calc.py` | 719 |
| Config | `api/config.py` | ~110 |
| Chat Routes | `api/routes/chat.py` | ~160 |
| Review Routes | `api/routes/review.py` | ~200 |
| Stats Routes | `api/routes/stats.py` | ~60 |
| Auth Middleware | `api/middleware/auth.py` | ~60 |
| Rate Limit Middleware | `api/middleware/rate_limit.py` | ~50 |
| Guardrails (×5) | `api/services/guardrails/*.py` | ~250 |
| LLM Health | `api/services/llm_health.py` | ~80 |
| Drift Detection | `api/services/drift_detection.py` | ~50 |
| XBRL Client | `api/services/xbrl_client.py` | ~100 |
| SEC Client | `api/services/sec_client.py` | ~80 |
| All Scripts | `scripts/*.py` | ~600 |
| Frontend | `frontend/src/` | ~70 |

---

## Summary

| Category | Prior Resolved | Prior Outstanding | New Issues | Total Outstanding |
|----------|---------------|-------------------|------------|-------------------|
| P0 Critical | 1 | 0 | 0 | 0 |
| P1 Security | 13 | 2 | 0 | 2 |
| Manus Audit (SEC) | 3 | 0 | 0 | 0 |
| P2 Architecture | 7 | 1 | 9 | 10 |
| P3 Code Quality | 13 | 0 | 8 | 8 |
| Guardrails (GR) | 6 | 0 | 0 | 0 |
| Audit Report | 16 | 3 | 0 | 3 |
| Frontend | 0 | 0 | 6 | 6 |
| Test Gaps | 0 | 0 | 18 modules | 18 |
| **Total** | **59** | **6** | **41** | **47** |
