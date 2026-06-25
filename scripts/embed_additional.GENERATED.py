#!/usr/bin/env python3
"""Embed additional recent annual (10-K / 20-F) and 10-Q filings into edgar_embeddings."""

import sys
import os
import gc
import argparse
from pathlib import Path

# ── environment setup (before other imports) ──────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

os.environ["EMBEDDING_PROVIDER"] = "sentence-transformers"
os.environ["ST_EMBEDDING_MODEL"] = "Qwen/Qwen3-Embedding-0.6B"
os.environ["EMBEDDING_DIM"] = "1024"
os.environ.setdefault("EDGAR_USER_AGENT", "Evan Goh evangohsg@gmail.com")

import warnings
from bs4 import XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# ── imports ───────────────────────────────────────────────────────────────────
from datetime import datetime, timezone
from loguru import logger

from api.config import Config
from api.services.embeddings import get_embeddings
from api.services.structure_chunker import StructureChunker
from api.services._edgar_identity import ensure_edgar_identity
from scripts.embed_edgar import (
    parse_html_file,
    _extract_sections_with_labels,
    _ensure_schema,
    _TICKER_CIK,
)

from edgar import Company
import duckdb


# ── helpers ───────────────────────────────────────────────────────────────────

def _normalize_filings(fresult):
    """Return a list of Filing objects from the result of latest(n)."""
    if fresult is None:
        return []
    # If it is already iterable (Filings collection), convert to list
    try:
        return list(fresult)
    except TypeError:
        return [fresult]


def _filing_path(ticker: str, form_type: str, accession: str) -> Path:
    acc_clean = accession.replace("-", "")
    return (
        ROOT / "data" / "edgar_downloads" / ticker.upper() / form_type
        / acc_clean / "primary-document.html"
    )


def _period_from_accession(accession: str) -> str:
    yy = accession.split("-")[1]
    if int(yy) < 50:
        return f"20{yy}-12-31"
    return f"19{yy}-12-31"


