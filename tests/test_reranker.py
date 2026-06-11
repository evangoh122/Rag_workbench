"""
tests/test_reranker.py — Unit tests for the cross-encoder reranker service.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest
from langchain_core.documents import Document

from api.services.reranker import rerank


@pytest.fixture
def sample_docs():
    return [
        Document(page_content="Apple reported revenue of $383 billion", metadata={"source": "edgar", "ticker": "AAPL"}),
        Document(page_content="The weather is sunny today", metadata={"source": "noise"}),
        Document(page_content="Apple's gross margin was 45 percent", metadata={"source": "edgar", "ticker": "AAPL"}),
        Document(page_content="Random text about cooking recipes", metadata={"source": "noise"}),
        Document(page_content="Apple net income reached $97 billion", metadata={"source": "edgar", "ticker": "AAPL"}),
    ]


class TestReranker:
    def test_empty_docs_returns_empty(self):
        result = rerank("test query", [], top_k=5)
        assert result == []

    def test_model_unavailable_returns_truncated(self, sample_docs):
        """When CrossEncoder is unavailable, docs should be returned truncated to top_k."""
        with patch("api.services.reranker._get_model", return_value=None):
            result = rerank("Apple revenue", sample_docs, top_k=3)
            assert len(result) == 3
            assert result == sample_docs[:3]

    def test_rerank_scores_and_sorts(self, sample_docs):
        """When model is available, docs should be reranked by score descending."""
        mock_model = MagicMock()
        # Scores: irrelevant docs get low scores, relevant docs get high scores
        mock_model.predict.return_value = [0.9, 0.1, 0.8, 0.05, 0.7]

        with patch("api.services.reranker._get_model", return_value=mock_model):
            result = rerank("Apple revenue", sample_docs, top_k=3)

        assert len(result) == 3
        # Most relevant (0.9) should be first
        assert result[0].page_content == "Apple reported revenue of $383 billion"
        # Second most relevant (0.8)
        assert result[1].page_content == "Apple's gross margin was 45 percent"
        # Third most relevant (0.7)
        assert result[2].page_content == "Apple net income reached $97 billion"

    def test_rerank_top_k_limits_results(self, sample_docs):
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.9, 0.1, 0.8, 0.05, 0.7]

        with patch("api.services.reranker._get_model", return_value=mock_model):
            result = rerank("Apple revenue", sample_docs, top_k=2)

        assert len(result) == 2

    def test_rerank_preserves_metadata(self, sample_docs):
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.9, 0.1, 0.8, 0.05, 0.7]

        with patch("api.services.reranker._get_model", return_value=mock_model):
            result = rerank("Apple revenue", sample_docs, top_k=1)

        assert result[0].metadata["ticker"] == "AAPL"
        assert result[0].metadata["source"] == "edgar"

    def test_rerank_calls_model_with_correct_pairs(self, sample_docs):
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.5] * 5

        with patch("api.services.reranker._get_model", return_value=mock_model):
            rerank("test query", sample_docs, top_k=3)

        call_args = mock_model.predict.call_args[0][0]
        assert len(call_args) == 5
        assert call_args[0] == ("test query", "Apple reported revenue of $383 billion")

    def test_rerank_predict_failure_returns_truncated(self, sample_docs):
        """If model.predict() raises, docs should be returned truncated (fail silently)."""
        mock_model = MagicMock()
        mock_model.predict.side_effect = RuntimeError("CUDA out of memory")

        with patch("api.services.reranker._get_model", return_value=mock_model):
            result = rerank("Apple revenue", sample_docs, top_k=3)

        assert len(result) == 3
        assert result == sample_docs[:3]
