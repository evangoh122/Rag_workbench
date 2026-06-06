"""
asymmetric_rag.py
Asymmetric Dual-Model RAG Pipeline for Financial Documents.

Architecture:
  - Ingestion:  Qwen3-Embedding-8B   (heavy, offline, captures deep financial nuance)
  - Querying:   Qwen3-Embedding-0.6B (lightweight, runtime, sub-second latency)

Both models share an aligned semantic space — vectors from 0.6B map accurately
against vectors from 8B using standard cosine similarity.

Pipeline:
  1. Query Decomposition  — split compound queries into atomic sub-queries
  2. Dense Retrieval      — Qwen3-0.6B embeddings + cosine similarity
  3. Sparse Retrieval     — BM25Okapi keyword matching
  4. Reciprocal Rank Fusion (RRF) — merge dense + sparse rankings
  5. Cross-Encoder Reranking — bge-reranker-large for final relevance scoring
  6. Synthesis            — LLM generates answer from reranked context

Requires:
  ollama pull qwen3-embedding:8b
  ollama pull qwen3-embedding:0.6b
  pip install ollama rank_bm25 sentence-transformers
"""
import os
import math
import hashlib
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed

import duckdb
import numpy as np
from loguru import logger

# ── Configuration ─────────────────────────────────────────────────────────────

DB_PATH = os.getenv("DB_PATH", "./data/ibkr.duckdb")

# Asymmetric embedding models — different sizes, shared semantic space
INGESTION_MODEL = os.getenv("EMBED_MODEL_INGEST", "qwen3-embedding:8b")
QUERY_MODEL     = os.getenv("EMBED_MODEL_QUERY", "qwen3-embedding:0.6b")

# Reranker model — lightweight cross-encoder for final relevance scoring
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-base")

# Retrieval parameters
VECTOR_TOP_K   = int(os.getenv("VECTOR_TOP_K", "20"))
BM25_TOP_K     = int(os.getenv("BM25_TOP_K", "20"))
RRF_K          = int(os.getenv("RRF_K", "60"))       # RRF constant (standard: 60)
FINAL_TOP_K    = int(os.getenv("FINAL_TOP_K", "10"))  # after reranking
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "true").lower() == "true"

# Query decomposition
DECOMPOSE_ENABLED = os.getenv("DECOMPOSE_ENABLED", "true").lower() == "true"
MAX_SUB_QUERIES   = int(os.getenv("MAX_SUB_QUERIES", "4"))

# Embedding dimensions (auto-detected at runtime, fallback for DuckDB schema)
EMBED_DIM_INGEST = int(os.getenv("EMBED_DIM_INGEST", "1024"))
EMBED_DIM_QUERY  = int(os.getenv("EMBED_DIM_QUERY", "1024"))


# ── Data Structures ───────────────────────────────────────────────────────────

@dataclass
class RetrievedChunk:
    """A single retrieved chunk with its provenance and scores."""
    text: str
    source: str          # vector | bm25 | edgar_facts | edgar_embeddings | price
    ticker: str = ""
    metadata: dict = field(default_factory=dict)
    dense_rank: int = 0
    bm25_rank: int = 0
    rrf_score: float = 0.0
    rerank_score: float = 0.0
    content_hash: str = ""

    def __post_init__(self):
        if not self.content_hash:
            self.content_hash = hashlib.md5(self.text.encode()).hexdigest()


# ── Embedding Layer ───────────────────────────────────────────────────────────

