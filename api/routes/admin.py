"""Admin endpoints for data refresh and maintenance."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Literal

import duckdb
import requests
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel

from api.middleware.auth import get_admin_api_key
from api.config import Config

router = APIRouter()

EDGAR_USER_AGENT = os.getenv("EDGAR_USER_AGENT", "RAGWorkbench/1.0 (research@example.com)")
SEC_RATE_LIMIT_DELAY = 0.15

TICKER_TO_CIK = {
    "ADI": "0000006607", "AMD": "0000002488", "AVGO": "0001730168",
    "INTC": "0000050863", "MU": "0000723125", "NVDA": "0001045810",
    "QCOM": "0000804328", "TXN": "0000097476", "TSM": "0001046179",
    "MRVL": "0000721938", "NXPI": "0001109168", "MCHP": "0000831368",
    "MPWR": "0001267902", "SWKS": "0000412700", "QRVO": "0001603872",
    "ON": "0001666635", "AMAT": "0000069515", "LRCX": "0000707549",
    "KLAC": "0000799167", "TER": "0000097210", "ENTG": "0001170010",
    "ONTO": "0001055605", "FORM": "0001003485", "PLAB": "0000867840",
    "COHU": "0000021539", "KLIC": "0000031277", "ICHR": "0001680247",
    "VECO": "0000707478", "AEHR": "0001049521", "ACLS": "0000897077",
    "AMKR": "0001057887",
}

KEY_CONCEPTS = [
    "us-gaap/Revenues", "us-gaap/NetIncomeLoss", "us-gaap/Assets",
    "us-gaap/Liabilities", "us-gaap/StockholdersEquity",
    "us-gaap/OperatingIncomeLoss", "us-gaap/GrossProfit",
    "us-gaap/CostOfGoodsAndServicesSold", "us-gaap/ResearchAndDevelopmentExpense",
    "us-gaap/CashAndCashEquivalentsAtCarryingValue", "us-gaap/LongTermDebt",
    "us-gaap/EarningsPerShareBasic", "us-gaap/CommonStockSharesOutstanding",
    "us-gaap/OperatingCashFlow",
    "us-gaap/NetCashProvidedByUsedInOperatingActivities",
    "us-gaap/PaymentsToAcquirePropertyPlantAndEquipment",
]


class RefreshResponse(BaseModel):
    status: str
    tickers_processed: int
    facts_loaded: int
    timestamp: str
    skipped_tickers: list[str] = []


def _fetch_company_facts(cik: str) -> dict | None:
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


def _extract_facts(company_data: dict, ticker: str, cik: str) -> list[dict]:
    facts_list = []
    us_gaap = company_data.get("facts", {}).get("us-gaap", {})
    for full_concept in KEY_CONCEPTS:
        concept_name = full_concept.split("/")[-1]
        concept_data = us_gaap.get(concept_name, {})
        units = concept_data.get("units", {})
        unit_data = units.get("USD", units.get("USD/shares", units.get("shares", [])))
        if not unit_data:
            continue
        for entry in unit_data:
            if entry.get("form", "") not in ("10-K", "10-K/A"):
                continue
            facts_list.append({
                "ticker": ticker, "cik": cik, "concept": concept_name,
                "value": entry.get("val"),
                "unit": "USD" if "USD" in units else "shares",
                "period_end": entry.get("end"), "period_start": entry.get("start"),
                "form_type": entry.get("form", ""),
                "accession": entry.get("accn", ""), "filed": entry.get("filed", ""),
                "fiscal_year": entry.get("fy"), "fiscal_period": entry.get("fp"),
            })
    return facts_list


def _ensure_tables(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("CREATE SEQUENCE IF NOT EXISTS xbrl_facts_seq START 1")
    conn.execute("CREATE SEQUENCE IF NOT EXISTS filing_chunks_seq START 1")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS xbrl_facts (
            id INTEGER PRIMARY KEY DEFAULT(nextval('xbrl_facts_seq')),
            ticker VARCHAR NOT NULL, cik VARCHAR NOT NULL,
            concept VARCHAR NOT NULL, value DOUBLE, unit VARCHAR,
            period_end VARCHAR, period_start VARCHAR, form_type VARCHAR,
            accession VARCHAR, filed VARCHAR, fiscal_year INTEGER,
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ticker_embeddings (
            ticker VARCHAR PRIMARY KEY, description TEXT,
            sector VARCHAR, industry VARCHAR
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS edgar_embeddings (
            ticker            VARCHAR NOT NULL,
            accession         VARCHAR NOT NULL,
            text              TEXT NOT NULL,
            embedding         FLOAT[],
            updated_at        VARCHAR,
            cik               VARCHAR,
            section_id        VARCHAR,
            form_type         VARCHAR DEFAULT '10-K',
            period_of_report  VARCHAR,
            chunk_index       INTEGER,
            section_type      VARCHAR DEFAULT 'narrative',
            content_type      VARCHAR DEFAULT 'narrative'
        )
    """)
    conn.execute("""
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
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS polygon_bars (
            ticker   VARCHAR NOT NULL,
            ts       TIMESTAMP NOT NULL,
            close    DOUBLE,
            volume   DOUBLE,
            timespan VARCHAR
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_polygon_bars_ticker_ts
        ON polygon_bars (ticker, ts)
    """)


