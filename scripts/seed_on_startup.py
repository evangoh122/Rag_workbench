"""
seed_on_startup.py — Runs at container startup.
Waits for uvicorn to be ready, then triggers XBRL refresh if the DB is empty,
followed by chunking+embedding of 10-K filings into edgar_embeddings.
"""
import os
import time
import requests
from loguru import logger

ADMIN_KEY = os.getenv("ADMIN_API_KEY", "")
BASE_URL = "http://127.0.0.1:8000"


def wait_for_app(retries: int = 30, delay: float = 2.0) -> bool:
    for i in range(retries):
        try:
            r = requests.get(f"{BASE_URL}/api/health", timeout=5)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(delay)
    return False


def _stats() -> dict:
    try:
        r = requests.get(f"{BASE_URL}/api/stats", timeout=10)
        return r.json().get("data", {}) or {}
    except Exception:
        return {}


def xbrl_count() -> int:
    return _stats().get("xbrl_facts") or 0


def already_populated() -> bool:
    """True if the DB already has facts AND chunk embeddings — i.e. it was
    restored from the HF dataset at boot, so the EDGAR re-seed is unnecessary."""
    s = _stats()
    return (s.get("xbrl_facts") or 0) > 0 and (s.get("companies_with_chunks") or 0) > 0


def main():
    if not ADMIN_KEY:
        logger.warning("ADMIN_API_KEY not set — skipping startup XBRL seed")
        return

    logger.info("Waiting for uvicorn to be ready...")
    if not wait_for_app():
        logger.error("App did not start in time — skipping XBRL seed")
        return

    # The DB is normally restored from the HF dataset at boot (see
    # fetch_db_from_dataset.py / Dockerfile). If it already has facts + chunk
    # embeddings, the expensive EDGAR re-seed is redundant — skip it.
    if already_populated():
        s = _stats()
        logger.info(
            f"DB already populated from dataset (xbrl_facts={s.get('xbrl_facts')}, "
            f"companies_with_chunks={s.get('companies_with_chunks')}) — skipping EDGAR re-seed"
        )
        return

    count = xbrl_count()
    logger.info(f"Current XBRL facts in DB: {count} — triggering incremental refresh...")
    # Always call refresh (incremental mode skips tickers already present, only fetches new ones)
    try:
        r = requests.post(
            f"{BASE_URL}/api/admin/refresh-data",
            headers={"X-API-Key": ADMIN_KEY, "Content-Type": "application/json"},
            timeout=600,
        )
        if r.status_code == 200:
            d = r.json()
            logger.info(
                f"Startup seed complete — {d.get('tickers_processed')} tickers, "
                f"{d.get('facts_loaded')} facts, status={d.get('status')}"
            )
        else:
            logger.error(f"Startup seed failed: HTTP {r.status_code} — {r.text}")
    except Exception as e:
        logger.error(f"Startup seed error: {e}")

    # ── Step 2: Chunk + embed 10-K filings into edgar_embeddings ────────────
    # Process in smaller batches to stay within HF Space 16GB memory limit
    max_embed_retries = 3
    for attempt in range(1, max_embed_retries + 1):
        try:
            logger.info(f"Triggering filing chunking + embedding job (attempt {attempt}/{max_embed_retries})...")
            r = requests.post(
                f"{BASE_URL}/api/admin/embed-data",
                headers={"X-API-Key": ADMIN_KEY, "Content-Type": "application/json"},
                timeout=1800,
            )
            if r.status_code == 200:
                d = r.json()
                chunks = d.get("chunks_stored", 0)
                logger.info(f"Embedding complete — {chunks} chunks, status={d.get('status')}")
                if chunks > 0:
                    break
                logger.warning(f"Embedding returned 0 chunks — retrying...")
            else:
                logger.error(f"Embedding failed: HTTP {r.status_code} — {r.text}")
        except Exception as e:
            logger.error(f"Embedding error (attempt {attempt}): {e}")
        if attempt < max_embed_retries:
            time.sleep(30)
    else:
        logger.error("Embedding step failed after all retries — Space will start without chunk embeddings")


if __name__ == "__main__":
    main()
