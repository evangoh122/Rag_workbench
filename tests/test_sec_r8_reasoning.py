"""tests/test_sec_r8_reasoning.py — PR40 r8 peer reasoning-canonicalization.

The peer-comparison path surfaces its internal ticker keys (``ANTH``) in the
``verification.reasoning`` text the chat route returns. Only that user-facing
reasoning string is canonicalized; ``resolved_ticker``, ``chart.ticker``,
retrieved-doc metadata and other stored keys stay ``ANTH``.
"""
from __future__ import annotations

import re
from contextlib import ExitStack
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.middleware.auth import get_read_api_key
from api.routes import chat as chat_routes
from api.services import langgraph_engine, peer_comparison


def _metric(ticker: str, metric: str):
    return {
        "value": 10.0 if ticker == "ANTH" else 20.0,
        "period": "2025",
        "ok": True,
    }


def _peer_patches(stack: ExitStack, subject_peers):
    stack.enter_context(patch.object(
        peer_comparison, "resolve_peers",
        return_value={
            "peers": subject_peers,
            "named_competitors": [],
            "from_graph": [],
        },
    ))
    stack.enter_context(patch.object(
        peer_comparison, "compute_metric", side_effect=_metric,
    ))
    stack.enter_context(patch(
        "api.services.chart_tool.build_chart_spec",
        return_value={
            "data": [
                {"period": "2024", "value": 1.0},
                {"period": "2025", "value": 2.0},
            ],
        },
    ))
    stack.enter_context(patch.object(
        langgraph_engine, "_generate_educational_layers", return_value={},
    ))
    stack.enter_context(patch.object(langgraph_engine, "_spawn_consensus"))


def test_run_auditable_rag_peer_reasoning_is_canonical():
    with ExitStack() as stack:
        _peer_patches(stack, ["NVDA"])
        result = langgraph_engine.run_auditable_rag(
            "How does Anthropic compare with its peers?", "ANTH"
        )

    reasoning = result["verification_reasoning"]
    assert re.search(r"\bANTH\b", reasoning) is None
    assert "Peer comparison: Revenue across ANT, NVDA" in reasoning

    # Other user-visible peer fields are canonical too.
    assert re.search(r"\bANTH\b", result["final_answer"]) is None
    assert "| ANT *(subject)*" in result["final_answer"]
    assert re.search(r"\bANTH\b", result["what_it_means"]) is None
    assert all(re.search(r"\bANTH\b", f) is None for f in result["follow_ups"])

    # Internal identifiers keep the stored corpus key.
    assert result["resolved_ticker"] == "ANTH"
    assert result["chart"]["ticker"] == "ANTH"
    assert any(
        doc["metadata"]["ticker"] == "ANTH" for doc in result["retrieved_docs"]
    )


def test_non_ant_peer_reasoning_is_unchanged():
    with ExitStack() as stack:
        _peer_patches(stack, ["AMD"])
        result = langgraph_engine.run_auditable_rag(
            "How does NVIDIA compare with its peers?", "NVDA"
        )

    assert result["verification_reasoning"] == (
        "Peer comparison: Revenue across NVDA, AMD (mode=peer)."
    )


def test_shaped_response_canonicalizes_only_standalone_symbol():
    result = peer_comparison._shaped_response(
        "ans",
        "ANTHROPIC filed; Anthropic PBC and an ant colony; ANTH ticker; ANTH.",
    )

    assert result["verification_reasoning"] == (
        "ANTHROPIC filed; Anthropic PBC and an ant colony; ANT ticker; ANT."
    )


@pytest.fixture
def _chat_auth():
    app.dependency_overrides[get_read_api_key] = lambda: "test-key"
    yield
    app.dependency_overrides.clear()


@pytest.mark.usefixtures("_chat_auth")
def test_chat_auditable_rag_reasoning_boundary_is_canonical():
    client = TestClient(app)
    with ExitStack() as stack:
        _peer_patches(stack, ["NVDA"])
        stack.enter_context(patch.object(
            chat_routes, "check_input",
            return_value=type("Verdict", (), {"blocked": False})(),
        ))
        stack.enter_context(patch.object(
            chat_routes, "check_dialog",
            return_value=type(
                "Verdict", (), {"advice": False, "off_topic": False}
            )(),
        ))
        stack.enter_context(patch.object(
            chat_routes, "check_output",
            return_value=type("Verdict", (), {"masked_answer": None})(),
        ))
        response = client.post(
            "/api/chat/auditable-rag",
            json={
                "message": "How does Anthropic compare with its peers?",
                "ticker": "ANT",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert re.search(r"\bANTH\b", body["verification"]["reasoning"]) is None
    assert "ANT" in body["verification"]["reasoning"]
    assert re.search(r"\bANTH\b", body["answer"]) is None
    assert body["ticker"] == "ANTH"
    assert body["chart"]["ticker"] == "ANTH"
