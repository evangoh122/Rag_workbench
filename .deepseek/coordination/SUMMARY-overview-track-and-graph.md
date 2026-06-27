# SUMMARY — overview-track-and-graph — round 1

**Verdicts:** DeepSeek `APPROVED`, MiMo `APPROVED` → ✅ **CLEARED** (commit → push → HF).

## Changes
1. **Graph fix (App.tsx)** — the LIVE chat is rendered by App.tsx, not
   views/ChatView.tsx (the earlier fix patched the wrong file, so comparisons
   still showed no graph). App.tsx gated the chart on `chart.data.length > 0`; the
   multi-series comparison chart uses `series` (data: []). Gate now accepts data
   OR series; raw-XBRL fallback respects either. Backend verified for
   "compare amd and nvda total revenue over 5 years" (series AMD=4, NVDA=5).
2. **PostHog tracking link (RagOverview.tsx)** — overview page fired no pageview,
   so shared-link visits weren't recorded. Added a mount effect: $pageview +,
   when the URL carries utm_*/ref params, an `overview_link_visit` event tagged
   with them (so a minified link sent to someone registers when opened).

## Non-blocking nits (DeepSeek owns follow-ups)
- App.tsx fallback condition could be extracted to a `hasBackendChart` const.
- RagOverview effect has no cleanup/error-handling (fire-and-forget, acceptable).
