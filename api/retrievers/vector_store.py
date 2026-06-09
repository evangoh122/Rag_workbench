from typing import List
from langchain_core.documents import Document
from api.db.database import db_manager
from api.config import Config
from scripts.embed_tickers import _get_embeddings as get_embeddings
from loguru import logger

from rank_bm25 import BM25Okapi
import numpy as np

class BM25EmbeddingRetriever:
    """BM25 search over stored edgar_embeddings text."""

    def __init__(self, top_k: int = 5):
        self.top_k = top_k
        self._corpus: list[str] = []
        self._metadata: list[dict] = []
        self._bm25: BM25Okapi | None = None

    def _load_corpus(self, conn) -> None:
        rows = conn.execute(
            "SELECT ticker, accession, text, cik, section_id, form_type, period_of_report"
            " FROM edgar_embeddings"
        ).fetchall()
        self._corpus = [r[2] for r in rows]
        self._metadata = [
            {
                "ticker": r[0],
                "accession": r[1],
                "cik": r[3] or "",
                "section_id": r[4] or "",
                "form_type": r[5] or "10-K",
                "period_of_report": r[6] or "",
            }
            for r in rows
        ]
        tokenized = [doc.lower().split() for doc in self._corpus]
        self._bm25 = BM25Okapi(tokenized)

    def search(self, conn, query: str) -> List[Document]:
        if not self._corpus:
            try:
                self._load_corpus(conn)
            except Exception as e:
                logger.warning(f"BM25 corpus load failed: {e}")
                return []
        if not self._bm25:
            return []
        scores = self._bm25.get_scores(query.lower().split())
        top_idx = np.argsort(scores)[::-1][: self.top_k]
        return [
            Document(
                page_content=self._corpus[i],
                metadata={
                    **self._metadata[i],
                    "source": "bm25",
                    "score": float(scores[i]),
                },
            )
            for i in top_idx
            if scores[i] > 0
        ]

    def invalidate(self) -> None:
        """Clear cached corpus so it will be reloaded on next search."""
        self._corpus = []
        self._metadata = []
        self._bm25 = None

def _rrf_merge(
    dense: List[Document],
    sparse: List[Document],
    k: int = 60,
    alpha: float = 0.7,
) -> List[Document]:
    """Reciprocal Rank Fusion — combine dense and sparse ranked lists."""
    scores: dict[str, float] = {}
    content_map: dict[str, Document] = {}

    for rank, doc in enumerate(dense):
        key = doc.page_content[:100]
        scores[key] = scores.get(key, 0.0) + alpha / (k + rank + 1)
        content_map[key] = doc

    for rank, doc in enumerate(sparse):
        key = doc.page_content[:100]
        scores[key] = scores.get(key, 0.0) + (1 - alpha) / (k + rank + 1)
        content_map.setdefault(key, doc)

    return [
        content_map[key]
        for key in sorted(scores, key=scores.__getitem__, reverse=True)
    ]

# Module-level singleton BM25 retriever
_bm25_retriever = BM25EmbeddingRetriever(top_k=5)
