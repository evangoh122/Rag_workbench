"""Tests for the multi-company peer-comparison path (pure logic, no DB)."""
from api.services.peer_comparison import (
    detect_comparison,
    _metric_for_query,
    _tickers_named_in_query,
    _name_to_ticker,
    _format_value,
)


class TestComparisonDetection:
    def test_competitor_intent_is_peer_mode(self):
        d = detect_comparison(
            "How does NVIDIA's revenue growth compare to its competitors?", "NVDA")
        assert d is not None
        assert d["mode"] == "peer"
        assert d["subject"] == "NVDA"

    def test_industry_phrasing_is_peer_mode(self):
        d = detect_comparison("How does AMD stack up against the industry?", "AMD")
        assert d is not None and d["mode"] == "peer" and d["subject"] == "AMD"

    def test_two_named_companies_is_explicit_mode(self):
        d = detect_comparison("Compare NVDA and Intel gross margins", "NVDA")
        assert d is not None
        assert d["mode"] == "explicit"
        assert set(d["explicit"]) == {"NVDA", "INTC"}

    def test_three_named_companies_preserves_all(self):
        d = detect_comparison("NVDA vs QCOM vs TXN revenue", "NVDA")
        assert d is not None and d["mode"] == "explicit"
        assert set(d["explicit"]) == {"NVDA", "QCOM", "TXN"}

    def test_plain_single_company_question_is_not_a_comparison(self):
        assert detect_comparison("What is NVDA's gross margin?", "NVDA") is None

    def test_peer_intent_uses_caller_ticker_when_query_names_none(self):
        d = detect_comparison("How does it compare to competitors?", "MU")
        assert d is not None and d["mode"] == "peer" and d["subject"] == "MU"


class TestNameResolution:
    def test_company_names_map_to_tickers(self):
        assert _name_to_ticker("NVIDIA Corporation") == "NVDA"
        assert _name_to_ticker("Texas Instruments") == "TXN"
        assert _name_to_ticker("Broadcom Inc.") == "AVGO"

    def test_unknown_name_returns_none(self):
        assert _name_to_ticker("MediaTek") is None
        assert _name_to_ticker("") is None

    def test_named_tickers_in_query_order(self):
        assert _tickers_named_in_query("TXN then NVDA") == ["TXN", "NVDA"]


class TestMetricMapping:
    def test_growth_phrasing(self):
        assert _metric_for_query("revenue growth rate vs peers")[0] == "revenue_yoy_growth"

    def test_gross_margin_phrasing(self):
        assert _metric_for_query("compare gross margins")[0] == "gross_margin"

    def test_default_is_revenue(self):
        assert _metric_for_query("how do they compare")[0] == "revenue"


class TestValueFormatting:
    def test_percent_metric(self):
        assert _format_value("gross_margin", 71.14) == "71.1%"

    def test_usd_billions(self):
        assert _format_value("revenue", 130_497_000_000.0) == "$130.50B"

    def test_ratio(self):
        assert _format_value("debt_to_equity", 0.42) == "0.42"

    def test_missing_value_is_na(self):
        assert _format_value("revenue", None) == "n/a"
