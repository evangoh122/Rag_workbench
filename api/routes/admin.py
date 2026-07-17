"""Admin endpoints for data refresh and maintenance."""
from __future__ import annotations

import os
import time
import traceback
from datetime import datetime, timezone
from typing import Literal

import duckdb
import requests
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel

from api.middleware.auth import get_admin_api_key
from api.config import Config, TICKER_TO_CIK
from scripts.embed_edgar import run_embed_edgar_etl
from scripts.embed_tickers import run_embed_tickers_etl

router = APIRouter()

EDGAR_USER_AGENT = os.getenv("EDGAR_USER_AGENT", "RAGWorkbench/1.0 (research@example.com)")
SEC_RATE_LIMIT_DELAY = 0.15


KEY_CONCEPTS = [
    # Revenue: legacy "Revenues" plus the modern ASC 606 tags that most filers
    # switched to (~2018-2019). Without these, post-2018 revenue is missing for
    # MCHP/ADI/MRVL/AMAT/ON/STM (and stale for AMD/TXN/INTC), so numeric revenue
    # queries abstain at the verification gate.
    "us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax",
    "us-gaap/RevenueFromContractWithCustomerIncludingAssessedTax",
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
    """Fetch one company's raw SEC companyfacts payload by zero-padded CIK."""
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
    """Extract supported annual XBRL facts while preserving SEC provenance."""
    facts_list = []
    us_gaap = company_data.get("facts", {}).get("us-gaap", {})
    for full_concept in KEY_CONCEPTS:
        concept_name = full_concept.split("/")[-1]
        concept_data = us_gaap.get(concept_name, {})
        units = concept_data.get("units", {})
        unit_key = next((key for key in ("USD", "USD/shares", "shares") if units.get(key)), "")
        unit_data = units.get(unit_key, [])
        if not unit_data:
            continue
        for entry in unit_data:
            # 20-F / 20-F/A are the annual reports of foreign private issuers
            # (e.g. STM) — the equivalent of a 10-K for XBRL purposes.
            if entry.get("form", "") not in ("10-K", "10-K/A", "20-F", "20-F/A"):
                continue
            facts_list.append({
                "ticker": ticker, "cik": cik, "concept": concept_name,
                "value": entry.get("val"),
                "unit": unit_key,
                "period_end": entry.get("end"), "period_start": entry.get("start"),
                "form_type": entry.get("form", ""),
                "accession": entry.get("accn", ""), "filed": entry.get("filed", ""),
                "fiscal_year": entry.get("fy"), "fiscal_period": entry.get("fp"),
                "frame": entry.get("frame", ""),
            })
    return facts_list


def _ensure_tables(conn: duckdb.DuckDBPyConnection) -> None:
    """Create or migrate the admin ingestion tables and supporting indexes."""
    conn.execute("CREATE SEQUENCE IF NOT EXISTS xbrl_facts_seq START 1")
    conn.execute("CREATE SEQUENCE IF NOT EXISTS filing_chunks_seq START 1")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS xbrl_facts (
            id INTEGER PRIMARY KEY DEFAULT(nextval('xbrl_facts_seq')),
            ticker VARCHAR NOT NULL, cik VARCHAR NOT NULL,
            concept VARCHAR NOT NULL, value DOUBLE, unit VARCHAR,
            period_end VARCHAR, period_start VARCHAR, form_type VARCHAR,
            accession VARCHAR, filed VARCHAR, fiscal_year INTEGER,
            fiscal_period VARCHAR,
            frame VARCHAR
        )
    """)
    conn.execute("ALTER TABLE xbrl_facts ADD COLUMN IF NOT EXISTS frame VARCHAR")
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
            ticker VARCHAR, description TEXT,
            sector VARCHAR, industry VARCHAR
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_te_ticker
        ON ticker_embeddings (ticker)
    """)
    for col, col_type in [
        ("text",       "TEXT"),
        ("embedding",  "FLOAT[]"),
        ("updated_at", "VARCHAR"),
    ]:
        try:
            conn.execute(f"ALTER TABLE ticker_embeddings ADD COLUMN IF NOT EXISTS {col} {col_type}")
        except Exception:
            pass
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
                     f["fiscal_year"], f["fiscal_period"], f["frame"])
                    for f in facts
                ]
                conn.executemany("""
                    INSERT INTO xbrl_facts
                        (ticker, cik, concept, value, unit, period_end, period_start,
                         form_type, accession, filed, fiscal_year, fiscal_period, frame)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    timestamp = datetime.now(timezone.utc).isoformat()
    status: Literal["ok", "partial"] = "partial" if skipped else "ok"
    logger.info(f"Refresh complete — {total_facts} facts, {tickers_processed} tickers, {len(skipped)} skipped")
    return RefreshResponse(
        status=status,
        tickers_processed=tickers_processed,
        facts_loaded=total_facts,
        skipped_tickers=skipped,
        timestamp=timestamp,
    )


class SnapshotResponse(BaseModel):
    status: str
    uploaded: bool
    timestamp: str


@router.post("/snapshot", response_model=SnapshotResponse)
def snapshot_runtime_db(
    _: str = Depends(get_admin_api_key),
):
    """Persist the runtime/review DB (audit log, HITL decisions, calibration,
    eval_runs/eval_results) to the private HF dataset as Parquet.

    The Space has no persistent volume, so this is how that data survives restarts.
    Triggered daily by the snapshot CI/CD cron (.github/workflows/snapshot.yml) and
    available for manual/on-demand backups. force=True bypasses the on-Space guard
    since the call is an explicit admin request."""
    from api.services.runtime_snapshot import snapshot_review_db

    uploaded = snapshot_review_db(reason="cron", force=True)
    return SnapshotResponse(
        status="ok" if uploaded else "skipped",
        uploaded=uploaded,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


class EmbedResponse(BaseModel):
    status: str
    chunks_stored: int
    tickers_processed: int
    ticker_embeddings_stored: int = 0
    error: str = ""
    timestamp: str


@router.post("/embed-data", response_model=EmbedResponse)
def embed_data(
    _: str = Depends(get_admin_api_key),
):
    """Rebuild filing chunks and company-description embeddings (synchronous)."""
    tickers = list(TICKER_TO_CIK.keys())
    logger.info(f"Starting embed-edgar job for {len(tickers)} tickers")
    try:
        n = run_embed_edgar_etl(tickers)
        ticker_count = run_embed_tickers_etl()
        return EmbedResponse(
            status="ok",
            chunks_stored=n,
            tickers_processed=len(tickers),
            ticker_embeddings_stored=ticker_count,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Embed job failed:\n{tb}")
        return EmbedResponse(
            status="error",
            chunks_stored=0,
            tickers_processed=0,
            error=str(e)[:500],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
