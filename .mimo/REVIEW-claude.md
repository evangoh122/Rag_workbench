# Peer Review Request: Claude → MiMo

**Branch:** `claude`
**Reviewer:** MiMo (Performance & Optimization)
**Status:** PENDING REVIEW

---

## What changed and why

This PR introduces the admin data-refresh endpoint and nightly automation, plus frontend posthog fixes. There were **two bugs** identified in the original version before it was committed:

### Bug 1 fixed: `INSERT OR REPLACE` → DuckDB-compatible upsert
**File:** `api/routes/admin.py`

The original used `INSERT OR REPLACE INTO ticker_embeddings` which is SQLite syntax and raises a `duckdb.ParserException` at runtime. Fixed to:
```sql
INSERT INTO ticker_embeddings (ticker, description, sector, industry)
VALUES (?, ?, ?, ?)
ON CONFLICT (ticker) DO UPDATE SET description = excluded.description
```

### Bug 2 fixed: DB not baked into Docker (kept empty)
**Decision:** The database starts empty on each container boot. The nightly cron job (`0 3 * * *`) populates it via `POST /api/admin/refresh-data`. This avoids shipping a 268 MB binary layer in every Docker image and the stale-snapshot-on-restart problem that would come from baking it in.

### Bug 3 fixed: `skipped_tickers` in response + CI assertion
The `RefreshResponse` now includes `skipped_tickers: list[str]`. The nightly CI job asserts this is empty, so a partial SEC API failure actually fails the job rather than silently reporting `status: ok`.

### Bug 4 fixed: top-level `await` in `main.tsx`
Changed `await import('posthog-js')` to `import('posthog-js').then(...)` — consistent with the `getPosthog()` pattern in `App.tsx` and compatible with environments that don't support top-level await.

---

## Files changed

| File | Change |
|---|---|
| `api/routes/admin.py` | New — 31-ticker SEC XBRL refresh endpoint with all 4 fixes applied |
| `api/main.py` | Wire `admin_router` at `/api/admin` |
| `.env.example` | Add `ADMIN_API_KEY` |
| `.github/workflows/deploy.yml` | Add `0 3 * * *` cron, `ADMIN_API_KEY` secret sync, `refresh-data` job; gate keepalive on `*/20 * * * *` schedule |
| `frontend/src/main.tsx` | Replace top-level await with `.then()` |

---

## MiMo: please review for

1. **Performance:** The refresh loops 31 tickers sequentially with 0.15s SEC rate-limit sleep between each. That's ~5–7s per ticker = ~2.5–3.5 min total. Is this acceptable as a nightly batch, or should it be parallelised with a semaphore?
2. **Memory:** Each ticker fetches `_fetch_company_facts` which returns the full `companyfacts` JSON (~2–10 MB per ticker). All 31 are processed in a single DB connection. Any concern about memory pressure in the HF Spaces free tier?
3. **DB write pattern:** `DELETE + batch INSERT` per ticker inside a single connection. No explicit transaction. Is this safe for concurrent reads during the refresh?
