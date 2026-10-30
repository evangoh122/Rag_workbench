"""tests/test_sec_r7_fixes.py — PR40 r7 exact-head CodeRabbit regressions.

Focused production-path coverage for the five accepted r7 findings:

1. an explicit upper-case display ticker ``ANT`` wins over case-insensitive
   prose that happens to spell an ambiguous stored symbol (``form`` -> FORM);
2. caller/UI selections (``ANT``/``ant``/padded) normalize to stored ``ANTH``
   before retrieval, without reinterpreting query prose;
3. Graph RAG requests using ``ANT`` read stored ``ANTH`` graph rows through
   ``run_graph_rag``/``query_graph`` and the chat graph-RAG endpoint;
4. qualitative answers are canonical before ``lineage_node`` persists them, and
   every peer-comparison user-facing field/chart label is canonical while
   internal ticker/provenance/retrieval keys stay ``ANTH``;
5. the ordinary embedding-failure test captures WARNING as well as ERROR so its
   "no structured warning" assertion is non-vacuous (mutation probe external).
"""
from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import duckdb
import pytest
from fastapi.testclient import TestClient

from api.middleware.auth import get_read_api_key
from api.services import graph_rag_engine, langgraph_engine, peer_comparison
from api.services.ticker_canon import canonicalize_user_text

ANTH_ACCESSION = "0001628280-26-067168"


# --- finding 1: resolver precedence over ambiguous English stored symbols ----


@pytest.mark.parametrize("query", [
    "What was ANT revenue in its form S-1?",
    "What was ANT revenue in its Form S-1?",
    "ANT revenue, see the registration form",
])
def test_explicit_display_ticker_beats_ambiguous_stored_prose(query):
    assert langgraph_engine._resolve_query_ticker(query, "NVDA") == "ANTH"


@pytest.mark.parametrize("query,expected", [
    ("What is FORM revenue?", "FORM"),
    ("What is ONTO revenue?", "ONTO"),
    ("What is TER revenue?", "TER"),
    ("What is ANTH revenue?", "ANTH"),
    ("What is NVDA revenue?", "NVDA"),
    ("What is nvda revenue?", "NVDA"),
])
def test_genuine_explicit_stored_tickers_still_resolve(query, expected):
    assert langgraph_engine._resolve_query_ticker(query, "MU") == expected


@pytest.mark.parametrize("query,expected", [
    ("FormFactor revenue in its form S-1", "FORM"),   # company name precedence
    ("Anthropic revenue in its form S-1", "ANTH"),    # company name precedence
    ("fill out the form before filing", "MU"),
    ("an ant colony is eusocial", "MU"),
    ("Ant Group is a customer", "MU"),
    ("What is ANTA revenue?", "MU"),
    ("What is ANTHROPICSTYLE revenue?", "MU"),
])
def test_prose_and_substrings_never_select_a_ticker(query, expected):
    assert langgraph_engine._resolve_query_ticker(query, "MU") == expected


# --- finding 2: selected ticker normalization before retrieval ---------------


@pytest.mark.parametrize("selected", ["ANT", "ant", "  ANT  ", "anth", " ANTH ", " Ant "])
def test_selected_display_or_lowercase_ticker_normalizes_to_stored_key(selected):
    app = MagicMock()
    app.invoke.return_value = {"final_answer": "Revenue was $100."}
    with patch.object(langgraph_engine, "get_app", return_value=app), \
         patch.object(langgraph_engine, "_generate_educational_layers", return_value={}), \
         patch.object(langgraph_engine, "_spawn_consensus"):
        result = langgraph_engine.run_auditable_rag("What was its revenue?", selected)

    assert result["resolved_ticker"] == "ANTH"
    assert app.invoke.call_args.args[0]["ticker"] == "ANTH"


@pytest.mark.parametrize("selected,expected", [
    ("NVDA", "NVDA"),
    ("nvda", "NVDA"),
    ("ANTA", "ANTA"),
    ("MU", "MU"),
])
def test_selected_non_alias_ticker_is_not_reinterpreted(selected, expected):
    app = MagicMock()
    app.invoke.return_value = {"final_answer": "ok"}
    with patch.object(langgraph_engine, "get_app", return_value=app), \
         patch.object(langgraph_engine, "_generate_educational_layers", return_value={}), \
         patch.object(langgraph_engine, "_spawn_consensus"):
        result = langgraph_engine.run_auditable_rag("What was its revenue?", selected)

    assert result["resolved_ticker"] == expected
    assert app.invoke.call_args.args[0]["ticker"] == expected


