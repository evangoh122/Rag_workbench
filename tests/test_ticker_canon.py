"""
tests/test_ticker_canon.py — canonical ANT display symbol regressions.

Internal corpus keys stay ``ANTH``; only user-facing rendering is canonical.
"""
from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import pytest

from api.services.ticker_canon import (
    CANONICAL_TICKERS,
    QUERY_TICKER_ALIASES,
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


def test_dag_answer_is_canonical_before_educational_layers_and_keeps_provenance():
    from api.services.langgraph_engine import _text_grounded_decorations, run_auditable_rag

    answer = "ANTH reported revenue of $100."
    state = {"ticker": "ANTH", "numeric_text_grounded": True}
    note = _text_grounded_decorations(state, answer)["note"]
    docs = [{"metadata": {"ticker": "ANTH"}, "chunk_text": "ANTH revenue: $100"}]
    lineage = {"ticker": "ANTH", "source_file": "ANTH.htm"}
    dag_result = {**state, "final_answer": answer + note,
                  "retrieved_docs": docs, "lineage": lineage}
    app = MagicMock()
    app.invoke.return_value = dag_result
    with patch("api.services.langgraph_engine.get_app", return_value=app), \
         patch("api.services.langgraph_engine._generate_educational_layers", return_value={}) as layers, \
         patch("api.services.langgraph_engine._spawn_consensus"):
        result = run_auditable_rag("What is ANT revenue?", "MU")

    assert re.search(r"\bANTH\b", result["final_answer"]) is None
    assert "ANT's filing narrative" in result["final_answer"]
    layers.assert_called_once_with("What is ANT revenue?", result["final_answer"], "ANTH")
    assert result["ticker"] == result["resolved_ticker"] == "ANTH"
    assert result["retrieved_docs"] == [
        {"metadata": {"ticker": "ANTH"}, "chunk_text": "ANTH revenue: $100"},
    ]
    assert result["lineage"] == {"ticker": "ANTH", "source_file": "ANTH.htm"}


@pytest.mark.parametrize("query,selected", [
    ("What is ANT revenue?", "MU"),
    ("What is ant revenue?", "MU"),
    ("What about its revenue?", "ANT"),
    ("What is ANTH revenue?", "MU"),
])
def test_chat_routes_display_symbol_to_stored_key(query, selected):
    from api.services.langgraph_engine import run_auditable_rag

    assert QUERY_TICKER_ALIASES["ANT"] == "ANTH"
    app = MagicMock()
    app.invoke.return_value = {"final_answer": "Revenue was $100."}
    with patch("api.services.langgraph_engine.get_app", return_value=app), \
         patch("api.services.langgraph_engine._generate_educational_layers", return_value={}), \
         patch("api.services.langgraph_engine._spawn_consensus"):
        result = run_auditable_rag(query, selected)
    assert app.invoke.call_args.args[0]["ticker"] == "ANTH"
    assert result["resolved_ticker"] == "ANTH"


@pytest.mark.parametrize("query,expected", [
    ("ANT vs NVDA revenue", ["ANTH", "NVDA"]),
    ("NVDA vs ant revenue", ["NVDA", "ANTH"]),
    ("ANT and ANTH vs NVDA", ["ANTH", "NVDA"]),
    ("ANTA and AN vs NVDA", ["NVDA"]),
    ("ANTHROPICSTYLE vs NVDA", ["NVDA"]),
])
def test_comparison_routes_display_symbol_without_substring_matches(query, expected):
    from api.services.peer_comparison import _tickers_named_in_query, detect_comparison

    assert _tickers_named_in_query(query, strict_symbols=True) == expected
    decision = detect_comparison(query, "MU")
    if len(expected) > 1:
        assert decision == {"mode": "explicit", "subject": expected[0], "explicit": expected}
    else:
        assert decision is None


def test_peer_followup_uses_stored_key_for_display_selection():
    from api.services.peer_comparison import detect_comparison

    assert detect_comparison("How does it compare to peers?", "ANT") == {
        "mode": "peer", "subject": "ANTH", "explicit": ["ANTH"],
    }
