# Orchestrator Task — 2026-06-07
Feature: (A) Fix App.tsx violations + (B) Phase 1 PLAN-02 (EdgarTools Adapter)
Status: pending

---

## Task A — Fix frontend/src/App.tsx legacy violations (start immediately, independent)

These violations pre-date the frontend mandate and must be fixed before any new component
work is added. They are fully independent of Phase 1 backend work.

### Files
- frontend/src/App.tsx

### Violations to fix

| Line | Violation | Fix |
|------|-----------|-----|
| ~45  | `axios.post(...)` called inline | Extract to `frontend/src/api/chat.ts`; import and call from there |
| ~13  | `data?: any[]` — untyped | Change to `Record<string, unknown>[]` |
| ~60  | `catch (err: any)` — untyped | Change to `catch (err: unknown)` |
| ~147 | `(val: any, j)` — untyped | Derive type from row type |

Also: Check if `<ReactMarkdown>` is used anywhere without `disallowedElements={['script','iframe']}`.
If found, add the prop — this is a live XSS vector.

### Acceptance Criteria
- No `any` type annotations remain in App.tsx
- `axios.post` call is replaced with an import from `frontend/src/api/chat.ts`
- `<ReactMarkdown>` (if present) has `disallowedElements={['script','iframe']}` and raw HTML passthrough disabled
- TypeScript strict mode compiles with 0 errors: `npx tsc --noEmit`

---

## Task B — Execute Phase 1 PLAN-02 (EdgarTools Adapter) — START AFTER MIMO PUSHES PLAN-01

**Unblocks when:** `api/models/eval_types.py` appears on main (MIMO's commit `feat(phase-1): define eval_types dataclasses (PLAN-01)`)

Full plan is at: `.planning/phases/01-data-structures-reader-adapter/01-PLAN-02.md`
Read that file first — it has the verbatim code and exact acceptance criteria.

### Your Tasks (Wave 2)
- [ ] Add `edgartools>=2.26.0` to `requirements.txt` and install it
- [ ] Create `api/services/edgar_adapter.py` with `fetch_filing(cik, accession) -> ExtractionResult`
      — uses EdgarTools ONLY, no custom EDGAR/XBRL parser (CONSTRAINT-009)
      — XBRL facts → Provenance.XBRL; HTML tables → Provenance.STRUCTURED_TABLE
- [ ] Create `tests/test_edgar_adapter.py` with fixture-based unit tests (no network required)
      and a `@skipUnless(EDGAR_USER_AGENT)` integration smoke test
- [ ] Update `api/services/__init__.py` to re-export `fetch_filing` and `EdgarAdapterError`

### Files
- requirements.txt                    (update)
- api/services/edgar_adapter.py       (create)
- tests/test_edgar_adapter.py         (create)
- api/services/__init__.py            (update)

### Acceptance Criteria
- `python -c "from api.services.edgar_adapter import fetch_filing, EdgarAdapterError; print('OK')"` exits 0
- `python -m pytest tests/test_edgar_adapter.py -v -k "not smoke"` passes with 0 failures
- `grep -rn "xml.etree\|lxml\|xbrl\|beautifulsoup" api/services/edgar_adapter.py` returns 0 matches
- `grep "Provenance.XBRL" api/services/edgar_adapter.py` and `grep "Provenance.STRUCTURED_TABLE" api/services/edgar_adapter.py` both return results

### Key constraint
All SEC data parsing is delegated to EdgarTools — no custom parser code anywhere.
The adapter reads `EDGAR_USER_AGENT` from environment; do NOT hard-code an email.

### After completion
Commit with message: `feat(phase-1): add EdgarTools adapter (PLAN-02)`
Push to main.
