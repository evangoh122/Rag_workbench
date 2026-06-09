# Issue Tracker

**Last updated:** 2026-06-09 (deepseek branch audit)

---

## ✅ Resolved Issues

### P0 - Critical

| # | Issue | File | Fix |
|---|-------|------|-----|
| 1 | Race condition in `_rag_instance` singleton | `asymmetric_rag.py:859` | Added `threading.Lock()` with double-checked locking |

### P1 - Security

| # | Issue | File | Fix |
|---|-------|------|-----|
| 3 | Silent auth bypass when no API key | `api/middleware/auth.py` | Fail-closed: returns 503 when `API_KEY` not set |
| 4 | Timing-attack vulnerable comparison | `api/middleware/auth.py:26` | Uses `hmac.compare_digest()` |
| 5 | LLM-generated SQL injection (LIMIT) | `api/services/chat_engine.py:154` | Parameterized `LIMIT ?` with bound parameter |
| 6 | SQL injection via keyword fallback | `api/services/rag_engine.py:57` | Capped word list to 10 entries `[:10]` |
| 7 | SQL injection via f-string (rag_engine + asymmetric_rag) | Multiple | f-strings only build `?` placeholders; values are bound params |
| 8 | No input validation on `ChatRequest.message` | `api/models/schemas.py` | `Field(min_length=1, max_length=4000)` |
| 9 | No input validation on `history` field | `api/models/schemas.py` | `Field(max_length=50)` |
| 10 | Rate limiter unbounded memory | `api/middleware/rate_limit.py` | `TTLCache(maxsize=10_000, ttl=120)` + `asyncio.Lock()` |
| 11 | Overly permissive CORS | `api/middleware/cors_config.py` | Restricted to `GET, POST, OPTIONS` and specific headers |
| 12 | No CORS origin validation | `api/middleware/cors_config.py` | Regex validation `_ORIGIN_RE`, warns on invalid |
| 13 | Error messages leak internals | `chat_engine.py`, `rag_engine.py`, `chat.py` | Generic messages to client; details logged server-side |
| 14 | Hardcoded MiMo API URL | `evals/ragas_eval.py:83` | Reads `MIMO_BASE_URL` from env var |

### P2 - Architecture

| # | Issue | File | Fix |
|---|-------|------|-----|
| 23 | Deprecated `@app.on_event("startup")` | `api/main.py` | Migrated to `lifespan` context manager |
| 24 | No graceful shutdown | `api/main.py` | `db_manager.close()` in lifespan shutdown |

### P3 - Code Quality

| # | Issue | File | Fix |
|---|-------|------|-----|
| 25 | Missing `requests` in requirements | `requirements.txt` | Added `requests>=2.31.0` |
| 27 | `edgartools` allows breaking v3.x | `requirements.txt` | Pinned `>=2.26.0,<3.0.0` |
| 31 | Non-deterministic `hash()` | `api/services/rag_engine.py:259` | Uses `hashlib.sha256()` |
| 34 | Bare `except Exception` silent | `api/services/edgar_adapter.py:126,178` | Added `logger.debug()` messages |
| 38 | New DuckDB connection per query | `asymmetric_rag.py:791` | Uses shared `db_manager.get_connection()` |

### Audit Report (DATA_AUDIT_REPORT.md)

| ID | Issue | Fix |
|----|-------|-----|
| C2 | Test import error | Function `_xbrl_dataframe_to_fields` exists |
| C3 | SQL injection in vector_store.py | Table whitelist `_ALLOWED_TABLES` + parameterized LIMIT |
| H1 | Wrong form_type handling | Graceful `getattr` fallback to "UNKNOWN" |
| H3 | Duplicate ChatRequest schema | Removed unused `ChatResponse`/`HealthResponse` from schemas.py |
| H4 | Auth middleware never used | Wired into all `/api/chat/*` routes via `Depends(get_api_key)` |
| H6 | Rate limiter unbounded memory | `TTLCache` with bounded size and TTL |
| M4 | Thread safety in `get_rag_chain()` | `threading.Lock()` with double-checked locking |
| M9 | No CORS production config | `cors_config.py` with env-based origin validation |
| L5 | Unused schemas | Removed dead code from `schemas.py` |
| L7 | New DuckDB connection per query | Reuses `db_manager.get_connection()` |

---

