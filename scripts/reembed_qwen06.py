"""
reembed_qwen06.py — One-off migration: re-embed edgar_embeddings with Qwen.

The DB was originally embedded with ollama/nomic-embed-text (768-dim). The HF
Space now runs sentence-transformers Qwen/Qwen3-Embedding-0.6B (1024-dim), so the
stored vectors are incompatible. This re-embeds the *existing stored chunk texts*
(no EDGAR refetch) with the 0.6B model and writes 1024-dim vectors in place.

Resumable: only rows whose vector is not already 1024-dim are processed, and
progress is committed every COMMIT_EVERY batches, so re-running continues where
it stopped. graph_triples / xbrl_facts are untouched (dimension-independent).

Usage:
    python scripts/reembed_qwen06.py [--db-path ./data/rag.duckdb] [--batch 32]
"""
from __future__ import annotations

import argparse
import os
import time

# Use all CPU cores for the embedding matmuls (torch/MKL otherwise default to a
# fraction of logical CPUs). Must be set before torch/numpy are imported.
_NCPU = str(os.cpu_count() or 4)
os.environ.setdefault("OMP_NUM_THREADS", _NCPU)
os.environ.setdefault("MKL_NUM_THREADS", _NCPU)

import duckdb

MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"
TARGET_DIM = 1024
COMMIT_EVERY = 5  # batches (frequent commits = better progress visibility + resumability)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-path", default="./data/rag.duckdb")
    ap.add_argument("--batch", type=int, default=32)
    args = ap.parse_args()

    os.environ.setdefault("EMBEDDING_MAX_SEQ_LEN", "512")

    import torch
    from sentence_transformers import SentenceTransformer

    try:
        torch.set_num_threads(int(_NCPU))
    except Exception:
        pass
    print(f"[reembed] torch threads={torch.get_num_threads()}", flush=True)
    print(f"[reembed] loading {MODEL_NAME} ...", flush=True)
    model = SentenceTransformer(MODEL_NAME)
    try:
        model.max_seq_length = int(os.getenv("EMBEDDING_MAX_SEQ_LEN", "512"))
    except Exception:
        pass

    conn = duckdb.connect(args.db_path)

    total = conn.execute("SELECT COUNT(*) FROM edgar_embeddings").fetchone()[0]
    todo = conn.execute(
        "SELECT COUNT(*) FROM edgar_embeddings "
        "WHERE embedding IS NULL OR len(embedding) <> ?", [TARGET_DIM]
    ).fetchone()[0]
    print(f"[reembed] {total} rows total, {todo} need re-embedding "
          f"(already {TARGET_DIM}-dim: {total - todo})", flush=True)
    if todo == 0:
        print("[reembed] nothing to do.")
        conn.close()
        return

    # Use a STABLE surrogate key, not rowid. DuckDB rowids can drift across
    # commits (especially after DELETEs), which silently makes UPDATE..WHERE
    # rowid=? match nothing — leaving rows NULL while the loop counts them done.
    conn.execute("ALTER TABLE edgar_embeddings ADD COLUMN IF NOT EXISTS reembed_id BIGINT")
    conn.execute("CREATE SEQUENCE IF NOT EXISTS reembed_id_seq")
    conn.execute(
        "UPDATE edgar_embeddings SET reembed_id = nextval('reembed_id_seq') WHERE reembed_id IS NULL"
    )
    conn.commit()

    rows = conn.execute(
        "SELECT reembed_id, text FROM edgar_embeddings "
        "WHERE embedding IS NULL OR len(embedding) <> ? ORDER BY reembed_id", [TARGET_DIM]
    ).fetchall()

    done = 0
    t0 = time.time()
    batch_no = 0
    for i in range(0, len(rows), args.batch):
        chunk = rows[i:i + args.batch]
        ids = [r[0] for r in chunk]
        texts = [r[1] or "" for r in chunk]
        vecs = model.encode(
            texts, normalize_embeddings=True, convert_to_numpy=True,
            batch_size=args.batch,
        )
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        conn.executemany(
            "UPDATE edgar_embeddings SET embedding = ?, updated_at = ? WHERE reembed_id = ?",
            [(vecs[j].tolist(), ts, ids[j]) for j in range(len(ids))],
        )
        done += len(chunk)
        batch_no += 1
        if batch_no % COMMIT_EVERY == 0:
            conn.commit()
            rate = done / max(time.time() - t0, 1e-6)
            eta = (todo - done) / max(rate, 1e-6)
            print(f"[reembed] {done}/{todo}  ({rate:.1f}/s, eta {eta/60:.1f} min)", flush=True)

    conn.commit()
    # verify + clean up the surrogate key once the corpus is fully 1024-dim
    remaining = conn.execute(
        "SELECT COUNT(*) FROM edgar_embeddings WHERE embedding IS NULL OR len(embedding) <> ?",
        [TARGET_DIM],
    ).fetchone()[0]
    if remaining == 0:
        conn.execute("ALTER TABLE edgar_embeddings DROP COLUMN IF EXISTS reembed_id")
        conn.execute("DROP SEQUENCE IF EXISTS reembed_id_seq")
        conn.commit()
    dims = [r[0] for r in conn.execute(
        "SELECT DISTINCT len(embedding) FROM edgar_embeddings WHERE embedding IS NOT NULL"
    ).fetchall()]
    print(f"[reembed] DONE — {done} processed in {(time.time()-t0)/60:.1f} min. "
          f"remaining NULL/non-{TARGET_DIM}: {remaining}. vector dims now: {sorted(dims)}", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
