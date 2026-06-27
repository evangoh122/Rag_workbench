# REVIEW-REQUEST — multiyear-compare — round 1

**Coordinator:** DeepSeek
**Author of change:** Claude (drafted); going forward DeepSeek owns follow-up edits.
**Branch:** `feat/mindforge-consensus-rail` (uncommitted working tree)
**Gate:** No commit until **MiMo** + **DeepSeek** = `APPROVED`. Then merge to `main`
and push to origin (triggers HF Space deploy).

## Feature
Peer comparison now supports **multi-year time-series comparisons**. Previously a
query like *"compare nvidia and amd revenue over 5 years"* returned only each
company's **latest** fiscal year (single-period snapshot) — the "over 5 years" was
ignored and the multi-year data only ever fed the chart, never the answer text.

Now, when the query asks for a multi-year history (explicit "N years" horizon or a
trend/history signal) AND the metric has a chartable annual series, the path builds
a **year-by-year table** (one row per fiscal year, one column per company) + a
growth/CAGR read + a multi-series trend chart — all from the same deterministic,
filing-derived XBRL series. Otherwise it falls through to the existing snapshot.

Verified live output for the exact prompt:
```
**Revenue — NVDA vs. AMD (2022–2026)**
| Fiscal Year | NVDA | AMD |
| 2022 | $26.91B | $23.60B |
| ... | ... | ... |
| 2026 | $215.94B | — |
**What it means:** NVDA grew +702% (2022→2026), a 68% CAGR; AMD grew +47% ...
```

## Files changed
- `api/services/peer_comparison.py` —
  - new helpers: `_parse_year_horizon` (digit/written N, clamped 2.._MAX_TREND_YEARS=8),
    `_wants_multiyear` (horizon or trend/history signal), `_annual_series_for_metric`
    (reuses `chart_tool.build_chart_spec` annual points so numbers stay filing-derived),
    `_multiyear_comparison` (builds the year-by-year table + read + trend chart);
  - `_MULTIYEAR_CHARTABLE = {revenue, net_income, gross_margin, operating_margin, net_margin}`;
  - `run_peer_comparison` branches into `_multiyear_comparison` after the `<2 tickers`
    guard, returns None → falls back to snapshot when <2 companies have a series.
- `tests/test_peer_comparison.py` — added `TestYearHorizon` + `TestMultiyearDetection`
  (8 new cases). Suite: 25 passed (full set 58 with guardrails/persona).

## Per-agent checklists

### DeepSeek (logic + correctness) — REQUIRED (and owns any follow-up edits)
- [ ] `_parse_year_horizon` regex: handles "5 years", "5-year", "last three years";
      ignores unrelated digits; clamp 2..8 correct; no catastrophic backtracking.
- [ ] Year-window union logic (`all_years[-window:]`) correct when companies have
      different fiscal calendars (NVDA→2026, AMD→2025); "—" fill for missing years.
- [ ] CAGR/growth math: `((last/first)**(1/n_span)-1)*100`, guards for first<=0,
      n_span==0, percentage metrics (shows from→to, not % change).
- [ ] Fallthrough contract: returns None (→ snapshot) when <2 series; never raises
      into `run_auditable_rag` (which catches and falls back to single-company anyway).
- [ ] Chart payload shape (`series:[{name,data:[{period,value}]}]`) matches the
      existing multi-series trend chart the frontend already renders.

### MiMo (usability + performance / DB cost) — REQUIRED
- [ ] `_annual_series_for_metric` calls `build_chart_spec` per ticker (N DB reads for
      N companies). Acceptable for a comparison (≤5 tickers)? Any redundant queries?
- [ ] Table readability with up to 5 companies × up to 8 years.
- [ ] No change to the single-company hot path; multi-year only on comparison queries.

## Prompt to hand each agent
> Read `.deepseek/coordination/REVIEW-REQUEST-multiyear-compare.md`. Review the diff
> of `api/services/peer_comparison.py` + `tests/test_peer_comparison.py` against your
> checklist. Write your verdict to `.<agent>/VERDICT-multiyear-compare.md` using the
> format in `.deepseek/coordination/PROTOCOL.md`. Report findings; don't modify source.
