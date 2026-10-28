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
import gc
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
from api.services.sec_ingest import ingest_filing_structured
from api.services.structure_chunker import StructureChunker

from api.config import Config, TICKER_TO_CIK

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
    # ── Aerospace / Launch ──
    "SPCX": "0001181412",  # Space Exploration Technologies (SpaceX) — IPO'd 2026, S-1 / 424B4 prospectus
    "RKLB": "0001819994",  # Rocket Lab USA, Inc.
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

# Central config is authoritative for every application-supported ticker,
# including internal prospectus corpus keys such as ANTH.
_TICKER_CIK.update(TICKER_TO_CIK)

# All tickers for ingestion
DEMO_TICKERS: List[str] = [
    # Private / pre-ticker issuer (S-1 prospectus; internal key)
    "ANTH",
    # Aerospace / Launch (IPO prospectus, not a 10-K filer yet)
    "SPCX",
    # Aerospace / Launch (10-K filer)
    "RKLB",
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


# S-1 / 424B4 IPO prospectus headings, in the order they appear in a prospectus.
# Unlike 10-K "Item N" headings these are plain titles, so they are matched only
# as a STANDALONE heading (the whole line, see _prospectus_heading_re) and the
# extractor picks one ordered chain through them (_extract_prospectus_sections).
# Entries with a label are stored as sections; entries with label None are only
# delimiters that end the preceding section (e.g. so Business stops at
# "Management" instead of running to end-of-document, and Use of Proceeds stops
# at "Dividend Policy").
_PROSPECTUS_HEADINGS: List[tuple[str | None, str]] = [
    ("prospectus_summary", r"prospectus\s+summary"),
    ("risk_factors",       r"risk\s+factors"),
    (None, r"special\s+note\s+regarding\s+forward[-\s]looking\s+statements"),
    (None, r"(?:industry|market)(?:,?\s+(?:market|industry))?\s+(?:and\s+other\s+)?data"),
    ("use_of_proceeds",    r"use\s+of\s+proceeds"),
    (None, r"dividend\s+policy"),
    ("capitalization",     r"capitalization"),
    ("dilution",           r"dilution"),
    ("md_and_a",           r"management['’]?s\s+discussion\s+and\s+analysis"
                           r"(?:\s+of\s+financial\s+condition\s+and\s+results\s+of\s+operations)?"),
    ("business",           r"business(?:\s+overview)?"),
    (None, r"our\s+governance\s+structure\s+and\s+its\s+goals"),
    (None, r"management"),
    (None, r"(?:executive|director)\s+compensation"),
    (None, r"certain\s+relationships\s+and\s+related[-\s]party\s+transactions"),
    (None, r"principal(?:\s+and\s+selling)?\s+(?:stock|share)holders"),
    (None, r"description\s+of\s+(?:capital\s+stock|share\s+capital)"),
    (None, r"shares\s+eligible\s+for\s+future\s+sale"),
    (None, r"underwriting(?:\s*\(conflicts\s+of\s+interest\))?"),
    (None, r"legal\s+matters"),
    (None, r"experts"),
    (None, r"where\s+you\s+can\s+find\s+(?:more|additional)\s+information"),
    (None, r"index\s+to\s+(?:consolidated\s+)?financial\s+statements"),
]

# Forms whose text is a prospectus (titled sections), not a 10-K-style report.
_PROSPECTUS_FORMS = {"S-1", "S-1/A", "424B4", "424B3", "424B1", "F-1", "F-1/A"}

# Default form fetch order: periodic reports first (existing filers get their
# 10-K), then IPO prospectus forms as a fallback for newly-public companies that
# have no periodic report yet (e.g. SPCX). 424B4 = final prospectus, then the
# latest amendment, then the original S-1.
_DEFAULT_FORM_TYPES = ["10-K", "20-F", "10-Q", "424B4", "S-1/A", "S-1"]

# Forms sec-edgar-downloader rejects ("'S-1/A' forms are not supported").
_DOWNLOADER_UNSUPPORTED_FORMS = {"S-1/A", "F-1/A"}

# Internal corpus keys which are not EDGAR ticker symbols. Keep historical
# aliases such as SPCX on their existing lookup behavior.
_CIK_LOOKUP_ALIASES = {"ANTH"}


def _filing_lookup_key(ticker: str) -> str:
    """Return the EDGAR lookup identifier while preserving the corpus key."""
    normalized = ticker.upper()
    if normalized in _CIK_LOOKUP_ALIASES:
        return _TICKER_CIK[normalized]
    return ticker


def _downloader_filing_dir(lookup_key: str, form_type: str) -> Path:
    """Return the directory layout used by sec-edgar-downloader.

    Numeric lookup keys are already normalized to the package's zero-padded
    10-digit CIK format by ``_filing_lookup_key`` / ``TICKER_TO_CIK``.
    """
    return _DOWNLOAD_DIR / "sec-edgar-filings" / lookup_key / form_type


# Running page furniture left at the end of a slice ("Table of Contents" page
# header, bare page number) when the next heading sits at the top of a page.
_PAGE_FURNITURE_TAIL = re.compile(r"(?:\n[ \t]*(?:table\s+of\s+contents|\d{1,3})[ \t]*)+\s*$", re.IGNORECASE)


def _prospectus_heading_re(pattern: str) -> re.Pattern[str]:
    """Match ``pattern`` only when it is the ENTIRE line (optional trailing . or :).

    Whitespace inside the pattern may span line breaks so a heading wrapped over
    two lines still matches. A body line that merely *starts* with the word
    ("business, financial condition, and results of operations ...") does not.
    """
    return re.compile(r"(?im)^[ \t]*" + pattern + r"[ \t]*[.:]?[ \t]*$")


def _extract_prospectus_sections(text: str) -> List[tuple[str, str]]:
    """
    Extract the main sections of an IPO prospectus (S-1 / 424B4) from normalized
    text in which headings sit on their own line (see ``parse_prospectus_file``).

    Strategy (ordered, exact main-heading boundaries):

    1. Every heading in ``_PROSPECTUS_HEADINGS`` is located as a standalone line.
       Those hits include the table of contents and "The Offering" summary rows
       ("Use of proceeds", "Risk Factors"), which look like headings but sit only
       a few chars from the next heading.
    2. One candidate is chosen per label such that the chosen starts follow the
       canonical prospectus order (Summary -> Risk Factors -> Use of Proceeds ->
       Capitalization -> Dilution -> MD&A -> Business), maximizing the summed
       distance from each chosen heading to the next heading-like line of any
       kind. Real section bodies are long; TOC / summary-table hits are not, so
       they lose even when they come first. (A greedy "first match" or "longest
       slice ignoring order" pick cannot do this - it is what truncated Risk
       Factors at a body paragraph starting "business, financial condition".)
    3. A section ends at the next chosen heading or, if sooner, the first
       delimiter heading (Dividend Policy, Management, Underwriting, ...) that is
       canonically positioned after it, so Business does not run to end of file.

    Falls back to the full text if no section of >200 chars is found.
    """
    stages = _PROSPECTUS_HEADINGS
    hits: List[tuple[int, int]] = []  # (char offset, stage index)
    for stage, (_, pat) in enumerate(stages):
        for m in _prospectus_heading_re(pat).finditer(text):
            hits.append((m.start(), stage))
    hits.sort()
    if not hits:
        return [("full_text", text)]

    # Score each hit by the distance to the next hit of ANY stage (or EOF). A real
    # section is closed by a LATER canonical heading, so a hit whose next hit is
    # of the same or an earlier stage is a reference row (e.g. "Risk factors" in
    # "The Offering" table, followed further down by the real heading) and scores 0.
    positions = [pos for pos, _ in hits]
    score = [
        0 if i + 1 < len(hits) and hits[i + 1][1] <= stage
        else (positions[i + 1] if i + 1 < len(hits) else len(text)) - pos
        for i, (pos, stage) in enumerate(hits)
    ]

    # Best ordered chain over the labeled stages (hits are sorted by position,
    # labeled stages are increasing, so only compare to earlier hits).
    labeled = [i for i, hit in enumerate(hits) if stages[hit[1]][0] is not None]
    best: Dict[int, tuple[int, int | None]] = {}  # hit idx -> (chain score, prev hit idx)
    for i in labeled:
        stage_i = hits[i][1]
        prev, prev_total = None, 0
        for j in labeled:
            if j >= i:
                break
            if hits[j][1] < stage_i and positions[j] < positions[i] and best[j][0] > prev_total:
                prev, prev_total = j, best[j][0]
        best[i] = (prev_total + score[i], prev)
    if not best:
        return [("full_text", text)]
    tail: int | None = max(best, key=lambda k: best[k][0])
    chain: List[int] = []
    while tail is not None:
        chain.append(tail)
        tail = best[tail][1]
    chain.reverse()

    extracted: List[tuple[str, str]] = []
    for n, i in enumerate(chain):
        pos, stage = hits[i]
        end = positions[chain[n + 1]] if n + 1 < len(chain) else len(text)
        next_stage = hits[chain[n + 1]][1] if n + 1 < len(chain) else len(stages)
        for hpos, hstage in hits:
            if hpos > pos and hpos < end and stage < hstage < next_stage and stages[hstage][0] is None:
                end = hpos
                break
        segment = _PAGE_FURNITURE_TAIL.sub("", text[pos:end]).strip()
        if len(segment) > 200:
            extracted.append((stages[stage][0], segment))

    if not extracted:
        return [("full_text", text)]
    logger.debug(f"Extracted {len(extracted)} prospectus sections")
    return extracted


def _canonical_accession(accession: str) -> str:
    """Return the dashed form (0001628280-26-067168) used by production rows.

    sec-edgar-downloader names its directories with dashes, edgartools'
    ``accession_number`` is dashed too but this module used to strip them; one
    canonical form keeps ticker+accession deletes/idempotent re-runs working
    whichever fetch path produced the filing.
    """
    digits = re.sub(r"\D", "", accession)
    if len(digits) == 18:
        return f"{digits[:10]}-{digits[10:12]}-{digits[12:]}"
    return accession.strip()


def _fetch_filing_with_edgartools(ticker: str, form_types: List[str] = None) -> tuple[str, str, str]:
    """Download the latest filing using edgartools (uses SEC REST API, not blocked from cloud).
    Returns (file_path, form_type, accession_number)."""
    from edgar import Company
    from api.services._edgar_identity import ensure_edgar_identity

    ensure_edgar_identity()

    if form_types is None:
        form_types = _DEFAULT_FORM_TYPES

    try:
        company = Company(_filing_lookup_key(ticker))
        for form_type in form_types:
            try:
                filings = company.get_filings(form=form_type)
                if filings.empty:
                    continue
                filing = filings.latest(1)
                if filing is None:
                    continue
            except Exception as e:
                logger.debug(f"No {form_type} filing for {ticker}: {e}")
                continue

            accession = _canonical_accession(filing.accession_number)
            safe_dir = _DOWNLOAD_DIR / "sec-edgar-filings" / ticker / form_type / accession
            safe_dir.mkdir(parents=True, exist_ok=True)

            html_path = safe_dir / "primary-document.html"
            if not html_path.exists():
                try:
                    # Prefer the real structured HTML (inline XBRL context,
                    # tables, ix: tags). filing.text() is flattened text and
                    # must not masquerade as primary-document.html when HTML
                    # is available, or structured ingestion loses every tag.
                    structured_html = filing.html()
                    if isinstance(structured_html, str) and structured_html.strip():
                        html_path.write_text(structured_html, encoding="utf-8")
                    else:
                        full_text = filing.text()
                        html_path.write_text(full_text, encoding="utf-8")
                except Exception as e:
                    logger.warning(f"Could not get full text for {ticker} {form_type}: {e}")
                    continue

            logger.info(f"Found {form_type} for {ticker} via edgartools")
            return str(html_path), form_type, accession

    except Exception as e:
        logger.warning(f"edgartools failed for {ticker}: {e}")

    return "", "", ""


def _fetch_filing_with_downloader(ticker: str, form_types: List[str] = None) -> tuple[str, str]:
    """Download the latest filing for the given form types. Returns (file_path, form_type).
    Falls back to edgartools if sec_edgar_downloader is blocked.

    The form order in ``form_types`` is honoured on both fetch paths: forms the
    downloader cannot fetch (``_DOWNLOADER_UNSUPPORTED_FORMS``, e.g. S-1/A) are
    tried through edgartools at their place in the order, instead of being
    skipped so a stale original S-1 wins over the latest amendment.
    """
    if form_types is None:
        form_types = _DEFAULT_FORM_TYPES

    dl = Downloader(_COMPANY, _EMAIL, _DOWNLOAD_DIR)
    lookup_key = _filing_lookup_key(ticker)

    for form_type in form_types:
        if form_type in _DOWNLOADER_UNSUPPORTED_FORMS:
            path, form, _ = _fetch_filing_with_edgartools(ticker, [form_type])
            if path:
                return path, form
            continue
        try:
            num_downloaded = dl.get(form_type, lookup_key, limit=1, download_details=True)
            if num_downloaded == 0:
                continue

            ticker_dir = _downloader_filing_dir(lookup_key, form_type)
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

    # Fallback: try edgartools
    logger.info(f"sec_edgar_downloader failed for {ticker}, trying edgartools...")
    path, form, _ = _fetch_filing_with_edgartools(ticker, form_types)
    return path, form


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
    Item header appears. Uses the LONGEST match per section to avoid picking
    table-of-contents entries over the actual section body.

    Falls back to the full text under label 'full_text' if none found.
    """
    extracted: List[tuple[str, str]] = []

    for label, pattern in _TARGET_SECTIONS.items():
        # Use a bounded match: find the section start, then capture until the next
        # item heading or end of text. The [^\n]*? approach limits cross-line backtracking.
        section_re = re.compile(
            r"(?:^|\n)(\s*" + pattern + r"[^\n]*(?:\n(?!\s*item\s+\d)[^\n]*)*)",
            re.IGNORECASE | re.MULTILINE,
        )
        # Pick the longest match — TOC entries are short, real sections are long.
        # re.search() would return the TOC entry first; re.finditer() lets us
        # compare all matches and keep the one with the most content.
        best_match = None
        best_len = 0
        for m in section_re.finditer(text):
            match_len = len(m.group(1))
            if match_len > best_len:
                best_match = m
                best_len = match_len
        if best_match:
            section_text = best_match.group(1).strip()
            if len(section_text) > 200:
                extracted.append((label, section_text))

    if not extracted:
        logger.debug("No target sections found — falling back to full text")
        return [("full_text", text)]

    # Guard against table-of-contents-only matches. `.search()` returns the
    # FIRST occurrence of each Item header, which in many filings is the TOC
    # line (e.g. "Item 1. Business .... 5"), not the real section body deeper
    # in the document. Those slices are tiny, so when the kept sections cover
    # only a sliver of the filing the extraction has clearly latched onto the
    # TOC — fall back to full-text chunking, which covers the whole document
    # (this is what foreign 20-F filers already hit, and it yields rich,
    # well-distributed chunks).
    covered = sum(len(t) for _, t in extracted)
    if len(text) > 0 and covered < 0.15 * len(text):
        logger.debug(
            f"Section coverage {covered}/{len(text)} (<15%) looks like a TOC-only "
            f"match — falling back to full text"
        )
        return [("full_text", text)]

    logger.debug(f"Extracted {len(extracted)} sections")
    return extracted


def _clean_text(text: str) -> str:
    """Remove excessive whitespace and repeated blank lines left by get_text()."""
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_html_file(file_path: str) -> tuple[str, str]:
    """
    Parse document once: supports PDF, XML, and HTML. Strip script/style/iXBRL tags,
    extract visible text, clean whitespace. Returns (clean_full_text, raw_content).
    """
    try:
        path_lower = file_path.lower()
        if path_lower.endswith(".pdf"):
            try:
                import pypdf
                reader = pypdf.PdfReader(file_path)
                clean_text = ""
                for page in reader.pages:
                    clean_text += (page.extract_text() or "") + "\n"
                return _clean_text(clean_text), ""
            except Exception as pdf_err:
                logger.warning(f"Failed to parse PDF {file_path}: {pdf_err}")
                return "", ""

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        is_xml = path_lower.endswith(".xml") or content.strip().startswith("<?xml")
        parser = "xml" if is_xml else "lxml"
        soup = BeautifulSoup(content, parser)

        # Drop script/style and the iXBRL header, but UNWRAP inline fact tags so
        # their rendered values stay in the extracted text (decomposing them
        # silently deleted every inline numeric value from the corpus).
        for tag in soup(["script", "style", "ix:header"]):
            tag.decompose()
        for tag in soup(["ix:nonnumeric", "ix:nonfraction"]):
            tag.unwrap()

        clean = _clean_text(soup.get_text(separator="\n", strip=True))
        return clean, content
    except Exception as e:
        logger.warning(f"Failed to parse {file_path}: {e}")
        return "", ""


_BLOCK_TAGS = ["div", "p", "tr", "td", "th", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6",
               "table", "section", "ul", "ol", "body"]
_STYLE_PT = {k: re.compile(rf"{k}:\s*(-?[\d.]+)pt") for k in ("left", "width")}


def _html_to_layout_text(content: str) -> str:
    """Layout-aware HTML -> text for positioned (PDF-style) SEC prospectuses.

    ``BeautifulSoup.get_text("\\n")`` puts every inline ``<font>``/``<span>``
    fragment on its own line, so a heading drawn as ``Use`` ``of`` ``Proceeds``
    (or ``Prospectus`` ``Summary``) never forms a heading line. Here only block
    elements (div/p/tr/...) break lines and the fragments inside one visual line
    are concatenated; a space is inserted where positioned fragments are visibly
    apart (``left`` beyond the previous fragment's ``left + width``).
    """
    soup = BeautifulSoup(content, "lxml")
    for tag in soup(["script", "style", "ix:header"]):
        tag.decompose()
    for tag in soup(["ix:nonnumeric", "ix:nonfraction"]):
        tag.unwrap()

    for line in soup.find_all("div"):
        prev_end = None
        for frag in line.find_all("font", recursive=False):
            style = frag.get("style", "")
            left, width = (_STYLE_PT[k].search(style) for k in ("left", "width"))
            if left and prev_end is not None and float(left.group(1)) - prev_end > 1.0:
                frag.insert_before(" ")
            prev_end = float(left.group(1)) + float(width.group(1)) if left and width else None

    for tag in soup.find_all(_BLOCK_TAGS):
        tag.insert_before("\n")
        tag.insert_after("\n")
    text = soup.get_text("")
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r" ?\n[ \n]*", "\n", text)
    return text.strip()


def parse_prospectus_file(file_path: str) -> tuple[str, str]:
    """Return (normalized_text, raw_content) for an S-1 / 424B4 style prospectus.

    Both fetch paths feed the same section splitter, so both are reduced to ONE
    representation: plain text with headings on their own line. The downloader
    saves raw positioned HTML (-> ``_html_to_layout_text``); edgartools saves
    ``filing.text()`` which is already text (used as-is, only whitespace and the
    repeated "Table of Contents" page header are normalized).
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logger.warning(f"Failed to read {file_path}: {e}")
        return "", ""

    if re.search(r"<(?:html|body|div|p|font|table)\b", content[:200_000], re.IGNORECASE):
        try:
            text = _html_to_layout_text(content)
        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            return "", ""
    else:
        text = re.sub(r"[ \t\xa0]+", " ", content)
        text = re.sub(r" ?\n[ \n]*", "\n", text)
    text = re.sub(r"(?im)^table of contents$\n?", "", text)
    return text.strip(), content


# iXBRL exhibit filenames that carry facts beside the primary document:
# filing-fee exhibits (``exfilingfees``) and exhibit 107-style names.
_IXBRL_EXHIBIT_RE = re.compile(
    r"(?:exfilingfees|ex[-_]?107|exhibit[-_]?107)", re.IGNORECASE
)
_EXHIBIT_DOCUMENT_TYPE_RE = re.compile(
    r"(?:EX(?:HIBIT)?[\s\-_]*107|FILING[\s\-_]*FEE)", re.IGNORECASE
)
_HTML_EXHIBIT_SUFFIXES = (".htm", ".html", ".xhtml")
_SUBMISSION_FILENAME = "full-submission.txt"
_DOCUMENT_BLOCK_RE = re.compile(r"<DOCUMENT>(.*?)</DOCUMENT>", re.IGNORECASE | re.DOTALL)
_DOCUMENT_TYPE_RE = re.compile(r"<TYPE>\s*([^\r\n<]+)", re.IGNORECASE)
_DOCUMENT_FILENAME_RE = re.compile(r"<FILENAME>\s*([^\r\n<]+)", re.IGNORECASE)
_DOCUMENT_TEXT_RE = re.compile(r"<TEXT>(.*?)</TEXT>", re.IGNORECASE | re.DOTALL)
_STRUCTURED_HTML_RE = re.compile(
    r"<(?:html|body|table|ix:nonfraction)\b", re.IGNORECASE
)


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.debug(f"Could not read {path}: {exc}")
        return ""


def _submission_documents(submission_text: str) -> List[dict]:
    """Parse ``full-submission.txt`` DOCUMENT blocks into type/filename/text.

    The downloader writes the whole SEC submission (primary + exhibits) as this
    one artifact, so attached exhibit HTML must be split from here rather than
    assumed to exist as a sibling file.
    """
    documents: List[dict] = []
    for block in _DOCUMENT_BLOCK_RE.findall(submission_text or ""):
        text_match = _DOCUMENT_TEXT_RE.search(block)
        if text_match is None:
            continue
        type_match = _DOCUMENT_TYPE_RE.search(block)
        filename_match = _DOCUMENT_FILENAME_RE.search(block)
        documents.append({
            "type": type_match.group(1).strip() if type_match else "",
            "filename": filename_match.group(1).strip() if filename_match else "",
            "text": text_match.group(1).strip("\r\n"),
        })
    return documents


def _is_exhibit_document(document: dict) -> bool:
    name = document.get("filename") or ""
    doc_type = document.get("type") or ""
    return bool(
        _IXBRL_EXHIBIT_RE.search(name)
        or _EXHIBIT_DOCUMENT_TYPE_RE.search(doc_type)
        or _IXBRL_EXHIBIT_RE.search(doc_type)
    )


def _looks_structured_html(content: str) -> bool:
    return bool(_STRUCTURED_HTML_RE.search(content or ""))


def _is_primary_document(document: dict) -> bool:
    """True for the filing's primary structured document in a submission."""
    if _is_exhibit_document(document):
        return False
    doc_type = (document.get("type") or "").strip().upper()
    if doc_type.startswith("EX") or doc_type in {
        "GRAPHIC", "IMAGE", "COVER", "CORRESP", "XML", "XBRL INSTANCE DOCUMENT",
    }:
        return False
    return _looks_structured_html(document.get("text", ""))


def _find_ixbrl_exhibits(primary_path: str) -> List[tuple[str, str]]:
    """Acquire iXBRL exhibit documents from the real downloader artifacts.

    Attached documents are split from ``full-submission.txt`` first (the only
    artifact the installed downloader actually writes besides the primary
    document). Standalone sibling exhibit HTML is still accepted for callers
    that materialize files themselves, with duplicate filenames de-duplicated.
    Returns ``[(html_content, filename)]``; filename is the origin_doc.
    """
    try:
        primary = Path(primary_path)
        directory = primary.parent
        rows: List[tuple[str, str]] = []
        seen: set = set()

        submission = directory / _SUBMISSION_FILENAME
        if submission.is_file():
            for document in _submission_documents(_read_text_file(submission)):
                if not _is_exhibit_document(document) or not document["text"]:
                    continue
                name = document["filename"] or f"submission-document-{len(rows)}"
                if name in seen:
                    continue
                seen.add(name)
                rows.append((document["text"], name))

        for candidate in sorted(directory.iterdir()):
            if not candidate.is_file() or candidate == primary:
                continue
            name = candidate.name
            if name == _SUBMISSION_FILENAME:
                continue
            if not name.lower().endswith(_HTML_EXHIBIT_SUFFIXES):
                continue
            if not _IXBRL_EXHIBIT_RE.search(name) or name in seen:
                continue
            seen.add(name)
            rows.append((
                candidate.read_text(encoding="utf-8", errors="replace"), name,
            ))
        return rows
    except OSError as exc:
        logger.debug(f"Could not scan exhibits beside {primary_path}: {exc}")
        return []


def _acquire_filing_documents(primary_path: str) -> tuple[str, str, List[tuple[str, str]]]:
    """Return ``(primary_html, primary_origin_doc, exhibits)`` for one filing.

    Prefers the downloaded primary document. If it is missing or was flattened
    to plain text, the structured primary DOCUMENT block in
    ``full-submission.txt`` is materialized in its place so downstream parsers
    and structured ingestion see real tags/context/tables.
    """
    primary = Path(primary_path)
    primary_name = primary.name
    primary_html = _read_text_file(primary)

    if not _looks_structured_html(primary_html):
        submission = primary.parent / _SUBMISSION_FILENAME
        if submission.is_file():
            documents = _submission_documents(_read_text_file(submission))
            candidates = [document for document in documents
                          if _is_primary_document(document)]
            chosen = next(
                (document for document in candidates
                 if (document.get("filename") or "") == primary.name),
                candidates[0] if candidates else None,
            )
            if chosen is not None:
                primary_html = chosen["text"]
                primary_name = chosen["filename"] or primary_name
                try:
                    primary.write_text(primary_html, encoding="utf-8")
                except OSError as exc:
                    logger.debug(f"Could not materialize structured primary: {exc}")

    return primary_html, primary_name, _find_ixbrl_exhibits(str(primary))


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


def _reset_incompatible_embeddings(conn, expected_dim: int) -> bool:
    """Clear stored vectors when their dimensions do not match the active model."""
    stored_dims = {
        int(row[0])
        for row in conn.execute(
            "SELECT DISTINCT len(embedding) FROM edgar_embeddings WHERE embedding IS NOT NULL"
        ).fetchall()
        if row[0] is not None
    }
    if not stored_dims or stored_dims == {expected_dim}:
        return False

    logger.warning(
        "Stored embedding dimensions {} do not match configured dimension {}; rebuilding corpus",
        sorted(stored_dims), expected_dim,
    )
    conn.execute("DELETE FROM edgar_embeddings")
    conn.commit()
    return True


def run_embed_edgar_etl(tickers: List[str] = None, batch_size: int = 4) -> int:
    """
    Main ETL job: use sec-edgar-downloader to fetch 10-K/20-F/10-Q, chunk, embed, and store in DuckDB.
    Defaults to DEMO_TICKERS if no tickers provided.
    
    Processes tickers in batches with explicit memory cleanup to stay within HF Space limits.
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
    if model is None:
        logger.error("No embedding model available — cannot generate vectors. Ensure EMBEDDING_PROVIDER and HF_TOKEN are set.")
        return 0
    total_chunks_stored = 0

    with duckdb.connect(DB_PATH) as conn:
        try:
            conn.execute("LOAD vss")
        except Exception:
            pass

        # Ensure schema is up to date
        _ensure_schema(conn)

        # Append-only for data this run does not target: no global reset here.
        # (A dimension-based reset used to wipe every ticker's rows whenever the
        # corpus held another dimension.) Only the targeted ticker+accession rows
        # are replaced, below.

        for ticker in tickers:
            logger.info(f"Processing filings for {ticker}...")
            # Pre-bind so the finally's `del` is always safe even if a ticker
            # fails before these are assigned (e.g. download/parse error).
            text = raw_html = sections = all_chunks = None

            try:
                file_path, form_type = _fetch_filing_with_downloader(ticker, _DEFAULT_FORM_TYPES)

                if not file_path:
                    logger.warning(f"No filings downloaded for {ticker}.")
                    continue

                # Acquire the primary structured document and attached exhibit
                # documents from the real downloader artifacts before parsing,
                # so a flattened primary is replaced and full-submission.txt
                # exhibits are available to structured ingestion.
                acquired_primary, primary_origin_doc, exhibits = (
                    _acquire_filing_documents(file_path)
                )

                if form_type.upper() in _PROSPECTUS_FORMS:
                    text, raw_html = parse_prospectus_file(file_path)
                else:
                    text, raw_html = parse_html_file(file_path)

                if not text:
                    continue

                # Extract period_of_report from HTML or accession dir name
                accession_dir_name = Path(file_path).parent.name
                period_of_report = _extract_period_of_report(raw_html, accession_dir_name)
                accession = _canonical_accession(accession_dir_name)

                cik = _TICKER_CIK.get(ticker.upper(), "")

                # Structured fact extraction + reconciliation into the real
                # ingestion path. Atomic per (ticker, accession); a failure here
                # is caught by this ticker's try/except and leaves no partial
                # structured rows for its own filing.
                ingest_filing_structured(
                    conn,
                    ticker=ticker,
                    cik=cik,
                    accession=accession,
                    form_type=form_type,
                    primary_html=acquired_primary or raw_html,
                    exhibits=exhibits,
                    primary_origin_doc=primary_origin_doc,
                )

                # Section-aware chunking to preserve provenance. parse_html_file
                # already returns the cleaned full text, so split it directly. IPO
                # prospectus forms (S-1 / 424B4) use titled sections, not 10-K
                # "Item N" headings, so route them through the prospectus splitter.
                if form_type.upper() in _PROSPECTUS_FORMS:
                    sections = _extract_prospectus_sections(text)
                else:
                    sections = _extract_sections_with_labels(text)

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

                ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

                # Delete existing records for this ticker+accession. Compare with
                # dashes stripped on both sides so rows written by either fetch
                # path (dashed or undashed) are replaced, not duplicated.
                conn.execute(
                    "DELETE FROM edgar_embeddings WHERE ticker = ? "
                    "AND replace(accession, '-', '') = ?",
                    [ticker, accession.replace("-", "")]
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
            except Exception as e:
                logger.error(f"Failed to process {ticker}: {e}")
                continue
            finally:
                # Release this filing's memory before the next ticker — the raw
                # HTML (10-50MB), parsed tree, and chunk objects otherwise pile
                # up across all 31 tickers and OOM the 16Gi Space.
                del text, raw_html, sections, all_chunks
                gc.collect()

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
