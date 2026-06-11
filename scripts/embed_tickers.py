"""
embed_tickers.py
Generates text embeddings for ticker descriptions and stores them in DuckDB.

Uses Ollama (nomic-embed-text) for local embeddings.
"""
from datetime import datetime, timezone

import duckdb
from loguru import logger

from api.config import Config
from api.services.embeddings import get_embeddings

DB_PATH = Config.DB_PATH


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_embed_tickers_etl(batch_size: int = 100) -> int:
    """
    Read descriptions from polygon_tickers (DuckDB), embed with
    Ollama, and upsert into DuckDB ticker_embeddings.
    Returns number of tickers embedded.
    """
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()}
        missing = {"polygon_tickers", "ticker_embeddings"} - tables
        if missing:
            raise RuntimeError(
                f"Required tables not found in {DB_PATH}: {missing}. "
                "Run init_db() in IBKR_workbench first."
            )
        rows = conn.execute("""
            SELECT ticker, name, description
            FROM polygon_tickers
            WHERE description IS NOT NULL AND trim(description) != ''
        """).df().to_dict('records')

    if not rows:
        logger.warning("No ticker descriptions found — run --job polygon-ref first")
        return 0

    embeddings = get_embeddings()
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
                logger.debug(f"Embedded {total}/{len(rows)} tickers using Ollama")
            except Exception as e:
                logger.error(f"Batch embedding failed: {e}")
                continue

        conn.commit()

    logger.info(f"Embedding ETL complete: {total} tickers using Ollama")
    return total
