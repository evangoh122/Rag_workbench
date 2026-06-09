"""
seed_demo_data.py — Seed DuckDB with realistic synthetic XBRL facts for demo.

Used when SEC EDGAR API is unreachable (e.g., sandbox environment).
Data is based on publicly available annual report figures for AAPL, TSLA, MSFT.

Usage:
    python3 scripts/seed_demo_data.py [--db-path ./data/ibkr.duckdb]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import duckdb
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Realistic financial data (from public 10-K filings, in USD)
DEMO_DATA = [
    # AAPL FY2023 (period ending 2023-09-30)
    {"ticker": "AAPL", "cik": "0000320193", "concept": "Revenues", "value": 383_285_000_000, "unit": "USD", "period_end": "2023-09-30", "period_start": "2022-10-01", "form_type": "10-K", "accession": "0000320193-23-000106", "filed": "2023-11-03", "fiscal_year": 2023, "fiscal_period": "FY"},
    {"ticker": "AAPL", "cik": "0000320193", "concept": "NetIncomeLoss", "value": 96_995_000_000, "unit": "USD", "period_end": "2023-09-30", "period_start": "2022-10-01", "form_type": "10-K", "accession": "0000320193-23-000106", "filed": "2023-11-03", "fiscal_year": 2023, "fiscal_period": "FY"},
    {"ticker": "AAPL", "cik": "0000320193", "concept": "Assets", "value": 352_583_000_000, "unit": "USD", "period_end": "2023-09-30", "period_start": None, "form_type": "10-K", "accession": "0000320193-23-000106", "filed": "2023-11-03", "fiscal_year": 2023, "fiscal_period": "FY"},
    {"ticker": "AAPL", "cik": "0000320193", "concept": "Liabilities", "value": 290_437_000_000, "unit": "USD", "period_end": "2023-09-30", "period_start": None, "form_type": "10-K", "accession": "0000320193-23-000106", "filed": "2023-11-03", "fiscal_year": 2023, "fiscal_period": "FY"},
    {"ticker": "AAPL", "cik": "0000320193", "concept": "StockholdersEquity", "value": 62_146_000_000, "unit": "USD", "period_end": "2023-09-30", "period_start": None, "form_type": "10-K", "accession": "0000320193-23-000106", "filed": "2023-11-03", "fiscal_year": 2023, "fiscal_period": "FY"},
    {"ticker": "AAPL", "cik": "0000320193", "concept": "OperatingIncomeLoss", "value": 114_301_000_000, "unit": "USD", "period_end": "2023-09-30", "period_start": "2022-10-01", "form_type": "10-K", "accession": "0000320193-23-000106", "filed": "2023-11-03", "fiscal_year": 2023, "fiscal_period": "FY"},
    {"ticker": "AAPL", "cik": "0000320193", "concept": "GrossProfit", "value": 169_148_000_000, "unit": "USD", "period_end": "2023-09-30", "period_start": "2022-10-01", "form_type": "10-K", "accession": "0000320193-23-000106", "filed": "2023-11-03", "fiscal_year": 2023, "fiscal_period": "FY"},
    {"ticker": "AAPL", "cik": "0000320193", "concept": "CostOfGoodsAndServicesSold", "value": 214_137_000_000, "unit": "USD", "period_end": "2023-09-30", "period_start": "2022-10-01", "form_type": "10-K", "accession": "0000320193-23-000106", "filed": "2023-11-03", "fiscal_year": 2023, "fiscal_period": "FY"},
    {"ticker": "AAPL", "cik": "0000320193", "concept": "ResearchAndDevelopmentExpense", "value": 29_915_000_000, "unit": "USD", "period_end": "2023-09-30", "period_start": "2022-10-01", "form_type": "10-K", "accession": "0000320193-23-000106", "filed": "2023-11-03", "fiscal_year": 2023, "fiscal_period": "FY"},
    {"ticker": "AAPL", "cik": "0000320193", "concept": "CashAndCashEquivalentsAtCarryingValue", "value": 29_965_000_000, "unit": "USD", "period_end": "2023-09-30", "period_start": None, "form_type": "10-K", "accession": "0000320193-23-000106", "filed": "2023-11-03", "fiscal_year": 2023, "fiscal_period": "FY"},
    {"ticker": "AAPL", "cik": "0000320193", "concept": "LongTermDebt", "value": 95_281_000_000, "unit": "USD", "period_end": "2023-09-30", "period_start": None, "form_type": "10-K", "accession": "0000320193-23-000106", "filed": "2023-11-03", "fiscal_year": 2023, "fiscal_period": "FY"},
    {"ticker": "AAPL", "cik": "0000320193", "concept": "EarningsPerShareBasic", "value": 6.16, "unit": "USD/shares", "period_end": "2023-09-30", "period_start": "2022-10-01", "form_type": "10-K", "accession": "0000320193-23-000106", "filed": "2023-11-03", "fiscal_year": 2023, "fiscal_period": "FY"},
    # AAPL FY2022 (period ending 2022-09-24)
    {"ticker": "AAPL", "cik": "0000320193", "concept": "Revenues", "value": 394_328_000_000, "unit": "USD", "period_end": "2022-09-24", "period_start": "2021-09-26", "form_type": "10-K", "accession": "0000320193-22-000108", "filed": "2022-10-28", "fiscal_year": 2022, "fiscal_period": "FY"},
    {"ticker": "AAPL", "cik": "0000320193", "concept": "NetIncomeLoss", "value": 99_803_000_000, "unit": "USD", "period_end": "2022-09-24", "period_start": "2021-09-26", "form_type": "10-K", "accession": "0000320193-22-000108", "filed": "2022-10-28", "fiscal_year": 2022, "fiscal_period": "FY"},
    {"ticker": "AAPL", "cik": "0000320193", "concept": "Assets", "value": 352_755_000_000, "unit": "USD", "period_end": "2022-09-24", "period_start": None, "form_type": "10-K", "accession": "0000320193-22-000108", "filed": "2022-10-28", "fiscal_year": 2022, "fiscal_period": "FY"},
    {"ticker": "AAPL", "cik": "0000320193", "concept": "Liabilities", "value": 302_083_000_000, "unit": "USD", "period_end": "2022-09-24", "period_start": None, "form_type": "10-K", "accession": "0000320193-22-000108", "filed": "2022-10-28", "fiscal_year": 2022, "fiscal_period": "FY"},
    {"ticker": "AAPL", "cik": "0000320193", "concept": "StockholdersEquity", "value": 50_672_000_000, "unit": "USD", "period_end": "2022-09-24", "period_start": None, "form_type": "10-K", "accession": "0000320193-22-000108", "filed": "2022-10-28", "fiscal_year": 2022, "fiscal_period": "FY"},
    # TSLA FY2022 (period ending 2022-12-31)
    {"ticker": "TSLA", "cik": "0001318605", "concept": "Revenues", "value": 81_462_000_000, "unit": "USD", "period_end": "2022-12-31", "period_start": "2022-01-01", "form_type": "10-K", "accession": "0001318605-23-000006", "filed": "2023-01-31", "fiscal_year": 2022, "fiscal_period": "FY"},
    {"ticker": "TSLA", "cik": "0001318605", "concept": "NetIncomeLoss", "value": 12_556_000_000, "unit": "USD", "period_end": "2022-12-31", "period_start": "2022-01-01", "form_type": "10-K", "accession": "0001318605-23-000006", "filed": "2023-01-31", "fiscal_year": 2022, "fiscal_period": "FY"},
    {"ticker": "TSLA", "cik": "0001318605", "concept": "Assets", "value": 82_338_000_000, "unit": "USD", "period_end": "2022-12-31", "period_start": None, "form_type": "10-K", "accession": "0001318605-23-000006", "filed": "2023-01-31", "fiscal_year": 2022, "fiscal_period": "FY"},
    {"ticker": "TSLA", "cik": "0001318605", "concept": "Liabilities", "value": 36_440_000_000, "unit": "USD", "period_end": "2022-12-31", "period_start": None, "form_type": "10-K", "accession": "0001318605-23-000006", "filed": "2023-01-31", "fiscal_year": 2022, "fiscal_period": "FY"},
    {"ticker": "TSLA", "cik": "0001318605", "concept": "StockholdersEquity", "value": 44_704_000_000, "unit": "USD", "period_end": "2022-12-31", "period_start": None, "form_type": "10-K", "accession": "0001318605-23-000006", "filed": "2023-01-31", "fiscal_year": 2022, "fiscal_period": "FY"},
    {"ticker": "TSLA", "cik": "0001318605", "concept": "OperatingIncomeLoss", "value": 13_656_000_000, "unit": "USD", "period_end": "2022-12-31", "period_start": "2022-01-01", "form_type": "10-K", "accession": "0001318605-23-000006", "filed": "2023-01-31", "fiscal_year": 2022, "fiscal_period": "FY"},
    {"ticker": "TSLA", "cik": "0001318605", "concept": "GrossProfit", "value": 20_853_000_000, "unit": "USD", "period_end": "2022-12-31", "period_start": "2022-01-01", "form_type": "10-K", "accession": "0001318605-23-000006", "filed": "2023-01-31", "fiscal_year": 2022, "fiscal_period": "FY"},
    {"ticker": "TSLA", "cik": "0001318605", "concept": "CostOfGoodsAndServicesSold", "value": 60_609_000_000, "unit": "USD", "period_end": "2022-12-31", "period_start": "2022-01-01", "form_type": "10-K", "accession": "0001318605-23-000006", "filed": "2023-01-31", "fiscal_year": 2022, "fiscal_period": "FY"},
    {"ticker": "TSLA", "cik": "0001318605", "concept": "ResearchAndDevelopmentExpense", "value": 3_075_000_000, "unit": "USD", "period_end": "2022-12-31", "period_start": "2022-01-01", "form_type": "10-K", "accession": "0001318605-23-000006", "filed": "2023-01-31", "fiscal_year": 2022, "fiscal_period": "FY"},
    # MSFT FY2023 (period ending 2023-06-30)
    {"ticker": "MSFT", "cik": "0000789019", "concept": "Revenues", "value": 211_915_000_000, "unit": "USD", "period_end": "2023-06-30", "period_start": "2022-07-01", "form_type": "10-K", "accession": "0000789019-23-000069", "filed": "2023-07-25", "fiscal_year": 2023, "fiscal_period": "FY"},
    {"ticker": "MSFT", "cik": "0000789019", "concept": "NetIncomeLoss", "value": 72_361_000_000, "unit": "USD", "period_end": "2023-06-30", "period_start": "2022-07-01", "form_type": "10-K", "accession": "0000789019-23-000069", "filed": "2023-07-25", "fiscal_year": 2023, "fiscal_period": "FY"},
    {"ticker": "MSFT", "cik": "0000789019", "concept": "Assets", "value": 411_976_000_000, "unit": "USD", "period_end": "2023-06-30", "period_start": None, "form_type": "10-K", "accession": "0000789019-23-000069", "filed": "2023-07-25", "fiscal_year": 2023, "fiscal_period": "FY"},
    {"ticker": "MSFT", "cik": "0000789019", "concept": "Liabilities", "value": 205_753_000_000, "unit": "USD", "period_end": "2023-06-30", "period_start": None, "form_type": "10-K", "accession": "0000789019-23-000069", "filed": "2023-07-25", "fiscal_year": 2023, "fiscal_period": "FY"},
    {"ticker": "MSFT", "cik": "0000789019", "concept": "StockholdersEquity", "value": 206_223_000_000, "unit": "USD", "period_end": "2023-06-30", "period_start": None, "form_type": "10-K", "accession": "0000789019-23-000069", "filed": "2023-07-25", "fiscal_year": 2023, "fiscal_period": "FY"},
    {"ticker": "MSFT", "cik": "0000789019", "concept": "OperatingIncomeLoss", "value": 88_523_000_000, "unit": "USD", "period_end": "2023-06-30", "period_start": "2022-07-01", "form_type": "10-K", "accession": "0000789019-23-000069", "filed": "2023-07-25", "fiscal_year": 2023, "fiscal_period": "FY"},
    {"ticker": "MSFT", "cik": "0000789019", "concept": "GrossProfit", "value": 146_052_000_000, "unit": "USD", "period_end": "2023-06-30", "period_start": "2022-07-01", "form_type": "10-K", "accession": "0000789019-23-000069", "filed": "2023-07-25", "fiscal_year": 2023, "fiscal_period": "FY"},
    {"ticker": "MSFT", "cik": "0000789019", "concept": "CostOfGoodsAndServicesSold", "value": 65_863_000_000, "unit": "USD", "period_end": "2023-06-30", "period_start": "2022-07-01", "form_type": "10-K", "accession": "0000789019-23-000069", "filed": "2023-07-25", "fiscal_year": 2023, "fiscal_period": "FY"},
    {"ticker": "MSFT", "cik": "0000789019", "concept": "ResearchAndDevelopmentExpense", "value": 27_195_000_000, "unit": "USD", "period_end": "2023-06-30", "period_start": "2022-07-01", "form_type": "10-K", "accession": "0000789019-23-000069", "filed": "2023-07-25", "fiscal_year": 2023, "fiscal_period": "FY"},
    {"ticker": "MSFT", "cik": "0000789019", "concept": "CashAndCashEquivalentsAtCarryingValue", "value": 34_704_000_000, "unit": "USD", "period_end": "2023-06-30", "period_start": None, "form_type": "10-K", "accession": "0000789019-23-000069", "filed": "2023-07-25", "fiscal_year": 2023, "fiscal_period": "FY"},
    {"ticker": "MSFT", "cik": "0000789019", "concept": "LongTermDebt", "value": 41_990_000_000, "unit": "USD", "period_end": "2023-06-30", "period_start": None, "form_type": "10-K", "accession": "0000789019-23-000069", "filed": "2023-07-25", "fiscal_year": 2023, "fiscal_period": "FY"},
]


def seed(db_path: str) -> None:
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
    conn = duckdb.connect(db_path)

    # Create sequences and tables
    conn.execute("CREATE SEQUENCE IF NOT EXISTS xbrl_facts_seq START 1")
    conn.execute("CREATE SEQUENCE IF NOT EXISTS filing_chunks_seq START 1")
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_xbrl_ticker_concept ON xbrl_facts (ticker, concept)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_xbrl_ticker_period ON xbrl_facts (ticker, period_end)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ticker_embeddings (
            ticker      VARCHAR PRIMARY KEY,
            description TEXT,
            sector      VARCHAR,
            industry    VARCHAR
        )
    """)
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_ticker ON filing_chunks (ticker)")

    # Insert demo data
    for fact in DEMO_DATA:
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

    # Insert ticker metadata
    for ticker, name in [("AAPL", "Apple Inc."), ("TSLA", "Tesla, Inc."), ("MSFT", "Microsoft Corporation")]:
        conn.execute("""
            INSERT OR REPLACE INTO ticker_embeddings (ticker, description, sector, industry)
            VALUES (?, ?, ?, ?)
        """, [ticker, name, "Technology", "Consumer Electronics" if ticker == "AAPL" else "Software"])

    count = conn.execute("SELECT COUNT(*) FROM xbrl_facts").fetchone()[0]
    conn.close()
    logger.info(f"Seed complete — {count} XBRL facts in {db_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed DuckDB with demo XBRL data")
    parser.add_argument("--db-path", default="./data/ibkr.duckdb", help="Path to DuckDB file")
    args = parser.parse_args()
    seed(db_path=args.db_path)
