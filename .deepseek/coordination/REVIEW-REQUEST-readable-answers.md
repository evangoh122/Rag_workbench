# REVIEW-REQUEST — readable-answers — round 1

**Coordinator:** DeepSeek
**Author of change:** Claude (drafted)
**Branch:** `main` (uncommitted working tree, on top of committed `compare-table-render`)
**Gate:** No commit until **MiMo** + **DeepSeek** = `APPROVED`. Then commit to `main`
and `git push origin main` (triggers `.github/workflows/deploy.yml` → HF Space).

## Feature
Two readability initiatives on `output_node` (`api/services/langgraph_engine.py`):

1. **Wide / pivoted comparison table.** The comparison table was "long" — period
   repeated, each metric on its own row. Now it pivots to **one row per period, one
   column per metric**, and the `MAX_PERIODS=6` cap now counts **distinct periods**
   (not rows), so a period is never dropped just because it has several metrics.

2. **Gross-margin view + Margin %.** For gross-margin queries the table is
   purpose-built: `| Period | Revenue | Gross Profit | Gross Margin |`. Filers often
   tag only a subset, so Revenue is derived as `Gross Profit + COGS` and Gross Profit
   as `Revenue − COGS` where needed; `Gross Margin % = Gross Profit / Revenue * 100`.

3. **Thousand separators for single-number answers.** Scalar answers were emitting a
   raw float repr (`215938000000.0`). They now go through `_fmt_result` →
   `215,938,000,000`. Table cells use compact `_fmt_compact` (B/M, e.g. `25.11B`).

Verified live output:
```
| Period | Revenue | Gross Profit | Gross Margin |
| :-- | --: | --: | --: |
| 2023-08-31 | 15.54B | -1.42B | -9.1% |
| 2024-08-29 | 25.11B | 5.61B | 22.4% |
| 2025-08-28 | 37.38B | 14.87B | 39.8% |

Based on the SEC filing for NVDA, the answer is 215,938,000,000.
```

## Files changed
- `api/services/langgraph_engine.py`
  - new helpers: `_fmt_compact` (B/M abbreviation), `_fmt_result` (thousand-separator
    scalar via `_fmt_num`/`_safe_numeric`), `_fact_category` (concept → revenue/
    gross_profit/cogs; checks COGS before revenue since "CostOfRevenue" contains
    "revenue").
  - `output_node` comparison branch: period-based truncation; gross-margin branch
    (derive Revenue/GP, compute GM%); generic wide-pivot branch; `math_result` and
    scalar answers routed through `_fmt_result`.
- `tests/test_langgraph_engine.py` — `TestOutputNodeComparisonTable` rewritten for the
  wide format + 2 gross-margin cases (derived revenue, negative margin);
  `TestScalarAnswerFormatting` (thousand separators).

## Pre-review evidence
- `.venv/Scripts/python.exe -m pytest tests/test_langgraph_engine.py -q` → **27 passed**.
- No frontend files changed (still markdown rendered via `remark-gfm`).

## Per-agent checklists

### DeepSeek (logic + correctness) — REQUIRED
- [ ] Gross-margin math: derivations (`rev=gp+cogs`, `gp=rev-cogs`) and
      `gm=gp/rev*100` are correct; divide-by-zero guarded (`rev != 0`); missing
      components render `—` not a crash; negative gross profit handled.
- [ ] `_fact_category` ordering (COGS before revenue) so `CostOfRevenue` → cogs.
- [ ] Period-based truncation keeps the last 6 **distinct** periods and filters rows
      to them; no period dropped due to multi-metric row inflation.
- [ ] Generic wide pivot: stable column order, `—` for missing (period, metric),
      pipe-escaped headers.
- [ ] `_fmt_result` never raises (numeric → separators, non-numeric → str); scalar +
      "no matching periods" paths use it; `output_node` return contract unchanged.

### MiMo (usability + performance) — REQUIRED
- [ ] Wide table + Margin % is materially more readable than the prior long table.
- [ ] Compact `B/M` in tables vs full separators in the scalar answer is a sensible
      split (scannable table, precise single number).
- [ ] No new DB/hot-path cost: all in-memory over already-fetched facts; O(n) pivot.

## Prompt to hand each agent
> Read `.deepseek/coordination/REVIEW-REQUEST-readable-answers.md`. Review the diff of
> `api/services/langgraph_engine.py` + `tests/test_langgraph_engine.py` against your
> checklist. Write your verdict to `.<agent>/VERDICT-readable-answers.md` using the
> format in `.deepseek/coordination/PROTOCOL.md`. Report findings; don't modify source.
