"""
init_graph_triples.py — Load graphify-out knowledge graph data into DuckDB.

Creates the graph_triples table (if absent) and populates it from all
.graphify_chunk_*.json files in the graphify-out/ directory.

Usage:
    python3 scripts/init_graph_triples.py [--db-path ./data/rag.duckdb]

This script is idempotent: it uses INSERT OR IGNORE semantics so it is safe
to re-run without creating duplicates.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import uuid

import duckdb

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS graph_triples (
    id          VARCHAR PRIMARY KEY,
    ticker      VARCHAR NOT NULL DEFAULT '',
    subject     VARCHAR NOT NULL,
    predicate   VARCHAR NOT NULL,
    object      VARCHAR NOT NULL,
    confidence  DOUBLE  DEFAULT 1.0,
    source_file VARCHAR,
    source_loc  VARCHAR
)
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_gt_ticker_subj
ON graph_triples (ticker, subject)
"""

INSERT_SQL = """
INSERT OR IGNORE INTO graph_triples
    (id, ticker, subject, predicate, object, confidence, source_file, source_loc)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_chunk(conn: duckdb.DuckDBPyConnection, path: str, ticker: str = "") -> int:
    """Load edges from a single graphify chunk JSON file.  Returns row count inserted."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    edges = data.get("edges", [])
    inserted = 0
    for edge in edges:
        subject   = str(edge.get("source", "")).strip()
        predicate = str(edge.get("relation", "")).strip()
        obj       = str(edge.get("target", "")).strip()
        if not subject or not predicate or not obj:
            continue
        confidence  = float(edge.get("confidence_score", 1.0))
        source_file = edge.get("source_file")
        source_loc  = edge.get("source_location")
        conn.execute(INSERT_SQL, [
            str(uuid.uuid4()), ticker, subject, predicate, obj,
            confidence, source_file, source_loc,
        ])
        inserted += 1
    return inserted


def init_graph_triples(db_path: str, graphify_dir: str, ticker: str = "") -> None:
    conn = duckdb.connect(db_path)
    conn.execute(CREATE_TABLE_SQL)
    conn.execute(CREATE_INDEX_SQL)

    pattern = os.path.join(graphify_dir, ".graphify_chunk_*.json")
    chunk_files = sorted(glob.glob(pattern))

    if not chunk_files:
        print(f"[init_graph_triples] No chunk files found matching: {pattern}", file=sys.stderr)
        conn.close()
        return

    total = 0
    for path in chunk_files:
        n = load_chunk(conn, path, ticker=ticker)
        print(f"  Loaded {n:>5} triples from {os.path.basename(path)}")
        total += n

    conn.close()
    print(f"[init_graph_triples] Done — {total} triples loaded into {db_path}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Populate graph_triples table from graphify-out JSON")
    parser.add_argument("--db-path",       default="./data/rag.duckdb",  help="Path to DuckDB file")
    parser.add_argument("--graphify-dir",  default="./graphify-out",       help="Directory containing .graphify_chunk_*.json files")
    parser.add_argument("--ticker",        default="",                     help="Ticker symbol to tag all triples with (optional)")
    args = parser.parse_args()

    db_path = args.db_path
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
    init_graph_triples(db_path=db_path, graphify_dir=args.graphify_dir, ticker=args.ticker)
