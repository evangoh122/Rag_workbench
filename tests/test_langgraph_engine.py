"""
tests/test_langgraph_engine.py — Unit tests for the LangGraph engine.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest
import polars as pl
from api.services.langgraph_engine import (
    retrieval_node, extraction_node, math_node, verification_node,
    eval_node, output_node, abstention_node, run_auditable_rag
)

@pytest.fixture
def base_state():
    return {
        "query": "What is the gross margin for AAPL?",
        "ticker": "AAPL",
        "retrieved_docs": [],
        "xbrl_facts": [],
        "math_result": None,
        "math_steps": [],
        "verification_status": "PENDING",
        "verification_reasoning": "",
        "final_answer": "",
        "status": {},
    }

class TestLangGraphNodes:
    @patch("api.services.langgraph_engine.EDGARHybridRetriever")
    @patch("api.services.langgraph_engine.rerank_docs")
    @patch("api.services.langgraph_engine.filter_retrieval")
    def test_retrieval_node(self, mock_filter, mock_rerank, mock_retriever_cls, base_state):
        mock_retriever = mock_retriever_cls.return_value
        mock_doc = MagicMock()
        mock_doc.page_content = "Apple revenue was $383B"
        mock_doc.metadata = {"source": "10-K"}
        mock_retriever.invoke.return_value = [mock_doc]

        mock_rerank.return_value = [mock_doc]

        mock_filter.return_value.filtered_chunks = [
            {"chunk_text": "Apple revenue was $383B", "metadata": {"source": "10-K"}}
        ]
        mock_filter.return_value.dropped_count = 0
        
        result = retrieval_node(base_state)
        assert len(result["retrieved_docs"]) == 1
        assert result["retrieved_docs"][0]["chunk_text"] == "Apple revenue was $383B"
        assert result["status"]["retrieval"] == "success"

    @patch("api.services.langgraph_engine.get_latest_10k_facts")
    def test_extraction_node(self, mock_get_facts, base_state):
        df = pl.DataFrame({
            "concept": ["Revenues"],
            "value": [383000000000.0]
        })
        mock_get_facts.return_value = df
        
        result = extraction_node(base_state)
        assert len(result["xbrl_facts"]) == 1
        assert result["xbrl_facts"][0]["concept"] == "Revenues"
        assert result["status"]["extraction"] == "success"

    def test_math_node_gross_margin(self, base_state):
        base_state["xbrl_facts"] = [
            {"concept": "Revenues", "value": 1000.0, "period": "2023-12-31"},
            {"concept": "CostOfRevenue", "value": 600.0, "period": "2023-12-31"}
        ]
        base_state["query"] = "What is the gross margin?"
        
        result = math_node(base_state)
        assert result["math_result"] == 40.0
        assert any("Gross Margin" in step for step in result["math_steps"])

    @patch("api.services.langgraph_engine.verifier.verify_entailment")
    def test_verification_node_pass(self, mock_verify, base_state):
        base_state["retrieved_docs"] = [{"chunk_text": "Revenue was $1000"}]
        base_state["math_result"] = 1000.0
        mock_verify.return_value = ("PASS", "Values match.")
        
        result = verification_node(base_state)
        assert result["verification_status"] == "PASS"
        assert result["verification_reasoning"] == "Values match."

    @patch("api.services.langgraph_engine.validate_extraction")
    @patch("api.services.langgraph_engine.score_and_route")
    def test_eval_node(self, mock_score, mock_validate, base_state):
        base_state["xbrl_facts"] = [{"concept": "Revenues", "value": 1000.0}]
        
        mock_validate.return_value.is_valid = True
        mock_score.return_value.route.value = "AUTO"
        mock_score.return_value.confidence = 0.95
        mock_score.return_value.triggers_fired = []
        
        result = eval_node(base_state)
        assert result["eval_route"] == "AUTO"
        assert result["eval_confidence"] == 0.95

    def test_output_node(self, base_state):
        base_state["math_result"] = 40.0
        base_state["verification_status"] = "PASS"
        base_state["verification_reasoning"] = "Verified."
        
        result = output_node(base_state)
        assert "40.0" in result["final_answer"]
        assert "Verified." in result["final_answer"]

    def test_abstention_node(self, base_state):
        result = abstention_node(base_state)
        assert "cannot answer" in result["final_answer"]

class TestLangGraphFullFlow:
    @patch("api.services.langgraph_engine._generate_educational_layers", return_value={})
    @patch("api.services.langgraph_engine.get_app")
    def test_run_auditable_rag(self, mock_get_app, _mock_layers):
        mock_app = MagicMock()
        mock_get_app.return_value = mock_app
        mock_app.invoke.return_value = {"final_answer": "Mocked Answer"}

        result = run_auditable_rag("What is revenue?", "AAPL")
        assert result["final_answer"] == "Mocked Answer"
        # Educational-layer keys are always present (additive, default empty).
        assert result["what_it_means"] == ""
        assert result["how_to_interpret"] == ""
        assert result["follow_ups"] == []

    @patch("api.services.langgraph_engine.get_app")
    def test_run_auditable_rag_attaches_layers(self, mock_get_app):
        mock_app = MagicMock()
        mock_get_app.return_value = mock_app
        mock_app.invoke.return_value = {"final_answer": "Revenue was $37.4B."}
        with patch(
            "api.services.langgraph_engine._generate_educational_layers",
            return_value={
                "what_it_means": "It earned 37.4B.",
                "how_to_interpret": "Revenue is sales before costs.",
                "follow_ups": ["How did it grow?"],
            },
        ):
            result = run_auditable_rag("What is revenue?", "AAPL")
        assert result["what_it_means"] == "It earned 37.4B."
        assert result["follow_ups"] == ["How did it grow?"]

    @patch("api.services.langgraph_engine._generate_educational_layers", return_value={})
    @patch("api.services.langgraph_engine.get_app")
    def test_resolved_ticker_overrides_when_company_named(self, mock_get_app, _layers):
        """A question naming a company resolves to it, not the UI default — and
        this is generic across the covered universe, not just NVDA/MU."""
        mock_app = MagicMock()
        mock_get_app.return_value = mock_app
        mock_app.invoke.return_value = {"final_answer": "ok"}

        # caller passes the stale UI default; the named company must win.
        for query, expected in [
            ("What was NVIDIA's revenue?", "NVDA"),
            ("Tell me about Broadcom margins", "AVGO"),
            ("Intel risk factors?", "INTC"),
            ("Texas Instruments gross profit", "TXN"),
        ]:
            result = run_auditable_rag(query, "MU")
            assert result["resolved_ticker"] == expected, query
            assert mock_app.invoke.call_args[0][0]["ticker"] == expected

    @patch("api.services.langgraph_engine._generate_educational_layers", return_value={})
    @patch("api.services.langgraph_engine.get_app")
    def test_resolved_ticker_persists_on_generic_followup(self, mock_get_app, _layers):
        """A follow-up naming no company stays on the persisted ticker the UI
        sends — for any company, so follow-ups don't fall back to the default."""
        mock_app = MagicMock()
        mock_get_app.return_value = mock_app
        mock_app.invoke.return_value = {"final_answer": "ok"}

        for persisted in ["AVGO", "INTC", "AMD", "TXN"]:
            result = run_auditable_rag("What about its gross margin?", persisted)
            assert result["resolved_ticker"] == persisted
            assert mock_app.invoke.call_args[0][0]["ticker"] == persisted


