# VERDICT — multiyear-compare — MiMo — round 1
Status: APPROVED
Reviewed: `api/services/peer_comparison.py`, `tests/test_peer_comparison.py`

## Findings
- [SEVERITY: minor] `api/services/peer_comparison.py:311` — The regex `(\d+)\s*[-\s]?\s*(?:year|yr|fiscal year)` will match "5 years" but also "555 years" or "5year". The pattern is acceptable for this use case but could be tightened with a word boundary `\b` before the digit group to avoid partial matches within longer strings like "2025years". No functional impact given the input is natural language.
- [SEVERITY: nit] `api/services/peer_comparison.py:342` — The lazy import `from api.services.chart_tool import build_chart_spec` inside the function is fine for avoiding circular imports, but consider moving it to the top of the module if `chart_tool` is already a dependency of `peer_comparison`.

## Notes
- **DB cost**: `_annual_series_for_metric` calls `build_chart_spec` per ticker (N queries for N tickers). With ≤5 tickers per comparison and only on multi-year requests, this is acceptable and does not affect the single-company snapshot path.
- **Readability**: Table layout (up to 5 companies × 8 years) with markdown formatting and "—" for missing years is clear and verified in the example output.
- **Performance**: No changes to the hot path; multi-year branch is gated by `_wants_multiyear` and `_MULTIYEAR_CHARTABLE`, falling back to snapshot otherwise.
- **Test coverage**: 8 new cases cover parsing, detection, and chartability boundaries. Suite passes.
