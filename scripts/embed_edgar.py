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

from scripts.embed_tickers import _get_embeddings as _get_model

from api.config import Config

DB_PATH = Config.DB_PATH

# SEC requires a user-agent — parse from EDGAR_USER_AGENT (same var used by edgar_adapter.py)
# Format: "Company Name email@example.com"
_user_agent = os.getenv("EDGAR_USER_AGENT", "RAG-Workbench research@example.com")
_parts = _user_agent.split(" ", 1)
_COMPANY = _parts[0] if _parts else "RAG-Workbench"
_EMAIL = _parts[1] if len(_parts) > 1 else "research@example.com"
_DOWNLOAD_DIR = Path("./data/edgar_downloads")

# CIK lookup for well-known tickers
_TICKER_CIK: dict[str, str] = {
    # ── Semiconductor Design & IP ──
    "ADI":  "0000006607",  # Analog Devices
    "AIP":  "0001861842",  # Arteris
    "ALAB": "0001903832",  # Astera Labs
    "ALGM": "0000930155",  # Allegro MicroSystems
    "ALMU": "0001841107",  # Aeluma
    "AMBQ": "0001841107",  # Ambiq Micro (same CIK as Aeluma placeholder)
    "AMD":  "0000002488",  # Advanced Micro Devices
    "AOSL": "0000930155",  # Alpha & Omega (placeholder)
    "ARM":  "0001903832",  # Arm Holdings (placeholder)
    "ASX":  "0000930155",  # ASE Technology (placeholder)
    "AVGO": "0001730168",  # Broadcom
    "CBRS": "0001903832",  # Cerebras (placeholder)
    "CEVA": "0000930155",  # CEVA (placeholder)
    "CRDO": "0001903832",  # Credo Technology (placeholder)
    "CRUS": "0000930155",  # Cirrus Logic (placeholder)
    "DIOD": "0000930155",  # Diodes Inc (placeholder)
    "GCTS": "0001903832",  # GCT Semiconductor (placeholder)
    "GFS":  "0001903832",  # GlobalFoundries (placeholder)
    "GSIT": "0000930155",  # GSI Technology (placeholder)
    "HIMX": "0000930155",  # Himax (placeholder)
    "ICG":  "0001903832",  # Intchains (placeholder)
    "IMOS": "0000930155",  # ChipMOS (placeholder)
    "INDI": "0001903832",  # indie Semiconductor (placeholder)
    "INTC": "0000050863",  # Intel
    "IPWR": "0000930155",  # Ideal Power (placeholder)
    "LAES": "0001903832",  # SEALSQ (placeholder)
    "LASR": "0000930155",  # nLIGHT (placeholder)
    "LEDS": "0000930155",  # SemiLEDS (placeholder)
    "LSCC": "0000930155",  # Lattice Semiconductor (placeholder)
    "MCHP": "0000930155",  # Microchip Technology (placeholder)
    "MOBX": "0001903832",  # Mobix Labs (placeholder)
    "MPWR": "0000930155",  # Monolithic Power (placeholder)
    "MRAM": "0000930155",  # Everspin (placeholder)
    "MRVL": "0000930155",  # Marvell (placeholder)
    "MTSI": "0000930155",  # MACOM (placeholder)
    "MU":   "0000723125",  # Micron Technology
    "MX":   "0000930155",  # Magnachip (placeholder)
    "MXL":  "0000930155",  # MaxLinear (placeholder)
    "NVDA": "0001045810",  # Nvidia
    "NVEC": "0000930155",  # NVE Corp (placeholder)
    "NVTS": "0001903832",  # Navitas (placeholder)
    "NXPI": "0000930155",  # NXP (placeholder)
    "PI":   "0000930155",  # Impinj (placeholder)
    "POET": "0001903832",  # POET Technologies (placeholder)
    "POWI": "0000930155",  # Power Integrations (placeholder)
    "PRSO": "0000930155",  # Peraso (placeholder)
    "PXLW": "0000930155",  # Pixelworks (placeholder)
    "QCOM": "0000804328",  # Qualcomm
    "QRVO": "0000930155",  # Qorvo (placeholder)
    "QUIK": "0000930155",  # QuickLogic (placeholder)
    "RMBS": "0000930155",  # Rambus (placeholder)
    "SIMO": "0000930155",  # Silicon Motion (placeholder)
    "SITM": "0001903832",  # SiTime (placeholder)
    "SKYT": "0001903832",  # SkyWater (placeholder)
    "SLAB": "0000930155",  # Silicon Labs (placeholder)
    "SMTC": "0000930155",  # Semtech (placeholder)
    "SQNS": "0000930155",  # Sequans (placeholder)
    "STM":  "0000930155",  # STMicroelectronics (placeholder)
    "SWKS": "0000930155",  # Skyworks (placeholder)
    "SYNA": "0000930155",  # Synaptics (placeholder)
    "TSEM": "0000930155",  # Tower Semiconductor (placeholder)
    "TSM":  "0001046179",  # Taiwan Semiconductor
    "TXN":  "0000097476",  # Texas Instruments
    "UMC":  "0000930155",  # United Microelectronics (placeholder)
    "VLN":  "0001903832",  # Valens (placeholder)
    "VSH":  "0000930155",  # Vishay (placeholder)
    "WKEY": "0001903832",  # WISeKey (placeholder)
    "WOLF": "0000930155",  # Wolfspeed (placeholder)
    # ── Semiconductor Equipment & Materials ──
    "ACLS": "0000897077",  # Axcelis Technologies
    "ACMR": "0001680062",  # ACM Research
    "AEHR": "0001040470",  # Aehr Test Systems
    "AMAT": "0000069515",  # Applied Materials
    "AMBA": "0001280263",  # Ambarella
    "AMKR": "0001047127",  # Amkor Technology
    "ASML": "0000937966",  # ASML Holding
    "ASYS": "0000720500",  # Amtech Systems
    "ATOM": "0001420520",  # Atomera
    "AXTI": "0001051627",  # AXT Inc
    "CAMT": "0001109138",  # Camtek
    "COHU": "0000021535",  # Cohu
    "ENTG": "0001101302",  # Entegris
    "FORM": "0001039399",  # FormFactor
    "ICHR": "0001652535",  # Ichor Holdings
    "INTT": "0001036262",  # inTEST Corp
    "IPGP": "0001111928",  # IPG Photonics
    "KLAC": "0000319201",  # KLA Corp
    "KLIC": "0000056978",  # Kulicke & Soffa
    "LRCX": "0000707549",  # Lam Research
    "NVMI": "0001109345",  # Nova Ltd
    "ONTO": "0000704532",  # Onto Innovation
    "PLAB": "0000810136",  # Photronics
    "Q":    "0002058873",  # Qnity Electronics
    "SMTK": "0001817760",  # SmartKem
    "TER":  "0000097210",  # Teradyne
    "TRT":  "0000732026",  # Trio-Tech International
    "UCTT": "0001275014",  # Ultra Clean Holdings
    "VECO": "0000103145",  # Veeco Instruments
}

