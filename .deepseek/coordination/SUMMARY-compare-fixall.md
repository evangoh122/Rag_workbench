# SUMMARY — compare-fixall — round 1

**Verdicts:** DeepSeek `APPROVED`, MiMo `APPROVED` → ✅ **CLEARED** (commit → merge → HF).

## Problem
Multi-company comparison answers were missing graphs, sources, and the 3-layer
fields (what_it_means / how_to_interpret / follow_ups) that single-company answers have.

## Fixes
1. **Graphs** — `ChatView.tsx` gated chart render on `chart.data?.length > 0`; the
   multi-series comparison chart uses `series` (data: []). Gate now accepts either;
   raw-XBRL fallback respects the same.
2. **Sources** — `_filing_sources(tickers)` adds per-company latest-10-K EDGAR links
   (by CIK), threaded through multi-year + snapshot paths; status.retrieval=success.
3. **3-layer fields** — `_shaped_response` carries what_it_means/how_to_interpret/
   follow_ups; deterministic growth/CAGR read moved into structured what_it_means.

## Non-blocking findings (DeepSeek owns follow-ups)
- `_filing_sources` try/except breadth + redundant `or {}` (style).
- Ambiguous bare-ticker EDGAR search fallback when CIK unknown (known tickers fine).
- ChatView fallback condition could be terser (logic equivalent).

Verified live ("compare nvidia and amd revenue over 5 years"): chart series NVDA=5/
AMD=4, 2 EDGAR sources, all 3 layers populated. 29 peer + chat-route tests pass; tsc clean.
