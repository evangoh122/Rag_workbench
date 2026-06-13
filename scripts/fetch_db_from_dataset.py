"""
fetch_db_from_dataset.py — Restore the main DuckDB from a HF dataset at boot.

The HF Space disk is ephemeral, so the DB is wiped on every restart. Rather than
re-seed from EDGAR each boot (slow, and re-embeds only a subset), we restore a
pre-built rag.duckdb from a private HF dataset that already contains the Qwen
(1024-dim) embeddings, XBRL facts, and graph_triples.

Runs as the container entrypoint *before* uvicorn opens the DB connection, so the
app comes up pointing at the populated database. If the fetch fails (missing
token, network, repo), it logs and exits 0 so the container still starts and the
startup seed (seed_on_startup.py) can fall back to rebuilding from EDGAR.

Env:
  DB_DATASET_REPO  dataset repo id           (default: egoh33/Rag-workbench)
  DB_DATASET_FILE  filename within the repo  (default: rag.duckdb)
  HF_TOKEN         read token (required for a private dataset)
"""
from __future__ import annotations

import os
import shutil

from loguru import logger

from api.config import Config

REPO = os.getenv("DB_DATASET_REPO", "egoh33/Rag-workbench")
FILENAME = os.getenv("DB_DATASET_FILE", "rag.duckdb")
# A freshly-created empty DuckDB is a few hundred KB; a real corpus is >100MB.
MIN_REAL_DB_BYTES = 5_000_000


def main() -> None:
    db_path = Config.DB_PATH

    # Don't clobber an already-populated DB (e.g. local dev, or a warm restart
    # where the file survived).
    if os.path.exists(db_path) and os.path.getsize(db_path) > MIN_REAL_DB_BYTES:
        logger.info(
            "DB already present at {} ({:.0f} MB) — skipping dataset fetch",
            db_path, os.path.getsize(db_path) / 1e6,
        )
        return

    token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")
    if not token:
        logger.warning(
            "HF_TOKEN not set — cannot fetch private dataset {}. "
            "Falling back to startup seed.", REPO,
        )
        return

    try:
        from huggingface_hub import hf_hub_download

        logger.info("Fetching {} from dataset {} ...", FILENAME, REPO)
        cached = hf_hub_download(
            repo_id=REPO, filename=FILENAME, repo_type="dataset", token=token,
        )
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        shutil.copyfile(cached, db_path)
        logger.info(
            "DB restored from dataset to {} ({:.0f} MB)",
            db_path, os.path.getsize(db_path) / 1e6,
        )
    except Exception as e:
        logger.error(
            "Could not fetch DB from dataset {}: {} — falling back to startup seed",
            REPO, e,
        )


if __name__ == "__main__":
    main()
