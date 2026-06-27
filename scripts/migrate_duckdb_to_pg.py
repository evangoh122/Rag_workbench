#!/usr/bin/env python3
"""Migrate edgar_embeddings from DuckDB → Postgres (pgvector / pgvectorscale).

Reads the local DuckDB corpus and bulk-loads it into a Postgres table created by
db/pgvector/schema.sql. Idempotent: ON CONFLICT (ticker, accession, chunk_index)
DO NOTHING, so re-runs and partial loads are safe.

Prereqs:
  pip install "psycopg[binary]" pgvector duckdb
  # create the schema first:
  psql "$PG_DSN" -f db/pgvector/schema.sql

Usage:
  PG_DSN="postgresql://user:pass@host:5432/dbname?sslmode=require" \
  DUCKDB_PATH=data/rag.duckdb \
  python scripts/migrate_duckdb_to_pg.py [--batch 1000] [--limit N]

Tip: build the ANN index AFTER the bulk load (it's in schema.sql; if you create
the table without the index, load, then `CREATE INDEX ... USING diskann ...`,
the load is much faster).
"""
import argparse
import os
import sys

import duckdb
import psycopg
from pgvector.psycopg import register_vector

COLS = [
    "ticker", "accession", "text", "embedding", "updated_at", "cik",
    "section_id", "form_type", "period_of_report", "chunk_index",
    "section_type", "content_type",
]

INSERT_SQL = f"""
INSERT INTO edgar_embeddings ({", ".join(COLS)})
VALUES ({", ".join(["%s"] * len(COLS))})
ON CONFLICT (ticker, accession, chunk_index) DO NOTHING
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Migrate DuckDB embeddings into Postgres pgvector.")
    ap.add_argument("--batch", type=int, default=1000, help="Rows per insert batch.")
    ap.add_argument("--limit", type=int, default=0, help="Only migrate N rows (0 = all).")
    args = ap.parse_args()

    dsn = os.environ.get("PG_DSN")
    if not dsn:
        sys.exit("Set PG_DSN to your Postgres connection string.")
    duckdb_path = os.environ.get("DUCKDB_PATH", "data/rag.duckdb")

    con = duckdb.connect(duckdb_path, read_only=True)
    total = con.execute("SELECT count(*) FROM edgar_embeddings").fetchone()[0]
    q = f"SELECT {', '.join(COLS)} FROM edgar_embeddings"
    if args.limit:
        q += f" LIMIT {args.limit}"
    cur_duck = con.execute(q)
    print(f"Source rows: {total} (migrating {args.limit or total})")

    moved = 0
    with psycopg.connect(dsn) as pg:
        register_vector(pg)  # lets us pass Python lists/np arrays as vector params
        with pg.cursor() as cur:
            while True:
                rows = cur_duck.fetchmany(args.batch)
                if not rows:
                    break
                # DuckDB returns the embedding as a Python list[float]; pgvector
                # accepts it directly once register_vector is active.
                cur.executemany(INSERT_SQL, rows)
                pg.commit()
                moved += len(rows)
                print(f"  migrated {moved}/{total}", end="\r", flush=True)
    con.close()
    print(f"\nDone. Inserted up to {moved} rows (duplicates skipped).")
    print("If you deferred the ANN index, create it now (see db/pgvector/schema.sql).")


if __name__ == "__main__":
    main()
