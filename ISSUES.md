# Issue Tracker

## P0 - Critical Bugs (Will Crash)

### 1. Missing `logger` import in `edgar_adapter.py`
- **File:** `api/services/edgar_adapter.py:185`
- **Description:** `logger.warning(...)` called but `logger` never imported. Any code path that hits a failed XBRL statement parse or failed financials extraction will raise `NameError`.
- **Status:** ✅ FIXED - Code now uses `pass` instead of logger for exception handling.

### 2. Missing `Config` import in `companyfacts_client.py`
- **File:** `api/services/companyfacts_client.py:28,31,32,66`
- **Description:** Uses `Config.EDGAR_USER_AGENT` and `Config.SEC_RATE_LIMIT` but never imports `Config`. Raises `NameError` on instantiation.
- **Status:** ✅ FIXED - Import already present at line 8.

### 3. `asyncio.run()` misuse in Streamlit dashboard
- **File:** `dashboard.py:59-61`
- **Description:** `fetch_metrics()` calls `asyncio.run(get_dashboard_metrics())` which fails inside Streamlit's existing event loop. Also bypasses FastAPI middleware and dependency injection.
- **Status:** ✅ FIXED - Now uses `requests` to call API endpoint with `@st.cache_data(ttl=30)`.

### 4. Race condition in `_rag_instance` singleton
- **File:** `asymmetric_rag.py:864-867`
- **Description:** `get_rag()` uses `global _rag_instance` without a lock. If two threads call `ask_rag()` simultaneously at startup, both could construct separate `AsymmetricFinancialRAG` instances, doubling memory usage. Compare to `get_rag_chain()` in `rag_engine.py:290-296` which correctly uses `threading.Lock()`.
- **Fix:** Add `threading.Lock()` around the initialization check.

---

## P1 - Security Issues

