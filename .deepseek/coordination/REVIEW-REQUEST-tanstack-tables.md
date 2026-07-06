# REVIEW-REQUEST — tanstack-tables — round 1

**Coordinator:** DeepSeek
**Author of change:** Claude (drafted)
**Branch:** `main` (uncommitted working tree)
**Gate:** No commit until **MiMo** + **DeepSeek** = `APPROVED`. Then commit to `main`
and `git push origin main` (triggers `.github/workflows/deploy.yml` → HF Space).

## Feature
Comparison tables are now rendered on the frontend with **TanStack Table**
(`@tanstack/react-table`) — sortable, numeric-aware — instead of a static markdown
`<table>`. The backend still emits the same GFM markdown table (already reviewed, and a
graceful fallback); the frontend **parses** those table blocks out of the message and
renders them interactively, leaving surrounding prose to ReactMarkdown.

Decoupled by design: **no API-contract change**. Any markdown table (gross-margin view,
generic wide pivot, future tables) is upgraded at once.

## Files changed
- `frontend/src/utils/markdownTables.ts` *(new)* — `parseSegments(content)` splits a
  message into ordered `text` / `table` segments (a table = a `|`-line followed by a
  `| :-- | --: |` delimiter row, then `|`-rows). `splitCells` honours escaped `\|`;
  column alignment derived from the delimiter (`:--`/`--:`/`:-:`). `parseNumericCell`
  parses `15.54B` / `-9.1%` / `215,938,000,000` → number for sorting (dates → null).
- `frontend/src/components/DataTable.tsx` *(new)* — TanStack `useReactTable` with
  `getSortedRowModel`; a `smartSort` sortingFn compares numerically when both cells parse,
  else `localeCompare`. Alignment applied as `text-left/right/center` from the source
  delimiter; click-to-sort headers with chevron indicators.
- `frontend/src/components/MarkdownMessage.tsx` *(new)* — maps segments to `<DataTable>`
  or `<ReactMarkdown>` (remark-gfm, `skipHtml`, same `allowedElements`, tables kept as
  fallback).
- `frontend/src/App.tsx` — replaced the inline `<ReactMarkdown>` message block with
  `<MarkdownMessage content={msg.content} />`; dropped now-unused ReactMarkdown/remarkGfm
  imports.
- `frontend/src/index.css` — `.data-table*` styles (sortable header cursor/indicator,
  zebra, tabular-nums, hover); reuses the existing dark/emerald token palette.
- `frontend/package.json` / `package-lock.json` — add `@tanstack/react-table ^8`.

## Pre-review evidence
- `npm run build` (`tsc -b && vite build`) → **clean**.
- Parser validated on the real gross-margin answer: `segments: text, table, text`;
  headers/aligns/rows correct; numeric sort of margins `[-9.1, 12.2, 39.8]`; dates fall
  back to string sort.

## Per-agent checklists

### DeepSeek (correctness) — REQUIRED
- [ ] `parseSegments` only treats a block as a table when a delimiter row follows; prose
      containing a stray `|` stays text; ragged rows normalised to header width.
- [ ] `splitCells` escaped-pipe handling; alignment mapping matches the backend delimiter.
- [ ] `parseNumericCell` returns null for non-numeric (dates, labels) so sorting falls
      back to string; B/M/K and `%` handled; no NaN leaks.
- [ ] `smartSort` stable and total; no crash on empty/ragged cells.
- [ ] No XSS surface: cells render as escaped text (no `dangerouslySetInnerHTML`);
      `skipHtml` retained on the text path.

### MiMo (usability + performance) — REQUIRED
- [ ] Interactive sortable table is a clear readability win over the static one.
- [ ] Bundle cost of `@tanstack/react-table` acceptable (headless, tree-shakeable).
- [ ] `parseSegments`/render is O(n) per message, memoised on content; no re-parse churn.

## Prompt to hand each agent
> Read `.deepseek/coordination/REVIEW-REQUEST-tanstack-tables.md`. Review
> `frontend/src/utils/markdownTables.ts`, `frontend/src/components/DataTable.tsx`,
> `frontend/src/components/MarkdownMessage.tsx`, the `App.tsx`/`index.css` diffs against
> your checklist. Write your verdict to `.<agent>/VERDICT-tanstack-tables.md` using the
> format in `.deepseek/coordination/PROTOCOL.md`. Report findings; don't modify source.