## ⚠️ Outstanding Issues

### P1 - Security (User Action Required)

| # | Issue | File | Action |
|---|-------|------|--------|
| 2 | Real API keys in `.env` file | `.env` | Rotate exposed keys; use secrets manager |
| 15 | No API key scoping | `api/middleware/auth.py` | Design: implement key scopes or document limitation |
| 16 | Audit scripts expose codebase | `scripts/anthropic_audit.py`, `scripts/deepseek_audit.py` | Gate with confirmation flag; document risks |

### P2 - Architecture & Design

| # | Issue | File | Action |
|---|-------|------|--------|
| 17 | Two parallel RAG implementations | `asymmetric_rag.py` vs `rag_engine.py` | Consolidate or extract shared retrieval logic |
| 18 | Inconsistent logging frameworks | Multiple | Standardize on `loguru` |
| 19 | `load_dotenv()` called 7 times | Multiple | Single call in entry point only |
| 20 | Module-level global state (18+ vars) | Multiple | Encapsulate in config class with lazy init |
| 21 | No retry/backoff for SEC API | `api/services/edgar_adapter.py` | Add exponential backoff |
| 22 | DuckDB lock serializes all access | `api/db/database.py:46` | Use read/write lock or connection pool |

### P3 - Code Quality

| # | Issue | File | Action |
|---|-------|------|--------|
| 26 | Missing `pytest`/`httpx` in requirements | `requirements.txt` | Create `requirements-dev.txt` |
| 28 | Test assertion wrong for `window_size` | `tests/test_metrics_endpoint.py` | File removed; N/A if test re-created |
| 29 | BM25 index rebuilt on every restart | `asymmetric_rag.py:590` | Serialize/deserialize index to disk |
| 30 | Embedding computation one-at-a-time | `asymmetric_rag.py:122` | Batch embedding API or async parallelize |
| 32 | `warnings.filterwarnings("ignore")` too broad | `main.py` | Use targeted filters |
| 33 | `sys.path.insert(0, ...)` anti-pattern | `scripts/calibrate.py`, `scripts/shadow_run.py` | Use `pip install -e .` |
| 35 | `print()` instead of logger | `run.py`, `scripts/seed_metrics.py` | Replace with `logger.info()` |
| 36 | `unsafe_allow_html=True` with DB data | `dashboard.py:117` | Sanitize values or avoid HTML mode |
| 37 | Dead code `VectorStoreRetriever` | `api/retrievers/vector_store.py:12` | Remove or document intended use |
| 39 | Inconsistent provider key naming | `asymmetric_rag.py:822` vs `api/config.py` | Consolidate provider configs |
| 40 | DuckDB file possibly tracked in repo | `data/ibkr.duckdb` | `git ls-files` check; `git rm --cached` if needed |

### Audit Report - Outstanding

| ID | Issue | Action |
|----|-------|--------|
| C1 | API keys exposed in `.env` | Rotate keys; use secrets manager |
| H2 | XBRL_MISMATCH false positives (Apple) | Investigate `XbrlCrossValidator` period filtering |
| H5 | DB connection leaks in `companyfacts_client.py` | File removed; N/A |
| L1 | Naive BM25 tokenization | Add punctuation removal, stopwords |
| L2 | Query instruction prefix may be wrong | Verify against Qwen3 model docs |
| L3 | No confidence differentiation (all 0.98) | Tune provenance base scores |
| L4 | 10-K/A has 0.0 confidence | Add "no data" signal instead of 0.0 |
| L6 | Missing `__all__` in `api/services/__init__.py` | Define public API boundary |
| L8 | Separate EDGAR identities | Consolidate `embed_edgar.py` and `edgar_adapter.py` |
| L9 | RRF passes dummy scores | Pass actual similarity/BM25 scores |
| L10 | Regex catastrophic backtracking risk | Use non-greedy or atomic patterns |
| L11 | Frontend API base URL hardcoded | Use `VITE_API_BASE` env var |

---

## Summary

| Category | Resolved | Outstanding |
|----------|----------|-------------|
| P0 Critical | 1 | 0 |
| P1 Security | 12 | 3 (user action) |
| P2 Architecture | 2 | 6 |
| P3 Code Quality | 5 | 11 |
| Audit Report | 10 | 12 |
| **Total** | **30** | **32** |
