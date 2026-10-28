"""
tests/test_ticker_canon.py — canonical ANT display symbol regressions.

Internal corpus keys stay ``ANTH``; only user-facing rendering is canonical.
"""
from __future__ import annotations

import re
from unittest.mock import patch

from api.services.ticker_canon import (
    CANONICAL_TICKERS,
    canonicalize_user_text,
    display_ticker,
)


def test_display_ticker_maps_anth_to_ant():
    assert CANONICAL_TICKERS["ANTH"] == "ANT"
    assert display_ticker("ANTH") == "ANT"
    assert display_ticker("NVDA") == "NVDA"
    assert display_ticker("ANT") == "ANT"
    assert display_ticker("") == ""


def test_display_ticker_is_idempotent():
    once = display_ticker("ANTH")
    assert once == "ANT"
    assert display_ticker(once) == once


def test_canonicalize_user_text_maps_standalone_anth_token():
    assert canonicalize_user_text("ANTH") == "ANT"
    assert canonicalize_user_text("ANTH vs NVDA") == "ANT vs NVDA"
    assert canonicalize_user_text("| ANTH | 12 |") == "| ANT | 12 |"


def test_canonicalize_user_text_never_alters_anthropic_words():
    text = "ANTHROPIC filed its S-1; Anthropic PBC and ANTH ticker are distinct."
    out = canonicalize_user_text(text)
    assert "ANTHROPIC" in out
    assert "Anthropic PBC" in out
    assert out == (
        "ANTHROPIC filed its S-1; Anthropic PBC and ANT ticker are distinct."
    )
    assert canonicalize_user_text("Anthropic") == "Anthropic"
    assert canonicalize_user_text("ANTHROPIC") == "ANTHROPIC"


def test_canonicalize_user_text_is_idempotent_and_keeps_other_text():
    once = canonicalize_user_text("Report for ANTH: 100")
    assert once == "Report for ANT: 100"
    assert canonicalize_user_text(once) == once


@patch("api.services.peer_comparison.compute_metric")
def test_langgraph_rendered_answer_shows_ant_and_never_anth(mock_metric):
    from api.services.langgraph_engine import run_auditable_rag

    mock_metric.return_value = {"value": 1.0, "period": "2026"}
    result = run_auditable_rag(
        "How does NVIDIA's investment in Anthropic affect its revenue?",
        "NVDA",
    )

    answer = result["final_answer"]
    assert "| ANT |" in answer
    assert re.search(r"\bANTH\b", answer) is None