def test_query_issuer_still_wins_over_selected_display_ticker():
    app = MagicMock()
    app.invoke.return_value = {"final_answer": "ok"}
    with patch.object(langgraph_engine, "get_app", return_value=app), \
         patch.object(langgraph_engine, "_generate_educational_layers", return_value={}), \
         patch.object(langgraph_engine, "_spawn_consensus"):
        result = langgraph_engine.run_auditable_rag("What is NVDA revenue?", "ant")

    assert result["resolved_ticker"] == "NVDA"
    assert app.invoke.call_args.args[0]["ticker"] == "NVDA"


def test_selected_ticker_normalization_does_not_read_query_prose():
    app = MagicMock()
    app.invoke.return_value = {"final_answer": "ok"}
    with patch.object(langgraph_engine, "get_app", return_value=app), \
         patch.object(langgraph_engine, "_generate_educational_layers", return_value={}), \
         patch.object(langgraph_engine, "_spawn_consensus"):
        result = langgraph_engine.run_auditable_rag("an ant colony is eusocial", "MU")

    assert result["resolved_ticker"] == "MU"
    assert app.invoke.call_args.args[0]["ticker"] == "MU"


# --- finding 3: Graph RAG reads stored ANTH rows for display ANT -------------


def _stub_graph_llm(entities=("Anthropic",), answer="ANTH disclosed the figures."):
    llm = MagicMock()
    llm.with_structured_output.return_value.invoke.return_value = SimpleNamespace(
        entities=list(entities)
    )
    llm.invoke.return_value = SimpleNamespace(content=answer)
    return llm


def _graph_row(ticker="ANTH"):
    return (
        ticker, "Anthropic", "DISCLOSED", "revenue",
        "company", "metric", f"{ticker}:acc:0", "f.htm", "p1", 0.9,
    )


@pytest.mark.parametrize("selected", ["ANT", "ant", " ANT "])
def test_run_graph_rag_queries_stored_ticker_and_keeps_provenance(selected):
    cursor = MagicMock()
    cursor.fetchall.return_value = [_graph_row()]
    with patch.object(graph_rag_engine, "_get_llm", return_value=_stub_graph_llm()), \
         patch.object(graph_rag_engine.db_manager, "execute", return_value=cursor) as execute:
        result = graph_rag_engine.run_graph_rag("What did ANT disclose?", selected)

    # Retrieval used the stored key; triples keep stored provenance.
    assert execute.call_args.args[1][0] == "ANTH"
    assert result["extracted_triples"][0]["chunk_id"] == "ANTH:acc:0"
    # Only the user-facing answer text is canonicalized.
    assert result["final_answer"] == "ANT disclosed the figures."


def test_query_graph_normalizes_a_direct_display_ticker_state():
    cursor = MagicMock()
    cursor.fetchall.return_value = [_graph_row()]
    with patch.object(graph_rag_engine.db_manager, "execute", return_value=cursor) as execute:
        graph_rag_engine.query_graph({"ticker": "ANT", "search_entities": ["Anthropic"]})

    assert execute.call_args.args[1][0] == "ANTH"


def _chat_client():
    from api.main import app

    app.dependency_overrides[get_read_api_key] = lambda: "test-key"
    return app, TestClient(app)


