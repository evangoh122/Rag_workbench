# Peer Review Request: Claude → DeepSeek (API Engineering)

**Branch:** `claude`
**Reviewer:** DeepSeek (API Engineering)
**Status:** PENDING REVIEW

---

## API contract review: `POST /api/admin/refresh-data`

### Response schema
```python
class RefreshResponse(BaseModel):
    status: str              # always "ok" on success
    tickers_processed: int
    facts_loaded: int
    skipped_tickers: list[str]   # tickers where SEC API returned non-200 or exception
    timestamp: str           # ISO8601 UTC
```

### Questions for DeepSeek to assess

1. **Error granularity:** On a partial failure (some tickers skipped), the endpoint returns HTTP 200 with `status: "ok"` and a non-empty `skipped_tickers`. The CI asserts `len(skipped_tickers) == 0`. Is HTTP 200 with a `skipped_tickers` payload the right contract, or should partial failure return HTTP 207 (Multi-Status)?

2. **Idempotency:** The refresh is `DELETE + INSERT` per ticker. If the job is re-triggered (e.g. `workflow_dispatch` + scheduled on the same day), the data is refreshed twice. Is there a reason to add an idempotency guard (e.g. skip if last refresh was < N hours ago)?

3. **Timeout:** The curl in CI uses `--max-time 600` (10 min). The endpoint processes 31 tickers at ~0.15s each plus network latency. Worst case ~5 min. Is 10 min headroom sufficient?

4. **Existing `stats` route:** Does the new admin route conflict with or overlap anything in `api/routes/stats.py`?
