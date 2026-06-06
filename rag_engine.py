"""
rag_engine.py
Retrieval-Augmented Generation using LangChain LCEL + DuckDB.

Two retrieval sources:
  1. DuckDBVectorRetriever  — HNSW search over ticker_embeddings (ibkr.duckdb)
                              Falls back to keyword search when index is empty.
  2. EDGARFactsRetriever    — structured EDGAR financial facts (ibkr.duckdb)

Generation uses the same LLM provider as chat_engine (CHAT_PROVIDER in .env).

Run `python main.py --job embed-tickers` to populate the vector index.
"""
import os
from typing import Any, List, Optional

import duckdb
from loguru import logger

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI
from embed_tickers import _get_embeddings
from chat_engine import _BASE_URL, _MODEL, _KEY_ENV

DB_PATH = os.getenv("DB_PATH", "./data/ibkr.duckdb")
EMBEDDING_DIM = 768


def _open_conn() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(DB_PATH, read_only=True)
    try:
        conn.execute("LOAD vss")
    except Exception:
        pass
    return conn


# ── Core query functions (accept a shared connection) ─────────────────────────

def _query_vector(conn: Any, query: str, top_k: int = 5) -> List[Document]:
    try:
        count = conn.execute("SELECT COUNT(*) FROM ticker_embeddings").fetchone()[0]
        if count > 0:
            qvec = _get_embeddings().embed_query(query)
            rows = conn.execute(f"""
                SELECT ticker, text,
                       array_distance(embedding, ?::FLOAT[{EMBEDDING_DIM}]) AS dist
                FROM ticker_embeddings
                ORDER BY dist ASC
                LIMIT {top_k}
            """, [qvec]).fetchall()
            return [
                Document(
                    page_content=r[1],
                    metadata={"source": "vector_search", "ticker": r[0], "distance": r[2]},
                )
                for r in rows
            ]
    except Exception as e:
        logger.warning(f"Vector search failed: {e}")

    logger.info("Vector index empty — falling back to keyword search over polygon_tickers")
    return _query_keyword_fallback(conn, query, top_k)


def _query_keyword_fallback(conn: Any, query: str, top_k: int = 5) -> List[Document]:
    words = [w for w in query.split() if len(w) >= 4]
    try:
        if words:
            conditions = " OR ".join(
                "description ILIKE '%' || ? || '%' OR name ILIKE '%' || ? || '%'"
                for _ in words
            )
            params: list = []
            for w in words:
                params.extend([w, w])
            sql = f"""
                SELECT ticker,
                       name || ': ' || COALESCE(description, '') AS text
                FROM polygon_tickers
                WHERE description IS NOT NULL AND ({conditions})
                LIMIT ?
            """
            params.append(top_k)
            rows = conn.execute(sql, params).fetchall()
        else:
            rows = conn.execute("""
                SELECT ticker,
                       name || ': ' || COALESCE(description, '') AS text
                FROM polygon_tickers
                WHERE description IS NOT NULL
                LIMIT ?
            """, [top_k]).fetchall()

        return [
            Document(
                page_content=r[1],
                metadata={"source": "keyword_search", "ticker": r[0]},
            )
            for r in rows
        ]
    except Exception as e:
        logger.warning(f"Keyword fallback failed: {e}")
        return []


def _query_edgar_facts(conn: Any, query: str, top_k: int = 5, facts_per_ticker: int = 8) -> List[Document]:
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

        ph   = ", ".join("?" * len(found))
        rows = conn.execute(f"""
            SELECT ticker, label, value, unit, period_end, form_type
            FROM edgar_facts
            WHERE ticker IN ({ph})
              AND form_type IN ('10-K', '10-Q')
              AND value IS NOT NULL
            ORDER BY ticker, period_end DESC
            LIMIT ?
        """, found + [facts_per_ticker * len(found)]).fetchall()

        if not rows:
            return []

        by_ticker: dict = {}
        for ticker, label, value, unit, period_end, form_type in rows:
            by_ticker.setdefault(ticker, []).append(
                f"  {label}: {float(value):,.0f} {unit} ({period_end}, {form_type})"
            )

        return [
            Document(
                page_content=f"{ticker} EDGAR facts:\n" + "\n".join(lines),
                metadata={"source": "edgar_facts", "ticker": ticker},
            )
            for ticker, lines in by_ticker.items()
        ]
    except Exception as e:
        logger.warning(f"EDGAR facts retrieval failed: {e}")
        return []


def _query_edgar_embeddings(conn: Any, query: str, top_k: int = 5) -> List[Document]:
    try:
        count = conn.execute("SELECT COUNT(*) FROM edgar_embeddings").fetchone()[0]
        if count == 0:
            return []

        qvec = _get_embeddings().embed_query(query)
        rows = conn.execute(f"""
            SELECT ticker, text, accession,
                   array_distance(embedding, ?::FLOAT[{EMBEDDING_DIM}]) AS dist
            FROM edgar_embeddings
            ORDER BY dist ASC
            LIMIT {top_k}
        """, [qvec]).fetchall()

        return [
            Document(
                page_content=r[1],
                metadata={"source": "edgar_embeddings", "ticker": r[0], "accession": r[2], "distance": r[3]},
            )
            for r in rows
        ]
    except Exception as e:
        logger.warning(f"EDGAR embedding search failed: {e}")
        return []


