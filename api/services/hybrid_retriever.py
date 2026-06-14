"""
hybrid_retriever.py — BM25 + Vector hybrid retrieval with RRF fusion.

Combines semantic (vector cosine similarity) and lexical (BM25) search on the
same corpus, then fuses rankings via Reciprocal Rank Fusion (RRF) before
handing off to the cross-encoder reranker.

Pipeline:  Chunk → [BM25 + Vector] → RRF → Rerank → LLM

BM25 index is built lazily on first query and cached for the process lifetime.
"""
from __future__ import annotations

import hashlib
import re
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
    boost_ticker: str = "",
    ticker_boost: float = 2.0,
) -> list[Document]:
    """Reciprocal Rank Fusion over multiple ranked lists.

    RRF_score(d) = Σ 1 / (k + rank_i(d))

    If boost_ticker is set, docs whose ticker matches get their contribution
    multiplied by ticker_boost at fusion time, so they float to the top
    without completely excluding cross-ticker context.

    Uses (ticker, accession, content_hash) as a stable content key so the same
    chunk appearing in both BM25 and vector results is correctly deduplicated.
    """
    if k < 1:
        raise ValueError(f"rrf k must be >= 1, got {k}")
    if ticker_boost < 1.0:
        raise ValueError(f"ticker_boost must be >= 1.0, got {ticker_boost}")

    scores: dict[tuple, float] = {}
    doc_map: dict[tuple, Document] = {}

    for ranked_list in rankings:
        for rank, doc in enumerate(ranked_list):
            key = (
                doc.metadata.get("ticker", ""),
                doc.metadata.get("accession", ""),
                hashlib.md5(doc.page_content.encode()).hexdigest()[:16],
            )
            doc_map[key] = doc
            base = 1.0 / (k + rank + 1)
            if boost_ticker and doc.metadata.get("ticker") == boost_ticker:
                base *= ticker_boost
            scores[key] = scores.get(key, 0.0) + base

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


def bm25_search(
    query: str,
    top_k: int = 5,
    ticker: str = "",
    ticker_boost: float = 2.0,
) -> list[Document]:
    """Run BM25 keyword search over the full edgar_embeddings corpus.

    When ticker is provided, raw BM25 scores for matching docs are multiplied
    by ticker_boost before ranking — so they float to the top without hard-
    excluding cross-ticker chunks that may be highly relevant.
    """
    result = _load_bm25_index()
    if result is None:
        return []

    bm25, docs, _ = result
    query_tokens = tokenize(query)
    raw_scores = bm25.get_scores(query_tokens)

    if ticker:
        boosted = [
            (idx, s * ticker_boost if docs[idx].metadata.get("ticker") == ticker else s)
            for idx, s in enumerate(raw_scores)
        ]
    else:
        boosted = list(enumerate(raw_scores))

    scored = sorted(boosted, key=lambda x: x[1], reverse=True)
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


# ── Company name → ticker resolver ───────────────────────────────────────────

# Maps lowercase company name / unambiguous alias → ticker symbol.
# Rules for inclusion:
#   - Multi-word phrases are always safe (word-boundary regex handles them).
#   - Single words must be >= 5 chars AND not common English words.
#     Short ambiguous forms ("amd", "kla", "on") are intentionally excluded;
#     only their unambiguous long-form names are kept.
_COMPANY_ALIASES: dict[str, str] = {
    # Multi-word first (also matched first due to longest-key sort)
    "analog devices": "ADI",
    "advanced micro devices": "AMD",
    "taiwan semiconductor": "TSM",
    "nxp semiconductors": "NXPI",
    "microchip technology": "MCHP",
    "monolithic power": "MPWR",
    "on semiconductor": "ON",
    "applied materials": "AMAT",
    "lam research": "LRCX",
    "kla corporation": "KLAC",
    "onto innovation": "ONTO",
    "kulicke & soffa": "KLIC",
    "ichor holdings": "ICHR",
    "aehr test systems": "AEHR",
    "texas instruments": "TXN",
    "micron technology": "MU",
    "space exploration technologies": "SPCX",
    "space exploration": "SPCX",
    "space x": "SPCX",
    # Single-word aliases — unambiguous, >= 5 chars, not common English words
    "spacex": "SPCX",
    "broadcom": "AVGO",
    "intel": "INTC",
    "micron": "MU",
    "nvidia": "NVDA",
    "qualcomm": "QCOM",
    "tsmc": "TSM",
    "marvell": "MRVL",
    "microchip": "MCHP",
    "skyworks": "SWKS",
    "qorvo": "QRVO",
    "onsemi": "ON",
    "teradyne": "TER",
    "entegris": "ENTG",
    "formfactor": "FORM",
    "photronics": "PLAB",
    "kulicke": "KLIC",
    "ichor": "ICHR",
    "veeco": "VECO",
    "axcelis": "ACLS",
    "amkor": "AMKR",
    "cohu": "COHU",
    "aehr": "AEHR",
}

# Pre-compile regex patterns sorted longest-first so multi-word phrases match
# before their single-word substrings (e.g. "micron technology" before "micron").
_ALIAS_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b" + re.escape(alias) + r"\b", re.IGNORECASE), ticker)
    for alias, ticker in sorted(_COMPANY_ALIASES.items(), key=lambda x: len(x[0]), reverse=True)
]


def resolve_ticker_from_query(query: str, ticker: str = "") -> str:
    """Return the ticker to use for retrieval.

    If ticker is already set by the caller, return it unchanged.
    Otherwise scan the query for a known company name (whole-word match,
    longest alias wins) and return the mapped ticker.

    Returns "" if no match — callers must treat that as "no ticker filter".
    """
    if ticker:
        return ticker
    if not query:
        return ""
    for pattern, resolved in _ALIAS_PATTERNS:
        if pattern.search(query):
            logger.info(f"Auto-resolved ticker {resolved!r} from query text")
            return resolved
    return ""


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
    ticker_boost: float = 2.0

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        # Resolve ticker from query if caller didn't set one explicitly
        # ("Micron's revenue" → MU, "NVIDIA gross margin" → NVDA, etc.)
        effective_ticker = resolve_ticker_from_query(query, self.ticker)

        bm25_docs = bm25_search(query, top_k=self.top_k * 2, ticker=effective_ticker, ticker_boost=self.ticker_boost)
        vec_docs  = vector_search(query, top_k=self.top_k * 2, ticker=effective_ticker)

        # If only one method returned results, use it directly
        if not bm25_docs and not vec_docs:
            return []
        if not bm25_docs:
            return vec_docs[:self.top_k]
        if not vec_docs:
            return bm25_docs[:self.top_k]

        # RRF fusion with additional ticker boost at merge time
        fused = rrf_fuse([vec_docs, bm25_docs], k=self.rrf_k,
                         boost_ticker=effective_ticker, ticker_boost=self.ticker_boost)
        logger.debug(
            "Hybrid RRF: {} vector + {} BM25 -> {} fused (top_k={}, ticker={}, boost={}×)",
            len(vec_docs), len(bm25_docs), len(fused), self.top_k, effective_ticker, self.ticker_boost,
        )
        return fused[:self.top_k]
