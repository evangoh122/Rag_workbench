# VERDICT — overview-vanity-link — MiMo — round 1
Status: APPROVED
Reviewed: `frontend/src/App.tsx:1332-1338`, `frontend/src/pages/RagOverview.tsx:14,26-31,40`

## Findings
- [SEVERITY: minor] `RagOverview.tsx:40` — Changing dep from `[]` to `[refFromPath]` means the entire effect (including the unconditional `$pageview` capture on line 30) re-fires when navigating intra-SPA between a ref path (`/r/acme`) and a non-ref path (`/overview` or `/r`). This inflates `$pageview` counts but does **not** double-count `overview_link_visit` for the same ref. In practice the primary flow (land on `/r/acme` from a shared link → mount once → fire once) is unaffected. If you want to guard against it, add a `hasFired` ref or split the unconditional `$pageview` into its own `[]`-dep effect. Not blocking.

## Notes
- **Route shadowing**: `/overview`, `/r`, `/r/:ref` share no prefix collision with existing `/rag-overview` or `/rag/*`. React Router matches `/r` exactly and `/r/:ref` as a sibling — no shadow. ✓
- **Path-ref capture**: `useParams` correctly extracts `:ref`; the guard `if (refFromPath)` (line 28) correctly skips when `refFromPath` is `undefined` (visits to `/overview`, `/r`, `/rag-overview`). Path ref overwrites any `utm_*`-based `ref` query param by assignment order, matching the stated "path takes precedence" contract. ✓
- **TypeScript**: `as [string, string][]` cast after the null-filter is safe. ✓
- **Server**: SPA catch-all in `main.py` already serves `index.html` for `/r/*`, `/overview` — no server-side changes needed. ✓