class TestEducationalLayers:
    """Sections 3–5 of the Standard Response Framework (additive, best-effort)."""

    def test_guard_refusal_returns_empty(self):
        from api.services.langgraph_engine import _generate_educational_layers
        out = _generate_educational_layers(
            "q", "I cannot answer this with sufficient confidence.", "MU")
        assert out == {}

    def test_guard_empty_answer_returns_empty(self):
        from api.services.langgraph_engine import _generate_educational_layers
        assert _generate_educational_layers("q", "", "MU") == {}

    def test_disabled_flag_returns_empty(self, monkeypatch):
        from api.services.langgraph_engine import _generate_educational_layers
        monkeypatch.setenv("ANSWER_FRAMEWORK_ENABLED", "false")
        assert _generate_educational_layers("q", "Revenue was $37.4B.", "MU") == {}

    def test_happy_path_parses_json(self, monkeypatch):
        from api.services import langgraph_engine as eng
        monkeypatch.delenv("ANSWER_FRAMEWORK_ENABLED", raising=False)
        payload = (
            '{"what_it_means": "plain english", '
            '"how_to_interpret": "context", '
            '"follow_ups": ["a", "b", "c"]}'
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=payload))]
        )
        with patch.object(eng.Config, "get_provider_config",
                          return_value={"api_key": "k", "base_url": "http://x", "model": "m"}), \
             patch("openai.OpenAI", return_value=mock_client):
            out = eng._generate_educational_layers("What is revenue?", "Revenue was $37.4B.", "MU")
        assert out["what_it_means"] == "plain english"
        assert out["how_to_interpret"] == "context"
        assert out["follow_ups"] == ["a", "b", "c"]

    def test_malformed_json_returns_empty(self, monkeypatch):
        from api.services import langgraph_engine as eng
        monkeypatch.delenv("ANSWER_FRAMEWORK_ENABLED", raising=False)
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="not json at all"))]
        )
        with patch.object(eng.Config, "get_provider_config",
                          return_value={"api_key": "k", "base_url": "http://x", "model": "m"}), \
             patch("openai.OpenAI", return_value=mock_client):
            out = eng._generate_educational_layers("q", "Revenue was $37.4B.", "MU")
        assert out == {}


class TestQueryClassification:
    """Numeric vs qualitative routing — segment/breakdown questions must NOT be
    answered with a single top-line XBRL number (the breakdown lives in the
    filing narrative, only the qualitative path reads it)."""

    def test_breakdown_questions_route_qualitative(self):
        from api.services.langgraph_engine import _is_numeric_query
        for q in [
            "How does Micron's revenue break down by product segment, such as memory chips or storage?",
            "What is the revenue breakdown by segment?",
            "Revenue by product category",
            "segment revenue composition",
            "revenue by geography",
            "data center segment revenue",
            # "Where does the revenue come from" follow-ups want the breakdown,
            # not the top-line total.
            "What were the main sources of this revenue, such as data center or gaming?",
            "What are NVIDIA's sources of revenue?",
            "Where does the revenue come from?",
            "What is its revenue driven by?",
        ]:
            assert _is_numeric_query(q) is False, q

    def test_plain_numeric_questions_stay_numeric(self):
        from api.services.langgraph_engine import _is_numeric_query
        for q in [
            "What was total revenue in 2023?",
            "What is the gross margin?",
            "net income last year",
            "free cash flow",
            "revenue year over year growth",
        ]:
            assert _is_numeric_query(q) is True, q
