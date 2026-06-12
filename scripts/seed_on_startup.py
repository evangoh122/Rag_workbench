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


def xbrl_count() -> int:
    try:
        r = requests.get(f"{BASE_URL}/api/stats", timeout=10)
        return r.json().get("data", {}).get("xbrl_facts") or 0
    except Exception:
        return 0


def main():
    if not ADMIN_KEY:
        logger.warning("ADMIN_API_KEY not set — skipping startup XBRL seed")
        return

    logger.info("Waiting for uvicorn to be ready...")
    if not wait_for_app():
        logger.error("App did not start in time — skipping XBRL seed")
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
    try:
        logger.info("Triggering filing chunking + embedding job...")
        r = requests.post(
            f"{BASE_URL}/api/admin/embed-data",
            headers={"X-API-Key": ADMIN_KEY, "Content-Type": "application/json"},
            timeout=1800,
        )
        if r.status_code == 200:
            d = r.json()
            logger.info(
                f"Embedding complete — {d.get('chunks_stored')} chunks, "
                f"status={d.get('status')}"
            )
        else:
            logger.error(f"Embedding failed: HTTP {r.status_code} — {r.text}")
    except Exception as e:
        logger.error(f"Embedding error: {e}")


if __name__ == "__main__":
    main()
