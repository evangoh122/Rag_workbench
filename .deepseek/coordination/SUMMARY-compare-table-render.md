# SUMMARY — compare-table-render — round 1

**Verdicts:** MiMo `APPROVED`, DeepSeek `APPROVED` → ✅ **CLEARED** (commit → push origin main → HF deploy).
Reviews run via the reviewers' own model APIs (OpenAI-compatible endpoints); raw copies in `scripts/_*_compare_table_out.txt`.

## Change
Multi-period XBRL comparison answers now render as a GitHub-flavored markdown table
(`| Period | Metric | Value |`) instead of a run-on line of numbers. Frontend renders it
via `remark-gfm`; `.prose-refined` CSS styles tables + restores preflight-stripped
heading/list/blockquote styling.

## Pre-review fixes (already applied in this change set)
1. **[blocker]** `_humanize_concept` was undefined (NameError on the comparison happy path)
   → defined next to `_fmt_num`, reusing `xbrl_relevance._DISPLAY_NAMES` + PascalCase fallback.
2. **[minor]** dedup of duplicate `(period, concept)` facts moved **before** the
   `MAX_PERIODS=6` truncation.
3. **[nit]** table cells pipe-escaped.

## Lane results
| Lane     | Status   | Blocking findings |
| :------- | :------- | :---------------- |
| MiMo     | APPROVED | none |
| DeepSeek | APPROVED | none |

## Evidence
- Backend: `pytest tests/test_langgraph_engine.py -q` → 24 passed (incl. new
  `TestHumanizeConcept` + `TestOutputNodeComparisonTable`).
- Frontend: `tsc -b && vite build` → clean, `remark-gfm` bundled.

## Decision
Both required lanes APPROVED, no blocker/major → cleared to commit to `main` and
`git push origin main` (triggers `.github/workflows/deploy.yml` → HF Space
`egoh33/Auditable-Filing-QA`).
