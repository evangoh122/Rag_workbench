"""
Regression tests for api/services/xbrl_relevance.py.

Focus: zero-valued XBRL facts must be treated as real values, not dropped.
A legitimate 0 (zero long-term debt, zero R&D, etc.) previously became None via
truthiness fallback (`fact.get("value") or fact.get("val")`), rendering as "—"
and being marked unverified, and getting demoted in ranking.
"""
from api.services.xbrl_relevance import (
    _pick_value,
    _rank_facts,
    format_fact_for_display,
    get_relevant_facts,
)


# ── _pick_value ────────────────────────────────────────────────────────────────

def test_pick_value_keeps_zero():
    """A value of 0 must be returned as 0, not fall through to 'val' or None."""
    assert _pick_value({"value": 0}) == 0
    assert _pick_value({"value": 0.0}) == 0.0


def test_pick_value_falls_back_to_val_only_when_value_missing():
    assert _pick_value({"val": 123}) == 123
    # 'value' present (even as 0) wins over 'val'
    assert _pick_value({"value": 0, "val": 999}) == 0


def test_pick_value_none_when_both_absent():
    assert _pick_value({"concept": "X"}) is None


# ── format_fact_for_display ─────────────────────────────────────────────────────

def test_format_zero_value_is_verified_and_not_dropped():
    out = format_fact_for_display({
        "concept": "LongTermDebt", "value": 0, "unit": "USD", "period_end": "2024-09-28",
    })
    assert out["value"] == 0.0          # not None
    assert out["is_verified"] is True   # zero is a real, verified value
    assert out["label"] == "Long-Term Debt"
    assert out["period"] == "2024-09-28"  # period_end mapped to period


def test_format_maps_period_and_label():
    out = format_fact_for_display({
        "concept": "Revenues", "value": 30391000000, "unit": "USD", "period_end": "2024-09-28",
    })
    assert out["label"] == "Revenue"
    assert out["period"] == "2024-09-28"
    assert out["is_verified"] is True


def test_format_missing_value_is_unverified():
    out = format_fact_for_display({"concept": "Revenues", "unit": "USD", "period_end": "2024-09-28"})
    assert out["value"] is None
    assert out["is_verified"] is False


# ── _rank_facts / get_relevant_facts ───────────────────────────────────────────

def test_rank_does_not_demote_zero_valued_fact_below_missing():
    """A zero-valued fact in the primary group must outrank a value-less fact."""
    facts = [
        {"concept": "GrossProfit", "value": None, "period_end": "2024-09-28"},   # missing → demoted
        {"concept": "GrossProfit", "value": 0, "period_end": "2024-09-28"},      # zero → real value
    ]
    ranked = _rank_facts(facts, "profitability", top_n=2)
    assert ranked[0]["value"] == 0       # zero-valued fact ranks first
    assert ranked[1]["value"] is None


def test_get_relevant_facts_includes_zero_value():
    facts = [{"concept": "LongTermDebt", "value": 0, "unit": "USD", "period_end": "2024-09-28"}]
    result = get_relevant_facts("What is the company's long-term debt?", facts)
    assert result["total"] == 1
    assert len(result["relevant"]) == 1
    assert result["relevant"][0]["value"] == 0


def test_get_relevant_facts_empty():
    result = get_relevant_facts("anything", [])
    assert result["relevant"] == []
    assert result["total"] == 0
    assert result["group"] == "none"
