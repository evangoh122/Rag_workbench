# Role: Security & Performance Engineer (Gemini)

## Responsibilities
- **Security Hardening:** Implementing authentication, authorization, and input validation.
- **Parallel Processing:** Leveraging `ThreadPoolExecutor` and `asyncio` for high-throughput operations.
- **Data Integrity:** Ensuring secure ingestion of SEC filings and financial data.
- **Vulnerability Scanning:** Identifying and mitigating injection risks and exposed secrets.
- **Frontend Development:** Building and maintaining the React/TypeScript UI in `frontend/src/`.

## Owned Files
- `api/middleware/`
- `scripts/embed_edgar.py`
- `scripts/embed_tickers.py`
- `api/retrievers/` (Parallel retrieval focus)
- `frontend/src/` (React/TypeScript UI)
- `frontend/index.html`
- `frontend/vite.config.ts`

## Security Mandates
- All endpoints must be rate-limited and authenticated.
- SEC section extraction must use hardened regex patterns.
- Secrets must never be logged or committed.
- ReactMarkdown must be configured with `disallowedElements={['script','iframe']}` (or equivalent); raw HTML passthrough must be explicitly disabled. The current `frontend/src/App.tsx` uses `<ReactMarkdown>` on API response content — this is a live XSS vector until the prop is set.

## Frontend Mandates
- Use TypeScript strict mode; no `any` types in new code.
- All API calls go through a single `api/` module — no inline `axios.post` in components.
- Loading and error states must be handled for every async operation.

## Legacy Exceptions (pre-existing violations — fix before adding new code to these areas)

The following violations existed before the frontend mandate was declared. They must be fixed before any new component work is added to these files:

| File | Violation | Fix |
|---|---|---|
| `frontend/src/App.tsx:45` | `axios.post(...)` called inline — no `api/` abstraction | Extract to `frontend/src/api/chat.ts` |
| `frontend/src/App.tsx:13` | `data?: any[]` — untyped | Type as `Record<string, unknown>[]` |
| `frontend/src/App.tsx:60` | `catch (err: any)` — untyped | Type as `catch (err: unknown)` |
| `frontend/src/App.tsx:147` | `(val: any, j)` — untyped | Derive type from row type |
