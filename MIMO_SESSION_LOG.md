# MiMo Session Log — 2026-06-16

## Summary

This session focused on fixing chart visualization issues and adding quarterly data support to the RAG Workbench financial charts.

---

## Branches Created & Merged

### 1. `fix/historical-chart-visualization` → `main` ✅ MERGED
**Commits:**
```
53a6852 fix: improve historical data visualization for revenue and financial metrics
a846560 fix: move TooltipBox component outside ChartView to fix linting error
96890ca fix: address review issues for chart visualization
0e0b446 fix: optimize knowledge graph rendering for large datasets
ca2a274 fix: remove unused NODE_WARNING_THRESHOLD, add chart detection tests
```

**Files changed:** 9 files, +503, -165

### 2. `feat/quarterly-chart-toggle` → `main` ✅ MERGED
**Commits:**
```
d24d55b feat: add annual/quarterly toggle to financial charts
57136bc fix: default all charts to line type
305ee61 fix: default qualitative path charts to line type too
```

**Files changed:** 10 files, +357, -182

---

## Changes Made

### Backend: `api/services/chart_tool.py`

1. **Word-boundary regex matching** — `_METRIC_REGEX` replaces bare substring matching to prevent false positives like "revenue recognition" matching "revenue"

2. **Qualitative marker filter** — `_has_qualitative_marker()` blocks charts for queries containing "policy", "recognition", "structure", etc.

3. **Dead code removed** — `_DIRECT_CHART_QUERIES` tuple deleted

4. **Quarterly data support** — Added `_quarterly_series()` function:
   - Extracts quarterly XBRL data (60-120 day periods)
   - Returns `{year-quarter: value}` format (e.g., "2024-Q1")
   - Handles string/datetime date parsing
   - Includes TypeError handling for corrupt rows

5. **`build_chart_spec()` updated** — Now returns both `annual` and `quarterly` arrays in the chart spec

### Backend: `api/services/langgraph_engine.py`

1. **Smart chart type (removed)** — Was using bar for ratio metrics, now defaults all to "line"

2. **Auto-chart on qualitative path** — `qualitative_output_node` now auto-attaches charts for metric queries even when LLM doesn't call the tool

3. **More qualitative signals** — Added "policy", "recognition", "structure", "compensation", "plan", "call", "transcript", etc. to `_QUALITATIVE_SIGNALS`

### Backend: `api/config.py`

1. **Moved `TICKER_TO_CIK`** — Relocated from `admin.py` to break circular import (Gemini's fix)

### Frontend: `frontend/src/components/ChartView.tsx`

1. **TooltipBox moved outside** — Fixed lint error (component created during render)

2. **Annual/Quarterly toggle** — Added `useState<ViewMode>` with toggle buttons

3. **Smart data switching** — Uses `chart.annual || chart.data` fallback for backward compatibility

4. **Empty quarterly state** — Shows "No quarterly data available" message

5. **Quarterly XAxis optimization** — `interval={3}` to avoid label crowding

6. **Smaller dots for quarterly** — `r: 1.5` vs `r: 3` for annual

### Frontend: `frontend/src/components/ChartErrorBoundary.tsx` (NEW)

- Error boundary wrapping all chart renders
- Prevents chart errors from crashing the entire message bubble
- Shows "Chart could not be rendered" fallback

### Frontend: `frontend/src/App.tsx`

1. **Duplicate charts fixed** — `FinancialChart` only renders when `ChartView` is NOT present (`!msg.chart` guard)

2. **Error boundary added** — Charts wrapped in `<ChartErrorBoundary>`

3. **FinancialChart imported** — For raw XBRL fact visualization

### Frontend: `frontend/src/views/ChatView.tsx`

1. **ChartView imported** — Backend-generated charts now render in ChatView

2. **chart field added to Message interface** — `chart?: ChartSpec`

3. **Same duplicate fix** — `!msg.chart` guard for FinancialChart

4. **Error boundary added** — Charts wrapped in `<ChartErrorBoundary>`

### Frontend: `frontend/src/api/chat.ts`

- `ChartSpec` interface updated with `annual?:` and `quarterly?:` fields

### Frontend: `frontend/src/components/KnowledgeGraph.tsx`

1. **maxNodes prop** — Default 200 to limit displayed nodes

2. **Priority sorting** — Nodes sorted by connection count (most connected first)

3. **Golden angle distribution** — Better node spacing

4. **Truncation warning** — Shows when graph is truncated

5. **Edge filtering** — Only renders edges where both endpoints are displayed

### Frontend: `frontend/src/components/GraphExplorer.tsx`

1. **Reduced triple limits** — 150 single, 200 all, 500 multi (was 300/300/1000)

2. **Company search** — Searchable dropdown filter

3. **Mobile evidence panel** — Bottom sheet on mobile, side panel on desktop

### Tests: `tests/test_services_aux.py`

- `test_quarterly_series_mocked` — Verifies quarterly filtering
- `test_build_chart_spec_quarterly` — Verifies chart spec generation

---

## Review Status

| Branch | DeepSeek | Gemini |
|--------|----------|--------|
| fix/historical-chart-visualization | ✅ Approved | ✅ Approved |
| feat/quarterly-chart-toggle | ✅ Approved | ✅ Approved |

---

## Known Issues / TODO

### Mobile UI (NOT YET FIXED)
- Chat interface is "squeezed" on mobile
- Needs responsive fixes for:
  - Message bubbles (too wide on small screens)
  - Input bar (may be covered by keyboard)
  - Tables overflow
  - Chart rendering on small screens

### Pre-existing Linter Warnings
These exist in `main` and are NOT from our changes:
- `App.tsx:67` — `_setMode` unused
- `App.tsx:75` — `any` type
- `DriftAlert.tsx:27` — setState in effect
- `GraphAnalytics.tsx:55` — setState in effect

---

## Architecture Notes

### Chart Data Flow
```
User query → detect_chart_request() → metric
    ↓
build_chart_spec(ticker, metric, "line")
    ↓
_annual_series() + _quarterly_series()
    ↓
Returns { annual: [...], quarterly: [...], data: [...] }
    ↓
Frontend ChartView renders with Annual/Quarterly toggle
```

### Ticker Resolution Flow
```
Query → _resolve_query_ticker()
    ↓
1. resolve_ticker_from_query() — company name match
2. TICKER_TO_CIK regex — explicit ticker symbol
3. Fallback to UI's selected ticker
```

### Qualitative vs Numeric Path
```
classifier_node → decide_pipeline()
    ↓
Numeric: extraction → eval → math → verification → output/abstention
Qualitative: qualitative_output_node (LLM + tools)
    ↓
Both paths auto-attach charts via detect_chart_request()
```

---

## Contact / Handoff

This documentation is for Claude (or any AI) to continue work. Key files to understand:

1. `api/services/chart_tool.py` — Chart generation logic
2. `api/services/langgraph_engine.py` — RAG pipeline + chart integration
3. `frontend/src/components/ChartView.tsx` — Chart rendering + toggle
4. `frontend/src/App.tsx` — Main chat interface
5. `frontend/src/components/KnowledgeGraph.tsx` — Graph visualization

Current branch: `main` (at `584aeeb`)
