# Issue Tracker

**Last updated:** 2026-06-09 (claude branch — manus Phase 12-15 merged)

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

## ⚠️ Outstanding Issues

### P1 - Security (User Action Required)

| # | Issue | File | Action |
|---|-------|------|--------|
| 2 | Real API keys in `.env` | `.env` | Rotate keys; use secrets manager (local env — deferred) |
| 15 | No API key scoping | `auth.py` | Design: implement key scopes for read/write/admin tiers |

### P2 - Architecture & Design

| # | Issue | File | Action |
|---|-------|------|--------|
| 20 | Module-level global state (18+ vars) | Multiple | Encapsulate in config class |

### P3 - Code Quality

| # | Issue | File | Action |
|---|-------|------|--------|
| 32 | `warnings.filterwarnings` too broad | `main.py` | Already targeted; low priority |
| 35 | `print()` in run.py | `run.py` | Acceptable for CLI output |
| 40 | DuckDB file possibly tracked | `data/` | Not tracked; verified |

### Audit Report - Outstanding

| ID | Issue | Action |
|----|-------|--------|
| C1 | API keys in `.env` | Rotate keys (local env — deferred) |
| L2 | Query instruction prefix | Verify against Qwen3 docs |
| L4 | 10-K/A has 0.0 confidence | Add "no data" signal |

---

## Summary

| Category | Resolved | Outstanding |
|----------|----------|-------------|
| P0 Critical | 1 | 0 |
| P1 Security | 13 | 2 (user action) |
| Manus Audit (SEC-02/03/06) | 3 | 0 |
| P2 Architecture | 7 | 1 |
| P3 Code Quality | 10 | 3 |
| Guardrails (GR-01-06) | 6 | 0 |
| Audit Report | 16 | 3 |
| **Total** | **56** | **9** |
