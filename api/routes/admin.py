"""Admin endpoints for data refresh and maintenance."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

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


@router.post("/refresh-data", response_model=RefreshResponse)
def refresh_data(_: str = Depends(get_admin_api_key)):
    """Refresh XBRL facts from SEC EDGAR into the local DuckDB database."""
    db_path = Config.DB_PATH
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)

    logger.info("Admin data refresh started")
    conn = duckdb.connect(db_path)
    _ensure_tables(conn)

    total_facts = 0
    tickers_processed = 0

    try:
        for ticker, cik in TICKER_TO_CIK.items():
            data = _fetch_company_facts(cik)
            if data is None:
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
                INSERT OR REPLACE INTO ticker_embeddings (ticker, description, sector, industry)
                VALUES (?, ?, ?, ?)
            """, [ticker, company_name, "", ""])
            tickers_processed += 1
    except Exception as e:
        logger.error(f"Admin data refresh failed: {e}")
        raise HTTPException(status_code=500, detail=f"Data refresh failed: {e}") from e
    finally:
        conn.close()

    timestamp = datetime.now(timezone.utc).isoformat()
    logger.info(f"Admin data refresh complete — {total_facts} facts from {tickers_processed} tickers")
    return RefreshResponse(
        status="ok",
        tickers_processed=tickers_processed,
        facts_loaded=total_facts,
        timestamp=timestamp,
    )
