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
    @patch("api.services.langgraph_engine.get_app")
    def test_run_auditable_rag(self, mock_get_app):
        mock_app = MagicMock()
        mock_get_app.return_value = mock_app
        mock_app.invoke.return_value = {"final_answer": "Mocked Answer"}
        
        result = run_auditable_rag("What is revenue?", "AAPL")
        assert result["final_answer"] == "Mocked Answer"
