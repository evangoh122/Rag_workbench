"""
embed_tickers.py
Generates text embeddings for ticker descriptions and stores them in DuckDB.

Uses Gemini (Google AI) for embeddings to ensure high quality and zero local compute load.
"""
import os
from datetime import datetime, timezone
from typing import List

import duckdb
from loguru import logger
from langchain_google_genai import GoogleGenerativeAIEmbeddings

DB_PATH = os.getenv("DB_PATH", "./data/ibkr.duckdb")

_embeddings = None   # lazy-loaded Gemini embeddings
EMBEDDING_DIM = 768  # Gemini text-embedding-004 dimension


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _get_embeddings():
    global _embeddings
    if _embeddings is None:
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set in .env. Needed for Gemini embeddings.")

        logger.info("Initializing Gemini embeddings (models/text-embedding-004)...")
        _embeddings = GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004",
            google_api_key=api_key
        )
    return _embeddings


# ── Embedding ETL ─────────────────────────────────────────────────────────────

def run_embed_tickers_etl(batch_size: int = 100) -> int:
    """
    Read descriptions from polygon_tickers (DuckDB), embed with
    Gemini, and upsert into DuckDB ticker_embeddings.
    Returns number of tickers embedded.
    """
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        rows = conn.execute("""
            SELECT ticker, name, description
            FROM polygon_tickers
            WHERE description IS NOT NULL AND trim(description) != ''
        """).df().to_dict('records')

    if not rows:
        logger.warning("No ticker descriptions found — run --job polygon-ref first")
        return 0

    embeddings = _get_embeddings()
    total  = 0
    ts     = _utcnow()

    with duckdb.connect(DB_PATH) as conn:
        try:
            conn.execute("LOAD vss")
        except Exception:
            pass

        for i in range(0, len(rows), batch_size):
            batch  = rows[i : i + batch_size]
            texts  = [f"{r['name']}: {r['description']}" for r in batch]

            try:
                vecs = embeddings.embed_documents(texts)

                for j, row in enumerate(batch):
                    conn.execute("""
                        INSERT OR REPLACE INTO ticker_embeddings
                            (ticker, source, text, embedding, updated_at)
                        VALUES (?, 'polygon_desc', ?, ?, ?)
                    """, [row["ticker"], texts[j], vecs[j], ts])

                total += len(batch)
                logger.debug(f"Embedded {total}/{len(rows)} tickers using Gemini")
            except Exception as e:
                logger.error(f"Batch embedding failed: {e}")
                continue

        conn.commit()

    logger.info(f"Embedding ETL complete: {total} tickers using Gemini")
    return total
