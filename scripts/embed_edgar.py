"""
embed_edgar.py
Downloads the most recent 10-K for each ticker from SEC EDGAR using sec-edgar-downloader,
extracts text from high-signal sections (Business, Risk Factors, MD&A), chunks with
structure-aware logic (tables intact, semantic narrative splitting), embeds with Gemini,
and stores into DuckDB `edgar_embeddings`.

Structure-aware chunking:
- Tables are detected by pipe/grid/number patterns and kept as single chunks
- Narrative text is split by topic similarity (semantic chunking), not fixed size
- Each chunk is tagged with section_type (balance_sheet, income_statement, md_and_a, etc.)
"""
import os
import re
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List

import duckdb
from bs4 import BeautifulSoup
from loguru import logger
from sec_edgar_downloader import Downloader

from api.services.embeddings import get_embeddings as _get_model
from api.services.structure_chunker import StructureChunker

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
    "ADI":  "0000006281",  # Analog Devices
    "AIP":  "0001861842",  # Arteris
    "ALAB": "0001903832",  # Astera Labs
    "ALGM": "0000930155",  # Allegro MicroSystems
    "ALMU": "0001841107",  # Aeluma
    "AMBQ": "0001841107",  # Ambiq Micro
    "AMD":  "0000002488",  # Advanced Micro Devices
    "AOSL": "0001399751",  # Alpha & Omega Semiconductor
    "ARM":  "0001973239",  # Arm Holdings
    "ASX":  "0001740411",  # ASE Technology
    "AVGO": "0001730168",  # Broadcom
    "CBRS": "0001614067",  # Cerebras (placeholder - not public yet)
    "CEVA": "0001173489",  # CEVA Inc.
    "CRDO": "0001807794",  # Credo Technology
    "CRUS": "0000866787",  # Cirrus Logic
    "DIOD": "0000029002",  # Diodes Inc
    "GCTS": "0001964233",  # GCT Semiconductor
    "GFS":  "0001709048",  # GlobalFoundries
    "GSIT": "0000930184",  # GSI Technology
    "HIMX": "0001351115",  # Himax Technologies
    "ICG":  "0001956041",  # Intchains Group
    "IMOS": "0001222442",  # ChipMOS Technologies
    "INDI": "0001841925",  # indie Semiconductor
    "INTC": "0000050863",  # Intel
    "IPWR": "0001402281",  # Ideal Power
    "LAES": "0001962325",  # SEALSQ
    "LASR": "0001420188",  # nLIGHT
    "LEDS": "0001348123",  # SemiLEDS
    "LSCC": "0000057760",  # Lattice Semiconductor
    "MCHP": "0000827054",  # Microchip Technology
    "MOBX": "0001949175",  # Mobix Labs
    "MPWR": "0001280452",  # Monolithic Power Systems
    "MRAM": "0001439606",  # Everspin Technologies
    "MRVL": "0001835632",  # Marvell Technology
    "MTSI": "0001494877",  # MACOM Technology
    "MU":   "0000723125",  # Micron Technology
    "MX":   "0001509172",  # Magnachip Semiconductor
    "MXL":  "0001416800",  # MaxLinear
    "NVDA": "0001045810",  # Nvidia
    "NVEC": "0000846633",  # NVE Corp
    "NVTS": "0001854097",  # Navitas Semiconductor
    "NXPI": "0001413447",  # NXP Semiconductors
    "PI":   "0001414470",  # Impinj
    "POET": "0001625078",  # POET Technologies
    "POWI": "0001064728",  # Power Integrations
    "PRSO": "0001861063",  # Peraso
    "PXLW": "0001021432",  # Pixelworks
    "QCOM": "0000804328",  # Qualcomm
    "QRVO": "0001604778",  # Qorvo
    "QUIK": "0000882508",  # QuickLogic
    "RMBS": "0000917273",  # Rambus
    "SIMO": "0001321045",  # Silicon Motion
    "SITM": "0001777265",  # SiTime
    "SKYT": "0001837240",  # SkyWater Technology
    "SLAB": "0001050776",  # Silicon Labs
    "SMTC": "0000088462",  # Semtech
    "SQNS": "0001505503",  # Sequans Communications
    "STM":  "0000932787",  # STMicroelectronics
    "SWKS": "0000004127",  # Skyworks Solutions
    "SYNA": "0000817720",  # Synaptics
    "TSEM": "0000894439",  # Tower Semiconductor
    "TSM":  "0001046179",  # Taiwan Semiconductor
    "TXN":  "0000097476",  # Texas Instruments
    "UMC":  "0001111563",  # United Microelectronics
    "VLN":  "0001865955",  # Valens Semiconductor
    "VSH":  "0000103761",  # Vishay Intertechnology
    "WKEY": "0001678880",  # WISeKey
    "WOLF": "0000895419",  # Wolfspeed
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
    """Ensure edgar_embeddings table exists with all required columns (idempotent)."""
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

    # Add columns that may not exist in older schemas
    alter_stmts = [
        "ALTER TABLE edgar_embeddings ADD COLUMN IF NOT EXISTS cik VARCHAR",
        "ALTER TABLE edgar_embeddings ADD COLUMN IF NOT EXISTS section_id VARCHAR",
        "ALTER TABLE edgar_embeddings ADD COLUMN IF NOT EXISTS form_type VARCHAR DEFAULT '10-K'",
        "ALTER TABLE edgar_embeddings ADD COLUMN IF NOT EXISTS period_of_report VARCHAR",
        "ALTER TABLE edgar_embeddings ADD COLUMN IF NOT EXISTS chunk_index INTEGER",
        "ALTER TABLE edgar_embeddings ADD COLUMN IF NOT EXISTS section_type VARCHAR DEFAULT 'narrative'",
        "ALTER TABLE edgar_embeddings ADD COLUMN IF NOT EXISTS content_type VARCHAR DEFAULT 'narrative'",
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

    chunker = StructureChunker(
        max_chunk_size=1500,
        min_chunk_size=200,
        similarity_threshold=0.15,
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

            # Build chunks with structure-aware chunking
            all_chunks = []  # list of Chunk objects
            for section_label, section_text in sections:
                provenance_header = (
                    f"[TICKER:{ticker.upper()} | SECTION:{section_label} | "
                    f"PERIOD:{period_of_report} | FORM:{form_type}]\n"
                )
                section_chunks = chunker.chunk(
                    section_text,
                    section_label=section_label,
                    ticker=ticker.upper(),
                    period=period_of_report,
                    form_type=form_type,
                    provenance_header=provenance_header,
                )
                all_chunks.extend(section_chunks)

            logger.debug(
                f"{ticker}: Split into {len(all_chunks)} chunks across {len(sections)} sections "
                f"({sum(1 for c in all_chunks if c.metadata.content_type == 'table')} tables, "
                f"{sum(1 for c in all_chunks if c.metadata.content_type == 'narrative')} narrative)"
            )

            batch_size = 8
            ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

            # Delete existing records for this ticker+accession
            conn.execute(
                "DELETE FROM edgar_embeddings WHERE ticker = ? AND accession = ?",
                [ticker, accession]
            )

            for i in range(0, len(all_chunks), batch_size):
                batch = all_chunks[i: i + batch_size]
                batch_texts = [c.text for c in batch]
                vecs = model.embed_documents(batch_texts)

                for j, chunk in enumerate(batch):
                    conn.execute("""
                        INSERT INTO edgar_embeddings
                            (ticker, accession, text, embedding, updated_at,
                             cik, section_id, form_type, period_of_report, chunk_index,
                             section_type, content_type)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, [
                        ticker, accession, chunk.text, vecs[j], ts,
                        cik,
                        chunk.metadata.section_label,
                        form_type,
                        period_of_report,
                        chunk.metadata.chunk_index,
                        chunk.metadata.section_type,
                        chunk.metadata.content_type,
                    ])

                total_chunks_stored += len(batch)
            conn.commit()

    if _DOWNLOAD_DIR.exists():
        shutil.rmtree(_DOWNLOAD_DIR, ignore_errors=True)

    logger.info(f"EDGAR embedding complete. Stored {total_chunks_stored} total chunks.")
    return total_chunks_stored


if __name__ == "__main__":
    tickers_arg = os.getenv("EMBED_TICKERS", "")
    if tickers_arg:
        tickers = [t.strip() for t in tickers_arg.split(",")]
    else:
        tickers = DEMO_TICKERS
    logger.info(f"Running EDGAR embedding for {len(tickers)} tickers: {tickers}")
    run_embed_edgar_etl(tickers)
