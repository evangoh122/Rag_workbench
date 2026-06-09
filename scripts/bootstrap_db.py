"""
bootstrap_db.py — Seed DuckDB with XBRL facts and ticker embeddings for demo tickers.

This script:
1. Creates the required tables (ticker_embeddings, filing_chunks, graph_triples)
2. Fetches XBRL companyfacts from SEC EDGAR for a small set of tickers
3. Stores the facts in DuckDB for use by the RAG pipeline

Usage:
    python3 scripts/bootstrap_db.py [--tickers AAPL,TSLA,MSFT] [--db-path ./data/ibkr.duckdb]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import duckdb
import requests
from loguru import logger

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

# SEC EDGAR API config
EDGAR_USER_AGENT = os.getenv("EDGAR_USER_AGENT", "RAGWorkbench/1.0 (research@example.com)")
SEC_RATE_LIMIT_DELAY = 0.15  # 10 req/s max -> 100ms + margin

# CIK lookup for common tickers
TICKER_TO_CIK = {
    "AAPL": "0000320193",
    "TSLA": "0001318605",
    "MSFT": "0000789019",
    "NVDA": "0001045810",
    "AMZN": "0001018724",
    "META": "0001326801",
    "GOOGL": "0001652044",
    "JPM": "0000019617",
    "GS": "0000886982",
    "BAC": "0000070858",
}

# Key financial concepts to extract
KEY_CONCEPTS = [
    "us-gaap/Revenues",
    "us-gaap/NetIncomeLoss",
    "us-gaap/Assets",
    "us-gaap/Liabilities",
    "us-gaap/StockholdersEquity",
    "us-gaap/OperatingIncomeLoss",
    "us-gaap/GrossProfit",
    "us-gaap/CostOfGoodsAndServicesSold",
    "us-gaap/ResearchAndDevelopmentExpense",
    "us-gaap/CashAndCashEquivalentsAtCarryingValue",
    "us-gaap/LongTermDebt",
    "us-gaap/EarningsPerShareBasic",
    "us-gaap/CommonStockSharesOutstanding",
    "us-gaap/OperatingCashFlow",
    "us-gaap/NetCashProvidedByUsedInOperatingActivities",
    "us-gaap/PaymentsToAcquirePropertyPlantAndEquipment",
]


def fetch_company_facts(cik: str) -> dict | None:
    """Fetch companyfacts JSON from SEC EDGAR."""
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    headers = {"User-Agent": EDGAR_USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        time.sleep(SEC_RATE_LIMIT_DELAY)
        if resp.status_code == 200:
            return resp.json()
        logger.warning(f"SEC API returned {resp.status_code} for CIK {cik}")
        return None
    except Exception as e:
        logger.error(f"Failed to fetch companyfacts for CIK {cik}: {e}")
        return None


def extract_facts(company_data: dict, ticker: str, cik: str) -> list[dict]:
    """Extract key financial facts from companyfacts JSON."""
    facts_list = []
    us_gaap = company_data.get("facts", {}).get("us-gaap", {})

    for full_concept in KEY_CONCEPTS:
        concept_name = full_concept.split("/")[-1]
        concept_data = us_gaap.get(concept_name, {})
        units = concept_data.get("units", {})

        # Try USD first, then shares
        unit_data = units.get("USD", units.get("USD/shares", units.get("shares", [])))
        if not unit_data:
            continue

        for entry in unit_data:
            # Only take annual (10-K) filings
            form = entry.get("form", "")
            if form not in ("10-K", "10-K/A"):
                continue

            facts_list.append({
                "ticker": ticker,
                "cik": cik,
                "concept": concept_name,
                "value": entry.get("val"),
                "unit": "USD" if "USD" in units else "shares",
                "period_end": entry.get("end"),
                "period_start": entry.get("start"),
                "form_type": form,
                "accession": entry.get("accn", ""),
                "filed": entry.get("filed", ""),
                "fiscal_year": entry.get("fy"),
                "fiscal_period": entry.get("fp"),
            })

    return facts_list


def create_tables(conn: duckdb.DuckDBPyConnection) -> None:
    """Create all required tables."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS xbrl_facts (
            id          INTEGER PRIMARY KEY DEFAULT(nextval('xbrl_facts_seq')),
            ticker      VARCHAR NOT NULL,
            cik         VARCHAR NOT NULL,
            concept     VARCHAR NOT NULL,
            value       DOUBLE,
            unit        VARCHAR,
            period_end  VARCHAR,
            period_start VARCHAR,
            form_type   VARCHAR,
            accession   VARCHAR,
            filed       VARCHAR,
            fiscal_year INTEGER,
            fiscal_period VARCHAR
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_xbrl_ticker_concept
        ON xbrl_facts (ticker, concept)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_xbrl_ticker_period
        ON xbrl_facts (ticker, period_end)
    """)
    # Filing chunks table for retrieval
    conn.execute("""
        CREATE TABLE IF NOT EXISTS filing_chunks (
            id          INTEGER PRIMARY KEY DEFAULT(nextval('filing_chunks_seq')),
            ticker      VARCHAR NOT NULL,
            cik         VARCHAR NOT NULL,
            form_type   VARCHAR,
            period_end  VARCHAR,
            section     VARCHAR,
            chunk_text  TEXT NOT NULL,
            chunk_index INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_ticker
        ON filing_chunks (ticker)
    """)
    # Ticker embeddings placeholder
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ticker_embeddings (
            ticker      VARCHAR PRIMARY KEY,
            description TEXT,
            sector      VARCHAR,
            industry    VARCHAR
        )
    """)
    # graph_triples already created by database.py init
    conn.execute("""
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
    """)