class OllamaEmbedder:
    """
    Manages asymmetric embedding via Ollama.
    Uses 8B model for offline ingestion, 0.6B model for runtime queries.
    Both models share an aligned semantic space.
    """

    def __init__(self):
        self._client = None
        self._ingest_dim: Optional[int] = None
        self._query_dim: Optional[int] = None

    @property
    def client(self):
        if self._client is None:
            import ollama
            self._client = ollama
        return self._client

    def embed_ingest(self, texts: List[str]) -> List[List[float]]:
        """Embed documents using the heavy 8B ingestion model."""
        return self._embed_batch(texts, INGESTION_MODEL)

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query using the lightweight 0.6B query model."""
        # Instruction prefix routes the 0.6B vector into the 8B document domain
        instructional = (
            "Given a financial question, retrieve relevant documents "
            f"that answer the query: {text}"
        )
        resp = self.client.embeddings(model=QUERY_MODEL, prompt=instructional)
        return resp["embedding"]

    def embed_queries_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple queries using the 0.6B model (for query decomposition)."""
        return [self.embed_query(t) for t in texts]

    def _embed_batch(self, texts: List[str], model: str) -> List[List[float]]:
        """Embed a batch of texts, one at a time (Ollama doesn't support batch embed)."""
        vectors = []
        for text in texts:
            resp = self.client.embeddings(model=model, prompt=text)
            vectors.append(resp["embedding"])
        return vectors

    def get_ingest_dim(self) -> int:
        """Auto-detect ingestion model embedding dimension."""
        if self._ingest_dim is None:
            resp = self.client.embeddings(model=INGESTION_MODEL, prompt="test")
            self._ingest_dim = len(resp["embedding"])
            logger.info(f"Ingestion model ({INGESTION_MODEL}) dim: {self._ingest_dim}")
        return self._ingest_dim

    def get_query_dim(self) -> int:
        """Auto-detect query model embedding dimension."""
        if self._query_dim is None:
            resp = self.client.embeddings(model=QUERY_MODEL, prompt="test")
            self._query_dim = len(resp["embedding"])
            logger.info(f"Query model ({QUERY_MODEL}) dim: {self._query_dim}")
        return self._query_dim


# ── BM25 Sparse Retrieval ─────────────────────────────────────────────────────

