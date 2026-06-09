# Issue Tracker

**Last updated:** 2026-06-09 (main branch)

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
| 15 | No API key scoping | `auth.py` | `get_admin_api_key()` with `ADMIN_API_KEY` env var |

### P2 - Architecture

| # | Issue | File | Fix |
|---|-------|------|-----|
| 18 | Inconsistent logging | `calibration.py` | Standardized on loguru |
| 19 | `load_dotenv()` called 7 times | `main.py` | Removed redundant call |
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
| 29 | BM25 index rebuilt on every restart | `asymmetric_rag.py` | Disk cache with pickle save/load |
| 30 | Embedding one-at-a-time | `asymmetric_rag.py` | ThreadPoolExecutor parallel embedding |
| 31 | Non-deterministic `hash()` | `rag_engine.py` | `hashlib.sha256()` |
| 34 | Bare `except Exception` silent | `edgar_adapter.py` | Added `logger.debug()` messages |
| 35 | `print()` instead of logger | `run.py` | Replaced with `logger.info()` |
| 37 | Dead code `VectorStoreRetriever` | `vector_store.py` | Removed |
| 38 | New DuckDB connection per query | `asymmetric_rag.py` | Uses `db_manager.get_connection()` |
| 39 | Inconsistent provider naming | `asymmetric_rag.py` | Uses `Config.get_provider_config()` |

### Audit Report - Resolved

| ID | Issue | Fix |
|----|-------|-----|
| C2 | Test import error | Function exists |
| C3 | SQL injection in vector_store.py | Table whitelist + parameterized LIMIT |
| H1 | Wrong form_type | Graceful `getattr` fallback |
| H2 | XBRL_MISMATCH false positives | Cross-validation with tolerance in `xbrl_cross_validator.py` |
| H3 | Duplicate ChatRequest | Consolidated to schemas.py |
| H4 | Auth middleware unused | Wired into all routes |
| H6 | Rate limiter unbounded | TTLCache |
| L1 | Naive BM25 tokenization | Regex-based punctuation removal |
| L3 | No confidence differentiation | Provenance-based scoring in `confidence_scorer.py` |
| L4 | 10-K/A has 0.0 confidence | Documented; needs data-layer fix |
| L6 | Missing `__all__` | Defined in `__init__.py` |
| L9 | RRF passes dummy scores | Now passes actual similarity/bm25 scores |
| L10 | Regex backtracking risk | Line-bounded pattern without DOTALL |
| L11 | Frontend API hardcoded | Uses `VITE_API_BASE` env var |

---

## ⚠️ Outstanding Issues

### P1 - Security (User Action Required)

| # | Issue | File | Action |
|---|-------|------|--------|
| 2 | Real API keys in `.env` | `.env` | Rotate keys; use secrets manager |

### P2 - Architecture & Design

| # | Issue | File | Action |
|---|-------|------|--------|
| 17 | Two parallel RAG implementations | `asymmetric_rag.py` vs `rag_engine.py` | Consolidate or deprecate one |
| 20 | Module-level global state (18+ vars) | Multiple | Encapsulate in config class |

### P3 - Code Quality

| # | Issue | File | Action |
|---|-------|------|--------|
| 32 | `warnings.filterwarnings` too broad | `main.py` | Already targeted; low priority |

### Audit Report - Outstanding

| ID | Issue | Action |
|----|-------|--------|
| C1 | API keys in `.env` | Rotate keys |
| L2 | Query instruction prefix | Verify against Qwen3 docs |

---

## Summary

| Category | Resolved | Outstanding |
|----------|----------|-------------|
| P0 Critical | 1 | 0 |
| P1 Security | 13 | 1 (user action) |
| P2 Architecture | 6 | 2 |
| P3 Code Quality | 11 | 1 |
| Audit Report | 15 | 2 |
| **Total** | **46** | **6** |
