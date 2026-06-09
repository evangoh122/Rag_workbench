# Security Audit Report — RAG Workbench

**Auditor:** Manus AI
**Date:** 2026-06-09
**Branch:** `manus` (based on `fix/audit-corrections`)

---

## Executive Summary

The codebase demonstrates **good security hygiene** overall. No critical vulnerabilities were found that would allow remote code execution or data exfiltration in the current deployment model (single Docker container on Hugging Face Spaces). However, several medium-severity issues should be addressed before production deployment.

---

## Findings

### PASS — No Issues Found

| Category | Status | Notes |
|----------|--------|-------|
| Hardcoded secrets in source code | PASS | `.env` is in `.gitignore`, `.env.example` uses placeholder values |
| `eval()` / `exec()` / `os.system()` | PASS | None found anywhere in the codebase |
| Unsafe deserialization (pickle/yaml.load) | PASS | Not used |
| Path traversal | PASS | No user-controlled file paths |
| Open redirect | PASS | No redirect endpoints |
| File upload | PASS | No upload endpoints exist |
| Secret logging | PASS | No API keys logged; only API URLs printed in eval scripts |
| `.env` tracked in git | PASS | Not tracked; `.gitignore` covers it |
| `data/` directory | PASS | Excluded from git via `.gitignore` |

---

### MEDIUM — Issues Requiring Attention

#### SEC-01: SQL Injection via `EMBEDDING_DIM` f-string (Low Risk)

**File:** `api/services/rag_engine.py` (lines 40, 180)
**Issue:** `Config.EMBEDDING_DIM` is interpolated directly into SQL via f-string:
```python
f"array_distance(embedding, ?::FLOAT[{Config.EMBEDDING_DIM}]) AS dist"
```
**Risk:** Low — `EMBEDDING_DIM` is a hardcoded class constant (`768`), not user-controlled. However, if it were ever sourced from user input or an env var without validation, it would be injectable.
**Recommendation:** Validate that `EMBEDDING_DIM` is an integer at config load time. Add `assert isinstance(Config.EMBEDDING_DIM, int)`.

---

#### SEC-02: LLM-Generated SQL Execution (Medium Risk)

**File:** `api/services/chat_engine.py` (line 167)
**Issue:** The SQL mode executes LLM-generated SQL against DuckDB:
```python
f"SELECT * FROM ({sql}) AS chat_result LIMIT ?"
```
**Mitigations already in place:**
- `validate_read_only_sql()` blocks non-SELECT/WITH statements
- Blocked keyword list covers `CREATE`, `DROP`, `INSERT`, `DELETE`, `UPDATE`, `ATTACH`, `COPY`, `LOAD`, `PRAGMA`, `EXPORT`, `read_csv`, `read_parquet`, `read_json`, `httpfs`, etc.
- Statement length capped at 4096 chars
- Multi-statement (`;`) blocked
- DuckDB internal functions blocked
- Resource limits: `threads=2`, `memory_limit=256MB`
- Results limited to 100 rows

**Remaining risk:** DuckDB is a rapidly evolving database. New functions or syntax may bypass the blocklist. The `information_schema` and `duckdb_tables()` are not blocked, allowing schema enumeration.
**Recommendation:** Add `information_schema`, `duckdb_tables`, `duckdb_columns`, `duckdb_settings` to the blocked list. Consider running SQL in a read-only DuckDB connection (`:memory:` with attached read-only file).

---

#### SEC-03: Review Endpoints Unauthenticated by Default (Medium Risk)

**File:** `api/routes/review.py` (line 46-56)
**Issue:** If `REVIEW_API_KEY` env var is not set, all review endpoints (queue, metrics, drift, calibrate, decisions) are completely unauthenticated.
**Mitigations:** Warning logged at startup; `hmac.compare_digest` used for timing-safe comparison when key is set.
**Recommendation:** In production, make `REVIEW_API_KEY` mandatory (fail to start if unset). Document this in deployment guide.

---

#### SEC-04: CORS Wildcard Warning (Low Risk)

**File:** `api/middleware/cors_config.py`
**Issue:** If `CORS_ORIGINS=*` is set, all origins are allowed. The code correctly disables `allow_credentials` in this case.
**Mitigations:** Regex validation of origins; defaults to `http://localhost:3000`; wildcard disables credentials.
**Recommendation:** Document that `*` should never be used in production. Consider blocking `*` entirely outside development mode.

---

#### SEC-05: No Rate Limiting on SEC EDGAR Calls from User Requests (Low Risk)

**File:** `api/services/xbrl_client.py`
**Issue:** While the XBRL client has internal rate limiting (100ms between calls), there is no per-user rate limit on how many unique CIKs a user can query. A malicious user could trigger many SEC API calls.
**Mitigations:** Application-level rate limiter exists (30 req/min per IP in `api/middleware/rate_limit.py`); `lru_cache` on `fetch_company_facts` prevents repeated calls for same CIK.
**Recommendation:** Acceptable for current deployment. Monitor SEC rate limit headers in production.

---

#### SEC-06: SSRF via CIK Parameter (Low Risk)

**File:** `api/services/xbrl_client.py` (line 46)
**Issue:** The CIK is zero-padded and inserted into a fixed URL template:
```python
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
```
**Mitigations:** CIK is zero-padded with `zfill(10)` which constrains it to digits. The URL template is hardcoded to `data.sec.gov`.
**Recommendation:** Add explicit CIK validation: `if not cik.isdigit(): raise ValueError(...)`.

---

### INFORMATIONAL — Best Practice Suggestions

| Item | Recommendation |
|------|---------------|
| Dependency pinning | `requirements.txt` uses `>=` minimum versions. Pin exact versions for reproducibility. |
| No CSP headers | Add Content-Security-Policy headers in Nginx config for the frontend. |
| No request body size limit | FastAPI default is unlimited. Add `app.add_middleware(TrustedHostMiddleware)` and body size limits. |
| Eval scripts print API URLs | `evals/ragas_eval.py` and `evals/run_eval.py` print API base URLs. Not a secret leak but could expose internal infra. |

---

## Summary Table

| ID | Severity | Category | Status |
|----|----------|----------|--------|
| SEC-01 | Low | SQL Injection (theoretical) | Document for implementers |
| SEC-02 | Medium | LLM SQL Execution | Add schema enumeration blocklist |
| SEC-03 | Medium | Auth bypass by default | Make key mandatory in prod |
| SEC-04 | Low | CORS wildcard | Document; block in prod |
| SEC-05 | Low | SEC API abuse | Acceptable with current mitigations |
| SEC-06 | Low | SSRF (theoretical) | Add CIK digit validation |

---

## Conclusion

No critical or high-severity vulnerabilities were found. The codebase already implements defense-in-depth for its most dangerous feature (LLM SQL execution) with a comprehensive blocklist, resource limits, and statement validation. The primary recommendations for the implementing agents (MiMo/DeepSeek) are:

1. Add `information_schema` and `duckdb_*` to the SQL blocklist (SEC-02).
2. Make `REVIEW_API_KEY` mandatory in production mode (SEC-03).
3. Add CIK digit validation in `xbrl_client.py` (SEC-06).
4. These should be addressed as part of Phase 12 (Outstanding Integrations & Fixes).
