"""
extract_xbrl_facts.py — Extract XBRL facts from SEC EDGAR companyfacts API.

Fetches structured financial data (revenue, net income, assets, etc.) for all
semiconductor tickers and stores in the `edgar_facts` DuckDB table.

This replaces the broken async-based get_latest_10k_facts() with a synchronous
HTTP approach that works reliably.

Usage:
    python -m scripts.extract_xbrl_facts
    python -m scripts.extract_xbrl_facts --tickers NVDA,AMD,QCOM
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

import duckdb
import requests
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.config import Config

DB_PATH = Config.DB_PATH
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

_TICKER_CIK: dict[str, str] = {
    "ADI": "0000006281", "AIP": "0001861842", "ALAB": "0001903832",
    "ALGM": "0000930155", "ALMU": "0001841107", "AMD": "0000002488",
    "AOSL": "0001399751", "ARM": "0001973239", "ASX": "0001740411",
    "AVGO": "0001730168", "CEVA": "0001173489", "CRDO": "0001807794",
    "CRUS": "0000866787", "DIOD": "0000029002", "GFS": "0001709048",
    "GSIT": "0000930184", "HIMX": "0001351115", "IMOS": "0001222442",
    "INDI": "0001841925", "INTC": "0000050863", "LSCC": "0000057760",
    "MCHP": "0000827054", "MPWR": "0001280452", "MRAM": "0001439606",
    "MRVL": "0001835632", "MTSI": "0001494877", "MU": "0000723125",
    "MX": "0001509172", "MXL": "0001416800", "NVDA": "0001045810",
    "NVEC": "0000846633", "NVTS": "0001854097", "NXPI": "0001413447",
    "PI": "0001414470", "POET": "0001625078", "POWI": "0001064728",
    "PXLW": "0001021432", "QCOM": "0000804328", "QRVO": "0001604778",
    "QUIK": "0000882508", "RMBS": "0000917273", "SIMO": "0001321045",
    "SITM": "0001777265", "SKYT": "0001837240", "SLAB": "0001050776",
    "SMTC": "0000088462", "STM": "0000932787", "SWKS": "0000004127",
    "SYNA": "0000817720", "TSEM": "0000894439", "TSM": "0001046179",
    "TXN": "0000097476", "UMC": "0001111563", "VLN": "0001865955",
    "VSH": "0000103761", "WKEY": "0001678880", "WOLF": "0000895419",
    "ACLS": "0000897077", "ACMR": "0001680062", "AEHR": "0001040470",
    "AMAT": "0000069515", "AMBA": "0001280263", "AMKR": "0001047127",
    "ASML": "0000937966", "ASYS": "0000720500", "ATOM": "0001420520",
    "AXTI": "0001051627", "CAMT": "0001109138", "COHU": "0000021535",
    "ENTG": "0001101302", "FORM": "0001039399", "ICHR": "0001652535",
    "INTT": "0001036262", "IPGP": "0001111928", "KLAC": "0000319201",
    "KLIC": "0000056978", "LRCX": "0000707549", "NVMI": "0001109345",
    "ONTO": "0000704532", "PLAB": "0000810136", "TER": "0000097210",
    "TRT": "0000732026", "UCTT": "0001275014", "VECO": "0000103145",
}

DEMO_TICKERS: list[str] = list(_TICKER_CIK.keys())

_CONCEPTS = [
    ("us-gaap", "Revenues", "Revenues"),
    ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax", "Revenue"),
    ("us-gaap", "NetIncomeLoss", "Net Income"),
    ("us-gaap", "GrossProfit", "Gross Profit"),
    ("us-gaap", "OperatingIncomeLoss", "Operating Income"),
    ("us-gaap", "ResearchAndDevelopmentExpense", "R&D Expense"),
    ("us-gaap", "SellingGeneralAndAdministrativeExpense", "SG&A Expense"),
    ("us-gaap", "CostOfRevenue", "Cost of Revenue"),
    ("us-gaap", "CostOfGoodsAndServicesSold", "Cost of Goods Sold"),
    ("us-gaap", "IncomeTaxExpenseBenefit", "Income Tax Expense"),
    ("us-gaap", "InterestExpense", "Interest Expense"),
    ("us-gaap", "InterestIncome", "Interest Income"),
    ("us-gaap", "Assets", "Total Assets"),
    ("us-gaap", "Liabilities", "Total Liabilities"),
    ("us-gaap", "StockholdersEquity", "Stockholders Equity"),
    ("us-gaap", "CurrentAssets", "Current Assets"),
    ("us-gaap", "CurrentLiabilities", "Current Liabilities"),
    ("us-gaap", "LongTermDebt", "Long-term Debt"),
    ("us-gaap", "CashAndCashEquivalentsAtCarryingValue", "Cash"),
    ("us-gaap", "CashCashEquivalentsAndShortTermInvestments", "Cash & Equivalents"),
    ("us-gaap", "InventoryNet", "Inventory"),
    ("us-gaap", "PropertyPlantAndEquipmentNet", "PP&E Net"),
    ("us-gaap", "Goodwill", "Goodwill"),
    ("us-gaap", "NetCashProvidedByUsedInOperatingActivities", "Operating Cash Flow"),
    ("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment", "Capital Expenditures"),
    ("us-gaap", "EarningsPerShareBasic", "EPS Basic"),
    ("us-gaap", "EarningsPerShareDiluted", "EPS Diluted"),
    ("us-gaap", "CommonStockSharesOutstanding", "Shares Outstanding"),
]


def _rate_limited_get(url: str, max_retries: int = 3) -> dict:
    headers = {
        "User-Agent": os.getenv("EDGAR_USER_AGENT", "RAG-Workbench research@example.com"),
        "Accept": "application/json",
    }
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 60))
                logger.warning("Rate limited — waiting {}s", wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError:
            if resp.status_code == 404:
                return {}
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
        except requests.exceptions.RequestException:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
    return {}


def extract_facts_for_ticker(ticker: str, cik: str) -> list[dict[str, Any]]:
    url = COMPANYFACTS_URL.format(cik=cik)
    data = _rate_limited_get(url)

    if not data or "facts" not in data:
        logger.warning("No XBRL data for {} (CIK {})", ticker, cik)
        return []

    us_gaap = data.get("facts", {}).get("us-gaap", {})
    facts = []

    for taxonomy, concept, label in _CONCEPTS:
        concept_data = us_gaap.get(concept)
        if not concept_data:
            continue

        units = concept_data.get("units", {})
        for unit_key in ["USD", "USD/shares", "shares"]:
            if unit_key not in units:
                continue
            entries = units[unit_key]
            annual = [e for e in entries if e.get("form") == "10-K" and e.get("fp") == "FY"]
            if not annual:
                annual = [e for e in entries if e.get("form") == "20-F"]
            if not annual:
                continue

            annual.sort(key=lambda x: x.get("end", ""), reverse=True)
            seen_periods = set()
            for entry in annual[:10]:
                period_end = entry.get("end", "")
                if not period_end or period_end in seen_periods:
                    continue
                seen_periods.add(period_end)

                facts.append({
                    "ticker": ticker,
                    "cik": cik,
                    "taxonomy": taxonomy,
                    "concept": concept,
                    "label": label,
                    "unit": unit_key,
                    "value": entry.get("val"),
                    "period_start": entry.get("start", ""),
                    "period_end": period_end,
                    "form_type": entry.get("form", "10-K"),
                    "filed_date": entry.get("filed", ""),
                })

                if len(seen_periods) >= 3:
                    break
            break

    return facts


def ensure_edgar_facts_table(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS edgar_facts (
            ticker       VARCHAR NOT NULL,
            cik          VARCHAR NOT NULL,
            taxonomy     VARCHAR NOT NULL DEFAULT 'us-gaap',
            concept      VARCHAR NOT NULL,
            label        VARCHAR NOT NULL DEFAULT '',
            unit         VARCHAR NOT NULL DEFAULT 'USD',
            value        DOUBLE,
            period_start VARCHAR,
            period_end   VARCHAR NOT NULL,
            form_type    VARCHAR NOT NULL DEFAULT '10-K',
            filed_date   VARCHAR
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ef_ticker ON edgar_facts (ticker)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ef_concept ON edgar_facts (concept)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ef_period ON edgar_facts (period_end)")


def run_extraction(tickers: list[str] | None = None) -> int:
    if tickers is None:
        tickers = DEMO_TICKERS

    total = 0
    with duckdb.connect(DB_PATH) as conn:
        ensure_edgar_facts_table(conn)

        for ticker in tickers:
            cik = _TICKER_CIK.get(ticker.upper())
            if not cik:
                logger.warning("No CIK for {} — skipping", ticker)
                continue

            logger.info("Extracting XBRL facts for {} (CIK {})...", ticker, cik)
            try:
                facts = extract_facts_for_ticker(ticker, cik)
            except Exception as e:
                logger.error("Failed to extract {}: {}", ticker, e)
                continue

            if not facts:
                continue

            conn.execute("DELETE FROM edgar_facts WHERE ticker = ?", [ticker])

            for f in facts:
                conn.execute("""
                    INSERT INTO edgar_facts
                        (ticker, cik, taxonomy, concept, label, unit, value,
                         period_start, period_end, form_type, filed_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    f["ticker"], f["cik"], f["taxonomy"], f["concept"],
                    f["label"], f["unit"], f["value"],
                    f["period_start"], f["period_end"],
                    f["form_type"], f["filed_date"],
                ])

            total += len(facts)
            logger.info("  {} — {} facts extracted", ticker, len(facts))

            time.sleep(0.15)

        conn.commit()

    logger.info("XBRL extraction complete — {} total facts for {} tickers", total, len(tickers))
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract XBRL facts from SEC EDGAR")
    parser.add_argument("--tickers", help="Comma-separated tickers (default: all)")
    args = parser.parse_args()

    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",")]
    else:
        tickers = None

    run_extraction(tickers)
