"""
backfill_xbrl_coverage.py — Re-fetch XBRL facts for the coverage list.

Forces a refresh of xbrl_facts for the user-facing coverage tickers using the
(now corrected) admin ingestion path: fixed CIKs (AMAT/ON), modern ASC 606
revenue concepts, and 20-F support (STM). Run locally against data/rag.duckdb,
then rebuild + upload the dataset.

Usage:  PYTHONPATH=. python -m scripts.backfill_xbrl_coverage
"""
from __future__ import annotations

import duckdb
from loguru import logger

from api.config import Config
from api.routes.admin import (
    TICKER_TO_CIK, _ensure_tables, _fetch_company_facts, _extract_facts,
)

# 15 coverage tickers that have XBRL filings (SPCX is prospectus-only → excluded).
COVERAGE = [
    "MU", "NVDA", "AMD", "INTC", "AVGO", "QCOM", "TXN",
    "ADI", "MRVL", "ON", "MCHP", "STM", "AMAT", "LRCX", "KLAC",
]


def main() -> None:
    conn = duckdb.connect(Config.DB_PATH)
    _ensure_tables(conn)

    total = 0
    print(f"{'ticker':6} {'facts':6} {'latest_revenue':>18}")
    for t in COVERAGE:
        cik = TICKER_TO_CIK.get(t)
        if not cik:
            logger.warning("No CIK for {} — skipping", t)
            continue
        data = _fetch_company_facts(cik)
        if not data:
            print(f"{t:6} {'FETCH-FAIL':>6}")
            continue
        facts = _extract_facts(data, t, cik)
        if not facts:
            print(f"{t:6} {0:6}")
            continue
        conn.execute("DELETE FROM xbrl_facts WHERE ticker = ?", [t])
        conn.executemany(
            """
            INSERT INTO xbrl_facts
                (ticker, cik, concept, value, unit, period_end, period_start,
                 form_type, accession, filed, fiscal_year, fiscal_period, frame)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (f["ticker"], f["cik"], f["concept"], f["value"], f["unit"],
                 f["period_end"], f["period_start"], f["form_type"],
                 f["accession"], f["filed"], f["fiscal_year"], f["fiscal_period"],
                 f["frame"])
                for f in facts
            ],
        )
        # Latest revenue across legacy + ASC 606 concepts for a sanity readout.
        rev = [f for f in facts if "Revenue" in f["concept"] and f.get("value")]
        latest = max(rev, key=lambda f: f.get("period_end") or "", default=None)
        rev_str = f'{latest["value"]/1e9:.2f}B ({latest["period_end"]})' if latest else "—"
        print(f"{t:6} {len(facts):6} {rev_str:>18}")
        total += len(facts)

    conn.commit()
    conn.close()
    print(f"\nBackfill complete — {total} facts across {len(COVERAGE)} tickers.")


if __name__ == "__main__":
    main()