class BM25Index:
    """
    BM25Okapi sparse keyword index over the document corpus.
    Built at startup from the same chunks stored in DuckDB.
    """

    def __init__(self):
        self._bm25 = None
        self._chunks: List[Dict] = []  # [{text, source, ticker, metadata}, ...]
        self._tokenized: List[List[str]] = []

    def build(self, chunks: List[Dict]):
        """Build BM25 index from a list of chunk dicts."""
        from rank_bm25 import BM25Okapi

        self._chunks = chunks
        self._tokenized = [
            self._tokenize(c["text"]) for c in chunks
        ]
        self._bm25 = BM25Okapi(self._tokenized)
        logger.info(f"BM25 index built: {len(chunks)} chunks")

    def search(self, query: str, top_k: int = BM25_TOP_K) -> List[Tuple[Dict, float]]:
        """Return top-k chunks by BM25 score."""
        if self._bm25 is None or not self._chunks:
            return []

        tokens = self._tokenize(query)
        scores = self._bm25.get_scores(tokens)

        # Get top-k indices
        top_indices = np.argsort(scores)[::-1][:top_k]
        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                results.append((self._chunks[idx], float(scores[idx])))
        return results

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Simple whitespace + lowercasing tokenization."""
        return text.lower().split()


# ── Reciprocal Rank Fusion ────────────────────────────────────────────────────

def reciprocal_rank_fusion(
    rankings: List[List[Tuple[str, float]]],
    k: int = RRF_K,
) -> List[Tuple[str, float]]:
    """
    Reciprocal Rank Fusion (RRF) — blends multiple ranked lists into one.

    Args:
        rankings: List of ranked lists. Each inner list is [(doc_id, score), ...]
        k: RRF constant (default 60, standard from the original paper).

    Returns:
        Fused list of (doc_id, rrf_score) sorted by score descending.

    Math:
        RRF_score(d) = sum over all rankings of: 1 / (k + rank_i(d))
    """
    scores: Dict[str, float] = {}

    for ranking in rankings:
        for rank, (doc_id, _) in enumerate(ranking, start=1):
            if doc_id not in scores:
                scores[doc_id] = 0.0
            scores[doc_id] += 1.0 / (k + rank)

    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return fused


# ── Cross-Encoder Reranker ────────────────────────────────────────────────────

class CrossEncoderReranker:
    """
    Lightweight cross-encoder reranker using sentence-transformers.
    Evaluates (query, document) pairs directly for relevance scoring.
    """

    def __init__(self):
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder
            logger.info(f"Loading cross-encoder reranker: {RERANKER_MODEL}")
            self._model = CrossEncoder(RERANKER_MODEL, max_length=512)
        return self._model

    def rerank(
        self, query: str, chunks: List[RetrievedChunk], top_k: int = FINAL_TOP_K
    ) -> List[RetrievedChunk]:
        """Rerank chunks by query-document relevance using cross-encoder."""
        if not chunks:
            return []

        pairs = [(query, c.text) for c in chunks]
        scores = self.model.predict(pairs)

        for chunk, score in zip(chunks, scores):
            chunk.rerank_score = float(score)

        reranked = sorted(chunks, key=lambda c: c.rerank_score, reverse=True)
        return reranked[:top_k]


# ── Query Decomposition ───────────────────────────────────────────────────────

def decompose_query(query: str, llm_client: Any = None) -> List[str]:
    """
    Break a compound query into atomic sub-queries using an LLM.

    Example:
        "Compare AAPL and MSFT revenue, also show NVDA's latest price"
        → ["AAPL revenue from latest 10-K", "MSFT revenue from latest 10-K",
           "NVDA latest stock price"]

    Falls back to heuristic splitting if no LLM is available.
    """
    if not DECOMPOSE_ENABLED:
        return [query]

    # Try LLM-based decomposition first
    if llm_client is not None:
        try:
            return _llm_decompose(query, llm_client)
        except Exception as e:
            logger.warning(f"LLM decomposition failed, using heuristic: {e}")

    return _heuristic_decompose(query)


def _llm_decompose(query: str, client: Any) -> List[str]:
    """Use an LLM to decompose compound queries into atomic sub-queries."""
    prompt = (
        "You are a query decomposition engine. Break the following compound "
        "financial question into independent atomic sub-questions. Each sub-question "
        "should be answerable on its own. Return ONLY the sub-questions, one per line, "
        "numbered. If the question is already atomic, return it as-is.\n\n"
        f"Question: {query}\n\n"
        "Sub-questions:"
    )

    resp = client.chat.completions.create(
        model=os.getenv("CHAT_MODEL", "deepseek-chat"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=300,
    )
    text = resp.choices[0].message.content.strip()

    # Parse numbered lines
    sub_queries = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Remove numbering: "1. ", "2. ", etc.
        import re
        cleaned = re.sub(r"^\d+[\.\)]\s*", "", line)
        if cleaned:
            sub_queries.append(cleaned)

    # Cap at MAX_SUB_QUERIES
    sub_queries = sub_queries[:MAX_SUB_QUERIES]
    return sub_queries if len(sub_queries) > 1 else [query]


def _heuristic_decompose(query: str) -> List[str]:
    """
    Heuristic decomposition: split on conjunctions and semicolons.
    Handles cases like "show X and Y" or "compare A, B, and C".
    """
    import re

    # Split on ";", " and ", " also ", " plus "
    parts = re.split(r"[;]|\b(?:and|also|plus|additionally|furthermore)\b", query, flags=re.IGNORECASE)
    sub_queries = [p.strip() for p in parts if p.strip() and len(p.strip()) > 10]

    # If we got meaningful splits, prefix context from the first part
    if len(sub_queries) > 1:
        # Extract topic prefix from the main query for context preservation
        context_prefix = ""
        first = sub_queries[0].lower()
        if any(kw in first for kw in ["compare", "show", "list", "what", "which"]):
            context_prefix = sub_queries[0].split()[0] + " "
        return sub_queries[:MAX_SUB_QUERIES]

    return [query]


# ── DuckDB Data Sources ───────────────────────────────────────────────────────

def load_document_chunks(conn: duckdb.DuckDBPyConnection) -> List[Dict]:
    """
    Load all embeddable chunks from DuckDB for BM25 indexing.
    Sources: ticker_embeddings, edgar_embeddings, polygon_tickers (descriptions).
    """
    chunks = []

    # 1. Ticker embeddings
    try:
        rows = conn.execute(
            "SELECT ticker, text FROM ticker_embeddings"
        ).fetchall()
        for ticker, text in rows:
            chunks.append({
                "text": text,
                "source": "ticker_embeddings",
                "ticker": ticker,
                "doc_id": f"ticker_emb::{ticker}",
            })
        logger.info(f"Loaded {len(rows)} ticker embedding chunks")
    except Exception as e:
        logger.warning(f"Failed to load ticker_embeddings: {e}")

    # 2. EDGAR embeddings (10-K chunks)
    try:
        rows = conn.execute(
            "SELECT ticker, text, accession FROM edgar_embeddings"
        ).fetchall()
        for ticker, text, accession in rows:
            chunks.append({
                "text": text,
                "source": "edgar_embeddings",
                "ticker": ticker,
                "doc_id": f"edgar_emb::{ticker}::{accession}",
            })
        logger.info(f"Loaded {len(rows)} EDGAR embedding chunks")
    except Exception as e:
        logger.warning(f"Failed to load edgar_embeddings: {e}")

    # 3. Ticker descriptions (from polygon_tickers)
    try:
        rows = conn.execute("""
            SELECT ticker, name || ': ' || COALESCE(description, '') AS text
            FROM polygon_tickers
            WHERE description IS NOT NULL AND trim(description) != ''
        """).fetchall()
        for ticker, text in rows:
            chunks.append({
                "text": text,
                "source": "polygon_tickers",
                "ticker": ticker,
                "doc_id": f"ticker_desc::{ticker}",
            })
        logger.info(f"Loaded {len(rows)} polygon_tickers description chunks")
    except Exception as e:
        logger.warning(f"Failed to load polygon_tickers: {e}")

    return chunks


def load_vector_embeddings(
    conn: duckdb.DuckDBPyConnection,
) -> Tuple[List[Dict], List[List[float]]]:
    """
    Load pre-computed vector embeddings from DuckDB for dense search.
    Returns (chunk_metadata, embedding_vectors).
    """
    chunks = []
    vectors = []

    # Ticker embeddings
    try:
        rows = conn.execute(
            "SELECT ticker, text, embedding FROM ticker_embeddings"
        ).fetchall()
        for ticker, text, emb in rows:
            chunks.append({
                "text": text,
                "source": "ticker_embeddings",
                "ticker": ticker,
                "doc_id": f"ticker_emb::{ticker}",
            })
            vectors.append(emb)
    except Exception as e:
        logger.warning(f"Failed to load ticker embeddings: {e}")

    # EDGAR embeddings
    try:
        rows = conn.execute(
            "SELECT ticker, text, accession, embedding FROM edgar_embeddings"
        ).fetchall()
        for ticker, text, accession, emb in rows:
            chunks.append({
                "text": text,
                "source": "edgar_embeddings",
                "ticker": ticker,
                "doc_id": f"edgar_emb::{ticker}::{accession}",
            })
            vectors.append(emb)
    except Exception as e:
        logger.warning(f"Failed to load EDGAR embeddings: {e}")

    logger.info(f"Loaded {len(chunks)} pre-computed embeddings for dense search")
    return chunks, vectors


def query_edgar_facts_structured(
    conn: duckdb.DuckDBPyConnection, query: str, top_k: int = 5
) -> List[RetrievedChunk]:
    """Structured EDGAR facts lookup — finds tickers mentioned in query."""
    try:
        query_upper = query.upper()
        found = [r[0] for r in conn.execute(
            "SELECT ticker FROM polygon_tickers WHERE INSTR(?, ticker) > 0",
            [query_upper]
        ).fetchall()]

        if not found:
            found = [
                r[0] for r in conn.execute("""
                    SELECT ticker, MAX(filed_date) AS last_filed
                    FROM edgar_facts
                    GROUP BY ticker
                    ORDER BY last_filed DESC
                    LIMIT ?
                """, [top_k]).fetchall()
            ]

        if not found:
            return []

        ph = ", ".join("?" * len(found))
        rows = conn.execute(f"""
            SELECT ticker, label, value, unit, period_end, form_type
            FROM edgar_facts
            WHERE ticker IN ({ph})
              AND form_type IN ('10-K', '10-Q')
              AND value IS NOT NULL
            ORDER BY ticker, period_end DESC
            LIMIT ?
        """, found + [8 * len(found)]).fetchall()

        by_ticker: Dict[str, List[str]] = {}
        for ticker, label, value, unit, period_end, form_type in rows:
            by_ticker.setdefault(ticker, []).append(
                f"  {label}: {float(value):,.0f} {unit} ({period_end}, {form_type})"
            )

        return [
            RetrievedChunk(
                text=f"{ticker} EDGAR facts:\n" + "\n".join(lines),
                source="edgar_facts",
                ticker=ticker,
            )
            for ticker, lines in by_ticker.items()
        ]
    except Exception as e:
        logger.warning(f"EDGAR facts query failed: {e}")
        return []


def query_price_context_structured(
    conn: duckdb.DuckDBPyConnection, query: str
) -> List[RetrievedChunk]:
    """Latest close prices for tickers found in the query."""
    try:
        query_upper = query.upper()
        found = [r[0] for r in conn.execute(
            "SELECT DISTINCT ticker FROM polygon_bars WHERE INSTR(?, ticker) > 0",
            [query_upper]
        ).fetchall()] or None

        if not found:
            return []

        ph = ", ".join("?" * len(found))
        rows = conn.execute(f"""
            SELECT ticker, ts::DATE AS date, close, volume
            FROM polygon_bars
            WHERE ticker IN ({ph}) AND timespan = 'day'
            QUALIFY ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY ts DESC) = 1
        """, found).fetchall()

        if not rows:
            return []

        lines = "\n".join(
            f"  {r[0]}: ${r[2]:.2f} on {r[1]}  (vol {int(r[3] or 0):,})"
            for r in rows
        )
        return [RetrievedChunk(
            text=f"Latest prices:\n{lines}",
            source="polygon_bars",
        )]
    except Exception as e:
        logger.warning(f"Price context query failed: {e}")
        return []


# ── Asymmetric RAG Pipeline ───────────────────────────────────────────────────

class AsymmetricFinancialRAG:
    """
    Production-ready asymmetric RAG pipeline for financial documents.

    Architecture:
      - Ingestion:  Qwen3-Embedding-8B  (heavy, offline)
      - Querying:   Qwen3-Embedding-0.6B (lightweight, runtime)

    Pipeline:
      1. Query Decomposition (optional) → atomic sub-queries
      2. Dense retrieval  — cosine similarity over Qwen3 embeddings
      3. Sparse retrieval — BM25Okapi keyword matching
      4. RRF fusion       — blend dense + sparse rankings
      5. Cross-encoder reranking — final relevance scoring
      6. Structured sources — EDGAR facts, price context
      7. Synthesis        — LLM generates answer from reranked context
    """

    def __init__(self):
        self.embedder = OllamaEmbedder()
        self.bm25_index = BM25Index()
        self.reranker = CrossEncoderReranker() if RERANK_ENABLED else None

        # Pre-loaded data
        self._bm25_chunks: List[Dict] = []
        self._vector_chunks: List[Dict] = []
        self._vector_matrix: Optional[np.ndarray] = None
        self._vector_dim: Optional[int] = None
        self._initialized = False

    def initialize(self):
        """
        Load all data sources and build indices.
        Call once at startup (expensive — loads embeddings into memory).
        """
        if self._initialized:
            return

        logger.info("Initializing Asymmetric RAG pipeline...")

        conn = duckdb.connect(DB_PATH, read_only=True)
        try:
            # Load chunks for BM25
            self._bm25_chunks = load_document_chunks(conn)
            if self._bm25_chunks:
                self.bm25_index.build(self._bm25_chunks)

            # Load pre-computed embeddings for dense search
            self._vector_chunks, raw_vectors = load_vector_embeddings(conn)
            if raw_vectors:
                self._vector_matrix = np.array(raw_vectors, dtype=np.float32)
                self._vector_dim = self._vector_matrix.shape[1]
                # Normalize for cosine similarity
                norms = np.linalg.norm(self._vector_matrix, axis=1, keepdims=True)
                norms[norms == 0] = 1.0  # avoid division by zero
                self._vector_matrix = self._vector_matrix / norms
                logger.info(
                    f"Dense index: {self._vector_matrix.shape[0]} vectors, "
                    f"dim={self._vector_dim}"
                )
        finally:
            conn.close()

        self._initialized = True
        logger.info(
            f"Asymmetric RAG initialized: "
            f"{len(self._bm25_chunks)} BM25 chunks, "
            f"{len(self._vector_chunks)} dense vectors"
        )

    def retrieve(
        self, query: str, top_k: int = FINAL_TOP_K
    ) -> List[RetrievedChunk]:
        """
        Full retrieval pipeline for a single query.

        Steps:
          1. Dense retrieval (Qwen3-0.6B embeddings → cosine similarity)
          2. Sparse retrieval (BM25Okapi)
          3. RRF fusion
          4. Cross-encoder reranking
          5. Merge structured sources (EDGAR facts, prices)
        """
        self.initialize()

        # ── Step 1: Dense retrieval via query embedding ─────────────────────
        dense_results = self._dense_search(query, top_k=VECTOR_TOP_K)

        # ── Step 2: Sparse retrieval via BM25 ──────────────────────────────
        sparse_results = self._bm25_search(query, top_k=BM25_TOP_K)

        # ── Step 3: Reciprocal Rank Fusion ─────────────────────────────────
        fused = self._rrf_merge(dense_results, sparse_results)

        # ── Step 4: Cross-encoder reranking ────────────────────────────────
        if self.reranker and fused:
            fused = self.reranker.rerank(query, fused, top_k=top_k)
        else:
            fused = fused[:top_k]

        # ── Step 5: Merge structured data sources ──────────────────────────
        structured = self._get_structured_context(query)
        if structured:
            # Deduplicate structured chunks against retrieved
            seen = {c.content_hash for c in fused}
            for chunk in structured:
                if chunk.content_hash not in seen:
                    fused.append(chunk)
                    seen.add(chunk.content_hash)

        return fused

    def retrieve_with_decomposition(
        self, query: str, top_k: int = FINAL_TOP_K
    ) -> List[RetrievedChunk]:
        """
        Full pipeline with query decomposition.
        Breaks compound queries into sub-queries, retrieves for each,
        then deduplicates and reranks the combined results.
        """
        sub_queries = decompose_query(query)

        if len(sub_queries) <= 1:
            return self.retrieve(query, top_k)

        logger.info(f"Query decomposed into {len(sub_queries)} sub-queries: {sub_queries}")

        all_chunks: List[RetrievedChunk] = []
        seen_hashes: set = set()

        for sub_q in sub_queries:
            sub_chunks = self.retrieve(sub_q, top_k=top_k)
            for chunk in sub_chunks:
                if chunk.content_hash not in seen_hashes:
                    seen_hashes.add(chunk.content_hash)
                    all_chunks.append(chunk)

        # Final rerank on the combined set against the original query
        if self.reranker and all_chunks:
            all_chunks = self.reranker.rerank(query, all_chunks, top_k=top_k)
        else:
            all_chunks = all_chunks[:top_k]

        return all_chunks

    def ask(self, question: str) -> str:
        """
        End-to-end RAG: retrieve context → synthesize answer via LLM.
        """
        logger.info(f"RAG query: {question}")
        chunks = self.retrieve_with_decomposition(question)

        if not chunks:
            return "I don't have enough data to answer that question."

        context = self._format_context(chunks)
        return self._synthesize(question, context)

    # ── Internal retrieval methods ─────────────────────────────────────────

    def _dense_search(self, query: str, top_k: int) -> List[RetrievedChunk]:
        """Cosine similarity search over pre-computed embeddings."""
        if self._vector_matrix is None or len(self._vector_chunks) == 0:
            logger.info("No pre-computed vectors — skipping dense search")
            return []

        try:
            qvec = np.array(self.embedder.embed_query(query), dtype=np.float32)
            norm = np.linalg.norm(qvec)
            if norm > 0:
                qvec = qvec / norm

            # Cosine similarity (dot product of normalized vectors)
            similarities = self._vector_matrix @ qvec
            top_indices = np.argsort(similarities)[::-1][:top_k]

            results = []
            for idx in top_indices:
                if similarities[idx] > 0:
                    chunk = self._vector_chunks[idx]
                    results.append(RetrievedChunk(
                        text=chunk["text"],
                        source=f"dense::{chunk['source']}",
                        ticker=chunk.get("ticker", ""),
                        metadata={"similarity": float(similarities[idx])},
                        dense_rank=len(results) + 1,
                        doc_id=chunk["doc_id"],
                    ))
            return results
        except Exception as e:
            logger.warning(f"Dense search failed: {e}")
            return []

    def _bm25_search(self, query: str, top_k: int) -> List[RetrievedChunk]:
        """BM25 keyword search over document corpus."""
        hits = self.bm25_index.search(query, top_k=top_k)
        results = []
        for chunk_dict, score in hits:
            results.append(RetrievedChunk(
                text=chunk_dict["text"],
                source=f"bm25::{chunk_dict['source']}",
                ticker=chunk_dict.get("ticker", ""),
                metadata={"bm25_score": score},
                bm25_rank=len(results) + 1,
                doc_id=chunk_dict["doc_id"],
            ))
        return results

    def _rrf_merge(
        self,
        dense: List[RetrievedChunk],
        sparse: List[RetrievedChunk],
    ) -> List[RetrievedChunk]:
        """
        Merge dense and sparse results using Reciprocal Rank Fusion.

        RRF_score(d) = Σ 1/(k + rank_i(d)) across all ranking lists.
        """
        # Build rankings as [(doc_id, score), ...]
        dense_ranking = [(c.doc_id, 0.0) for c in dense]
        sparse_ranking = [(c.doc_id, 0.0) for c in sparse]

        fused_scores = reciprocal_rank_fusion(
            [dense_ranking, sparse_ranking], k=RRF_K
        )

        # Build a lookup from doc_id → RetrievedChunk
        chunk_map: Dict[str, RetrievedChunk] = {}
        for c in dense + sparse:
            if c.doc_id not in chunk_map:
                chunk_map[c.doc_id] = c

        # Assign RRF scores and sort
        results = []
        for doc_id, rrf_score in fused_scores:
            if doc_id in chunk_map:
                chunk = chunk_map[doc_id]
                chunk.rrf_score = rrf_score
                results.append(chunk)

        return results

    def _get_structured_context(self, query: str) -> List[RetrievedChunk]:
        """Get context from structured DuckDB sources (EDGAR facts, prices)."""
        conn = duckdb.connect(DB_PATH, read_only=True)
        try:
            facts = query_edgar_facts_structured(conn, query)
            prices = query_price_context_structured(conn, query)
            return facts + prices
        finally:
            conn.close()

    def _format_context(self, chunks: List[RetrievedChunk]) -> str:
        """Format retrieved chunks into a context string for the LLM."""
        parts = []
        for i, chunk in enumerate(chunks, 1):
            score_info = ""
            if chunk.rerank_score:
                score_info = f" (rerank: {chunk.rerank_score:.3f})"
            elif chunk.rrf_score:
                score_info = f" (rrf: {chunk.rrf_score:.4f})"

            header = f"[{i}] [{chunk.source}{' | ' + chunk.ticker if chunk.ticker else ''}]{score_info}"
            parts.append(f"{header}\n{chunk.text}")

        return "\n\n".join(parts) if parts else "No context found."

    def _synthesize(self, question: str, context: str) -> str:
        """Generate answer from context using the configured LLM."""
        try:
            from chat_engine import _get_client, _PROVIDER
            client = _get_client()
        except Exception as e:
            logger.error(f"Failed to get LLM client: {e}")
            return f"Error initializing LLM: {e}"

        prompt = (
            "You are a financial analyst assistant. Answer the question using ONLY "
            "the context below. Cite specific tickers and numbers. If the context is "
            "insufficient, say \"I don't have enough data to answer that.\"\n\n"
            f"Context:\n{context}\n\n"
            f"Question: {question}\n\n"
            "Answer:"
        )

        try:
            from chat_engine import _MODEL
            resp = client.chat.completions.create(
                model=_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1024,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"LLM synthesis failed: {e}")
            return f"Synthesis error: {e}"


# ── Singleton & Public API ────────────────────────────────────────────────────

_rag_instance: Optional[AsymmetricFinancialRAG] = None


def get_rag() -> AsymmetricFinancialRAG:
    """Get or create the singleton RAG instance."""
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = AsymmetricFinancialRAG()
    return _rag_instance


def ask_rag(question: str) -> str:
    """Public entry point — drop-in replacement for rag_engine.ask_rag()."""
    return get_rag().ask(question)


def retrieve_rag(question: str) -> List[RetrievedChunk]:
    """Public entry point for retrieval-only (no synthesis)."""
    return get_rag().retrieve_with_decomposition(question)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    import sys

    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "What is the primary business of Apple?"
    print(f"\nQuery: {query}\n")

    # Test retrieval
    chunks = retrieve_rag(query)
    print(f"Retrieved {len(chunks)} chunks:\n")
    for i, c in enumerate(chunks, 1):
        print(f"  [{i}] {c.source} | {c.ticker} | rrf={c.rrf_score:.4f} rerank={c.rerank_score:.3f}")
        print(f"      {c.text[:120]}...")
        print()

    # Test full pipeline
    print("\n--- Answer ---")
    print(ask_rag(query))
