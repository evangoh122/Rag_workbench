"""
scripts/sync_polygon_tickers.py
Fetch company details from Polygon.io and populate the polygon_tickers table in DuckDB.

Usage:
    python scripts/sync_polygon_tickers.py
"""
import os
import sys
import time
import requests
import duckdb
from pathlib import Path
from loguru import logger

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.config import Config

POLYGON_BASE = "https://api.polygon.io"
DB_PATH = Config.DB_PATH

TICKERS = [
    "MU", "NVDA", "AMD", "AVGO", "INTC", "QCOM", "TXN",
    "LRCX", "KLAC", "ACLS", "AEHR", "ENTG", "ICHR", "KLIC", "PLAB", "TER",
]

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS polygon_tickers (
    ticker              VARCHAR PRIMARY KEY,
    name                VARCHAR,
    market              VARCHAR,
    primary_exchange    VARCHAR,
    type                VARCHAR,
    active              BOOLEAN,
    currency_name       VARCHAR,
    cik                 VARCHAR,
    composite_figi      VARCHAR,
    market_cap          DOUBLE,
    phone_number        VARCHAR,
    address             VARCHAR,
    city                VARCHAR,
    state               VARCHAR,
    postal_code         VARCHAR,
    description         VARCHAR,
    sic_code            VARCHAR,
    sic_description     VARCHAR,
    homepage_url        VARCHAR,
    total_employees     INTEGER,
    list_date           VARCHAR,
    shares_outstanding  DOUBLE,
    weighted_shares_outstanding DOUBLE,
    last_updated        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

UPSERT_SQL = """
INSERT OR REPLACE INTO polygon_tickers (
    ticker, name, market, primary_exchange, type, active, currency_name,
    cik, composite_figi, market_cap, phone_number,
    address, city, state, postal_code,
    description, sic_code, sic_description,
    homepage_url, total_employees, list_date,
    shares_outstanding, weighted_shares_outstanding, last_updated
) VALUES (
    ?, ?, ?, ?, ?, ?, ?,
    ?, ?, ?, ?,
    ?, ?, ?, ?,
    ?, ?, ?,
    ?, ?, ?,
    ?, ?, CURRENT_TIMESTAMP
);
"""


def fetch_ticker_details(ticker: str, api_key: str) -> dict | None:
    """Fetch company details from Polygon for a single ticker with retry on 429."""
    for attempt in range(3):
        try:
            resp = requests.get(
                f"{POLYGON_BASE}/v3/reference/tickers/{ticker}",
                params={"apiKey": api_key},
                timeout=15,
            )
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 15))
                logger.warning(f"Rate limited on {ticker}, waiting {wait}s (attempt {attempt+1})")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json().get("results", {})
        except requests.RequestException as e:
            logger.error(f"Failed to fetch {ticker} (attempt {attempt+1}): {e}")
            if attempt < 2:
                time.sleep(5)
    return None


def row_from_result(ticker: str, data: dict) -> tuple:
    """Convert Polygon API result to a row tuple for the upsert."""
    addr = data.get("address", {})
    shares_out = data.get("share_class_shares_outstanding")
    weighted_shares = data.get("weighted_shares_outstanding")

    return (
        ticker,
        data.get("name", ""),
        data.get("market", ""),
        data.get("primary_exchange", ""),
        data.get("type", ""),
        data.get("active", False),
        data.get("currency_name", ""),
        data.get("cik", ""),
        data.get("composite_figi", ""),
        float(data.get("market_cap", 0) or 0),
        data.get("phone_number", ""),
        addr.get("address1", ""),
        addr.get("city", ""),
        addr.get("state", ""),
        addr.get("postal_code", ""),
        data.get("description", ""),
        data.get("sic_code", ""),
        data.get("sic_description", ""),
        data.get("homepage_url", ""),
        int(data.get("total_employees", 0) or 0),
        data.get("list_date", ""),
        float(shares_out) if shares_out else None,
        float(weighted_shares) if weighted_shares else None,
    )


def main():
    api_key = Config.POLYGON_API_KEY
    if not api_key:
        logger.error("POLYGON_API_KEY not set in .env")
        sys.exit(1)

    logger.info(f"Syncing {len(TICKERS)} tickers to polygon_tickers at {DB_PATH}")

    conn = duckdb.connect(DB_PATH)
    conn.execute(CREATE_TABLE_SQL)

    success = 0
    failed = []

    for ticker in TICKERS:
        logger.info(f"Fetching {ticker}...")
        data = fetch_ticker_details(ticker, api_key)
        if data is None:
            failed.append(ticker)
            continue

        row = row_from_result(ticker, data)
        conn.execute(UPSERT_SQL, row)
        logger.info(f"  -> {data.get('name', '?')} | market_cap={data.get('market_cap', 0):,.0f} | {data.get('sic_description', '')}")
        success += 1

        # Rate limit: 5 req/min on free tier
        if TICKERS.index(ticker) < len(TICKERS) - 1:
            time.sleep(12.5)  # ~5 req/min

    conn.close()

    logger.info(f"Done: {success} synced, {len(failed)} failed")
    if failed:
        logger.warning(f"Failed tickers: {', '.join(failed)}")


if __name__ == "__main__":
    main()
