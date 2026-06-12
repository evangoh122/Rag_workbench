"""
tests/test_hybrid_retriever.py — Unit tests for BM25 + Vector hybrid retriever.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch
from langchain_core.documents import Document

from api.services.hybrid_retriever import (
    tokenize,
    rrf_fuse,
    bm25_search,
    vector_search,
    resolve_ticker_from_query,
    EDGARHybridRetriever,
)


class TestTokenize:
    def test_basic(self):
        assert tokenize("Hello World") == ["hello", "world"]

    def test_preserves_case_lower(self):
        assert tokenize("Revenue GROSS Margin") == ["revenue", "gross", "margin"]

    def test_empty(self):
        assert tokenize("") == []


class TestRRFFuse:
    def test_single_list_passthrough(self):
        docs = [
            Document(page_content="A"),
            Document(page_content="B"),
        ]
        result = rrf_fuse([docs])
        assert len(result) == 2

    def test_two_lists_fused_by_rank(self):
        # Doc X is rank 1 in list A, rank 2 in list B
        # Doc Y is rank 2 in list A, rank 1 in list B
        # They should have equal RRF scores
        doc_x = Document(page_content="X")
        doc_y = Document(page_content="Y")

        result = rrf_fuse([[doc_x, doc_y], [doc_y, doc_x]])
        assert len(result) == 2
        # Both should have the same score: 1/(60+1) + 1/(60+2) each
        # Order doesn't matter since scores are equal

    def test_top_ranked_doc_wins(self):
        doc_best = Document(page_content="best")
        doc_worst = Document(page_content="worst")

        # best is rank 1 in both lists
        result = rrf_fuse([[doc_best, doc_worst], [doc_best, doc_worst]])
        assert result[0].page_content == "best"

    def test_unique_docs_across_lists(self):
        doc_a = Document(page_content="A")
        doc_b = Document(page_content="B")
        doc_c = Document(page_content="C")

        result = rrf_fuse([[doc_a, doc_b], [doc_b, doc_c]])
        assert len(result) == 3

    def test_empty_rankings(self):
        assert rrf_fuse([]) == []

    def test_custom_k_parameter(self):
        doc_a = Document(page_content="A")
        doc_b = Document(page_content="B")

        # With k=1, rank 1 gets 1/2=0.5, rank 2 gets 1/3≈0.333
        # With k=100, rank 1 gets 1/101≈0.0099, rank 2 gets 1/102≈0.0098
        # Both should rank A first regardless of k
        result = rrf_fuse([[doc_a, doc_b]], k=1)
        assert result[0].page_content == "A"

        result = rrf_fuse([[doc_a, doc_b]], k=100)
        assert result[0].page_content == "A"


class TestBM25Search:
    @patch("api.services.hybrid_retriever._load_bm25_index")
    def test_returns_empty_when_no_index(self, mock_load):
        mock_load.return_value = None
        assert bm25_search("test query") == []

    @patch("api.services.hybrid_retriever._load_bm25_index")
    def test_returns_ranked_docs(self, mock_load):
        from rank_bm25 import BM25Okapi

        docs = [
            Document(page_content="apple revenue growth", metadata={"ticker": "AAPL"}),
            Document(page_content="microsoft cloud services", metadata={"ticker": "MSFT"}),
            Document(page_content="apple iphone sales", metadata={"ticker": "AAPL"}),
        ]
        tokenised = [tokenize(d.page_content) for d in docs]
        bm25 = BM25Okapi(tokenised)
        mock_load.return_value = (bm25, docs, tokenised)

        results = bm25_search("apple", top_k=2)
        assert len(results) == 2
        # Both apple docs should rank above microsoft
        assert all("apple" in r.page_content for r in results)


class TestVectorSearch:
    @patch("api.services.hybrid_retriever.db_manager")
    @patch("api.services.hybrid_retriever.get_embeddings")
    def test_returns_empty_when_no_embeddings(self, mock_emb, mock_db):
        mock_db.get_connection.return_value.execute.return_value.fetchone.return_value = [10]
        mock_emb.return_value = None
        assert vector_search("test") == []

    @patch("api.services.hybrid_retriever.db_manager")
    @patch("api.services.hybrid_retriever.get_embeddings")
    def test_returns_empty_when_no_rows(self, mock_emb, mock_db):
        mock_db.get_connection.return_value.execute.return_value.fetchone.return_value = [0]
        assert vector_search("test") == []


class TestEDGARHybridRetriever:
    @patch("api.services.hybrid_retriever.bm25_search")
    @patch("api.services.hybrid_retriever.vector_search")
    def test_both_empty_returns_empty(self, mock_vec, mock_bm25):
        mock_bm25.return_value = []
        mock_vec.return_value = []

        retriever = EDGARHybridRetriever(top_k=5)
        results = retriever.invoke("test query")
        assert results == []

    @patch("api.services.hybrid_retriever.bm25_search")
    @patch("api.services.hybrid_retriever.vector_search")
    def test_only_bm25_returns_bm25(self, mock_vec, mock_bm25):
        bm25_docs = [Document(page_content="bm25 result")]
        mock_bm25.return_value = bm25_docs
        mock_vec.return_value = []

        retriever = EDGARHybridRetriever(top_k=5)
        results = retriever.invoke("test query")
        assert len(results) == 1
        assert results[0].page_content == "bm25 result"

    @patch("api.services.hybrid_retriever.bm25_search")
    @patch("api.services.hybrid_retriever.vector_search")
    def test_only_vector_returns_vector(self, mock_vec, mock_bm25):
        vec_docs = [Document(page_content="vector result")]
        mock_bm25.return_value = []
        mock_vec.return_value = vec_docs

        retriever = EDGARHybridRetriever(top_k=5)
        results = retriever.invoke("test query")
        assert len(results) == 1
        assert results[0].page_content == "vector result"

    @patch("api.services.hybrid_retriever.bm25_search")
    @patch("api.services.hybrid_retriever.vector_search")
    def test_both_return_rrf_fusion(self, mock_vec, mock_bm25):
        # Vector: [A, B], BM25: [B, A] — both agree B is relevant
        doc_a = Document(page_content="A")
        doc_b = Document(page_content="B")
        mock_vec.return_value = [doc_a, doc_b]
        mock_bm25.return_value = [doc_b, doc_a]

        retriever = EDGARHybridRetriever(top_k=5)
        results = retriever.invoke("test query")
        assert len(results) == 2
        # Both have equal RRF scores, so either order is fine
        contents = {r.page_content for r in results}
        assert contents == {"A", "B"}

    @patch("api.services.hybrid_retriever.bm25_search")
    @patch("api.services.hybrid_retriever.vector_search")
    def test_top_k_limits_results(self, mock_vec, mock_bm25):
        docs = [Document(page_content=f"doc{i}") for i in range(10)]
        mock_vec.return_value = docs
        mock_bm25.return_value = docs

        retriever = EDGARHybridRetriever(top_k=3)
        results = retriever.invoke("test query")
        assert len(results) == 3

    @patch("api.services.hybrid_retriever.bm25_search")
    @patch("api.services.hybrid_retriever.vector_search")
    def test_passes_ticker_to_vector_search(self, mock_vec, mock_bm25):
        mock_vec.return_value = []
        mock_bm25.return_value = []

        retriever = EDGARHybridRetriever(top_k=5, ticker="AAPL")
        retriever.invoke("test query")

        mock_vec.assert_called_once_with("test query", top_k=10, ticker="AAPL")


class TestResolveTickerFromQuery:
    # ── caller-provided ticker takes priority ────────────────────────────────
    def test_caller_ticker_returned_unchanged(self):
        assert resolve_ticker_from_query("What is Micron's revenue?", ticker="NVDA") == "NVDA"

    def test_caller_ticker_not_overridden_by_query(self):
        assert resolve_ticker_from_query("nvidia gross margin", ticker="MU") == "MU"

    # ── correct resolutions ──────────────────────────────────────────────────
    @pytest.mark.parametrize("query,expected", [
        ("What is Micron Technology's gross margin?", "MU"),
        ("micron revenue last year",                  "MU"),
        ("NVIDIA's total revenue in 10-K",            "NVDA"),
        ("nvidia gross margin",                       "NVDA"),
        ("What did Intel report in 2023?",            "INTC"),
        ("on semiconductor operating income",         "ON"),
        ("onsemi free cash flow",                     "ON"),
        ("lam research capital expenditure",          "LRCX"),
        ("kla corporation earnings",                  "KLAC"),
        ("micron technology vs advanced micro devices", "AMD"),  # "advanced micro devices" (22) > "micron technology" (17)
    ])
    def test_correct_resolution(self, query, expected):
        assert resolve_ticker_from_query(query) == expected

    # ── false-positive guard (MiMo issue #1) ────────────────────────────────
    @pytest.mark.parametrize("query", [
        "revenue on Q3 was strong",           # "on" as preposition
        "the amended filing shows growth",    # not "amd"
        "blacklisted vendor removed",         # not "kla"
        "compare Q1 to Q2 performance",       # no company name
        "what is the operating margin?",      # generic query
        "show me the income statement",       # generic query
    ])
    def test_no_false_positive(self, query):
        assert resolve_ticker_from_query(query) == ""

    # ── edge cases ───────────────────────────────────────────────────────────
    def test_none_query_returns_empty(self):
        assert resolve_ticker_from_query(None) == ""   # type: ignore[arg-type]

    def test_empty_string_returns_empty(self):
        assert resolve_ticker_from_query("") == ""

    def test_no_match_returns_empty(self):
        assert resolve_ticker_from_query("What is the weather today?") == ""

    def test_case_insensitive(self):
        assert resolve_ticker_from_query("MICRON Technology revenue") == "MU"
        assert resolve_ticker_from_query("Nvidia gross profit") == "NVDA"