# All semiconductor tickers for ingestion
DEMO_TICKERS: List[str] = [
    # Semiconductor Design & IP
    "ADI", "AIP", "ALAB", "ALGM", "ALMU", "AMD", "AOSL", "ARM", "ASX",
    "AVGO", "CBRS", "CEVA", "CRDO", "CRUS", "DIOD", "GCTS", "GFS", "GSIT",
    "HIMX", "ICG", "IMOS", "INDI", "INTC", "IPWR", "LAES", "LASR", "LEDS",
    "LSCC", "MCHP", "MOBX", "MPWR", "MRAM", "MRVL", "MTSI", "MU", "MX",
    "MXL", "NVDA", "NVEC", "NVTS", "NXPI", "PI", "POET", "POWI", "PRSO",
    "PXLW", "QCOM", "QRVO", "QUIK", "RMBS", "SIMO", "SITM", "SKYT", "SLAB",
    "SMTC", "SQNS", "STM", "SWKS", "SYNA", "TSEM", "TSM", "TXN", "UMC",
    "VLN", "VSH", "WKEY", "WOLF",
    # Semiconductor Equipment & Materials
    "ACLS", "ACMR", "AEHR", "AMAT", "AMBA", "AMKR", "ASML", "ASYS", "ATOM",
    "AXTI", "CAMT", "COHU", "ENTG", "FORM", "ICHR", "INTT", "IPGP", "KLAC",
    "KLIC", "LRCX", "NVMI", "ONTO", "PLAB", "Q", "SMTK", "TER", "TRT",
    "UCTT", "VECO",
]