@router.post("/refresh-data", response_model=RefreshResponse)
def refresh_data(
    force: bool = False,
    _: str = Depends(get_admin_api_key),
):
    """Load XBRL facts from SEC EDGAR. Skips tickers already in DB unless force=true."""
    db_path = Config.DB_PATH
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)

    conn = duckdb.connect(db_path)
    _ensure_tables(conn)

    # Find which tickers already have data so we can skip them
    try:
        existing = {
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT ticker FROM xbrl_facts"
            ).fetchall()
        }
    except Exception:
        existing = set()

    new_tickers = {t: c for t, c in TICKER_TO_CIK.items() if force or t not in existing}

    if not new_tickers:
        conn.close()
        logger.info("All tickers already loaded — nothing to do (use force=true to re-fetch)")
        return RefreshResponse(status="ok", tickers_processed=0, facts_loaded=0, timestamp=datetime.now(timezone.utc).isoformat())

    logger.info(f"Refreshing {len(new_tickers)} tickers (force={force}, existing={len(existing)})")

    total_facts = 0
    tickers_processed = 0
    skipped: list[str] = []

    try:
        for ticker, cik in new_tickers.items():
            data = _fetch_company_facts(cik)
            if data is None:
                skipped.append(ticker)
                continue

            facts = _extract_facts(data, ticker, cik)
            if facts:
                conn.execute("DELETE FROM xbrl_facts WHERE ticker = ?", [ticker])
                batch = [
                    (f["ticker"], f["cik"], f["concept"], f["value"],
                     f["unit"], f["period_end"], f["period_start"],
                     f["form_type"], f["accession"], f["filed"],
                     f["fiscal_year"], f["fiscal_period"])
                    for f in facts
                ]
                conn.executemany("""
                    INSERT INTO xbrl_facts
                        (ticker, cik, concept, value, unit, period_end, period_start,
                         form_type, accession, filed, fiscal_year, fiscal_period)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, batch)
                total_facts += len(batch)

            company_name = data.get("entityName", ticker)
            conn.execute("""
                INSERT INTO ticker_embeddings (ticker, description, sector, industry)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (ticker) DO UPDATE SET description = excluded.description
            """, [ticker, company_name, "", ""])
            tickers_processed += 1
    except Exception as e:
        logger.error(f"Admin data refresh failed: {e}")
        raise HTTPException(status_code=500, detail=f"Data refresh failed: {e}") from e
    finally:
        conn.close()

class EmbedResponse(BaseModel):
    status: str
    chunks_stored: int
    timestamp: str


@router.post("/embed-data", response_model=EmbedResponse)
def embed_data(
    _: str = Depends(get_admin_api_key),
):
    """Chunk + embed 10-K filings for all tickers into edgar_embeddings."""
    from scripts.embed_edgar import run_embed_edgar_etl

    tickers = list(TICKER_TO_CIK.keys())
    logger.info(f"Starting embed-edgar job for {len(tickers)} tickers")
    try:
        n = run_embed_edgar_etl(tickers)
        return EmbedResponse(
            status="ok",
            chunks_stored=n,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        logger.error(f"Embed job failed: {e}")
        raise HTTPException(status_code=500, detail=f"Embed job failed: {e}") from e