def _is_present(conn, ticker: str, accession: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM edgar_embeddings WHERE ticker=? AND accession=? LIMIT 1",
        [ticker.upper(), accession],
    ).fetchone()
    return row is not None


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Embed additional recent filings into edgar_embeddings."
    )
    parser.add_argument(
        "--forms",
        choices=["annual", "10-Q"],
        default="annual",
        help='Which forms to fetch: "annual" (10-K + 20-F, latest 2) or "10-Q" (latest 1).',
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned fetch/skip per ticker; write nothing to DB.",
    )
    parser.add_argument(
        "--tickers",
        type=str,
        default=None,
        help="Comma-separated ticker list. Default: all tickers already in edgar_embeddings.",
    )
    parser.add_argument(
        "--log",
        type=str,
        default=None,
        help="Optional loguru file sink path.",
    )
    args = parser.parse_args()

    if args.log:
        logger.add(args.log, rotation="10 MB", level="DEBUG")

    ensure_edgar_identity()

    model = get_embeddings()
    if model is None:
        logger.error("Embedding model unavailable; cannot proceed.")
        sys.exit(1)

    chunker = StructureChunker(
        max_chunk_size=1500,
        min_chunk_size=200,
        similarity_threshold=0.15,
    )

    # Determine tickers
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        con_ro = duckdb.connect(Config.DB_PATH, read_only=True)
        try:
            rows = con_ro.execute(
                "SELECT DISTINCT ticker FROM edgar_embeddings"
            ).fetchall()
        finally:
            con_ro.close()
        tickers = [r[0] for r in rows]

    if not tickers:
        logger.warning("No tickers found to process.")
        return

    # Determine which forms to query
    if args.forms == "annual":
        form_queries = [("10-K", 2), ("20-F", 2)]
    else:
        form_queries = [("10-Q", 1)]

    # Summary tracking
    summary: dict[str, dict] = {}  # ticker -> {"added": int, "skipped": int}

    # Open a read connection for dedup checks
    dedup_conn = duckdb.connect(Config.DB_PATH, read_only=True)

    # Prepare write connection unless dry-run
    write_conn = None
    if not args.dry_run:
        write_conn = duckdb.connect(Config.DB_PATH)
        try:
            write_conn.execute("LOAD vss")
        except Exception:
            pass
        _ensure_schema(write_conn)

    try:
        for ticker in tickers:
            summary.setdefault(ticker, {"added": 0, "skipped": 0, "total_chunks": 0})
            logger.info(f"=== Processing {ticker} ===")

            for form_code, n_latest in form_queries:
                # Fetch filings from EDGAR
                try:
                    company = Company(ticker)
                    filings = company.get_filings(form=form_code)
                    latest = filings.latest(n_latest)
                except Exception as exc:
                    logger.error(f"[{ticker}] Failed to get {form_code} filings: {exc}")
                    continue

                filing_list = _normalize_filings(latest)

                if not filing_list:
                    logger.info(f"[{ticker}] No {form_code} filings found.")
                    continue

                for fl in filing_list:
                    try:
                        accession = fl.accession_number
                        form_type = fl.form
                    except Exception as exc:
                        logger.error(f"[{ticker}/{form_code}] Cannot read filing metadata: {exc}")
                        continue

                    logger.info(f"[{ticker}] {form_type} | {accession}")

                    # Dedup check
                    if _is_present(dedup_conn, ticker, accession):
                        logger.info(f"[{ticker}] skip (already present): {accession}")
                        summary[ticker]["skipped"] += 1
                        continue

                    if args.dry_run:
                        logger.info(f"[{ticker}] DRY-RUN would fetch: {form_type} {accession}")
                        summary[ticker]["added"] += 1
                        continue

                    # Download filing text to temp file
                    fpath = _filing_path(ticker, form_type, accession)
                    try:
                        if not fpath.exists():
                            fpath.parent.mkdir(parents=True, exist_ok=True)
                            raw_text = fl.text()
                            fpath.write_text(raw_text, encoding="utf-8")
                    except Exception as exc:
                        logger.error(f"[{ticker}] Failed to download/write {accession}: {exc}")
                        continue

                    # Parse
                    try:
                        text, _raw = parse_html_file(str(fpath))
                    except Exception as exc:
                        logger.error(f"[{ticker}] Failed to parse {accession}: {exc}")
                        continue

                    if not text or not text.strip():
                        logger.warning(f"[{ticker}] Empty text for {accession}, skipping.")
                        continue

                    period_of_report = _period_from_accession(accession)
                    cik = _TICKER_CIK.get(ticker.upper(), "")
                    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

                    # Extract sections and chunk
                    sections = _extract_sections_with_labels(text)
                    all_chunks = []
                    for section_label, section_text in sections:
                        if not section_text or not section_text.strip():
                            continue
                        provenance_header = (
                            f"[TICKER:{ticker.upper()} | SECTION:{section_label} | "
                            f"PERIOD:{period_of_report} | FORM:{form_type}]\n"
                        )
                        try:
                            chunks = chunker.chunk(
                                section_text,
                                section_label=section_label,
                                ticker=ticker.upper(),
                                period=period_of_report,
                                form_type=form_type,
                                provenance_header=provenance_header,
                            )
                        except Exception as exc:
                            logger.error(
                                f"[{ticker}] Chunking failed for section '{section_label}' "
                                f"in {accession}: {exc}"
                            )
                            continue
                        all_chunks.extend(chunks)

                    if not all_chunks:
                        logger.warning(f"[{ticker}] No chunks produced for {accession}.")
                        continue

                    # Delete any existing rows for this (ticker, accession) – idempotent
                    write_conn.execute(
                        "DELETE FROM edgar_embeddings WHERE ticker=? AND accession=?",
                        [ticker.upper(), accession],
                    )

                    # Prepare batch data
                    batch_texts = [c.text for c in all_chunks]
                    total_chunks = len(batch_texts)

                    # Embed in batches of 4
                    all_vecs = []
                    BATCH_SIZE = 4
                    for bi in range(0, total_chunks, BATCH_SIZE):
                        batch = batch_texts[bi : bi + BATCH_SIZE]
                        try:
                            vecs = model.embed_documents(batch)
                            all_vecs.extend(vecs)
                        except Exception as exc:
                            logger.error(
                                f"[{ticker}] Embedding failed for batch {bi}:{bi+BATCH_SIZE} "
                                f"in {accession}: {exc}"
                            )
                            # Fill with None to skip these
                            all_vecs.extend([None] * len(batch))

                    # Insert rows
                    rows_inserted = 0
                    for j, chunk in enumerate(all_chunks):
                        vec = all_vecs[j]
                        if vec is None:
                            continue
                        write_conn.execute(
                            """INSERT INTO edgar_embeddings
                               (ticker, accession, text, embedding, updated_at, cik,
                                section_id, form_type, period_of_report, chunk_index,
                                section_type, content_type)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            [
                                ticker.upper(),
                                accession,
                                chunk.text,
                                vec,
                                ts,
                                cik,
                                chunk.metadata.section_label,
                                form_type,
                                period_of_report,
                                chunk.metadata.chunk_index,
                                chunk.metadata.section_type,
                                chunk.metadata.content_type,
                            ],
                        )
                        rows_inserted += 1

                    write_conn.commit()
                    summary[ticker]["added"] += 1
                    summary[ticker]["total_chunks"] += rows_inserted
                    logger.info(
                        f"[{ticker}] Stored {rows_inserted} chunks for "
                        f"{form_type} {accession}"
                    )

                    # Cleanup between filings
                    del text, _raw, sections, all_chunks, batch_texts, all_vecs
                    gc.collect()

    finally:
        dedup_conn.close()
        if write_conn is not None:
            write_conn.close()

    # Final summary
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    for ticker, stats in summary.items():
        logger.info(
            f"  {ticker}: added={stats['added']}, skipped={stats['skipped']}, "
            f"total_chunks_stored={stats['total_chunks']}"
        )


if __name__ == "__main__":
    main()