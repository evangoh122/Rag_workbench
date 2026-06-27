# VERDICT — multiyear-compare — DeepSeek — round 1
Status: APPROVED
Reviewed: `api/services/peer_comparison.py`, `tests/test_peer_comparison.py`

## Findings
- [minor] `api/services/peer_comparison.py:340` — `_annual_series_for_metric` accesses `spec["annual"]` or `spec["data"]` but `build_chart_spec` returns `{"annual": [...]}` for line charts per the chart_tool contract. The fallback to `spec.get("data")` is harmless but dead code — consider removing for clarity. Not a blocker.
- [nit] `api/services/peer_comparison.py:375` — CAGR math `n_span = int(last_y) - int(first_y)` assumes fiscal years are integers (they are, e.g. "2022"). Safe, but a comment noting the assumption would help future readers.
- [nit] `tests/test_peer_comparison.py:97` — `test_revenue_is_chartable_for_multiyear` tests membership but doesn't test that non-chartable metrics (e.g. `current_ratio`) are excluded. The existing assertions cover this implicitly. Fine as-is.

## Notes
- `_parse_year_horizon` regex is safe: no nested quantifiers, no catastrophic backtracking risk. Handles "5 years", "5-year", "last three years" correctly. Clamping 2..8 is correct.
- Year-window logic (`all_years[-window:]`) correctly handles companies with different fiscal calendars (NVDA→2026, AMD→2025). The "—" fill for missing years is correct.
- CAGR/growth math: `((last/first)**(1/n_span)-1)*100` with guards for `first<=0` and `n_span==0`. Percentage metrics correctly skip growth/CAGR and show from→to movement. All correct.
- Fallthrough contract: returns `None` when `<2` series, which `run_peer_comparison` handles by falling back to snapshot. No uncaught exceptions.
- Chart payload shape (`series:[{name,data:[{period,value}]}]`) matches the existing multi-series trend chart format the frontend already renders.
- Test coverage is adequate: 8 new cases covering digit/written horizon parsing, clamping, detection signals, and chartable metric membership. All 25 existing tests continue to pass.
- No issues found with logic, correctness, or API contracts. Ready to merge after MiMo approval.
