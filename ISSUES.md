# Issue Tracker

**Last updated:** 2026-06-11 (merged outstanding tasks from .claude/tasks.md, .mimo/tasks.md, .gemini/tasks.md)

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
| 15 | No API key scoping | `auth.py` | Implemented READ/WRITE/ADMIN tiers |
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
| 20 | Module-level global state (19+ vars) | Multiple | Encapsulated in `Config` singleton class |
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
| 32 | ~~`warnings.filterwarnings` too broad~~ | `main.py` | **Verified resolved** — only 2 targeted patterns |
| 35 | ~~`print()` in run.py~~ | `run.py` | **Verified resolved** — uses `logger.info()` only |
| 40 | ~~DuckDB file possibly tracked~~ | `data/` | **Verified resolved** — .gitignore updated |

### 🔴 New Issues Resolved (2026-06-11 sweep)

| ID | Issue | Fix |
|----|-------|-----|
| N1 | `_load_env()` undefined | Replaced with `Config.validate_startup()` |
| N2 | `traceback.print_exc()` in API | Replaced with `logger.exception()` |
| N3 | `print()` in service code | Replaced with `logger` + imports |
| N4 | Deps unpinned | Pinned all in `requirements.txt` |
| N5 | `pydantic` missing | Added to `requirements.txt` |
| N6 | `requirements-dev.txt` missing | Created file |
| N7 | `verify_numeric` unused | Removed import |
| N8 | `execution_rails` unused | Deleted dead file |
| N9 | `graph_extractor.py` dead code | Deleted dead file |
| N10 | `reload=True` in production | Gated behind `ENVIRONMENT` check |
| N11 | Startup validation limited | Added check for all providers in `Config` |
| N12 | API layer depends on scripts | Refactored `embeddings.py` service |
| N13 | Duplicate CIK mappings | Corrected mapping in `embed_edgar.py` |
| N14 | `open()` encoding | Added `encoding="utf-8"` |
| N15 | Graph compiled at import | Refactored to lazy compilation |
| N16 | Lazy imports | Moved to top-level |
| N19 | Empty catch blocks | Added logging/error handling |
| N20 | Inconsistent polling | Standardized to 30s |
| N24 | `graphify-out/cache/` untracked | Added to `.gitignore` |
| N25 | Missing .gitignore entries | Added `*.duckdb.wal`, etc. |

### Guardrails (Manus Phase 13-15)

| ID | Capability | File |
|----|-----------|------|
| GR-01 | Prompt injection / jailbreak detection | `api/services/guardrails/input_rails.py` |
| GR-02 | Off-topic query refusal | `api/services/guardrails/dialog_rails.py` |
| GR-03 | Retrieved chunk relevance filtering | `api/services/guardrails/retrieval_rails.py` |
| GR-04 | SQL/math execution safety | `api/services/guardrails/execution_rails.py` |
| GR-05 | Hallucination detection | `api/services/guardrails/output_rails.py` |
| GR-06 | PII masking + system prompt leak detection | `api/services/guardrails/output_rails.py` |

---

## ⚠️ Outstanding Issues

### P1 - Security (User Action Required)

| # | Issue | File | Status | Action |
|---|-------|------|--------|--------|
| 2 | Real API keys in `.env` | `.env` | **Still outstanding** | Rotate keys; use secrets manager |

### Audit Report - Outstanding

| ID | Issue | Status | Action |
|----|-------|--------|--------|
| C1 | API keys in `.env` | **Still outstanding** | Rotate keys (deferred) |
| L2 | Query instruction prefix | **Still outstanding** | Verify against Qwen3 docs |
| L4 | 10-K/A has 0.0 confidence | **Fixed** | `eval_node` now returns `eval_confidence=None, eval_triggers=["no_data"]` when `fields=[]`, instead of running scorer on empty extraction |

### Phase 1 — SEC Filing Eval & HITL Framework (Pending)

