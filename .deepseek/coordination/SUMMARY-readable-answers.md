# SUMMARY — readable-answers — round 1

**Verdicts:** MiMo `APPROVED`, DeepSeek `APPROVED` → ✅ **CLEARED** (commit → push origin main → HF deploy).
Reviews run via the reviewers' own model APIs; raw copies in `scripts/_*_readable-answers_out.txt`.

## Change
Two readability initiatives on `output_node`:
1. Comparison table pivoted **wide** (one row per period, one column per metric); the
   `MAX_PERIODS=6` cap now counts **distinct periods**, not rows.
2. Gross-margin queries get `| Period | Revenue | Gross Profit | Gross Margin |` with
   derived Revenue (`GP+COGS`) / Gross Profit (`Rev−COGS`) and `GM% = GP/Rev*100`.
3. Single-number answers use thousand separators (`215,938,000,000`) via `_fmt_result`;
   table cells use compact `B/M` via `_fmt_compact`.

## Lane results
| Lane     | Status   | Findings |
| :------- | :------- | :------- |
| MiMo     | APPROVED | 1 nit (see below) |
| DeepSeek | APPROVED | none |

## Non-blocking
- MiMo nit: "gross-margin branch re-processes all rows even when no GM keywords." —
  Misread: the `cats` dict is built **inside** the `if is_gm_ask:` branch, so it only
  runs for gross-margin queries. No change needed.

## Evidence
- `pytest tests/test_langgraph_engine.py` → 27 passed (wide-pivot, gross-margin derive,
  negative margin, scalar separators).
- Final validation: `pytest langgraph + peer_comparison + routes_chat + chat_engine` →
  **71 passed**.
- Live render verified: MU gross-margin table (−9.1% / 22.4% / 39.8%) and NVDA scalar
  (`215,938,000,000`).

## Decision
Both required lanes APPROVED, no blocker/major → cleared to commit to `main` and
`git push origin main` (triggers `.github/workflows/deploy.yml` → HF Space).
