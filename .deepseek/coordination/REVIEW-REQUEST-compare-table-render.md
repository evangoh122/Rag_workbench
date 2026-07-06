# REVIEW-REQUEST — compare-table-render — round 1

**Coordinator:** DeepSeek
**Author of change:** Claude (drafted)
**Branch:** `main` (uncommitted working tree)
**Gate:** No commit until **MiMo** + **DeepSeek** = `APPROVED`. Then commit to `main`
and `git push origin main` (triggers `.github/workflows/deploy.yml` → HF Space
`egoh33/Auditable-Filing-QA`).

## Feature
Multi-period XBRL comparison answers now render as a **GitHub-flavored markdown table**
instead of a run-on line of numbers. Previously `output_node`'s comparison branch emitted
lines like `  2024-12-31  NetIncomeLoss: 6,000,000,000` — hard to scan. Now it emits a
real `| Period | Metric | Value |` table, the frontend renders it via `remark-gfm`, and
`.prose-refined` CSS styles tables + restores heading/list/blockquote styling stripped by
Tailwind preflight.

A pre-commit self-review caught and **fixed** three issues in this same change set:
1. **[blocker]** `output_node` called `_humanize_concept(concept)` which was **defined
   nowhere** — a `NameError` on the comparison happy path. Now defined next to `_fmt_num`,
   reusing `xbrl_relevance._DISPLAY_NAMES` with a PascalCase-splitting fallback.
2. **[minor]** dedup of duplicate `(period, concept)` facts ran *after* the `MAX_PERIODS=6`
   truncation, so amended-filing duplicates could evict valid periods. Dedup now runs
   **before** truncation.
3. **[nit]** table cells weren't pipe-escaped; metric label now `.replace("|", "\\|")`.

## Files changed
- `api/services/langgraph_engine.py`
  - new import: `_DISPLAY_NAMES` from `api.services.xbrl_relevance`.
  - new helper `_humanize_concept(concept)` (after `_fmt_num`, ~line 691): `_DISPLAY_NAMES`
    lookup → PascalCase split fallback (`re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", concept)`).
  - `output_node` comparison branch (~line 768): dedup moved above `MAX_PERIODS` truncation;
    emits bold heading + `| Period | Metric | Value |` GFM table; metric cell humanized +
    pipe-escaped; `math_result` line kept.
- `frontend/src/App.tsx` — `import remarkGfm from 'remark-gfm'`; `remarkPlugins={[remarkGfm]}`
  on `<ReactMarkdown>`; `allowedElements` extended with `table, thead, tbody, tr, th, td, del`.
- `frontend/src/index.css` — `.prose-refined` styling: table (full-width, tabular-nums,
  zebra, right-aligned numeric cols), headings h1–h4, lists, blockquote, hr, links, em.
- `frontend/package.json` / `package-lock.json` — add `remark-gfm ^4.0.1`.
- `tests/test_langgraph_engine.py` — new `TestHumanizeConcept` (3 cases) + new
  `TestOutputNodeComparisonTable` (2 cases: concept humanized in table; duplicates collapsed
  before truncation → exactly 6 distinct rows survive, most-recent kept).
- `.gitignore` — ignore local-only `docs/link Tracking Taxonomy.md`.

## Pre-review evidence
- Backend: `.venv/Scripts/python.exe -m pytest tests/test_langgraph_engine.py -q` → **24 passed**.
- Frontend: `npm run build` (`tsc -b && vite build`) → **clean**; `remark-gfm` bundled.

## Per-agent checklists

### DeepSeek (logic + correctness / contracts) — REQUIRED
- [ ] `_humanize_concept` never raises: empty string passthrough; unmapped concept falls back
      to PascalCase split; mapped concept returns display name. No unbound references.
- [ ] Dedup runs **before** `MAX_PERIODS` truncation; keeps first occurrence per
      `(period, concept)`; `MAX_PERIODS=6` caps distinct rows.
- [ ] Emitted string is valid GFM: header row + `| :-- | :-- | --: |` delimiter, one row per
      fact, alignment markers correct.
- [ ] No regression to the non-comparison (`latest`/`general`) answer path or the
      `natural_yoy_summary` prefix.
- [ ] `output_node` return contract (`final_answer`, `status`) unchanged.

### MiMo (usability + performance / DB cost) — REQUIRED
- [ ] Table readability with up to 6 periods; humanized metric labels (e.g. `Net Income`,
      `COGS`) clearer than raw XBRL concepts.
- [ ] No new DB/hot-path cost: `_DISPLAY_NAMES` is an in-memory dict; dedup is O(n) over
      already-fetched facts; no extra queries.
- [ ] Frontend: `remark-gfm` + extended `allowedElements` render tables safely (`skipHtml`
      retained); CSS right-aligns numeric columns; no layout regression for non-table answers.

## Prompt to hand each agent
> Read `.deepseek/coordination/REVIEW-REQUEST-compare-table-render.md`. Review the diff of
> `api/services/langgraph_engine.py`, `frontend/src/App.tsx`, `frontend/src/index.css`, and
> `tests/test_langgraph_engine.py` against your checklist. Write your verdict to
> `.<agent>/VERDICT-compare-table-render.md` using the format in
> `.deepseek/coordination/PROTOCOL.md`. Report findings; don't modify source.
