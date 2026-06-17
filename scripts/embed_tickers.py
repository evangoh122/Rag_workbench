"""
embed_tickers.py
Generates text embeddings for ticker descriptions and stores them in DuckDB.

Uses the configured embedding provider and model.
"""
from datetime import datetime, timezone

import duckdb
from loguru import logger

from api.config import Config
from api.services.embeddings import get_embeddings

DB_PATH = Config.DB_PATH


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _reset_incompatible_embeddings(conn, expected_dim: int) -> bool:
    """Clear stale ticker vectors while preserving company metadata."""
    stored_dims = {
        int(row[0])
        for row in conn.execute(
            "SELECT DISTINCT len(embedding) FROM ticker_embeddings WHERE embedding IS NOT NULL"
        ).fetchall()
        if row[0] is not None
    }
    if not stored_dims or stored_dims == {expected_dim}:
        return False

    logger.warning(
        "Stored ticker embedding dimensions {} do not match configured dimension {}; rebuilding corpus",
        sorted(stored_dims), expected_dim,
    )
    conn.execute(
        "UPDATE ticker_embeddings SET text = NULL, embedding = NULL, updated_at = NULL"
    )
    conn.commit()
    return True


def _load_ticker_rows(conn) -> list[dict]:
    """Load the richest available company descriptions for ticker embedding."""
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
    }
    if "ticker_embeddings" not in tables:
        raise RuntimeError(f"ticker_embeddings table not found in {DB_PATH}")

    if "polygon_tickers" in tables:
        rows = conn.execute("""
            SELECT te.ticker,
                   COALESCE(NULLIF(trim(pt.name), ''), te.description, te.ticker) AS name,
                   COALESCE(NULLIF(trim(pt.description), ''), te.description) AS description
            FROM ticker_embeddings te
            LEFT JOIN polygon_tickers pt ON pt.ticker = te.ticker
            WHERE COALESCE(NULLIF(trim(pt.description), ''), NULLIF(trim(te.description), '')) IS NOT NULL
        """).df().to_dict("records")
    else:
        rows = conn.execute("""
            SELECT ticker,
                   COALESCE(NULLIF(trim(description), ''), ticker) AS name,
                   description
            FROM ticker_embeddings
            WHERE NULLIF(trim(description), '') IS NOT NULL
        """).df().to_dict("records")
    return rows


def run_embed_tickers_etl(batch_size: int = 100) -> int:
    """
    Read available company descriptions, embed with the configured model,
    and upsert into DuckDB ticker_embeddings.
    Returns number of tickers embedded.
    """
    with duckdb.connect(DB_PATH) as conn:
        _reset_incompatible_embeddings(conn, Config.EMBEDDING_DIM)
        rows = _load_ticker_rows(conn)

    if not rows:
        logger.warning("No ticker descriptions found")
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

                # Wrap in a transaction to make the batch delete-then-insert atomic
                conn.execute("BEGIN TRANSACTION")
                try:
                    for j, row in enumerate(batch):
                        conn.execute("DELETE FROM ticker_embeddings WHERE ticker = ?", [row["ticker"]])
                        conn.execute("""
                            INSERT INTO ticker_embeddings
                                (ticker, text, embedding, updated_at)
                            VALUES (?, ?, ?, ?)
                        """, [row["ticker"], texts[j], vecs[j], ts])
                    conn.execute("COMMIT")
                except Exception as tx_err:
                    conn.execute("ROLLBACK")
                    raise tx_err

                total += len(batch)
                logger.debug(f"Embedded {total}/{len(rows)} tickers")
            except Exception as e:
                logger.error(f"Batch embedding failed: {e}")
                continue

        conn.commit()

    logger.info(f"Embedding ETL complete: {total} tickers")
    return total
