"""Admin endpoints for data refresh and maintenance."""
from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
SEC_RATE_LIMIT_DELAY = 0.15   # 6.7 req/s — within SEC's 10 req/s limit
_MAX_RESPONSE_BYTES = 20 * 1024 * 1024  # 20 MB guard against unexpectedly large payloads
_FETCH_WORKERS = 8

TICKER_TO_CIK: dict[str, str] = {
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

# One concurrent refresh at a time — two simultaneous POSTs would interleave
# DELETE/INSERT on the same DuckDB file and corrupt data.
_refresh_lock = threading.Lock()

# Serialises the per-request rate-limit sleep so parallel workers don't
# burst past SEC's 10 req/s limit.
_rate_lock = threading.Lock()

# Tables are created once per process lifetime, not on every refresh call.
_tables_initialized = False
_tables_init_lock = threading.Lock()


class RefreshResponse(BaseModel):
    status: Literal["ok", "partial"]
    tickers_processed: int
    facts_loaded: int
    skipped_tickers: list[str]
    timestamp: str


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------

def _create_tables(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("CREATE SEQUENCE IF NOT EXISTS xbrl_facts_seq START 1")
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
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_xbrl_ticker_concept ON xbrl_facts (ticker, concept)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_xbrl_ticker_period ON xbrl_facts (ticker, period_end)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_xbrl_accession ON xbrl_facts (accession)"
    )
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ticker_embeddings (
            ticker VARCHAR PRIMARY KEY,
            description TEXT,
            sector VARCHAR,
            industry VARCHAR
        )
    """)


def ensure_tables_once(db_path: str) -> None:
    """Initialize DB schema exactly once per process — not on every refresh call."""
    global _tables_initialized
    if _tables_initialized:
        return
    with _tables_init_lock:
        if _tables_initialized:
            return
        conn = duckdb.connect(db_path)
        try:
            _create_tables(conn)
        finally:
            conn.close()
        _tables_initialized = True


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------

def _fetch_company_facts(cik: str) -> dict | None:
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    headers = {"User-Agent": EDGAR_USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code != 200:
            logger.warning(f"SEC API returned {resp.status_code} for CIK {cik}")
            return None
        if len(resp.content) > _MAX_RESPONSE_BYTES:
            logger.error(
                f"Response for CIK {cik} is {len(resp.content):,} bytes "
                f"(limit {_MAX_RESPONSE_BYTES:,}) — skipping"
            )
            return None
        return resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch companyfacts for CIK {cik}: {e}")
        return None


def _fetch_with_rate_limit(args: tuple[str, str]) -> tuple[str, dict | None]:
    """Acquire the rate-limit gate (0.15 s spacing), then fetch. Returns (ticker, data)."""
    ticker, cik = args
    with _rate_lock:
        time.sleep(SEC_RATE_LIMIT_DELAY)
    return ticker, _fetch_company_facts(cik)


def _extract_facts(company_data: dict, ticker: str, cik: str) -> list[tuple]:
    facts = []
    us_gaap = company_data.get("facts", {}).get("us-gaap", {})
    for full_concept in KEY_CONCEPTS:
        concept_name = full_concept.split("/")[-1]
        concept_data = us_gaap.get(concept_name, {})
        units = concept_data.get("units", {})
        unit_data = units.get("USD", units.get("USD/shares", units.get("shares", [])))
        for entry in unit_data:
            if entry.get("form", "") not in ("10-K", "10-K/A"):
                continue
            facts.append((
                ticker, cik, concept_name,
                entry.get("val"),
                "USD" if "USD" in units else "shares",
                entry.get("end"), entry.get("start"),
                entry.get("form", ""),
                entry.get("accn", ""), entry.get("filed", ""),
                entry.get("fy"), entry.get("fp"),
            ))
    return facts


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/refresh-data", response_model=RefreshResponse)
def refresh_data(_: str = Depends(get_admin_api_key)):
    """Refresh XBRL facts from SEC EDGAR. Returns 409 if a refresh is already running."""
    if not _refresh_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Refresh already in progress")

    try:
        db_path = Config.DB_PATH
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        ensure_tables_once(db_path)

        logger.info("Admin data refresh started")

        # Phase 1: parallel fetch — rate-limit gate is serialised, HTTP in parallel
        fetch_results: dict[str, dict | None] = {}
        with ThreadPoolExecutor(max_workers=_FETCH_WORKERS) as pool:
            futures = {
                pool.submit(_fetch_with_rate_limit, (ticker, cik)): ticker
                for ticker, cik in TICKER_TO_CIK.items()
            }
            for future in as_completed(futures):
                ticker_key, data = future.result()
                fetch_results[ticker_key] = data

        # Phase 2: DB writes — single-threaded, each ticker in its own transaction
        conn = duckdb.connect(db_path)
        total_facts = 0
        tickers_processed = 0
        skipped: list[str] = []

        try:
            for ticker, cik in TICKER_TO_CIK.items():
                data = fetch_results.get(ticker)
                if data is None:
                    skipped.append(ticker)
                    continue

                facts = _extract_facts(data, ticker, cik)
                company_name = data.get("entityName", ticker)
                del data  # release companyfacts JSON memory before next iteration

                conn.execute("BEGIN")
                try:
                    if facts:
                        conn.execute("DELETE FROM xbrl_facts WHERE ticker = ?", [ticker])
                        conn.executemany("""
                            INSERT INTO xbrl_facts
                                (ticker, cik, concept, value, unit, period_end, period_start,
                                 form_type, accession, filed, fiscal_year, fiscal_period)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, facts)
                        total_facts += len(facts)

                    conn.execute("""
                        INSERT INTO ticker_embeddings (ticker, description, sector, industry)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT (ticker) DO UPDATE SET description = excluded.description
                    """, [ticker, company_name, "", ""])
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise

                tickers_processed += 1
        except Exception as e:
            # detail may include DB path — acceptable for an admin-only endpoint
            logger.error(f"Admin data refresh failed mid-loop: {e}")
            raise HTTPException(status_code=500, detail=f"Data refresh failed: {e}") from e
        finally:
            conn.close()

    finally:
        _refresh_lock.release()

    timestamp = datetime.now(timezone.utc).isoformat()
    status: Literal["ok", "partial"] = "partial" if skipped else "ok"
    logger.info(
        f"Admin data refresh complete — {total_facts} facts from "
        f"{tickers_processed} tickers, {len(skipped)} skipped, status={status}"
    )
    return RefreshResponse(
        status=status,
        tickers_processed=tickers_processed,
        facts_loaded=total_facts,
        skipped_tickers=skipped,
        timestamp=timestamp,
    )
