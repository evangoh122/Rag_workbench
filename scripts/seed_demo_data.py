"""
seed_demo_data.py — Seed DuckDB with realistic XBRL facts for semiconductor demo.

Used when SEC EDGAR API is unreachable (e.g., sandbox environment).
Data is based on publicly available annual report figures for semiconductor companies.

Usage:
    python3 scripts/seed_demo_data.py [--db-path ./data/rag.duckdb]
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
    # NVDA FY2025 (period ending 2025-01-26)
    {"ticker": "NVDA", "cik": "0001045810", "concept": "Revenues", "value": 130_497_000_000, "unit": "USD", "period_end": "2025-01-26", "period_start": "2024-01-29", "form_type": "10-K", "accession": "0001045810-25-000012", "filed": "2025-02-26", "fiscal_year": 2025, "fiscal_period": "FY"},
    {"ticker": "NVDA", "cik": "0001045810", "concept": "NetIncomeLoss", "value": 72_880_000_000, "unit": "USD", "period_end": "2025-01-26", "period_start": "2024-01-29", "form_type": "10-K", "accession": "0001045810-25-000012", "filed": "2025-02-26", "fiscal_year": 2025, "fiscal_period": "FY"},
    {"ticker": "NVDA", "cik": "0001045810", "concept": "GrossProfit", "value": 97_936_000_000, "unit": "USD", "period_end": "2025-01-26", "period_start": "2024-01-29", "form_type": "10-K", "accession": "0001045810-25-000012", "filed": "2025-02-26", "fiscal_year": 2025, "fiscal_period": "FY"},
    {"ticker": "NVDA", "cik": "0001045810", "concept": "ResearchAndDevelopmentExpense", "value": 12_900_000_000, "unit": "USD", "period_end": "2025-01-26", "period_start": "2024-01-29", "form_type": "10-K", "accession": "0001045810-25-000012", "filed": "2025-02-26", "fiscal_year": 2025, "fiscal_period": "FY"},
    {"ticker": "NVDA", "cik": "0001045810", "concept": "Assets", "value": 111_600_000_000, "unit": "USD", "period_end": "2025-01-26", "period_start": None, "form_type": "10-K", "accession": "0001045810-25-000012", "filed": "2025-02-26", "fiscal_year": 2025, "fiscal_period": "FY"},
    {"ticker": "NVDA", "cik": "0001045810", "concept": "NetCashProvidedByUsedInOperatingActivities", "value": 64_100_000_000, "unit": "USD", "period_end": "2025-01-26", "period_start": "2024-01-29", "form_type": "10-K", "accession": "0001045810-25-000012", "filed": "2025-02-26", "fiscal_year": 2025, "fiscal_period": "FY"},
    # AMD FY2024 (period ending 2024-12-28)
    {"ticker": "AMD", "cik": "0000002488", "concept": "NetIncomeLoss", "value": 1_641_000_000, "unit": "USD", "period_end": "2024-12-28", "period_start": "2023-12-31", "form_type": "10-K", "accession": "0000002488-25-000007", "filed": "2025-02-04", "fiscal_year": 2024, "fiscal_period": "FY"},
    {"ticker": "AMD", "cik": "0000002488", "concept": "GrossProfit", "value": 12_700_000_000, "unit": "USD", "period_end": "2024-12-28", "period_start": "2023-12-31", "form_type": "10-K", "accession": "0000002488-25-000007", "filed": "2025-02-04", "fiscal_year": 2024, "fiscal_period": "FY"},
    {"ticker": "AMD", "cik": "0000002488", "concept": "ResearchAndDevelopmentExpense", "value": 6_500_000_000, "unit": "USD", "period_end": "2024-12-28", "period_start": "2023-12-31", "form_type": "10-K", "accession": "0000002488-25-000007", "filed": "2025-02-04", "fiscal_year": 2024, "fiscal_period": "FY"},
    {"ticker": "AMD", "cik": "0000002488", "concept": "Assets", "value": 69_200_000_000, "unit": "USD", "period_end": "2024-12-28", "period_start": None, "form_type": "10-K", "accession": "0000002488-25-000007", "filed": "2025-02-04", "fiscal_year": 2024, "fiscal_period": "FY"},
    # QCOM FY2024 (period ending 2024-09-29)
    {"ticker": "QCOM", "cik": "0000804328", "concept": "Revenues", "value": 38_962_000_000, "unit": "USD", "period_end": "2024-09-29", "period_start": "2023-10-01", "form_type": "10-K", "accession": "0000804328-24-000022", "filed": "2024-11-06", "fiscal_year": 2024, "fiscal_period": "FY"},
    {"ticker": "QCOM", "cik": "0000804328", "concept": "NetIncomeLoss", "value": 10_142_000_000, "unit": "USD", "period_end": "2024-09-29", "period_start": "2023-10-01", "form_type": "10-K", "accession": "0000804328-24-000022", "filed": "2024-11-06", "fiscal_year": 2024, "fiscal_period": "FY"},
    {"ticker": "QCOM", "cik": "0000804328", "concept": "ResearchAndDevelopmentExpense", "value": 8_900_000_000, "unit": "USD", "period_end": "2024-09-29", "period_start": "2023-10-01", "form_type": "10-K", "accession": "0000804328-24-000022", "filed": "2024-11-06", "fiscal_year": 2024, "fiscal_period": "FY"},
    # TXN FY2024 (period ending 2024-12-31)
    {"ticker": "TXN", "cik": "0000097476", "concept": "NetIncomeLoss", "value": 4_799_000_000, "unit": "USD", "period_end": "2024-12-31", "period_start": "2024-01-01", "form_type": "10-K", "accession": "0000097476-25-000008", "filed": "2025-02-05", "fiscal_year": 2024, "fiscal_period": "FY"},
    {"ticker": "TXN", "cik": "0000097476", "concept": "GrossProfit", "value": 9_100_000_000, "unit": "USD", "period_end": "2024-12-31", "period_start": "2024-01-01", "form_type": "10-K", "accession": "0000097476-25-000008", "filed": "2025-02-05", "fiscal_year": 2024, "fiscal_period": "FY"},
    {"ticker": "TXN", "cik": "0000097476", "concept": "ResearchAndDevelopmentExpense", "value": 2_000_000_000, "unit": "USD", "period_end": "2024-12-31", "period_start": "2024-01-01", "form_type": "10-K", "accession": "0000097476-25-000008", "filed": "2025-02-05", "fiscal_year": 2024, "fiscal_period": "FY"},
    {"ticker": "TXN", "cik": "0000097476", "concept": "Assets", "value": 35_500_000_000, "unit": "USD", "period_end": "2024-12-31", "period_start": None, "form_type": "10-K", "accession": "0000097476-25-000008", "filed": "2025-02-05", "fiscal_year": 2024, "fiscal_period": "FY"},
    # INTC FY2024 (period ending 2024-12-28)
    {"ticker": "INTC", "cik": "0000050863", "concept": "NetIncomeLoss", "value": -18_756_000_000, "unit": "USD", "period_end": "2024-12-28", "period_start": "2023-12-31", "form_type": "10-K", "accession": "0000050863-25-000004", "filed": "2025-01-30", "fiscal_year": 2024, "fiscal_period": "FY"},
    {"ticker": "INTC", "cik": "0000050863", "concept": "GrossProfit", "value": 17_300_000_000, "unit": "USD", "period_end": "2024-12-28", "period_start": "2023-12-31", "form_type": "10-K", "accession": "0000050863-25-000004", "filed": "2025-01-30", "fiscal_year": 2024, "fiscal_period": "FY"},
    {"ticker": "INTC", "cik": "0000050863", "concept": "ResearchAndDevelopmentExpense", "value": 16_500_000_000, "unit": "USD", "period_end": "2024-12-28", "period_start": "2023-12-31", "form_type": "10-K", "accession": "0000050863-25-000004", "filed": "2025-01-30", "fiscal_year": 2024, "fiscal_period": "FY"},
    {"ticker": "INTC", "cik": "0000050863", "concept": "Assets", "value": 196_500_000_000, "unit": "USD", "period_end": "2024-12-28", "period_start": None, "form_type": "10-K", "accession": "0000050863-25-000004", "filed": "2025-01-30", "fiscal_year": 2024, "fiscal_period": "FY"},
    # MU FY2024 (period ending 2024-08-29)
    {"ticker": "MU", "cik": "0000723125", "concept": "NetIncomeLoss", "value": 778_000_000, "unit": "USD", "period_end": "2024-08-29", "period_start": "2023-09-01", "form_type": "10-K", "accession": "0000723125-24-000033", "filed": "2024-10-25", "fiscal_year": 2024, "fiscal_period": "FY"},
    {"ticker": "MU", "cik": "0000723125", "concept": "GrossProfit", "value": 5_600_000_000, "unit": "USD", "period_end": "2024-08-29", "period_start": "2023-09-01", "form_type": "10-K", "accession": "0000723125-24-000033", "filed": "2024-10-25", "fiscal_year": 2024, "fiscal_period": "FY"},
    {"ticker": "MU", "cik": "0000723125", "concept": "Assets", "value": 69_400_000_000, "unit": "USD", "period_end": "2024-08-29", "period_start": None, "form_type": "10-K", "accession": "0000723125-24-000033", "filed": "2024-10-25", "fiscal_year": 2024, "fiscal_period": "FY"},
    # AVGO FY2024 (period ending 2024-11-03)
    {"ticker": "AVGO", "cik": "0001730168", "concept": "NetIncomeLoss", "value": 5_895_000_000, "unit": "USD", "period_end": "2024-11-03", "period_start": "2023-10-30", "form_type": "10-K", "accession": "0001730168-24-000025", "filed": "2024-12-20", "fiscal_year": 2024, "fiscal_period": "FY"},
    {"ticker": "AVGO", "cik": "0001730168", "concept": "GrossProfit", "value": 32_500_000_000, "unit": "USD", "period_end": "2024-11-03", "period_start": "2023-10-30", "form_type": "10-K", "accession": "0001730168-24-000025", "filed": "2024-12-20", "fiscal_year": 2024, "fiscal_period": "FY"},
    {"ticker": "AVGO", "cik": "0001730168", "concept": "ResearchAndDevelopmentExpense", "value": 9_300_000_000, "unit": "USD", "period_end": "2024-11-03", "period_start": "2023-10-30", "form_type": "10-K", "accession": "0001730168-24-000025", "filed": "2024-12-20", "fiscal_year": 2024, "fiscal_period": "FY"},
    {"ticker": "AVGO", "cik": "0001730168", "concept": "Assets", "value": 165_600_000_000, "unit": "USD", "period_end": "2024-11-03", "period_start": None, "form_type": "10-K", "accession": "0001730168-24-000025", "filed": "2024-12-20", "fiscal_year": 2024, "fiscal_period": "FY"},
    # LRCX FY2024 (period ending 2024-06-30)
    {"ticker": "LRCX", "cik": "0000707549", "concept": "NetIncomeLoss", "value": 3_800_000_000, "unit": "USD", "period_end": "2024-06-30", "period_start": "2023-07-01", "form_type": "10-K", "accession": "0000707549-24-000035", "filed": "2024-08-15", "fiscal_year": 2024, "fiscal_period": "FY"},
    {"ticker": "LRCX", "cik": "0000707549", "concept": "GrossProfit", "value": 7_100_000_000, "unit": "USD", "period_end": "2024-06-30", "period_start": "2023-07-01", "form_type": "10-K", "accession": "0000707549-24-000035", "filed": "2024-08-15", "fiscal_year": 2024, "fiscal_period": "FY"},
    {"ticker": "LRCX", "cik": "0000707549", "concept": "ResearchAndDevelopmentExpense", "value": 1_900_000_000, "unit": "USD", "period_end": "2024-06-30", "period_start": "2023-07-01", "form_type": "10-K", "accession": "0000707549-24-000035", "filed": "2024-08-15", "fiscal_year": 2024, "fiscal_period": "FY"},
    # TER FY2024 (period ending 2024-12-31)
    {"ticker": "TER", "cik": "0000097210", "concept": "Revenues", "value": 2_800_000_000, "unit": "USD", "period_end": "2024-12-31", "period_start": "2024-01-01", "form_type": "10-K", "accession": "0000097210-25-000006", "filed": "2025-02-13", "fiscal_year": 2024, "fiscal_period": "FY"},
    {"ticker": "TER", "cik": "0000097210", "concept": "NetIncomeLoss", "value": 542_400_000, "unit": "USD", "period_end": "2024-12-31", "period_start": "2024-01-01", "form_type": "10-K", "accession": "0000097210-25-000006", "filed": "2025-02-13", "fiscal_year": 2024, "fiscal_period": "FY"},
    {"ticker": "TER", "cik": "0000097210", "concept": "GrossProfit", "value": 1_600_000_000, "unit": "USD", "period_end": "2024-12-31", "period_start": "2024-01-01", "form_type": "10-K", "accession": "0000097210-25-000006", "filed": "2025-02-13", "fiscal_year": 2024, "fiscal_period": "FY"},
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
    semis = [
        ("NVDA", "Nvidia Corporation", "Technology", "Semiconductors"),
        ("AMD", "Advanced Micro Devices", "Technology", "Semiconductors"),
        ("QCOM", "Qualcomm Incorporated", "Technology", "Semiconductors"),
        ("TXN", "Texas Instruments Incorporated", "Technology", "Semiconductors"),
        ("INTC", "Intel Corporation", "Technology", "Semiconductors"),
        ("MU", "Micron Technology Inc.", "Technology", "Semiconductors"),
        ("AVGO", "Broadcom Inc.", "Technology", "Semiconductors"),
        ("LRCX", "Lam Research Corporation", "Technology", "Semiconductor Equipment"),
        ("TER", "Teradyne Inc.", "Technology", "Semiconductor Equipment"),
    ]
    for ticker, name, sector, industry in semis:
        conn.execute("""
            INSERT OR REPLACE INTO ticker_embeddings (ticker, description, sector, industry)
            VALUES (?, ?, ?, ?)
        """, [ticker, name, sector, industry])

    count = conn.execute("SELECT COUNT(*) FROM xbrl_facts").fetchone()[0]
    conn.close()
    logger.info(f"Seed complete — {count} XBRL facts in {db_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed DuckDB with semiconductor XBRL data")
    parser.add_argument("--db-path", default="./data/rag.duckdb", help="Path to DuckDB file")
    args = parser.parse_args()
    seed(db_path=args.db_path)
