#!/usr/bin/env python3
"""Embed additional recent annual (10-K / 20-F) and 10-Q filings into edgar_embeddings.

Authored via MiMo, reviewed by DeepSeek, validated/edited by Claude.
For companies already present in `edgar_embeddings`, fetch the 2 most recent annual
filings (10-K, or 20-F for foreign filers) or the 1 most recent 10-Q, and embed any
filing whose accession is not yet stored. Dedup is by (ticker, accession); a
DELETE-before-INSERT makes re-runs idempotent.

Conventions preserved to match existing rows:
  - accession kept WITH dashes (e.g. 0000006281-25-000153)
  - period_of_report = 20{YY}-12-31 from the accession's middle segment (matches the
    existing fallback convention used for both 10-K and 10-Q rows in this corpus)

Run with the duckdb-1.5.x venv (the on-disk DB is 1.5.x format):
  .venv\\Scripts\\python.exe scripts/embed_additional.py --forms annual --dry-run
  .venv\\Scripts\\python.exe scripts/embed_additional.py --forms annual
  .venv\\Scripts\\python.exe scripts/embed_additional.py --forms 10-Q
"""

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

# ── performance: saturate CPU cores for local embedding ───────────────────────
# The Space caps batch=4 / few threads for its 16Gi limit; this box has 8 physical
# cores and ~40GB free, so go wide. These MUST be set before torch is imported.
try:
    import psutil as _ps
    _NTHREADS = _ps.cpu_count(logical=False) or os.cpu_count() or 8
except Exception:
    _NTHREADS = os.cpu_count() or 8
os.environ.setdefault("OMP_NUM_THREADS", str(_NTHREADS))
os.environ.setdefault("MKL_NUM_THREADS", str(_NTHREADS))
os.environ.setdefault("TOKENIZERS_PARALLELISM", "true")
# sentence-transformers' internal encode batch (LocalSTEmbeddings reads this).
os.environ.setdefault("EMBEDDING_BATCH_SIZE", os.getenv("EMBED_DOC_BATCH", "64"))

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

DB_PATH = Config.DB_PATH  # singleton instance attr (mirrors scripts/embed_edgar.py)


# ── helpers ───────────────────────────────────────────────────────────────────

