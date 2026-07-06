# SUMMARY — tanstack-tables — round 1

**Verdicts:** MiMo `APPROVED`, DeepSeek `APPROVED` → ✅ **CLEARED** (commit → push origin main → HF deploy).
Reviews run via the reviewers' own model APIs; raw copies in `scripts/_*_tanstack-tables_out.txt`.

## Change
Comparison tables are now rendered with **TanStack Table** — sortable, numeric-aware —
by parsing the GFM markdown the backend already emits (`parseSegments`). Prose still
renders via ReactMarkdown. No API-contract change; markdown `<table>` retained as
fallback.

New: `frontend/src/utils/markdownTables.ts`, `components/DataTable.tsx`,
`components/MarkdownMessage.tsx`. Modified: `App.tsx` (swap render), `index.css`
(`.data-table*`), `package.json` (`@tanstack/react-table ^8`).

## Lane results
| Lane     | Status   | Findings |
| :------- | :------- | :------- |
| MiMo     | APPROVED | none |
| DeepSeek | APPROVED | none |

## Evidence
- `npm run build` (`tsc -b && vite build`) → clean.
- Parser validated on the real gross-margin answer: `segments: text, table, text`;
  headers/aligns/rows correct; numeric margin sort `[-9.1, 12.2, 39.8]`; dates → string sort.
- DeepSeek confirmed: delimiter-gated parsing, escaped pipes, ragged-row normalisation,
  B/M/K/% numeric parse with no NaN leaks, stable/total sort, no XSS surface.

## Decision
Both required lanes APPROVED, no blocker/major → cleared to commit to `main` and
`git push origin main` (triggers `.github/workflows/deploy.yml` → HF Space).