def _query_price_context(conn: Any, query: str, top_k: int = 10) -> List[Document]:
    try:
        query_upper = query.upper()
        found = [r[0] for r in conn.execute(
            "SELECT DISTINCT ticker FROM polygon_bars WHERE INSTR(?, ticker) > 0",
            [query_upper]
        ).fetchall()] or None

        if found:
            ph  = ", ".join("?" * len(found))
            sql = f"""
                SELECT ticker, ts::DATE AS date, close, volume
                FROM polygon_bars
                WHERE ticker IN ({ph}) AND timespan = 'day'
                QUALIFY ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY ts DESC) = 1
            """
            rows = conn.execute(sql, found).fetchall()
        else:
            rows = []

        if not rows:
            return []

        lines = "\n".join(
            f"  {r[0]}: ${r[2]:.2f} on {r[1]}  (vol {int(r[3] or 0):,})"
            for r in rows
        )
        return [Document(
            page_content=f"Latest prices:\n{lines}",
            metadata={"source": "polygon_bars"},
        )]
    except Exception as e:
        logger.warning(f"Price context retrieval failed: {e}")
        return []


# ── Retriever classes (LangChain-compatible, open their own connection) ────────

class DuckDBVectorRetriever(BaseRetriever):
    """HNSW vector search over ticker_embeddings; falls back to keyword search."""
    top_k: int = 5

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        conn = _open_conn()
        try:
            return _query_vector(conn, query, self.top_k)
        finally:
            conn.close()


class EDGARFactsRetriever(BaseRetriever):
    """Structured EDGAR financial facts for tickers mentioned in the query."""
    top_k: int = 5
    facts_per_ticker: int = 8

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        conn = _open_conn()
        try:
            return _query_edgar_facts(conn, query, self.top_k, self.facts_per_ticker)
        finally:
            conn.close()


class EDGAREmbeddingsRetriever(BaseRetriever):
    """HNSW vector search over edgar_embeddings (10-K/10-Q chunks)."""
    top_k: int = 5

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        conn = _open_conn()
        try:
            return _query_edgar_embeddings(conn, query, self.top_k)
        finally:
            conn.close()


class PriceContextRetriever(BaseRetriever):
    """Latest close prices from polygon_bars for tickers found in the query."""
    top_k: int = 10

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        conn = _open_conn()
        try:
            return _query_price_context(conn, query, self.top_k)
        finally:
            conn.close()


# ── RAG chain ─────────────────────────────────────────────────────────────────

_RAG_PROMPT = ChatPromptTemplate.from_template("""You are a financial analyst assistant.
Answer the question using ONLY the context below. Cite specific tickers and numbers.
If the context is insufficient, say "I don't have enough data to answer that."

Context:
{context}

Question: {question}

Answer:""")


def _format_docs(docs: List[Document]) -> str:
    parts = []
    for d in docs:
        src = d.metadata.get("source", "unknown")
        ticker = d.metadata.get("ticker", "")
        header = f"[{src}{' | ' + ticker if ticker else ''}]"
        parts.append(f"{header}\n{d.page_content}")
    return "\n\n".join(parts) if parts else "No context found."


def _combined_retriever(query: str) -> List[Document]:
    """Run all four queries over one shared connection, deduplicate by content hash."""
    conn = _open_conn()
    try:
        all_docs = (
            _query_vector(conn, query)
            + _query_edgar_facts(conn, query)
            + _query_edgar_embeddings(conn, query)
            + _query_price_context(conn, query)
        )
    finally:
        conn.close()

    seen: set = set()
    unique: List[Document] = []
    for doc in all_docs:
        key = hash(doc.page_content)
        if key not in seen:
            seen.add(key)
            unique.append(doc)
    return unique


_rag_chain = None  # module-level singleton


def build_rag_chain():
    """Build LCEL RAG chain (cached — built once per process)."""
    global _rag_chain
    if _rag_chain is not None:
        return _rag_chain

    from chat_engine import _PROVIDER

    if _PROVIDER == "anthropic":
        from langchain_anthropic import ChatAnthropic
        api_key = os.getenv(_KEY_ENV, "")
        if not api_key:
            raise ValueError(f"RAG: {_KEY_ENV} not set in .env for provider '{_PROVIDER}'")
        llm = ChatAnthropic(model=_MODEL, api_key=api_key)
    else:
        if _KEY_ENV is None:
            api_key = "ollama"
        else:
            api_key = os.getenv(_KEY_ENV, "")
            if not api_key:
                raise ValueError(f"RAG: {_KEY_ENV} not set in .env for provider '{_PROVIDER}'")
        llm = ChatOpenAI(model=_MODEL, api_key=api_key, base_url=_BASE_URL)

    _rag_chain = (
        {
            "context":  lambda q: _format_docs(_combined_retriever(q)),
            "question": RunnablePassthrough(),
        }
        | _RAG_PROMPT
        | llm
        | StrOutputParser()
    )
    return _rag_chain


def ask_rag(question: str) -> str:
    """Entry point: answer a question using the RAG pipeline."""
    logger.info(f"RAG query: {question}")
    try:
        chain = build_rag_chain()
        return chain.invoke(question)
    except Exception as e:
        logger.error(f"RAG failed: {e}")
        return f"RAG error: {e}"


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    print(ask_rag("What is the primary business of Apple?"))
