"""
seed_on_startup.py — Runs at container startup.
Waits for uvicorn to be ready, then triggers XBRL refresh if the DB is empty.
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

    if xbrl_count() > 0:
        logger.info("XBRL facts already loaded — skipping seed")
        return

    logger.info("DB is empty — triggering XBRL refresh from SEC EDGAR...")
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


if __name__ == "__main__":
    main()
