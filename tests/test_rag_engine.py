import pytest
from unittest.mock import MagicMock, patch
from langchain_core.documents import Document
from api.services.rag_engine import (
    DuckDBVectorRetriever, EDGARFactsRetriever, EDGAREmbeddingsRetriever, _format_docs
)

class TestRagEngine:
    @pytest.fixture
    def mock_db(self):
        with patch("api.services.rag_engine.db_manager") as mock:
            yield mock

    @pytest.fixture
    def mock_embeddings(self):
        with patch("api.services.rag_engine.get_embeddings") as mock:
            mock_inst = MagicMock()
            mock.return_value = mock_inst
            yield mock_inst

    def test_format_docs(self):
        docs = [
            Document(page_content="Content 1", metadata={"source": "src1", "ticker": "T1"}),
            Document(page_content="Content 1", metadata={"source": "src1", "ticker": "T1"}), # Duplicate
            Document(page_content="Content 2", metadata={"source": "src2"}),
        ]
        formatted = _format_docs(docs)
        assert "Content 1" in formatted
        assert "Content 2" in formatted
        # Should only have 2 unique parts
        assert formatted.count("[src") == 2

    def test_vector_retriever_empty_db(self, mock_db):
        mock_db.get_connection.return_value.execute.return_value.fetchone.return_value = [0]
        retriever = DuckDBVectorRetriever(top_k=2)
        
        # Should fallback to keyword search
        with patch.object(DuckDBVectorRetriever, "_keyword_fallback") as mock_fallback:
            mock_fallback.return_value = [Document(page_content="fallback")]
            results = retriever.invoke("test query")
            assert len(results) == 1
            assert results[0].page_content == "fallback"

    def test_edgar_facts_retriever(self, mock_db):
        # Mocking ticker search
        mock_db.get_connection.return_value.execute.return_value.fetchall.side_effect = [
            [("NVDA",)], # Found ticker
            [("NVDA", "Revenue", 1000.0, "USD", "2023-12-31", "10-K")] # Found fact
        ]
        retriever = EDGARFactsRetriever(top_k=1)
        results = retriever.invoke("What is NVDA revenue?")
        
        assert len(results) == 1
        assert "NVDA EDGAR facts" in results[0].page_content
        assert "Revenue: 1,000" in results[0].page_content

    def test_edgar_embeddings_retriever(self, mock_db, mock_embeddings):
        mock_db.get_connection.return_value.execute.return_value.fetchone.return_value = [10]
        mock_db.get_connection.return_value.execute.return_value.fetchall.return_value = [
            ("NVDA", "Text chunk", "acc-123", 0.1)
        ]
        mock_embeddings.embed_query.return_value = [0.1] * 768
        
        retriever = EDGAREmbeddingsRetriever(top_k=1)
        results = retriever.invoke("AI chips")
        
        assert len(results) == 1
        assert results[0].metadata["ticker"] == "NVDA"
        assert results[0].page_content == "Text chunk"
