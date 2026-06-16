"""
chart_tool.py — Build chart specs for the frontend (recharts) from XBRL facts.

Exposed to the LLM as the `create_financial_chart` tool. The key guardrail:
the chart's data points are computed *here*, deterministically, from the
company's filed XBRL facts — never from numbers the model generates. The model
only chooses WHICH metric to chart; the figures stay auditable.

A chart needs a real multi-year series (>= 2 fiscal years); otherwise we return
None and the caller falls back to a normal text answer.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from loguru import logger

# Metrics the tool can chart → (label, unit, kind). Level = dollar series;
# ratio = percentage computed per year from its components.
_CHART_METRICS: Dict[str, Dict[str, str]] = {
    "revenue":          {"label": "Revenue",          "unit": "USD", "kind": "level"},
    "net_income":       {"label": "Net Income",       "unit": "USD", "kind": "level"},
    "gross_profit":     {"label": "Gross Profit",     "unit": "USD", "kind": "level"},
    "operating_income": {"label": "Operating Income", "unit": "USD", "kind": "level"},
    "rd_expense":       {"label": "R&D Expense",       "unit": "USD", "kind": "level"},
    "gross_margin":     {"label": "Gross Margin",      "unit": "%",   "kind": "ratio"},
    "operating_margin": {"label": "Operating Margin",  "unit": "%",   "kind": "ratio"},
    "net_margin":       {"label": "Net Margin",        "unit": "%",   "kind": "ratio"},
}

# XBRL concept aliases per logical metric (filers tag revenue differently).
_REVENUE_CONCEPTS = [
    "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet", "SalesRevenueGoodsNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
]
_COGS_CONCEPTS = ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"]
_LEVEL_CONCEPTS: Dict[str, List[str]] = {
    "revenue": _REVENUE_CONCEPTS,
    "net_income": ["NetIncomeLoss"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "rd_expense": ["ResearchAndDevelopmentExpense"],
}

_MAX_YEARS = 8  # keep the chart readable

CHARTABLE_METRICS = sorted(_CHART_METRICS.keys())

# Words that signal the user wants a trend/visual, used by the numeric path to
# auto-attach a chart (the qualitative path uses the LLM tool instead).
_CHART_TRIGGER_WORDS = (
    "chart", "plot", "graph", "visuali", "trend", "historical", "history",
    "over time", "over the years", "year over year", "year-over-year",
    "by year", "yoy", "trajectory", "trended",
    "show", "display", "compare", "comparison", "pattern", "growth",
    "change", "changed", "evolving", "evolution", "progression",
)

# Query phrasing → chart metric. First match wins; order specific → general.
# Each phrase is compiled into a regex with word boundaries to avoid false
# positives like "revenue recognition" matching "revenue".
_METRIC_PHRASES: List[tuple] = [
    (("gross margin", "gross profit margin"), "gross_margin"),
    (("operating margin",), "operating_margin"),
    (("net margin", "profit margin"), "net_margin"),
    (("gross profit",), "gross_profit"),
    (("operating income",), "operating_income"),
    (("r&d", "research and development"), "rd_expense"),
    (("net income", "earnings", "profit"), "net_income"),
    (("revenue", "sales", "top line"), "revenue"),
]

# Pre-compile regex patterns with word boundaries for each metric phrase.
_METRIC_REGEX: List[tuple] = []
for phrases, metric in _METRIC_PHRASES:
    patterns = []
    for phrase in phrases:
        # Escape special chars, then wrap with word boundaries
        escaped = re.escape(phrase)
        patterns.append(re.compile(r'\b' + escaped + r'\b', re.IGNORECASE))
    _METRIC_REGEX.append((patterns, metric))

# Qualitative markers that indicate a question about a concept, not a data query.
_QUALITATIVE_MARKERS = (
    "policy", "recognition", "structure", "compensation", "plan",
    "definition", "accounting", "treatment", "standard", "guidance",
    "methodology", "approach", "technique", "method", "process",
    "regulation", "rule", "requirement", "disclosure",
)


def _has_qualitative_marker(query: str) -> bool:
    """Check if the query contains qualitative markers that indicate a
    conceptual question rather than a data query."""
    q = query.lower()
    return any(re.search(r'\b' + re.escape(m) + r'\b', q) for m in _QUALITATIVE_MARKERS)


def detect_chart_request(query: str) -> Optional[str]:
    """If the query asks for a trend/visual of a chartable metric, return that
    metric; otherwise None. Used to auto-build a chart on the numeric path.

    Uses word-boundary regex matching to avoid false positives like
    "revenue recognition policy" triggering a revenue chart.
    """
    q = (query or "").lower()
    if not q:
        return None

    # Skip chart generation for clearly qualitative queries
    if _has_qualitative_marker(q):
        return None

    # Check for explicit trigger words + metric combination
    has_trigger = any(w in q for w in _CHART_TRIGGER_WORDS)
    if has_trigger:
        for patterns, metric in _METRIC_REGEX:
            if any(p.search(q) for p in patterns):
                return metric

    # Direct metric query with word boundaries: only match if the query is
    # primarily about the metric itself (not about policies, definitions, etc.)
    for patterns, metric in _METRIC_REGEX:
        if any(p.search(q) for p in patterns):
            return metric

    return None


def _annual_series(ticker: str, concepts: List[str]) -> Dict[str, float]:
    """Return {fiscal_year: value} for a concept set, annual periods only.

    Annual is detected by a period spanning ~a full year (>= 300 days), which
    filters out the quarterly facts that share the same concept. One value per
    fiscal year (the latest period_end in that year wins).
    """
    from api.db.database import db_manager

    if not concepts:
        return {}
    placeholders = ",".join("?" for _ in concepts)
    sql = (
        f"SELECT period_end, value FROM xbrl_facts "
        f"WHERE ticker = ? AND concept IN ({placeholders}) "
        f"  AND value IS NOT NULL AND period_start IS NOT NULL AND period_end IS NOT NULL "
        f"  AND date_diff('day', CAST(period_start AS DATE), CAST(period_end AS DATE)) >= 300 "
        f"ORDER BY period_end"
    )
    by_year: Dict[str, float] = {}
    try:
        rows = db_manager.execute(sql, [ticker, *concepts]).fetchall()
        for period_end, value in rows:
            year = str(period_end)[:4]
            if year.isdigit():
                by_year[year] = float(value)  # later period_end in year wins
    except Exception as e:
        logger.warning(f"_annual_series({ticker}) failed: {e}")
    return by_year


def build_chart_spec(ticker: str, metric: str,
                     chart_type: str = "line") -> Optional[Dict[str, Any]]:
    """Build a recharts spec for a metric's annual history, or None."""
    meta = _CHART_METRICS.get(metric)
    if not meta or not ticker:
        logger.info(f"chart_tool: unsupported metric {metric!r}")
        return None
    if chart_type not in ("line", "bar"):
        chart_type = "line"

    points: List[Dict[str, Any]] = []
    if meta["kind"] == "level":
        series = _annual_series(ticker, _LEVEL_CONCEPTS[metric])
        for year in sorted(series):
            points.append({"period": year, "value": round(series[year], 2)})
    else:
        rev = _annual_series(ticker, _REVENUE_CONCEPTS)
        if metric == "gross_margin":
            gp = _annual_series(ticker, ["GrossProfit"])
            cogs = _annual_series(ticker, _COGS_CONCEPTS)
            # Recover revenue by identity (GP + COGS) for filers lacking a
            # top-line revenue tag.
            for y in set(gp) | set(cogs):
                if y not in rev and y in gp and y in cogs:
                    rev[y] = gp[y] + cogs[y]
            num = gp
        elif metric == "operating_margin":
            num = _annual_series(ticker, ["OperatingIncomeLoss"])
        else:  # net_margin
            num = _annual_series(ticker, ["NetIncomeLoss"])
        for year in sorted(set(rev) & set(num)):
            denom = rev[year]
            if denom:
                points.append({"period": year, "value": round(num[year] / denom * 100, 2)})

    if len(points) < 2:
        return None
    points = points[-_MAX_YEARS:]

    return {
        "type": chart_type,
        "title": f"{ticker} — {meta['label']} ({points[0]['period']}–{points[-1]['period']})",
        "metric": metric,
        "label": meta["label"],
        "unit": meta["unit"],
        "ticker": ticker,
        "data": points,
    }