def _normalize_filings(fresult):
    """Return a list of Filing objects from the result of latest(n).

    latest(2) returns an EntityFilings collection (iterable -> list yields Filings);
    latest(1) returns a single EntityFiling (not iterable -> TypeError fallback);
    None (no filings) -> empty list.
    """
    if fresult is None:
        return []
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
    """20{YY}-12-31 from the accession middle segment — matches existing corpus rows."""
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
        help='Which forms to fetch: "annual" (10-K + 20-F, latest 2) or "10-Q".',
    )
    parser.add_argument(
        "--quarters",
        type=int,
        default=3,
        help="For --forms 10-Q: how many of the most recent 10-Qs to fetch per "
        "company. Default 3 = ~1 fiscal year of quarterlies (Q4 is in the 10-K). "
        "Already-stored accessions are skipped, so companies that already have "
        "their quarterlies are no-ops.",
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

    # Pin torch to all cores (default was only 4 on this box).
    try:
        import torch
        torch.set_num_threads(_NTHREADS)
        logger.info(f"torch threads set to {torch.get_num_threads()} (cores={_NTHREADS})")
    except Exception as exc:
        logger.warning(f"Could not set torch threads: {exc}")

    model = get_embeddings()
    if model is None:
        logger.error("Embedding model unavailable; cannot proceed.")
        sys.exit(1)

    chunker = StructureChunker(
        max_chunk_size=1500,
        min_chunk_size=200,
        similarity_threshold=0.15,
    )

    # Single connection: read-only for dry-run (also avoids the write lock), else
    # read-write so dedup checks see rows committed earlier in the same run.
    conn = duckdb.connect(DB_PATH, read_only=args.dry_run)
    if not args.dry_run:
        try:
            conn.execute("LOAD vss")
        except Exception:
            pass
        _ensure_schema(conn)

    try:
        # Determine tickers
        if args.tickers:
            tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
        else:
            rows = conn.execute(
                "SELECT DISTINCT ticker FROM edgar_embeddings ORDER BY ticker"
            ).fetchall()
            tickers = [r[0] for r in rows]

        if not tickers:
            logger.warning("No tickers found to process.")
            return

        summary: dict[str, dict] = {}  # ticker -> {"added", "skipped", "total_chunks"}

        for ticker in tickers:
            summary.setdefault(ticker, {"added": 0, "skipped": 0, "total_chunks": 0})
            logger.info(f"=== Processing {ticker} ===")

            # Only extend the annual form this ticker ALREADY files, so a former
            # foreign filer that now files 10-K (e.g. NXPI) doesn't pull ancient
            # 20-Fs, and pure 20-F filers (STM, TSM) get 20-F, not 10-K.
            existing_forms = {
                r[0] for r in conn.execute(
                    "SELECT DISTINCT form_type FROM edgar_embeddings WHERE ticker=?",
                    [ticker.upper()],
                ).fetchall()
            }
            if args.forms == "annual":
                if "10-K" in existing_forms:
                    form_plan = [("10-K", 2)]
                elif "20-F" in existing_forms:
                    form_plan = [("20-F", 2)]
                else:
                    logger.info(
                        f"[{ticker}] no 10-K/20-F in corpus (forms={sorted(existing_forms)}); "
                        f"skipping annual."
                    )
                    continue
            else:
                form_plan = [("10-Q", max(1, args.quarters))]

            for form_code, n_latest in form_plan:
                # Pull a wider window, then keep only EXACT-form filings (drop
                # amendments like 10-K/A) and take the n most recent.
                try:
                    filings = Company(ticker).get_filings(form=form_code)
                    if filings is None or getattr(filings, "empty", False):
                        logger.info(f"[{ticker}] No {form_code} filings found.")
                        continue
                    window = _normalize_filings(filings.latest(max(n_latest + 6, 8)))
                except Exception as exc:
                    logger.error(f"[{ticker}] Failed to get {form_code} filings: {exc}")
                    continue

                filing_list = [
                    f for f in window if getattr(f, "form", None) == form_code
                ][:n_latest]
                if not filing_list:
                    logger.info(f"[{ticker}] No exact {form_code} filings found.")
                    continue

                for fl in filing_list:
                    try:
                        accession = fl.accession_number
                        form_type = fl.form
                    except Exception as exc:
                        logger.error(f"[{ticker}/{form_code}] Cannot read filing metadata: {exc}")
                        continue

                    # Dedup check
                    if _is_present(conn, ticker, accession):
                        logger.info(f"[{ticker}] skip (already present): {form_type} {accession}")
                        summary[ticker]["skipped"] += 1
                        continue

                    if args.dry_run:
                        logger.info(f"[{ticker}] DRY-RUN would fetch: {form_type} {accession}")
                        summary[ticker]["added"] += 1
                        continue

                    # Download filing text to a local file (skip if already downloaded)
                    fpath = _filing_path(ticker, form_type, accession)
                    try:
                        if not fpath.exists():
                            fpath.parent.mkdir(parents=True, exist_ok=True)
                            fpath.write_text(fl.text(), encoding="utf-8")
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

                    # Extract sections and chunk (20-F falls back to full_text)
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

                    # Idempotent: clear any existing rows for this filing first
                    conn.execute(
                        "DELETE FROM edgar_embeddings WHERE ticker=? AND accession=?",
                        [ticker.upper(), accession],
                    )

                    # Embed in batches, keeping vector order aligned with all_chunks
                    batch_texts = [c.text for c in all_chunks]
                    all_vecs = []
                    BATCH_SIZE = int(os.getenv("EMBED_DOC_BATCH", "64"))
                    embed_failed = False
                    for bi in range(0, len(batch_texts), BATCH_SIZE):
                        batch = batch_texts[bi: bi + BATCH_SIZE]
                        try:
                            all_vecs.extend(model.embed_documents(batch))
                        except Exception as exc:
                            logger.error(
                                f"[{ticker}] Embedding failed for batch {bi}:{bi+BATCH_SIZE} "
                                f"in {accession}: {exc}"
                            )
                            embed_failed = True
                            break

                    # Never store a PARTIAL filing. If any batch failed (e.g. CUDA OOM),
                    # skip the whole filing: the earlier DELETE already cleared any prior
                    # rows for this accession, so it is left absent and retried cleanly on a
                    # future run — instead of being marked 'present' with chunks missing.
                    if embed_failed or len(all_vecs) != len(all_chunks):
                        logger.warning(
                            f"[{ticker}] SKIPPING {form_type} {accession} — embedding "
                            f"incomplete; not stored (will retry on a future run)."
                        )
                        summary[ticker]["skipped"] += 1
                        continue

                    rows_inserted = 0
                    for j, chunk in enumerate(all_chunks):
                        vec = all_vecs[j]
                        conn.execute(
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

                    conn.commit()
                    summary[ticker]["added"] += 1
                    summary[ticker]["total_chunks"] += rows_inserted
                    logger.info(
                        f"[{ticker}] Stored {rows_inserted} chunks for {form_type} {accession}"
                    )

                    # Release this filing's memory before the next one
                    del text, _raw, sections, all_chunks, batch_texts, all_vecs
                    gc.collect()
    finally:
        conn.close()

    # Final summary
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    tot_added = tot_skipped = tot_chunks = 0
    for ticker, stats in summary.items():
        tot_added += stats["added"]
        tot_skipped += stats["skipped"]
        tot_chunks += stats["total_chunks"]
        logger.info(
            f"  {ticker}: added={stats['added']}, skipped={stats['skipped']}, "
            f"total_chunks_stored={stats['total_chunks']}"
        )
    logger.info(
        f"TOTAL: added={tot_added}, skipped={tot_skipped}, chunks_stored={tot_chunks}"
    )


if __name__ == "__main__":
    main()
