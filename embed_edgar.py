"""
embed_edgar.py
Downloads the most recent 10-K for each ticker from SEC EDGAR using sec-edgar-downloader,
extracts text from high-signal sections (Business, Risk Factors, MD&A), splits into chunks
via LangChain, embeds with Gemini, and stores into DuckDB `edgar_embeddings`.

Section targeting avoids iXBRL boilerplate, repeated table headers, and XBRL metadata that
degrade RAG quality when the full document is parsed with get_text().
"""
import os
import re
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional

import duckdb
from bs4 import BeautifulSoup
from loguru import logger
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sec_edgar_downloader import Downloader

from embed_tickers import _get_embeddings as _get_model

DB_PATH = os.getenv("DB_PATH", "./data/ibkr.duckdb")

# SEC requires a user-agent
_EMAIL = os.getenv("EDGAR_EMAIL", "research@example.com")
_COMPANY = "RAG-Workbench"
_DOWNLOAD_DIR = Path("./data/edgar_downloads")

# 10-K sections worth embedding — ordered by semantic value for RAG
_TARGET_SECTIONS: Dict[str, str] = {
    "item_1":   r"item\s+1[\.\s]+business",
    "item_1a":  r"item\s+1a[\.\s]+risk\s+factor",
    "item_7":   r"item\s+7[\.\s]+management",
    "item_7a":  r"item\s+7a[\.\s]+quantitative",
    "item_8":   r"item\s+8[\.\s]+financial\s+statement",
}
# Pattern that marks the START of any target or adjacent section (used as end boundary)
_ANY_ITEM = re.compile(
    r"(?:^|\n)\s*item\s+\d+[a-z]?[\.\s]",
    re.IGNORECASE | re.MULTILINE,
)


def fetch_latest_10k_with_downloader(ticker: str) -> str:
    """Download the latest 10-K and return path to primary HTML document."""
    dl = Downloader(_COMPANY, _EMAIL, _DOWNLOAD_DIR)

    try:
        num_downloaded = dl.get("10-K", ticker, limit=1, download_details=True)
        if num_downloaded == 0:
            return ""

        ticker_dir = _DOWNLOAD_DIR / "sec-edgar-filings" / ticker / "10-K"
        if not ticker_dir.exists():
            return ""

        accession_dirs = [d for d in ticker_dir.iterdir() if d.is_dir()]
        if not accession_dirs:
            return ""

        primary_doc_path = accession_dirs[0] / "primary-document.html"
        return str(primary_doc_path) if primary_doc_path.exists() else ""
    except Exception as e:
        logger.warning(f"Failed to download 10-K for {ticker}: {e}")
        return ""


def _extract_sections(text: str) -> str:
    """
    Extract target 10-K sections from plain text by matching Item headers.

    Finds each target section's start via regex, then reads until the next
    Item header appears. Falls back to the full text if no sections are found.
    """
    extracted: List[str] = []

    for label, pattern in _TARGET_SECTIONS.items():
        section_re = re.compile(
            r"(?:^|\n)(\s*" + pattern + r".*?)(?=\n\s*item\s+\d|$)",
            re.IGNORECASE | re.DOTALL | re.MULTILINE,
        )
        match = section_re.search(text)
        if match:
            section_text = match.group(1).strip()
            # Drop sections that are mostly whitespace or very short (table-of-contents refs)
            if len(section_text) > 200:
                extracted.append(f"=== {label.upper().replace('_', ' ')} ===\n{section_text}")

    if not extracted:
        logger.debug("No target sections found — falling back to full text")
        return text

    combined = "\n\n".join(extracted)
    logger.debug(f"Extracted {len(extracted)} sections ({len(combined):,} chars)")
    return combined


def _clean_text(text: str) -> str:
    """Remove excessive whitespace and repeated blank lines left by get_text()."""
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_html_file(file_path: str) -> str:
    """Parse HTML, strip tags, extract target sections, clean whitespace."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        soup = BeautifulSoup(content, "lxml")

        # Remove script/style/XBRL inline elements that pollute get_text()
        for tag in soup(["script", "style", "ix:nonnumeric", "ix:nonfraction", "ix:header"]):
            tag.decompose()

        raw = soup.get_text(separator="\n", strip=True)
        clean = _clean_text(raw)
        return _extract_sections(clean)
    except Exception as e:
        logger.warning(f"Failed to parse {file_path}: {e}")
        return ""


def run_embed_edgar_etl(tickers: List[str]) -> int:
    """
    Main ETL job: use sec-edgar-downloader to fetch 10-Ks, chunk, embed, and store in DuckDB.
    """
    logger.info("Starting EDGAR embedding ETL with sec-edgar-downloader...")

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=150,
        length_function=len,
    )

    model = _get_model()
    total_chunks_stored = 0

    with duckdb.connect(DB_PATH) as conn:
        try:
            conn.execute("LOAD vss")
        except Exception:
            pass

        for ticker in tickers:
            logger.info(f"Processing 10-K for {ticker}...")

            file_path = fetch_latest_10k_with_downloader(ticker)

            if not file_path:
                logger.warning(f"No 10-K filing downloaded for {ticker}.")
                continue

            text = parse_html_file(file_path)

            if not text:
                continue

            chunks = text_splitter.split_text(text)
            logger.debug(f"{ticker}: Split into {len(chunks)} chunks.")

            batch_size = 64
            ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
            accession = Path(file_path).parent.name

            for i in range(0, len(chunks), batch_size):
                batch_chunks = chunks[i : i + batch_size]
                vecs = model.embed_documents(batch_chunks)

                if i == 0:
                    conn.execute(
                        "DELETE FROM edgar_embeddings WHERE ticker = ? AND accession = ?",
                        [ticker, accession]
                    )

                for j, chunk_text in enumerate(batch_chunks):
                    conn.execute("""
                        INSERT INTO edgar_embeddings
                            (ticker, accession, text, embedding, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, [ticker, accession, chunk_text, vecs[j], ts])

                total_chunks_stored += len(batch_chunks)
            conn.commit()

    if _DOWNLOAD_DIR.exists():
        shutil.rmtree(_DOWNLOAD_DIR, ignore_errors=True)

    logger.info(f"EDGAR embedding complete. Stored {total_chunks_stored} total chunks.")
    return total_chunks_stored