def test_chat_graph_rag_endpoint_reads_stored_rows_for_display_ticker():
    app, client = _chat_client()
    cursor = MagicMock()
    cursor.fetchall.return_value = [_graph_row()]
    try:
        with patch("api.routes.chat.check_input") as m_in, \
             patch("api.routes.chat.check_dialog") as m_dia, \
             patch("api.routes.chat.check_output") as m_out, \
             patch.object(graph_rag_engine, "_get_llm", return_value=_stub_graph_llm()), \
             patch.object(graph_rag_engine.db_manager, "execute", return_value=cursor) as execute:
            m_in.return_value = MagicMock(blocked=False)
            m_dia.return_value = MagicMock(off_topic=False, advice=False)
            m_out.return_value = MagicMock(masked_answer=None)
            response = client.post(
                "/api/chat/graph-rag",
                json={"message": "What did ANT disclose?", "ticker": "ANT"},
            )
    finally:
        app.dependency_overrides = {}

    assert response.status_code == 200
    assert execute.call_args.args[1][0] == "ANTH"
    assert response.json()["answer"] == "ANT disclosed the figures."
    assert response.json()["triples"][0]["chunk_id"] == "ANTH:acc:0"


# --- finding 4a: qualitative answer canonical before lineage persistence -----


def _qualitative_node_result():
    with patch("openai.OpenAI") as openai_cls:
        def _create(**_kwargs):
            msg = MagicMock()
            msg.tool_calls = None
            msg.content = "Anthropic reported revenue of $1.2 billion."
            return MagicMock(choices=[MagicMock(message=msg)])

        openai_cls.return_value.chat.completions.create.side_effect = _create
        state = {
            "query": "What revenue did ANT report?",
            "ticker": "ANTH",
            "retrieved_docs": [{
                "chunk_text": "Anthropic reported revenue of $1.2 billion.",
                "metadata": {"ticker": "ANTH", "source": "S-1"},
            }],
            "xbrl_facts": [],
            "query_intent": "general",
            "history": [],
            "numeric_text_grounded": True,
            "status": {},
        }
        return state, langgraph_engine.qualitative_output_node(state)


def test_qualitative_answer_is_canonical_before_lineage_persists_it():
    state, node_result = _qualitative_node_result()

    # The node itself must be canonical: lineage_node runs before the caller's
    # post-invoke canonicalization.
    assert re.search(r"\bANTH\b", node_result["final_answer"]) is None
    assert "ANT's filing narrative" in node_result["final_answer"]
    assert "Anthropic reported" in node_result["final_answer"]

    conn = duckdb.connect(":memory:")
    try:
        with patch(
            "api.db.database.db_manager.get_review_connection", return_value=conn
        ):
            langgraph_engine.lineage_node({
                **state,
                **node_result,
                "eval_route": None,
                "eval_confidence": 0.9,
                "eval_triggers": [],
                "xbrl_facts": [],
                "retrieved_docs": [],
            })
        ticker, answer = conn.execute(
            "SELECT ticker, answer FROM audit_runs"
        ).fetchone()
    finally:
        conn.close()

    # Audit ticker/provenance keep the stored key; persisted answer is canonical.
    assert ticker == "ANTH"
    assert re.search(r"\bANTH\b", answer) is None
    assert "ANT's filing narrative" in answer


# --- finding 4b: every peer user-facing field canonicalized ------------------


def _assert_no_raw_anth(value):
    if isinstance(value, str):
        assert re.search(r"\bANTH\b", value) is None, value
    elif isinstance(value, list):
        for item in value:
            _assert_no_raw_anth(item)


def test_multiyear_peer_fields_and_chart_labels_are_canonical():
    def _spec(ticker, metric, kind):
        return {"annual": [
            {"period": "2022", "value": 10.0},
            {"period": "2023", "value": 20.0},
        ]}

    with patch.object(
        peer_comparison, "compute_metric",
        side_effect=lambda tk, metric: {"value": 20.0, "period": "2023", "ok": True},
    ), patch("api.services.chart_tool.build_chart_spec", side_effect=_spec):
        result = peer_comparison.run_peer_comparison(
            "Compare ANTH vs NVDA revenue over 2 years",
            {"mode": "explicit", "subject": "ANTH", "explicit": ["ANTH", "NVDA"]},
        )

    for field in ("final_answer", "what_it_means", "how_to_interpret"):
        _assert_no_raw_anth(result[field])
    _assert_no_raw_anth(result["follow_ups"])
    _assert_no_raw_anth(result["chart"]["title"])
    assert [s["name"] for s in result["chart"]["series"]] == ["ANT", "NVDA"]
    assert "ANT" in result["final_answer"]

    # Internal provenance is deliberately untouched.
    assert result["chart"]["ticker"] == "ANTH"
    assert {d["metadata"]["ticker"] for d in result["retrieved_docs"]} == {"ANTH", "NVDA"}


