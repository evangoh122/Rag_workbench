"""
hybrid_retriever.py — BM25 + Vector hybrid retrieval with RRF fusion.

Combines semantic (vector cosine similarity) and lexical (BM25) search on the
same corpus, then fuses rankings via Reciprocal Rank Fusion (RRF) before
handing off to the cross-encoder reranker.

Pipeline:  Chunk → [BM25 + Vector] → RRF → Rerank → LLM

BM25 index is built lazily on first query and cached for the process lifetime.
"""
from __future__ import annotations

import threading
from typing import List, Optional

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks.manager import CallbackManagerForRetrieverRun
from loguru import logger
from rank_bm25 import BM25Okapi

from api.config import Config
from api.db.database import db_manager
from api.services.embeddings import get_embeddings

# ── Tokenizer ─────────────────────────────────────────────────────────────────

def tokenize(text: str) -> list[str]:
    """Simple whitespace + lowercase tokenisation for BM25."""
    return text.lower().split()


# ── RRF Fusion ────────────────────────────────────────────────────────────────

def rrf_fuse(
    rankings: list[list[Document]],
    k: int = 60,
) -> list[Document]:
    """Reciprocal Rank Fusion over multiple ranked lists.

    RRF_score(d) = Σ 1 / (k + rank_i(d))

    Uses (ticker, accession, text[:80]) as a stable content key so the same
    chunk appearing in both BM25 and vector results is correctly deduplicated.
    """
    scores: dict[tuple, float] = {}
    doc_map: dict[tuple, Document] = {}

    for ranked_list in rankings:
        for rank, doc in enumerate(ranked_list):
            key = (
                doc.metadata.get("ticker", ""),
                doc.metadata.get("accession", ""),
                doc.page_content[:80],
            )
            doc_map[key] = doc
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)

    sorted_keys = sorted(scores, key=lambda k_: scores[k_], reverse=True)
    return [doc_map[k_] for k_ in sorted_keys]


# ── BM25 index cache ──────────────────────────────────────────────────────────

_bm25_lock = threading.Lock()
_bm25_index: Optional[BM25Okapi] = None
_bm25_docs: Optional[list[Document]] = None
_bm25_tokenised: Optional[list[list[str]]] = None


def _load_bm25_index() -> tuple[BM25Okapi, list[Document], list[list[str]]] | None:
    """Load edgar_embeddings into an in-memory BM25 index (cached)."""
    global _bm25_index, _bm25_docs, _bm25_tokenised

    if _bm25_index is not None:
        return _bm25_index, _bm25_docs, _bm25_tokenised

    with _bm25_lock:
        if _bm25_index is not None:
            return _bm25_index, _bm25_docs, _bm25_tokenised

        try:
            conn = db_manager.get_connection()
            rows = conn.execute(
                "SELECT ticker, text, accession FROM edgar_embeddings"
            ).fetchall()

            if not rows:
                logger.info("edgar_embeddings empty — BM25 index not built")
                return None

            docs: list[Document] = []
            tokenised: list[list[str]] = []
            for ticker, text, accession in rows:
                docs.append(Document(
                    page_content=text,
                    metadata={"source": "edgar_embeddings", "ticker": ticker, "accession": accession},
                ))
                tokenised.append(tokenize(text))

            bm25 = BM25Okapi(tokenised)
            _bm25_index = bm25
            _bm25_docs = docs
            _bm25_tokenised = tokenised
            logger.info("BM25 index built from {} edgar_embeddings rows", len(docs))
        except Exception as e:
            logger.error("Failed to build BM25 index: {}", e)
            return None

    return _bm25_index, _bm25_docs, _bm25_tokenised


def bm25_search(query: str, top_k: int = 5, ticker: str = "") -> list[Document]:
    """Run BM25 keyword search over edgar_embeddings, optionally filtered to one ticker."""
    result = _load_bm25_index()
    if result is None:
        return []

    bm25, docs, _ = result
    query_tokens = tokenize(query)
    scores = bm25.get_scores(query_tokens)

    scored = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
    if ticker:
        scored = [(idx, s) for idx, s in scored if docs[idx].metadata.get("ticker") == ticker]
    return [docs[idx] for idx, _ in scored[:top_k]]


def vector_search(query: str, top_k: int = 5, ticker: str = "") -> list[Document]:
    """Run cosine-similarity vector search over edgar_embeddings."""
    try:
        conn = db_manager.get_connection()
        count = conn.execute("SELECT COUNT(*) FROM edgar_embeddings").fetchone()[0]
        if count == 0:
            return []

        embeddings = get_embeddings()
        if embeddings is None:
            logger.warning("Ollama embeddings not available — vector search skipped")
            return []
        qvec = embeddings.embed_query(query)

        if ticker:
            rows = conn.execute(f"""
                SELECT ticker, text, accession,
                       array_distance(embedding, ?::FLOAT[{Config.EMBEDDING_DIM}]) AS dist
                FROM edgar_embeddings
                WHERE ticker = ?
                ORDER BY dist ASC
                LIMIT ?
            """, [qvec, ticker, top_k]).fetchall()
        else:
            rows = conn.execute(f"""
                SELECT ticker, text, accession,
                       array_distance(embedding, ?::FLOAT[{Config.EMBEDDING_DIM}]) AS dist
                FROM edgar_embeddings
                ORDER BY dist ASC
                LIMIT ?
            """, [qvec, top_k]).fetchall()

        return [
            Document(
                page_content=r[1],
                metadata={"source": "edgar_embeddings", "ticker": r[0], "accession": r[2], "distance": r[3]},
            )
            for r in rows
        ]
    except Exception as e:
        logger.warning("Vector search failed: {}", e)
        return []


# ── Hybrid Retriever ──────────────────────────────────────────────────────────

class EDGARHybridRetriever(BaseRetriever):
    """BM25 + Vector hybrid retriever with RRF fusion.

    Runs both retrieval methods in sequence on the edgar_embeddings corpus,
    fuses rankings via Reciprocal Rank Fusion, and returns the merged list.
    Falls back gracefully to whichever method is available.
    """
    top_k: int = 5
    ticker: str = ""
    rrf_k: int = 60

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        bm25_docs = bm25_search(query, top_k=self.top_k * 2, ticker=self.ticker)
        vec_docs = vector_search(query, top_k=self.top_k * 2, ticker=self.ticker)

        # If only one method returned results, use it directly
        if not bm25_docs and not vec_docs:
            return []
        if not bm25_docs:
            return vec_docs[:self.top_k]
        if not vec_docs:
            return bm25_docs[:self.top_k]

        # RRF fusion
        fused = rrf_fuse([vec_docs, bm25_docs], k=self.rrf_k)
        logger.debug(
            "Hybrid RRF: {} vector + {} BM25 -> {} fused (top_k={})",
            len(vec_docs), len(bm25_docs), len(fused), self.top_k,
        )
        return fused[:self.top_k]