_TARGET_SECTIONS: Dict[str, str] = {
    "item_1":   r"item\s+1[\s.:—–-]+business",
    "item_1a":  r"item\s+1a[\s.:—–-]+risk\s+factor",
    "item_7":   r"item\s+7[\s.:—–-]+management",
    "item_7a":  r"item\s+7a[\s.:—–-]+quantitative",
    "item_8":   r"item\s+8[\s.:—–-]+financial\s+statement",
}
_ANY_ITEM = re.compile(
    r"(?:^|\n)\s*item\s+\d+[a-z]?[\s.:—–-]",
    re.IGNORECASE | re.MULTILINE,
)

# 20-F sections for foreign private issuers
_20F_SECTIONS: Dict[str, str] = {
    "item_1":   r"item\s+1[\s.:—–-]+description\s+of\s+business",
    "item_3":   r"item\s+3[\s.:—–-]+key\s+information",
    "item_4":   r"item\s+4[\s.:—–-]+information\s+on\s+the\s+company",
    "item_5":   r"item\s+5[\s.:—–-]+operating",
    "item_6":   r"item\s+6[\s.:—–-]+directors",
    "item_7":   r"item\s+7[\s.:—–-]+major\s+shareholders",
    "item_8":   r"item\s+8[\s.:—–-]+financial\s+information",
    "item_10":  r"item\s+10[\s.:—–-]+additional\s+information",
    "item_11":  r"item\s+11[\s.:—–-]+quantitative",
}


def _fetch_filing_with_downloader(ticker: str, form_types: List[str] = None) -> tuple[str, str]:
    """Download the latest filing for the given form types. Returns (file_path, form_type)."""
    if form_types is None:
        form_types = ["10-K", "20-F", "10-Q"]

    dl = Downloader(_COMPANY, _EMAIL, _DOWNLOAD_DIR)

    for form_type in form_types:
        try:
            num_downloaded = dl.get(form_type, ticker, limit=1, download_details=True)
            if num_downloaded == 0:
                continue

            ticker_dir = _DOWNLOAD_DIR / "sec-edgar-filings" / ticker / form_type
            if not ticker_dir.exists():
                continue

            accession_dirs = [d for d in ticker_dir.iterdir() if d.is_dir()]
            if not accession_dirs:
                continue

            primary_doc_path = accession_dirs[0] / "primary-document.html"
            if primary_doc_path.exists():
                logger.info(f"Found {form_type} for {ticker}")
                return str(primary_doc_path), form_type
        except Exception as e:
            logger.debug(f"Failed to download {form_type} for {ticker}: {e}")
            continue

    return "", ""


def fetch_latest_10k_with_downloader(ticker: str) -> str:
    """Download the latest 10-K and return path to primary HTML document."""
    file_path, _ = _fetch_filing_with_downloader(ticker, ["10-K"])
    return file_path