def test_snapshot_peer_fields_and_bar_labels_are_canonical():
    with patch.object(
        peer_comparison, "compute_metric",
        side_effect=lambda tk, metric: {"value": 20.0 if tk == "ANTH" else 10.0,
                                        "period": "2023", "ok": True},
    ), patch("api.services.chart_tool.build_chart_spec", return_value={"data": [{"period": "2023", "value": 5.0}]}):
        result = peer_comparison.run_peer_comparison(
            "Compare ANTH vs NVDA revenue",
            {"mode": "explicit", "subject": "ANTH", "explicit": ["ANTH", "NVDA"]},
        )

    for field in ("final_answer", "what_it_means", "how_to_interpret"):
        _assert_no_raw_anth(result[field])
    _assert_no_raw_anth(result["follow_ups"])
    _assert_no_raw_anth(result["chart"]["title"])
    assert {p["period"] for p in result["chart"]["data"]} == {"ANT", "NVDA"}
    assert result["chart"]["ticker"] == "ANTH"


def test_run_auditable_rag_canonicalizes_patched_peer_auxiliary_fields():
    shaped = {
        "final_answer": "**Revenue — ANTH vs. peers**\n| ANTH | $1 |",
        "what_it_means": "ANTH ranks #1 on revenue.",
        "how_to_interpret": "ANTH's filing is comparable.",
        "follow_ups": ["Compare ANTH and NVDA revenue", "What drove ANTH's revenue?"],
        "chart": {
            "type": "line", "title": "Revenue — ANTH vs. peers",
            "ticker": "ANTH",
            "series": [{"name": "ANTH", "data": []}, {"name": "NVDA", "data": []}],
        },
        "retrieved_docs": [{"metadata": {"ticker": "ANTH"}, "chunk_text": "ANTH"}],
        "lineage": {"ticker": "ANTH"},
    }
    with patch.object(
        peer_comparison, "detect_comparison",
        return_value={"mode": "explicit", "subject": "ANTH", "explicit": ["ANTH", "NVDA"]},
    ), patch.object(peer_comparison, "run_peer_comparison", return_value=shaped):
        result = langgraph_engine.run_auditable_rag("Compare ANT vs NVDA revenue", "NVDA")

    for field in ("final_answer", "what_it_means", "how_to_interpret"):
        _assert_no_raw_anth(result[field])
    _assert_no_raw_anth(result["follow_ups"])
    _assert_no_raw_anth(result["chart"]["title"])
    assert [s["name"] for s in result["chart"]["series"]] == ["ANT", "NVDA"]
    # Internal keys/provenance stay stored.
    assert result["resolved_ticker"] == "ANTH"
    assert result["chart"]["ticker"] == "ANTH"
    assert result["retrieved_docs"][0]["metadata"]["ticker"] == "ANTH"
    assert result["lineage"]["ticker"] == "ANTH"


# --- finding 5: capture boundary positive control ---------------------------


def test_warning_threshold_captures_structured_warning_error_only_would_not():
    from loguru import logger

    def _capture_logs(level):
        messages: list[str] = []
        handler = logger.add(lambda m: messages.append(str(m)), level=level)
        return messages, handler

    warning_messages, warning_handler = _capture_logs(level="WARNING")
    error_messages, error_handler = _capture_logs(level="ERROR")
    try:
        logger.warning(f"Structured ingestion failed for ANTH {ANTH_ACCESSION}: probe")
        logger.error("Failed to process ANTH: probe")
    finally:
        logger.remove(warning_handler)
        logger.remove(error_handler)

    assert any("Structured ingestion failed" in m for m in warning_messages)
    assert any("Failed to process ANTH" in m for m in warning_messages)
    # The old ERROR-only capture would miss the structured WARNING entirely.
    assert not any("Structured ingestion failed" in m for m in error_messages)


def test_canonicalization_keeps_anthropic_prose():
    assert canonicalize_user_text("ANTHROPIC and Anthropic PBC; ANTH ticker") == (
        "ANTHROPIC and Anthropic PBC; ANT ticker"
    )