def bootstrap(tickers: list[str], db_path: str) -> None:
    """Main bootstrap routine."""
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
    conn = duckdb.connect(db_path)

    # Create sequences
    conn.execute("CREATE SEQUENCE IF NOT EXISTS xbrl_facts_seq START 1")
    conn.execute("CREATE SEQUENCE IF NOT EXISTS filing_chunks_seq START 1")

    create_tables(conn)

    total_facts = 0
    for ticker in tickers:
        cik = TICKER_TO_CIK.get(ticker)
        if not cik:
            logger.warning(f"No CIK mapping for {ticker}, skipping")
            continue

        logger.info(f"Fetching companyfacts for {ticker} (CIK {cik})...")
        data = fetch_company_facts(cik)
        if data is None:
            continue

        facts = extract_facts(data, ticker, cik)
        logger.info(f"  Extracted {len(facts)} facts for {ticker}")

        # Insert facts
        for fact in facts:
            conn.execute("""
                INSERT INTO xbrl_facts
                    (ticker, cik, concept, value, unit, period_end, period_start,
                     form_type, accession, filed, fiscal_year, fiscal_period)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                fact["ticker"], fact["cik"], fact["concept"], fact["value"],
                fact["unit"], fact["period_end"], fact["period_start"],
                fact["form_type"], fact["accession"], fact["filed"],
                fact["fiscal_year"], fact["fiscal_period"],
            ])
            total_facts += 1

        # Insert ticker metadata
        company_name = data.get("entityName", ticker)
        conn.execute("""
            INSERT OR REPLACE INTO ticker_embeddings (ticker, description, sector, industry)
            VALUES (?, ?, ?, ?)
        """, [ticker, company_name, "", ""])

    conn.close()
    logger.info(f"Bootstrap complete — {total_facts} XBRL facts loaded into {db_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bootstrap DuckDB with SEC EDGAR XBRL data")
    parser.add_argument("--tickers", default="AAPL,TSLA,MSFT,NVDA,AMZN",
                        help="Comma-separated ticker symbols")
    parser.add_argument("--db-path", default="./data/ibkr.duckdb",
                        help="Path to DuckDB file")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    bootstrap(tickers=tickers, db_path=args.db_path)
