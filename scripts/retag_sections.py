"""
retag_sections.py — Re-tag existing full_text chunks with correct section_ids.

Reconstructs the full filing text from stored chunks, runs section extraction
to find section boundaries, then assigns each chunk to the section whose text
contains the chunk's opening sentence.

This avoids re-embedding — only metadata is updated.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import duckdb
from loguru import logger

from api.config import Config
from scripts.embed_edgar import _extract_sections_with_labels


def retag_ticker(conn, ticker: str) -> int:
    """Re-tag all full_text chunks for a ticker. Returns count of updated rows."""
    # Get all full_text chunks ordered by chunk_index
    rows = conn.execute("""
        SELECT rowid, text, chunk_index
        FROM edgar_embeddings
        WHERE ticker = ? AND section_id = 'full_text'
        ORDER BY accession, chunk_index
    """, [ticker]).fetchall()

    if not rows:
        return 0

    # Reconstruct full text from chunks
    full_text = "\n\n".join(r[1] for r in rows)

    # Extract sections
    sections = _extract_sections_with_labels(full_text)
    if not sections or (len(sections) == 1 and sections[0][0] == "full_text"):
        return 0  # No improvement possible

    # Build a map: for each section, record its start position in full_text
    section_ranges = []
    for label, section_text in sections:
        # Find where this section text starts in the full text
        # Use the first 200 chars as a search anchor (handles minor whitespace diffs)
        anchor = section_text[:200].strip()
        # Normalize whitespace for matching
        anchor_clean = re.sub(r"\s+", " ", anchor)
        full_clean = re.sub(r"\s+", " ", full_text)
        pos = full_clean.find(anchor_clean)
        if pos >= 0:
            section_ranges.append((label, pos, pos + len(section_text)))

    if not section_ranges:
        return 0

    # Sort by position
    section_ranges.sort(key=lambda x: x[1])

    # For each chunk, find which section it belongs to
    # Strategy: use the chunk's opening text as an anchor
    updated = 0
    full_clean = re.sub(r"\s+", " ", full_text)

    for rowid, chunk_text, chunk_idx in rows:
        # Use first 150 chars of chunk as anchor
        chunk_anchor = chunk_text[:150].strip()
        chunk_anchor_clean = re.sub(r"\s+", " ", chunk_anchor)
        chunk_pos = full_clean.find(chunk_anchor_clean)

        if chunk_pos < 0:
            continue  # Can't locate chunk in full text

        # Find which section contains this position
        for label, start, end in section_ranges:
            if start <= chunk_pos < end:
                conn.execute(
                    "UPDATE edgar_embeddings SET section_id = ? WHERE rowid = ?",
                    [label, rowid]
                )
                updated += 1
                break

    return updated


def main():
    db_path = Config.DB_PATH
    logger.info(f"Opening database: {db_path}")
    conn = duckdb.connect(db_path, read_only=False)

    # Find tickers with full_text chunks
    tickers = conn.execute("""
        SELECT DISTINCT ticker, COUNT(*) as cnt
        FROM edgar_embeddings
        WHERE section_id = 'full_text'
        GROUP BY ticker
        ORDER BY cnt DESC
    """).fetchall()

    logger.info(f"Found {len(tickers)} tickers with full_text chunks")
    total_updated = 0

    for ticker, cnt in tickers:
        updated = retag_ticker(conn, ticker)
        total_updated += updated
        if updated > 0:
            logger.info(f"  {ticker}: {updated}/{cnt} chunks retagged")
        else:
            logger.info(f"  {ticker}: no improvement ({cnt} chunks still full_text)")

    conn.commit()
    conn.close()

    logger.info(f"Done. Total chunks retagged: {total_updated}")

    # Verify results
    conn2 = duckdb.connect(db_path, read_only=True)
    remaining = conn2.execute("""
        SELECT COUNT(*) FROM edgar_embeddings WHERE section_id = 'full_text'
    """).fetchone()[0]
    tagged = conn2.execute("""
        SELECT section_id, COUNT(*) as cnt
        FROM edgar_embeddings
        WHERE section_id != 'full_text'
        GROUP BY section_id
        ORDER BY cnt DESC
    """).fetchall()
    conn2.close()

    logger.info(f"Remaining full_text chunks: {remaining}")
    logger.info("Section distribution after retagging:")
    for sid, cnt in tagged:
        logger.info(f"  {sid}: {cnt}")


if __name__ == "__main__":
    main()
