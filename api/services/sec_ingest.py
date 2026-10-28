"""
sec_ingest.py — structured SEC filing ingestion (iXBRL facts + statement tables).

This is the production entry point behind ``scripts.embed_edgar.run_embed_edgar_etl``:
it parses iXBRL facts from the primary document and any exhibit documents,
resolves continuation chains, normalizes exact numerics, parses statement
tables, reconciles table-derived values against XBRL facts on equivalent keys,
and persists facts + reconciliation rows atomically per (ticker, accession).

Fee-taxonomy facts (``ffd:*`` / filing-fee tables) live ONLY in the fee
provenance table: they are never financial values and never reconciled as
financials, so a filing-fee-only XBRL report yields explicit UNAVAILABLE
financial rows instead of a false match.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from typing import Any, Optional, Sequence

from api.services import sec_reconcile as sr
from api.services.sec_reconcile import (
    StatementFact,
    is_fee_fact,
    normalize_numeric,
    parse_statement_tables,
    reconcile,
    split_fee_vs_financial,
)

SEC_FINANCIAL_FACTS_TABLE = "sec_financial_facts"
SEC_FEE_FACTS_TABLE = "sec_fee_facts"

_FACT_COLUMNS = (
    "ticker, accession, issuer, concept, unit, duration, dimensions, value, "
    "source, origin_doc, document_id, fact_id, context_ref, unit_ref, "
    "scale, sign, decimals, fmt, raw_text, hidden"
)
_FACT_PLACEHOLDERS = ", ".join("?" for _ in range(20))

SEC_FINANCIAL_FACTS_DDL = (
    f"CREATE TABLE IF NOT EXISTS {SEC_FINANCIAL_FACTS_TABLE} ("
    "ticker VARCHAR NOT NULL, accession VARCHAR NOT NULL, issuer VARCHAR NOT NULL, "
    "concept VARCHAR NOT NULL, unit VARCHAR NOT NULL, duration VARCHAR NOT NULL, "
    "dimensions VARCHAR NOT NULL, value VARCHAR NOT NULL, source VARCHAR NOT NULL, "
    "origin_doc VARCHAR, document_id VARCHAR, fact_id VARCHAR, context_ref VARCHAR, "
    "unit_ref VARCHAR, scale INTEGER, sign VARCHAR, decimals VARCHAR, fmt VARCHAR, "
    "raw_text VARCHAR, hidden BOOLEAN)"
)
SEC_FEE_FACTS_DDL = (
    f"CREATE TABLE IF NOT EXISTS {SEC_FEE_FACTS_TABLE} ("
    "ticker VARCHAR NOT NULL, accession VARCHAR NOT NULL, issuer VARCHAR NOT NULL, "
    "concept VARCHAR NOT NULL, unit VARCHAR NOT NULL, duration VARCHAR NOT NULL, "
    "dimensions VARCHAR NOT NULL, value VARCHAR NOT NULL, source VARCHAR NOT NULL, "
    "origin_doc VARCHAR, document_id VARCHAR, fact_id VARCHAR, context_ref VARCHAR, "
    "unit_ref VARCHAR, scale INTEGER, sign VARCHAR, decimals VARCHAR, fmt VARCHAR, "
    "raw_text VARCHAR, hidden BOOLEAN)"
)
_FACT_INSERT_SQL = (
    f"INSERT INTO {SEC_FINANCIAL_FACTS_TABLE} ({_FACT_COLUMNS}) "
    f"VALUES ({_FACT_PLACEHOLDERS})"
)
_FEE_INSERT_SQL = (
    f"INSERT INTO {SEC_FEE_FACTS_TABLE} ({_FACT_COLUMNS}) "
    f"VALUES ({_FACT_PLACEHOLDERS})"
)

# --- statement-table labels -> XBRL concept local names --------------------

_LABEL_ALIASES = {
    "revenue": "revenues",
    "revenues": "revenues",
    "totalrevenue": "revenues",
    "totalrevenues": "revenues",
    "netsales": "revenues",
    "salesrevenue": "revenues",
    "salesrevenues": "revenues",
    "costofrevenue": "costofrevenue",
    "costofrevenues": "costofrevenue",
    "costofsales": "costofrevenue",
    "grossprofit": "grossprofit",
    "grossmargin": "grossprofit",
    "operatingincome": "operatingincomeloss",
    "operatingincomeloss": "operatingincomeloss",
    "incomefromoperations": "operatingincomeloss",
    "netincome": "netincomeloss",
    "netincomeloss": "netincomeloss",
    "netearnings": "netincomeloss",
    "netloss": "netincomeloss",
    "researchanddevelopment": "researchanddevelopmentexpense",
    "researchanddevelopmentexpense": "researchanddevelopmentexpense",
    "sellinggeneralandadministrative": "sellinggeneralandadministrativeexpense",
    "sellinggeneralandadministrativeexpense": "sellinggeneralandadministrativeexpense",
    "totalassets": "assets",
    "assets": "assets",
    "totalliabilities": "liabilities",
    "liabilities": "liabilities",
    "cashandcashequivalents": "cashandcashequivalentsatcarryingvalue",
    "cash": "cashandcashequivalentsatcarryingvalue",
    "stockholdersequity": "stockholdersequity",
    "shareholdersequity": "stockholdersequity",
}

_FEE_LABEL_RE = re.compile(r"(?:filing\s*fee|fee\s*table|fee\s*rate|fee\s*offset)", re.IGNORECASE)
_INSTANT_HEADER_RE = re.compile(r"\b(?:as\s+of|instant|balance\s+sheet)\b", re.IGNORECASE)
_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_MONTH_COUNT_WORDS = {"three": 3, "six": 6, "nine": 9, "twelve": 12}
_MONTHS_ENDED_DATE_RE = re.compile(
    r"\b(three|six|nine|twelve|\d{1,2})\s+months?\s+ended\s+"
    r"(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?\s+"
    r"(\d{1,2}),?\s+((?:19|20)\d{2})\b",
    re.IGNORECASE,
)
_MONTHS_ENDED_YEAR_RE = re.compile(
    r"\b(?:three|six|nine|twelve|\d{1,2})\s+months?\s+ended\s+"
    r"(?:19|20)\d{2}\b",
    re.IGNORECASE,
)
_QUARTER_ENDED_DATE_RE = re.compile(
    r"\b(?:fiscal\s+)?quarter\s+ended\s+"
    r"(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?\s+"
    r"(\d{1,2}),?\s+((?:19|20)\d{2})\b",
    re.IGNORECASE,
)
_QUARTER_ENDED_YEAR_RE = re.compile(
    r"\b(?:fiscal\s+)?quarter\s+ended\s+(?:19|20)\d{2}\b",
    re.IGNORECASE,
)
_YEAR_ENDED_DATE_RE = re.compile(
    r"\b(?:fiscal\s+)?year\s+ended\s+"
    r"(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?\s+"
    r"(\d{1,2}),?\s+((?:19|20)\d{2})\b",
    re.IGNORECASE,
)
_YEAR_ENDED_YEAR_RE = re.compile(
    r"\b(?:fiscal\s+)?year\s+ended\s+((?:19|20)\d{2})\b",
    re.IGNORECASE,
)
_PERIOD_YEAR_RE = re.compile(
    r"\b(?:fiscal\s+)?year\s+((?:19|20)\d{2})\b",
    re.IGNORECASE,
)

_MONTH_DAY_YEAR_RE = re.compile(
    r"\b(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?\s+"
    r"(\d{1,2}),?\s+((?:19|20)\d{2})\b",
    re.IGNORECASE,
)

# --- local XML helpers ------------------------------------------------------


def _localname(tag: Any) -> str:
    if not isinstance(tag, str):
        return ""
    if tag.startswith("{"):
        tag = tag.split("}", 1)[1]
    return tag.split(":", 1)[-1].lower()


def _text_of(el: Any) -> str:
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def _first_local_text(el: Any, name: str) -> Optional[str]:
    for child in el.iter():
        if child is not el and _localname(getattr(child, "tag", None)) == name:
            text = _text_of(child)
            if text:
                return text
    return None


def _typed_member_value(member: Any) -> str:
    """Stable text identity for a typed dimension member.

    The typed value is whatever the source text says (``Customer A``); no
    taxonomy default is invented. Multiple direct children keep their order
    with ``|`` so two different structures can never collapse to the same key.
    """
    children = [
        child for child in member
        if isinstance(getattr(child, "tag", None), str)
    ]
    values = [_text_of(child) for child in children]
    values = [value for value in values if value]
    return "|".join(values) if values else _text_of(member)


def _parse_contexts(doc: Any) -> dict:
    """id -> (period, dimensions, issuer) parsed from ``xbrli:context``.

    The issuer is the context's own entity identifier, never the caller's CIK.
    Explicit AND typed dimensions are preserved with their source values; a
    context with neither yields an empty dimension tuple, not a fabricated one.
    """
    contexts: dict = {}
    for el in doc.iter():
        if _localname(getattr(el, "tag", None)) != "context":
            continue
        cid = el.get("id")
        if not cid:
            continue
        instant = _first_local_text(el, "instant")
        start = _first_local_text(el, "startdate")
        end = _first_local_text(el, "enddate")
        if instant:
            period = instant
        elif start and end:
            period = f"{start}..{end}"
        else:
            period = ""
        dimensions: dict = {}
        for member in el.iter():
            name = _localname(getattr(member, "tag", None))
            if name not in ("explicitmember", "typedmember"):
                continue
            dimension = member.get("dimension")
            if not dimension:
                continue
            dimensions[dimension] = (
                _text_of(member) if name == "explicitmember"
                else _typed_member_value(member)
            )
        issuer = _first_local_text(el, "identifier") or ""
        contexts[cid] = (period, tuple(sorted(dimensions.items())), issuer)
    return contexts


def _normalize_unit(measure: str) -> str:
    text = (measure or "").strip()
    if not text:
        return ""
    return text.split(":")[-1].upper()


def _parse_units(doc: Any) -> dict:
    """id -> normalized unit string parsed from ``xbrli:unit``."""
    units: dict = {}
    for el in doc.iter():
        if _localname(getattr(el, "tag", None)) != "unit":
            continue
        uid = el.get("id")
        if not uid:
            continue
        measures = [
            _normalize_unit(_text_of(child))
            for child in el.iter()
            if child is not el and _localname(getattr(child, "tag", None)) == "measure"
        ]
        measures = [m for m in measures if m]
        units[uid] = "/".join(measures)
    return units


def _norm_label(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _unique_concept(candidates: Sequence[str]) -> Optional[str]:
    """Return the sole distinct concept, or ``None`` when ambiguous."""
    distinct: list = []
    for concept in candidates:
        if concept not in distinct:
            distinct.append(concept)
    return distinct[0] if len(distinct) == 1 else None


def _concept_for_label(label: str, concepts: Sequence[str]) -> str:
    """Conservative deterministic table-label -> XBRL concept mapping.

    An exact concept match wins. Alias and trailing-plural matches are only
    accepted when exactly ONE distinct concept matches; if two taxonomy
    concepts both look plausible, the label stays unresolved and reconciles as
    UNAVAILABLE instead of being silently bound to one of them.
    """
    stripped = (label or "").strip()
    if not stripped:
        return stripped
    lowered = stripped.lower()
    exact = [concept for concept in concepts if concept.lower() == lowered]
    if exact:
        return _unique_concept(exact) or stripped
    alias = _LABEL_ALIASES.get(_norm_label(stripped), _norm_label(stripped))
    alias_hits = [
        concept for concept in concepts
        if _norm_label(concept.split(":")[-1]) == alias
    ]
    if alias_hits:
        return _unique_concept(alias_hits) or stripped
    plural_hits = [
        concept for concept in concepts
        if _norm_label(concept.split(":")[-1]).rstrip("s") == alias.rstrip("s")
    ]
    if plural_hits:
        return _unique_concept(plural_hits) or stripped
    return stripped


def _iso_date(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}-{day.day:02d}"


def _start_before_months(end: date, months: int) -> date:
    """First day of an N-month period that ends on ``end`` (genuine duration)."""
    total = end.year * 12 + (end.month - 1) - int(months)
    year, month_index = divmod(total, 12)
    month = month_index + 1
    day = min(end.day, calendar.monthrange(year, month)[1])
    return date(year, month, day) + timedelta(days=1)


def _period_from_header(header: str) -> str:
    """Resolve a table column header to a source-established period.

    Instants require an explicit instant cue (``As of``/``balance sheet``).
    ``Year ended <date>`` and ``N months ended <date>`` establish a genuine
    duration. A partial header such as ``Three months ended 2026`` does NOT
    establish the missing day/month, so it stays unresolved (``""``) instead
    of being promoted to a calendar year.
    """
    text = header or ""
    instant = _INSTANT_HEADER_RE.search(text)
    month_day = _MONTH_DAY_YEAR_RE.search(text)

    if instant:
        if not month_day:
            return ""  # a bare year does not establish an instant day/month
        month = _MONTHS[month_day.group(1).lower()]
        return _iso_date(date(
            int(month_day.group(3)), month, int(month_day.group(2)),
        ))

    months_ended = _MONTHS_ENDED_DATE_RE.search(text)
    if months_ended:
        count_raw = months_ended.group(1).lower()
        count = _MONTH_COUNT_WORDS.get(count_raw, None)
        if count is None:
            try:
                count = int(count_raw)
            except ValueError:
                return ""
        end = date(
            int(months_ended.group(4)),
            _MONTHS[months_ended.group(2).lower()],
            int(months_ended.group(3)),
        )
        return f"{_iso_date(_start_before_months(end, count))}..{_iso_date(end)}"

    quarter_ended = _QUARTER_ENDED_DATE_RE.search(text)
    if quarter_ended:
        end = date(
            int(quarter_ended.group(3)),
            _MONTHS[quarter_ended.group(1).lower()],
            int(quarter_ended.group(2)),
        )
        return f"{_iso_date(_start_before_months(end, 3))}..{_iso_date(end)}"

    year_ended = _YEAR_ENDED_DATE_RE.search(text)
    if year_ended:
        end = date(
            int(year_ended.group(3)),
            _MONTHS[year_ended.group(1).lower()],
            int(year_ended.group(2)),
        )
        return f"{_iso_date(_start_before_months(end, 12))}..{_iso_date(end)}"

    if _MONTHS_ENDED_YEAR_RE.search(text) or _QUARTER_ENDED_YEAR_RE.search(text):
        return ""  # incomplete quarter header: end date not established

    year_ended_only = _YEAR_ENDED_YEAR_RE.search(text)
    if year_ended_only:
        year = int(year_ended_only.group(1))
        return f"{year:04d}-01-01..{year:04d}-12-31"

    period_year = _PERIOD_YEAR_RE.search(text)
    if period_year:
        year = int(period_year.group(1))
        return f"{year:04d}-01-01..{year:04d}-12-31"

    # A bare "December 31, 2026" or "2026" does not say instant vs duration.
    return ""


def _is_fee_label(label: str) -> bool:
    return is_fee_fact(label) or bool(_FEE_LABEL_RE.search(label or ""))


_CURRENCY_CODES = {
    "USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "CNY", "RMB", "HKD",
    "INR", "KRW", "TWD", "BRL", "MXN", "SEK", "NOK", "DKK", "SGD", "NZD",
    "ZAR",
}
_CURRENCY_CODE_RE = re.compile(
    r"\b(" + "|".join(sorted(_CURRENCY_CODES)) + r")\b", re.IGNORECASE
)
_CURRENCY_SYMBOLS = {"€": "EUR", "£": "GBP", "¥": "JPY", "₩": "KRW", "₹": "INR"}


def _currency_candidates(texts: Sequence[str]) -> set:
    found: set = set()
    for text in texts:
        found.update(
            match.group(1).upper() for match in _CURRENCY_CODE_RE.finditer(text or "")
        )
        for symbol, code in _CURRENCY_SYMBOLS.items():
            if symbol in (text or ""):
                found.add(code)
    return found


def _table_unit(table: Any, document_unit: str) -> str:
    """Currency from the table's own metadata, else the document's sole unit.

    An explicit caption/header currency always wins. Conflicting explicit
    currencies stay ambiguous (``""``) instead of picking one. Only when the
    table says nothing do we inherit the primary document's single declared
    XBRL unit — never a hard-coded USD default.
    """
    candidates = _currency_candidates([table.caption or "", *table.columns])
    if candidates:
        return next(iter(candidates)) if len(candidates) == 1 else ""
    return (document_unit or "").strip().upper()


def _issuer_key(value: Any) -> str:
    text = str(value or "").strip()
    digits = re.sub(r"\D", "", text)
    return str(int(digits)) if digits else text.lower()


def _issuers_agree(left: Any, right: Any) -> bool:
    return bool(left) and bool(right) and _issuer_key(left) == _issuer_key(right)


# --- fact extraction --------------------------------------------------------


def _xbrl_facts(html: str, *, ticker: str, accession: str,
                origin_doc: str) -> list:
    """Numeric iXBRL facts with full provenance from one document."""
    if not (html or "").strip():
        return []
    import lxml.html

    doc = lxml.html.document_fromstring(html)
    contexts = _parse_contexts(doc)
    units = _parse_units(doc)
    facts: list = []
    for index, fact in enumerate(sr.extract_ix_facts(html, document_id=origin_doc)):
        if not fact.numeric:
            continue
        numeric = normalize_numeric(
            fact.text, scale=fact.scale, sign=fact.sign,
            fmt=fact.fmt, decimals=fact.decimals,
        )
        if not numeric.supported or numeric.value is None:
            continue
        period, dimensions, issuer = contexts.get(
            fact.context_ref or "", ("", (), "")
        )
        scoped_id = (
            f"{origin_doc}#{fact.fact_id}" if fact.fact_id
            else f"{origin_doc}#fact{index}"
        )
        facts.append(StatementFact(
            issuer=issuer,
            concept=fact.concept,
            unit=units.get(fact.unit_ref or "", ""),
            duration=period,
            value=numeric.value,
            accession=accession,
            dimensions=dimensions,
            ticker=ticker,
            origin_doc=origin_doc,
            scale=fact.scale,
            sign=fact.sign,
            decimals=fact.decimals,
            fact_id=scoped_id,
            document_id=origin_doc,
            fmt=fact.fmt,
            raw_text=fact.text,
            context_ref=fact.context_ref,
            unit_ref=fact.unit_ref,
            hidden=fact.hidden,
        ))
    return facts


def _table_facts(primary_html: str, *, ticker: str, accession: str,
                 origin_doc: str, xbrl_concepts: Sequence[str],
                 table_issuer: str, document_unit: str) -> list:
    """Statement-table facts normalized with source-derived identity only."""
    facts: list = []
    for table in parse_statement_tables(primary_html):
        scale = table.scale if table.scale is not None else 0
        unit = _table_unit(table, document_unit)
        for row in table.rows:
            label = (row.label or "").strip()
            if not label or _is_fee_label(label):
                continue
            concept = _concept_for_label(label, xbrl_concepts)
            for cell in row.cells:
                if cell.value is None:
                    continue
                duration = _period_from_header(cell.column)
                value = sr._scale_exact(cell.value, int(scale)) if scale else cell.value
                facts.append(StatementFact(
                    issuer=table_issuer,
                    concept=concept,
                    unit=unit,
                    duration=duration,
                    value=value,
                    accession=accession,
                    dimensions=(),
                    ticker=ticker,
                    origin_doc=origin_doc,
                    scale=table.scale,
                    raw_text=cell.raw,
                    document_id=origin_doc,
                ))
    return facts


def _fact_payload(fact: StatementFact, *, ticker: str, accession: str,
                  source: str) -> tuple:
    dimensions = ";".join(f"{k}={v}" for k, v in fact.dimensions)
    return (
        ticker,
        accession,
        fact.issuer,
        fact.concept,
        fact.unit,
        fact.duration,
        dimensions,
        sr.decimal_text(fact.value),
        source,
        fact.origin_doc,
        fact.document_id,
        fact.fact_id,
        fact.context_ref,
        fact.unit_ref,
        fact.scale,
        fact.sign,
        fact.decimals,
        fact.fmt,
        fact.raw_text,
        fact.hidden,
    )


def _ensure_tables(conn: Any) -> None:
    conn.execute(SEC_FINANCIAL_FACTS_DDL)
    conn.execute(SEC_FEE_FACTS_DDL)
    conn.execute(sr.RECONCILIATION_DDL)
    for statement in (
        "ALTER TABLE sec_reconciliation ADD COLUMN IF NOT EXISTS table_candidates VARCHAR",
        "ALTER TABLE sec_reconciliation ADD COLUMN IF NOT EXISTS xbrl_candidates VARCHAR",
    ):
        try:
            conn.execute(statement)
        except Exception:
            pass


def _persist(conn: Any, *, ticker: str, accession: str,
             fact_rows: Sequence[tuple], fee_rows: Sequence[tuple],
             recon_rows: Sequence[sr.ReconciliationRow]) -> None:
    """Delete-before-insert all structured rows in ONE transaction."""
    _ensure_tables(conn)
    accession_key = (accession or "").replace("-", "")
    conn.execute("BEGIN TRANSACTION")
    try:
        for table in (SEC_FINANCIAL_FACTS_TABLE, SEC_FEE_FACTS_TABLE):
            conn.execute(
                f"DELETE FROM {table} WHERE ticker = ? "
                "AND replace(accession, '-', '') = ?",
                [ticker, accession_key],
            )
        conn.execute(
            "DELETE FROM sec_reconciliation WHERE ticker = ? "
            "AND replace(accession, '-', '') = ?",
            [ticker, accession_key],
        )
        if fact_rows:
            conn.executemany(_FACT_INSERT_SQL, list(fact_rows))
        if fee_rows:
            conn.executemany(_FEE_INSERT_SQL, list(fee_rows))
        sr.delete_and_insert_reconciliation(conn, list(recon_rows))
    except Exception:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def ingest_filing_structured(
    conn: Any,
    *,
    ticker: str,
    cik: str,
    accession: str,
    form_type: str,
    primary_html: str,
    exhibits: Sequence[tuple[str, str]] = (),
    primary_origin_doc: Optional[str] = None,
) -> dict:
    """Extract, reconcile and persist one filing's structured financial data.

    ``exhibits`` is ``[(html_content, origin_doc)]``; exhibit facts keep their
    own document-scoped ids and origin_doc provenance. Fee facts are persisted
    ONLY in the fee table and never reconciled as financials.
    """
    del form_type  # provenance is carried by origin_doc/document ids for now
    primary_doc = primary_origin_doc or f"{accession or 'primary'}.htm"
    origin_docs = [(primary_html or "", primary_doc)]
    origin_docs.extend((html or "", name) for html, name in exhibits)

    all_facts: list = []
    for html, name in origin_docs:
        all_facts.extend(_xbrl_facts(
            html, ticker=ticker, accession=accession, origin_doc=name,
        ))

    fee_facts, financial_facts = split_fee_vs_financial(all_facts)

    # Table identity is bound to the primary document ONLY when the document's
    # context issuer(s) unanimously establish it AND the caller's CIK agrees.
    # A caller/context conflict leaves the table issuer unestablished ("") so
    # no table row can be declared equivalent to that filing's XBRL facts.
    financial_issuers = {f.issuer.strip() for f in financial_facts if f.issuer.strip()}
    document_issuer = (
        next(iter(financial_issuers)) if len(financial_issuers) == 1 else ""
    )
    table_issuer = (
        document_issuer
        if document_issuer and (not cik or _issuers_agree(document_issuer, cik))
        else ""
    )
    financial_units = {f.unit.strip() for f in financial_facts if f.unit.strip()}
    document_unit = (
        next(iter(financial_units)) if len(financial_units) == 1 else ""
    )

    xbrl_concepts = [f.concept for f in financial_facts]
    table_facts = _table_facts(
        primary_html or "",
        ticker=ticker, accession=accession,
        origin_doc=primary_doc, xbrl_concepts=xbrl_concepts,
        table_issuer=table_issuer, document_unit=document_unit,
    )
    recon_rows = reconcile(table_facts, financial_facts)

    fact_rows = [
        _fact_payload(f, ticker=ticker, accession=accession, source="table")
        for f in table_facts
    ] + [
        _fact_payload(f, ticker=ticker, accession=accession, source="xbrl")
        for f in financial_facts
    ]
    fee_rows = [
        _fact_payload(f, ticker=ticker, accession=accession, source="xbrl")
        for f in fee_facts
    ]

    _persist(conn, ticker=ticker, accession=accession,
             fact_rows=fact_rows, fee_rows=fee_rows, recon_rows=recon_rows)
    return {
        "table_facts": len(table_facts),
        "financial_facts": len(financial_facts),
        "fee_facts": len(fee_facts),
        "reconciliation": len(recon_rows),
    }