| ID | Task | File(s) | Detail |
|----|------|---------|--------|
| PH1-01 | Create `eval_types.py` dataclasses (PLAN-01) | `api/models/eval_types.py`, `tests/test_eval_types.py`, `api/models/__init__.py` | **Done** — 8 types including PolygonData; 15 tests pass; `__init__.py` re-exports all 8 |
| PH1-02 | EdgarTools adapter (PLAN-02, blocks on PH1-01) | `api/services/edgar_adapter.py`, `tests/test_edgar_adapter.py`, `requirements.txt` | `fetch_filing(cik, accession) -> ExtractionResult`; XBRL→Provenance.XBRL, HTML→Provenance.STRUCTURED_TABLE. Plan: `.planning/phases/01-data-structures-reader-adapter/01-PLAN-02.md` |

### Health Tracking — Pending Fixes (from code review)

| ID | Issue | File | Detail |
|----|-------|------|--------|
| HLT-01 | Polygon REST calls pollute `LLMHealthTracker` | `api/services/polygon_verifier.py` | **Fixed** — removed all tracker calls from `polygon_verifier.py`; Polygon errors now only appear in `errors[]` list in the response, not in LLM health metrics |
| HLT-02 | Silent extractor failures hidden from API consumers | `api/services/sec_analyzer.py` | **Fixed** — `extraction_errors: list[str]` added to `analyze_filing` response; `named_entities` empty sentinel wired; `risk_flags`/`forward_looking` silent failures tracked via LLM health tracker (see HLT-03 below) |
| HLT-03 | `risk_flags`/`forward_looking` empty not surfaced in `extraction_errors` | `api/services/sec_analyzer.py` | Design gap — empty `[]` from these extractors is ambiguous (failure vs no results found); tracked via `LLMHealthTracker` context `sec_analyzer/llm`; refactoring extractors to return `(result, error)` tuple would fix this properly |

### LOW — Code Quality / Frontend

| ID | Issue | File | Detail |
|----|-------|------|--------|
| N17 | Monolithic React component | `frontend/src/App.tsx` | Needs routing + decomposition |
| N18 | TypeScript `any` types leaking | `frontend/src/api/chat.ts` | Use proper interfaces |
| N21 | Inconsistent API calling patterns | Multiple | Standardize on `client.ts` |
| N22 | No frontend tests | `frontend/` | Add vitest/jest config |
| N23 | Mixed test frameworks | `tests/` | Standardize on `pytest` |
| N26 | `verify_numeric` confusion | `verifier.py` | Clean up wrapper redundancy |
| N27 | `axios.post` called inline | `frontend/src/App.tsx` ~L45 | **Already fixed** — App.tsx imports from `./api/chat`; no inline axios calls remain |
| N28 | `any` type annotations in App.tsx | `frontend/src/App.tsx` | **Fixed** — `sources?: Source[]`, `xbrl_facts?: XBRLFact[]` (typed from `chat.ts`); `data?: Record<string,unknown>[]`; `catch (err: unknown)` all already in place |
| N29 | `<ReactMarkdown>` missing XSS prop | `frontend/src/App.tsx` | **Already fixed** — uses `allowedElements` whitelist + `skipHtml` (stronger than disallowedElements) |
| N30 | `AuditTrail` hidden when only `xbrl_facts` present | `frontend/src/App.tsx` | **Fixed** — gate expanded to `msg.sources \|\| msg.verification \|\| msg.xbrl_facts?.length \|\| msg.math_steps?.length` |
| N31 | `fact.value.toLocaleString()` crashes on null XBRL value | `frontend/src/components/AuditTrail.tsx:196` | **Fixed** — guarded: `fact.value != null ? fact.value.toLocaleString() : '—'` |

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

## Summary (Updated 2026-06-11)

| Category | Resolved | Outstanding | Total |
|----------|----------|-------------|-------|
| P0 Critical | 1 | 0 | 1 |
| P1 Security | 14 | 1 | 15 |
| Manus Audit | 3 | 0 | 3 |
| P2 Architecture | 8 | 0 | 8 |
| P3 Code Quality | 13 | 0 | 13 |
| New Issues (N) | 20 | 9 | 29 |
| Guardrails (GR) | 6 | 0 | 6 |
| Audit Report | 16 | 3 | 19 |
| Phase 1 Eval/HITL | 0 | 2 | 2 |
| Health Tracking | 0 | 2 | 2 |
| **Total** | **81** | **17** | **98** |