def _extract_period_of_report(html_content: str, accession_dir_name: str) -> str:
    """
    Extract period_of_report from the filing HTML <period-of-report> tag,
    or fall back to parsing the accession directory name, or the current year.
    """
    # Try to find <period-of-report> tag
    match = re.search(r"<period-of-report>(.*?)</period-of-report>", html_content, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Try to parse from accession directory name (format: XXXXXXXXXX-YY-ZZZZZZ)
    # The accession number encodes the filing date in YY portion
    acc_match = re.match(r"\d{10}-(\d{2})-\d{6}", accession_dir_name)
    if acc_match:
        year_short = acc_match.group(1)
        year = int(year_short)
        # Convert 2-digit year: 00-49 -> 2000-2049, 50-99 -> 1950-1999
        full_year = 2000 + year if year < 50 else 1900 + year
        return f"{full_year}-12-31"

    # Fall back to current year
    return f"{datetime.now().year}-12-31"


def _extract_sections_with_labels(text: str) -> List[tuple[str, str]]:
    """
    Extract target 10-K sections from plain text by matching Item headers.
    Returns a list of (section_label, section_text) tuples.

    Finds each target section's start via regex, then reads until the next
    Item header appears. Falls back to the full text under label 'full_text' if none found.
    """
    extracted: List[tuple[str, str]] = []

    for label, pattern in _TARGET_SECTIONS.items():
        # Use a bounded match: find the section start, then capture until the next
        # item heading or end of text. The [^\n]*? approach limits cross-line backtracking.
        section_re = re.compile(
            r"(?:^|\n)(\s*" + pattern + r"[^\n]*(?:\n(?!\s*item\s+\d)[^\n]*)*)",
            re.IGNORECASE | re.MULTILINE,
        )
        match = section_re.search(text)
        if match:
            section_text = match.group(1).strip()
            # Drop sections that are mostly whitespace or very short (table-of-contents refs)
            if len(section_text) > 200:
                extracted.append((label, section_text))

    if not extracted:
        logger.debug("No target sections found — falling back to full text")
        return [("full_text", text)]

    logger.debug(f"Extracted {len(extracted)} sections")
    return extracted


def _extract_sections(text: str) -> str:
    """
    Extract target 10-K sections from plain text by matching Item headers.

    Finds each target section's start via regex, then reads until the next
    Item header appears. Falls back to the full text if no sections are found.
    """
    sections = _extract_sections_with_labels(text)
    if len(sections) == 1 and sections[0][0] == "full_text":
        return sections[0][1]

    parts = [f"=== {label.upper().replace('_', ' ')} ===\n{text}" for label, text in sections]
    combined = "\n\n".join(parts)
    logger.debug(f"Extracted {len(sections)} sections ({len(combined):,} chars)")
    return combined


def _clean_text(text: str) -> str:
    """Remove excessive whitespace and repeated blank lines left by get_text()."""
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_html_file(file_path: str) -> tuple[str, str]:
    """
    Parse HTML, strip tags, extract target sections, clean whitespace.
    Returns (extracted_text, raw_html_content) so caller can extract period_of_report.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        soup = BeautifulSoup(content, "lxml")

        # Remove script/style/XBRL inline elements that pollute get_text()
        for tag in soup(["script", "style", "ix:nonnumeric", "ix:nonfraction", "ix:header"]):
            tag.decompose()

        raw = soup.get_text(separator="\n", strip=True)
        clean = _clean_text(raw)
        return _extract_sections(clean), content
    except Exception as e:
        logger.warning(f"Failed to parse {file_path}: {e}")
        return "", ""


def _ensure_schema(conn) -> None:
    """Ensure edgar_embeddings table has all required columns (idempotent)."""
    # Add new columns if they don't exist (ALTER TABLE IF NOT EXISTS column)
    alter_stmts = [
        "ALTER TABLE edgar_embeddings ADD COLUMN IF NOT EXISTS cik VARCHAR",
        "ALTER TABLE edgar_embeddings ADD COLUMN IF NOT EXISTS section_id VARCHAR",
        "ALTER TABLE edgar_embeddings ADD COLUMN IF NOT EXISTS form_type VARCHAR DEFAULT '10-K'",
        "ALTER TABLE edgar_embeddings ADD COLUMN IF NOT EXISTS period_of_report VARCHAR",
        "ALTER TABLE edgar_embeddings ADD COLUMN IF NOT EXISTS chunk_index INTEGER",
    ]
    for stmt in alter_stmts:
        try:
            conn.execute(stmt)
        except Exception as e:
            logger.debug(f"Schema alter skipped (may already exist): {e}")


def run_embed_edgar_etl(tickers: List[str] = None) -> int:
    """
    Main ETL job: use sec-edgar-downloader to fetch 10-K/20-F/10-Q, chunk, embed, and store in DuckDB.
    Defaults to DEMO_TICKERS if no tickers provided.
    """
    if tickers is None:
        tickers = DEMO_TICKERS

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

        # Ensure schema is up to date
        _ensure_schema(conn)

        for ticker in tickers:
            logger.info(f"Processing filings for {ticker}...")

            file_path, form_type = _fetch_filing_with_downloader(ticker, ["10-K", "20-F", "10-Q"])

            if not file_path:
                logger.warning(f"No filings downloaded for {ticker}.")
                continue

            text, raw_html = parse_html_file(file_path)

            if not text:
                continue

            # Extract period_of_report from HTML or accession dir name
            accession_dir_name = Path(file_path).parent.name
            period_of_report = _extract_period_of_report(raw_html, accession_dir_name)
            accession = accession_dir_name

            cik = _TICKER_CIK.get(ticker.upper(), "")

            # Use section-aware chunking to preserve provenance
            sections = _extract_sections_with_labels(
                _clean_text(
                    BeautifulSoup(raw_html, "lxml").get_text(separator="\n", strip=True)
                    if raw_html else text
                )
            )

            # Build chunks with metadata headers per section
            all_chunks: List[tuple[str, str]] = []  # (chunk_text, section_label)
            for section_label, section_text in sections:
                provenance_header = (
                    f"[TICKER:{ticker.upper()} | SECTION:{section_label} | "
                    f"PERIOD:{period_of_report} | FORM:{form_type}]\n"
                )
                section_with_header = provenance_header + section_text
                section_chunks = text_splitter.split_text(section_with_header)
                for chunk in section_chunks:
                    all_chunks.append((chunk, section_label))

            logger.debug(f"{ticker}: Split into {len(all_chunks)} chunks across {len(sections)} sections.")

            batch_size = 8
            ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

            # Delete existing records for this ticker+accession
            conn.execute(
                "DELETE FROM edgar_embeddings WHERE ticker = ? AND accession = ?",
                [ticker, accession]
            )

            for i in range(0, len(all_chunks), batch_size):
                batch = all_chunks[i: i + batch_size]
                batch_texts = [c[0] for c in batch]
                batch_labels = [c[1] for c in batch]
                vecs = model.embed_documents(batch_texts)

                for j, (chunk_text, section_label) in enumerate(zip(batch_texts, batch_labels)):
                    conn.execute("""
                        INSERT INTO edgar_embeddings
                            (ticker, accession, text, embedding, updated_at,
                             cik, section_id, form_type, period_of_report, chunk_index)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, [
                        ticker, accession, chunk_text, vecs[j], ts,
                        cik,
                        section_label,
                        form_type,
                        period_of_report,
                        i + j,
                    ])

                total_chunks_stored += len(batch)
            conn.commit()

    if _DOWNLOAD_DIR.exists():
        shutil.rmtree(_DOWNLOAD_DIR, ignore_errors=True)

    logger.info(f"EDGAR embedding complete. Stored {total_chunks_stored} total chunks.")
    return total_chunks_stored


if __name__ == "__main__":
    import sys
    tickers_arg = os.getenv("EMBED_TICKERS", "")
    if tickers_arg:
        tickers = [t.strip() for t in tickers_arg.split(",")]
    else:
        tickers = DEMO_TICKERS
    logger.info(f"Running EDGAR embedding for {len(tickers)} tickers: {tickers}")
    run_embed_edgar_etl(tickers)
