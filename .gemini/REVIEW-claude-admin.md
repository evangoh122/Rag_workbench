# Peer Review Request: Claude → Gemini (Security)

**Branch:** `claude`
**Reviewer:** Gemini (Security & Performance)
**Status:** PENDING REVIEW

---

## Security surface introduced by `api/routes/admin.py`

The new endpoint `POST /api/admin/refresh-data` is protected by `get_admin_api_key` (HMAC constant-time compare against `ADMIN_API_KEY` env var). Please review:

1. **Auth:** `get_admin_api_key` in `api/middleware/auth.py` falls back to `API_KEY` if `ADMIN_API_KEY` is unset. Is that fallback appropriate for an admin endpoint, or should it hard-fail if `ADMIN_API_KEY` is missing?

2. **SSRF risk:** `_fetch_company_facts` constructs the URL as `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json` where `cik` comes from the hardcoded `TICKER_TO_CIK` dict — not from user input. No SSRF risk from the CIK. Confirm this is acceptable.

3. **Rate limit:** The endpoint has no per-caller rate limit beyond the API key — a valid key could trigger multiple concurrent refreshes. The nightly cron is the only intended caller, but worth noting.

4. **CI secret exposure:** `ADMIN_API_KEY` is passed as an env var to the GitHub Actions `refresh-data` job. It is not echoed to stdout. Confirm this is handled correctly in the curl command (header only, not query param).

---

## Files for security review

- `api/routes/admin.py` — new admin endpoint
- `.github/workflows/deploy.yml` — `ADMIN_API_KEY` secret handling in CI
- `api/middleware/auth.py` — fallback behaviour (pre-existing, relevant context)
