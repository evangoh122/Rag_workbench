"""Corpus-integrity guardrail for the embedding ETL workflows.

Single source of truth for "never destroy the vector DB". Used by the GitHub
Actions embed/refresh workflows around the embedding step:

    python scripts/etl_guardrail.py snapshot data/rag.duckdb /tmp/before.json
    # ... run the embedding ...
    python scripts/etl_guardrail.py verify   data/rag.duckdb /tmp/before.json

`verify` exits non-zero (so the workflow fails BEFORE uploading) on any
destructive change, leaving the published dataset untouched. It blocks:
  - the DB failing to open (truncated / corrupt),
  - vectors that are not uniformly 1024-dim (mixed dims silently break retrieval),
  - null embeddings,
  - a drop in total row count or distinct-ticker count,
  - any previously-present (ticker, accession) filing disappearing.

On success it writes `changed` (true only if rows strictly grew) and a `summary`
to $GITHUB_OUTPUT so the workflow uploads/restarts only when there is something new.
"""
import json
import os
import sys

import duckdb

EXPECTED_DIM = 1024


def _read(db_path: str):
    con = duckdb.connect(db_path, read_only=True)  # opening proves it isn't corrupt
    try:
        total = con.execute("SELECT count(*) FROM edgar_embeddings").fetchone()[0]
        tickers = con.execute("SELECT count(DISTINCT ticker) FROM edgar_embeddings").fetchone()[0]
        dims = con.execute(
            "SELECT len(embedding) d, count(*) n FROM edgar_embeddings GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall()
        nulls = con.execute("SELECT count(*) FROM edgar_embeddings WHERE embedding IS NULL").fetchone()[0]
        pairs = {
            f"{t}|{a}"
            for t, a in con.execute(
                "SELECT DISTINCT ticker, accession FROM edgar_embeddings"
            ).fetchall()
        }
        return {"total": total, "tickers": tickers, "dims": dims, "nulls": nulls, "pairs": pairs}
    finally:
        con.close()


def _emit(key: str, value: str) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


def snapshot(db_path: str, out_path: str) -> None:
    s = _read(db_path)
    json.dump(
        {"total": s["total"], "tickers": s["tickers"], "pairs": sorted(s["pairs"])},
        open(out_path, "w", encoding="utf-8"),
    )
    print(f"BEFORE: {s['total']} chunks, {s['tickers']} tickers, {len(s['pairs'])} filings")


def verify(db_path: str, before_path: str) -> None:
    before = json.load(open(before_path, encoding="utf-8"))
    after = _read(db_path)

    errors = []
    dims = after["dims"]
    if not (len(dims) == 1 and dims[0][0] == EXPECTED_DIM):
        errors.append(f"vectors not uniformly {EXPECTED_DIM}-dim: {dims}")
    if after["nulls"]:
        errors.append(f"{after['nulls']} null embeddings present")
    if after["total"] < before["total"]:
        errors.append(f"row count SHRANK {before['total']} -> {after['total']} (data loss)")
    if after["tickers"] < before["tickers"]:
        errors.append(f"distinct tickers SHRANK {before['tickers']} -> {after['tickers']}")
    missing = sorted(set(before["pairs"]) - after["pairs"])
    if missing:
        errors.append(f"{len(missing)} previously-present filings vanished, e.g. {missing[:5]}")

    print(
        f"AFTER:  {after['total']} chunks, {after['tickers']} tickers, "
        f"{len(after['pairs'])} filings; dims={dims} nulls={after['nulls']}"
    )
    if errors:
        for e in errors:
            print(f"::error::DESTRUCTIVE CHANGE BLOCKED — {e}")
        print("Refusing to upload. Published dataset left untouched.")
        sys.exit(1)

    changed = "true" if after["total"] > before["total"] else "false"
    summary = f"{before['total']} -> {after['total']} chunks, {len(after['pairs'])} filings"
    print(f"Integrity OK ({summary}). New chunks: {after['total'] - before['total']}. changed={changed}")
    _emit("changed", changed)
    _emit("summary", summary)


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] not in ("snapshot", "verify"):
        sys.exit("usage: etl_guardrail.py {snapshot|verify} <db_path> <json_path>")
    if sys.argv[1] == "snapshot":
        snapshot(sys.argv[2], sys.argv[3])
    else:
        verify(sys.argv[2], sys.argv[3])