### 5. Real API keys present in `.env` file
- **File:** `.env:6,9-10,18,21`
- **Description:** The `.env` file contains real API keys: `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `DEEPSEEK_API_KEY`, and `XIAOMI_API_KEY` in plaintext on disk. Could be accidentally committed (despite `.gitignore`), leaked via backup, or exposed through directory listing. `XIAOMI_API_KEY` is undocumented -- not in `.env.example`.
- **Fix:** Move secrets to environment variables or a secret manager; rotate exposed keys; add `XIAOMI_API_KEY` to `.env.example` or document its purpose.

### 6. Timing-attack vulnerable API key comparison
- **File:** `api/middleware/auth.py:16`
- **Description:** `if api_key != expected_key:` uses Python's default string comparison which short-circuits on first differing byte. Vulnerable to timing side-channel attacks.
- **Status:** ✅ FIXED - Now uses `hmac.compare_digest()`.

### 7. Silent auth bypass when no API key configured
- **File:** `api/middleware/auth.py:12-14`
- **Description:** If `API_KEY` env var is not set, middleware returns `None` (allows all requests) with no warning logged. Unconfigured deployment is completely open.
- **Status:** ✅ FIXED - Now logs warning when API_KEY not set.

### 8. LLM-generated SQL injection surface
- **File:** `api/services/chat_engine.py:153`
- **Description:** `sql` variable from LLM response is interpolated via f-string into DuckDB query. Blocklist validator (`validate_read_only_sql`) is not exhaustive - `COPY` and other DuckDB-specific syntax variants may bypass it.
- **Status:** ✅ FIXED - LIMIT now parameterized with `?` placeholder.

### 9. SQL injection via keyword fallback (`_keyword_fallback`)
- **File:** `api/services/rag_engine.py:55-74`
- **Description:** `_keyword_fallback` constructs SQL conditions from user query words: `conditions = " OR ".join("description ILIKE '%' || ? || '%' ..." for _ in words)`. Empty or malicious `words` lists produce malformed SQL. No length limit on `words`, potentially leading to query explosion (1000-word query = 2000 parameter bindings).
- **Fix:** Add `maxsplit` or token limit to `query.split()`, validate word list length before constructing SQL.

### 10. SQL injection via f-string in `rag_engine.py` and `asymmetric_rag.py`
- **Files:** `api/services/rag_engine.py:67,129,175,211`, `asymmetric_rag.py:478,522`
- **Description:** Multiple instances of f-string SQL construction where `conditions` are built from `" OR ".join(...)` of user-controlled query words. While values are parameterized with `?`, the structural SQL is built via string interpolation.
- **Fix:** Use DuckDB's prepared statement API or construct queries programmatically rather than via f-strings.

### 11. No input validation on `ChatRequest.message`
- **File:** `api/models/schemas.py:4-6`
- **Description:** `ChatRequest` accepts `message: str` with no length constraint or content sanitization. A 10MB message gets passed to LLM APIs (incurring costs) and DuckDB SQL queries.
- **Fix:** Add `max_length=2000` or similar Pydantic constraint; add content sanitization.

### 12. No input validation on `history` field
- **File:** `api/models/schemas.py:6`
- **Description:** `history: Optional[List[Dict[str, str]]]` has no length limit. Malicious client could send thousands of messages, causing excessive LLM token usage and API costs.
- **Fix:** Add `max_length` constraint or enforce max list size.

### 13. Rate limiter lacks thread safety, persistence, and dict iteration safety
- **File:** `api/middleware/rate_limit.py:6-7,20-22`
- **Description:** `_rate_limits` dict and `_request_count` modified without locking. In-memory only -- doesn't survive restarts or work across multiple workers. `request.client.host` can return `None` behind reverse proxy. Additionally, periodic stale IP cleanup iterates `_rate_limits.items()` and deletes entries without holding a lock, risking `RuntimeError: dictionary changed size during iteration` under concurrent access.
- **Status:** ✅ FIXED - Now uses `asyncio.Lock()` for all mutations, reads real IP from `X-Forwarded-For` header.

### 14. Audit scripts expose codebase to external LLM APIs
- **Files:** `scripts/anthropic_audit.py:10`, `scripts/deepseek_audit.py:10`
- **Description:** These scripts read real API keys via `os.getenv()` and send all codebase files to external LLM auditors. If accidentally invoked, they leak proprietary code. `BASE_URL` constants point to commercial API endpoints -- requests incur real costs.
- **Fix:** Gate with explicit confirmation flag; add `.gitignore` exclusions; document purpose and risks.

### 15. No API key scoping -- same key for all endpoints
- **File:** `api/middleware/auth.py:8-21`
- **Description:** `get_api_key()` applies the same API key check to all endpoints (`/api/chat`, `/api/metrics`). No scoped keys, read-only vs. admin keys, or key rotation mechanism.
- **Fix:** Implement key scopes or at minimum document this limitation.

### 16. No CORS origin validation
- **File:** `api/main.py:20`
- **Description:** `allow_origins=os.getenv("CORS_ORIGINS", "...").split(",")` naively splits on commas. Any string in the env var (e.g., `"http://evil.com"`) is accepted as a valid origin.
- **Fix:** Validate that each origin string is a well-formed URL.

---

## P2 - Architecture & Design Issues

### 17. Two parallel RAG implementations diverge
- **Files:** `asymmetric_rag.py` (901 lines) vs `api/services/rag_engine.py` (327 lines)
- **Description:** `asymmetric_rag.py` implements standalone RAG with Ollama/BM25/RRF. `rag_engine.py` implements LangChain-based RAG with Gemini/DuckDB. API route calls `rag_engine.py` only. `asymmetric_rag.py:870` has its own `ask_rag` that is never called. Both duplicate identical retrievers (DuckDB vector search, EDGAR facts query, price context query) with nearly identical SQL.
- **Fix:** Consolidate into single implementation or extract shared retrieval logic into a common base.

### 18. Top-level `edgar` import forces install
- **File:** `api/services/companyfacts_client.py:7`
- **Description:** `from edgar import Company, set_identity` at module level. If `edgartools` not installed, importing `api.services` crashes entirely. `edgar_adapter.py` correctly defers imports to function scope.
- **Status:** ✅ FIXED - Import now deferred to function scope.

### 19. Inconsistent logging frameworks
- **Files:** `xbrl_validator.py`, `semantic_validator.py`, `companyfacts_client.py` use stdlib `logging`; `rag_engine.py`, `chat_engine.py`, `asymmetric_rag.py` use `loguru`
- **Description:** Log configuration set via `loguru` in `main.py` does not apply to stdlib `logging` modules. Output format and levels are inconsistent.
- **Fix:** Standardize on one framework (prefer `loguru` since it's the primary).

### 20. `api/services/__init__.py` eagerly imports all services
- **File:** `api/services/__init__.py:1-17`
- **Description:** Imports from `edgar_adapter`, `companyfacts_client`, etc. at module load time. Any code importing `api.services` will fail if optional dependencies (like `edgartools`) are missing.
- **Fix:** Use lazy imports or remove re-exports from `__init__.py`.

### 21. `load_dotenv()` called 7 times across codebase
- **Files:** `main.py:18`, `api/config.py:7`, `asymmetric_rag.py:883`, `scripts/calibrate.py:26`, `scripts/shadow_run.py:31`, `scripts/anthropic_audit.py:7`, `scripts/deepseek_audit.py:8`
- **Description:** Multiple calls create inconsistent initial states depending on import order -- some modules read `os.getenv()` at module level before `load_dotenv()` is called in the entry point.
- **Fix:** Single `load_dotenv()` call in the application entry point only.

### 22. Module-level global state across 18+ variables
- **Files:** `asymmetric_rag.py:37-59`, `embed_tickers.py:19`, `rate_limit.py:6-7`
- **Description:** Module-level variables read from `os.getenv()` at import time, globals for embeddings and rate limits. Makes testing difficult and creates hard-to-debug import order dependencies.
- **Fix:** Encapsulate in a configuration class with lazy initialization.

### 23. No retry/backoff for SEC API network errors
- **File:** `api/services/edgar_adapter.py:148-195`
- **Description:** `fetch_filing()` calls the SEC API with no retry logic. Network timeouts or rate-limiting fail immediately.
- **Fix:** Add exponential backoff and circuit breaker.

### 24. DuckDB opened `read_only=False` everywhere
- **File:** `api/db/database.py:22`
- **Description:** `duckdb.connect(Config.DB_PATH, read_only=False)` -- chat/RAG endpoints only need read access. A bug in SQL generation producing a DDL statement could corrupt the database. `.env` comment on line 3 says "read-only for chat/RAG" which the code contradicts.
- **Fix:** Open read-only for query paths; use a separate write connection for ingestion.

### 25. DuckDB lock serializes all DB access
- **File:** `api/db/database.py:36`
- **Description:** The lock is held for the entire `execute()` call including query execution, serializing ALL database access to a single thread. Defeats DuckDB's concurrent-read support.
- **Fix:** Use a read/write lock or connection pool.

---

## P3 - Code Quality & Bugs

### 26. Missing `requests` in `requirements.txt`
- **File:** `requirements.txt`
- **Description:** `dashboard.py` and audit scripts use `import requests` but it's not listed. May fail on fresh install.
- **Status:** ✅ FIXED - Added `requests>=2.31.0` to requirements.txt.

### 27. Test assertion wrong for `window_size`
- **File:** `tests/test_metrics_endpoint.py:58`
- **Description:** Asserts `data["window_size"] == 500` but endpoint returns `len(decisions)` (would be 6 given test data). Test will fail when run.
- **Fix:** Change assertion to match actual returned value.

### 28. Deprecated `datetime.utcnow()`
- **File:** `scripts/shadow_run.py:120`
- **Description:** `datetime.utcnow()` deprecated in Python 3.12+. Rest of codebase correctly uses `datetime.now(timezone.utc)`.
- **Status:** ✅ FIXED - Now uses `datetime.now(timezone.utc)`.

### 29. No graceful shutdown - DuckDB connection leak
- **File:** `api/main.py`
- **Description:** No shutdown event handler to call `db_manager.close()`. `DatabaseManager` has `close()` method (database.py:41) but it's never invoked.
- **Status:** ✅ FIXED - Now uses `lifespan` context manager with shutdown handler.

### 30. Deprecated `@app.on_event("startup")`
- **File:** `api/main.py:30`
- **Description:** `@app.on_event("startup")` deprecated in FastAPI 0.109+.
- **Status:** ✅ FIXED - Migrated to `lifespan` context manager pattern.

### 31. Duplicate imports in `calibrate.py`
- **File:** `scripts/calibrate.py:24-28`
- **Description:** `import sys` on lines 24 and 27. `from pathlib import Path` on lines 25 and 28.
- **Status:** ✅ FIXED - Duplicate imports removed.

### 32. Unused imports
- **Files:** `run.py:2` (`import os`), `dashboard.py:6` (`import time`), `dashboard.py:8` (`import json`)
- **Description:** Imported but never used.
- **Status:** ✅ FIXED - Unused imports removed.

### 33. Missing `pytest`/`httpx` in requirements
- **File:** `requirements.txt`
- **Description:** Tests use `pytest` and `TestClient` (requires `httpx`) but neither listed.
- **Status:** ✅ FIXED - Created `requirements-dev.txt` with pytest, httpx, and ruff.

### 34. DuckDB VSS extension load failure silently swallowed
- **Files:** `api/db/database.py:28`, `scripts/embed_tickers.py:77`, `scripts/embed_edgar.py:148`
- **Description:** `conn.execute("LOAD vss")` wrapped in bare `except Exception: pass`. If VSS required for vector search, later failures will be confusing.
- **Status:** ✅ FIXED - Now logs warning when VSS fails to load.

### 35. `seed_metrics.py` accesses private `db_manager._conn_lock`
- **File:** `scripts/seed_metrics.py:75`
- **Description:** Directly accesses private attribute. Breaks encapsulation.
- **Status:** ✅ FIXED - Added public `lock()` method to DatabaseManager.

### 36. Dead code in `api/retrievers/vector_store.py`
- **File:** `api/retrievers/vector_store.py`
- **Description:** `VectorStoreRetriever` defined but never imported or used anywhere. Actual retrieval done by `DuckDBVectorRetriever` in `rag_engine.py`.
- **Fix:** Remove or document intended future use.

### 37. `asymmetric_rag.py` opens new DuckDB connection per query
- **File:** `asymmetric_rag.py:791-797`
- **Description:** `_get_structured_context()` calls `duckdb.connect()` every invocation, bypassing `DatabaseManager` singleton.
- **Fix:** Use shared `DatabaseManager` instance.

### 38. `asymmetric_rag.py` uses MD5 for content hashing
- **File:** `asymmetric_rag.py:80`
- **Description:** `hashlib.md5()` used for deduplication. MD5 is slow on large inputs and has known collisions.
- **Status:** ✅ FIXED - Now uses Python's built-in `hash()`.

### 39. Dashboard polling has no caching
- **File:** `dashboard.py:55-63`
- **Description:** `fetch_metrics()` called on every Streamlit rerun (any interaction). Full DB query and metric computation each time.
- **Status:** ✅ FIXED - Added `@st.cache_data(ttl=30)`.

### 40. `edgartools` version constraint allows breaking v3.x
- **File:** `requirements.txt:23`
- **Description:** `edgartools>=2.26.0` allows 3.x which has breaking API changes (e.g., `get_filing()` removed).
- **Status:** ✅ FIXED - Pinned to `edgartools>=2.26.0,<3.0.0`.

### 41. `api/routes/__init__.py` missing `metrics` export
- **File:** `api/routes/__init__.py:1`
- **Description:** Only exports `chat`, not `metrics`. Inconsistent with actual route registration.
- **Status:** ✅ FIXED - Added `from . import metrics`.

### 42. BM25 index rebuilt from scratch on every restart
- **File:** `asymmetric_rag.py:590-592`
- **Description:** Loads all chunks from DuckDB and builds index in memory every time `initialize()` is called. No persistence.
- **Fix:** Serialize/deserialize BM25 index to disk.

### 43. Embedding computation is one-at-a-time
- **File:** `asymmetric_rag.py:122-128`
- **Description:** `_embed_batch()` iterates and calls `self.client.embeddings()` individually. Significant bottleneck for large ingestion.
- **Fix:** Use batch embedding API when available, or parallelize with asyncio.

### 44. Non-deterministic `hash()` for document deduplication
- **File:** `api/services/rag_engine.py:256`
- **Description:** `content_hash = hash(d.page_content)` -- Python's `hash()` is non-deterministic across runs (due to `PYTHONHASHSEED`). Two identical documents in separate runs may produce different hash values.
- **Fix:** Use `hashlib.md5()` or `hashlib.sha256()`.

### 45. `warnings.filterwarnings("ignore")` too broad
- **File:** `main.py:12-13`
- **Description:** Suppressing all `UserWarning` from `langchain_core` and urllib3 hides legitimate deprecation or behavior warnings.
- **Fix:** Use more targeted filters or suppress only specific warning messages.

### 46. `sys.path.insert(0, ...)` anti-pattern
- **Files:** `scripts/calibrate.py:24`, `scripts/shadow_run.py:28`
- **Description:** Manipulating `sys.path` at runtime is fragile and can cause import shadowing. Should be handled via proper package installation or `PYTHONPATH`.
- **Fix:** Use `pip install -e .` or set `PYTHONPATH` externally.

### 47. Bare `except Exception` swallowing critical errors
- **Files:** `api/services/edgar_adapter.py:57`, `api/services/companyfacts_client.py:118,174`, `scripts/embed_edgar.py:148`, `scripts/embed_tickers.py:77`
- **Description:** Swallows all exceptions including `MemoryError`, `KeyboardInterrupt`, and `SystemExit`. Masks genuine failures and makes debugging impossible.
- **Fix:** Catch specific exceptions or at minimum log the error before swallowing.

### 48. `print()` used instead of logger in production code
- **Files:** `run.py:5-6`, `scripts/seed_metrics.py:8,85`, `scripts/anthropic_audit.py:33,79-83`, `scripts/deepseek_audit.py:15-17,39,86-90`
- **Description:** Multiple files use `print()` for logging output instead of the configured `loguru` logger.
- **Fix:** Replace `print()` with `logger.info()` or `logger.debug()`.

### 49. `unsafe_allow_html=True` with database-sourced data
- **File:** `dashboard.py:117`
- **Description:** `st.markdown(..., unsafe_allow_html=True)` embeds `agreement["agreement_rate"]`, `data["window_size"]`, and `status_text` from the API/database into an HTML-enabled markdown block. If the database were compromised, malicious HTML/JS could execute in users' browsers.
- **Fix:** Sanitize values before embedding or avoid `unsafe_allow_html=True` for DB-sourced data.

### 50. `embed_tickers.py` opens DuckDB twice -- stale data risk
- **File:** `scripts/embed_tickers.py:50,74`
- **Description:** First connection reads data `read_only=True`, second connection writes embeddings. Data read in connection 1 could be stale by the time connection 2 writes.
- **Fix:** Use a single connection for the read-then-write workflow.

### 51. `_check_edgar_user_agent()` hardcodes example email
- **File:** `scripts/shadow_run.py:49-54`
- **Description:** Error message contains `'Acme Corp acme@example.com'` -- sets bad precedent of hardcoding placeholder credentials in source code.
- **Fix:** Reference a config variable instead.

### 52. Inconsistent provider key naming
- **File:** `asymmetric_rag.py:822-823`
- **Description:** `_synthesize()` defines a provider config that includes `"mimo"`, while `api/config.py`'s `get_provider_config()` does not. `asymmetric_rag.py` reads `MIMO_API_KEY` from environment but this key is undocumented in `.env.example`.
- **Fix:** Consolidate provider configs or document the divergence.

### 53. DuckDB `data/ibkr.duckdb` possibly tracked in repo
- **File:** `data/ibkr.duckdb`
- **Description:** 0-byte DuckDB file exists in `data/`. While `.gitignore` has `data/**/*.duckdb`, this file may have been tracked before the rule was added.
- **Fix:** Verify with `git ls-files data/ibkr.duckdb`; if tracked, remove with `git rm --cached`.
