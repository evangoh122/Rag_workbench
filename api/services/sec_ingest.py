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

import re
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
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}
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


def _parse_contexts(doc: Any) -> dict:
    """id -> (resolved period, dimensions) parsed from ``xbrli:context``."""
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
            if _localname(getattr(member, "tag", None)) != "explicitmember":
                continue
            dimension = member.get("dimension")
            if dimension:
                dimensions[dimension] = _text_of(member)
        contexts[cid] = (period, tuple(sorted(dimensions.items())))
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


def _concept_for_label(label: str, concepts: Sequence[str]) -> str:
    """Best deterministic table-label -> XBRL concept mapping.

    An exact concept match wins; otherwise a small alias table and a trailing
    plural-S comparison resolve common statement labels. Unmapped labels stay
    as their own key, which reconciles as UNAVAILABLE rather than guessing.
    """
    stripped = (label or "").strip()
    if not stripped:
        return stripped
    lowered = stripped.lower()
    for concept in concepts:
        if concept.lower() == lowered:
            return concept
    alias = _LABEL_ALIASES.get(_norm_label(stripped), _norm_label(stripped))
    for concept in concepts:
        local = _norm_label(concept.split(":")[-1])
        if local == alias:
            return concept
    for concept in concepts:
        local = _norm_label(concept.split(":")[-1])
        if local.rstrip("s") == alias.rstrip("s"):
            return concept
    return stripped


def _period_from_header(header: str) -> str:
    """Resolve a table column header to an instant date or ``start..end`` period."""
    text = header or ""
    month_day = _MONTH_DAY_YEAR_RE.search(text)
    if month_day:
        month = _MONTHS[month_day.group(1).lower()]
        day = int(month_day.group(2))
        year = int(month_day.group(3))
        iso = f"{year:04d}-{month:02d}-{day:02d}"
        return iso if _INSTANT_HEADER_RE.search(text) else f"{iso}..{iso}"
    years = _YEAR_RE.findall(text)
    if not years:
        return ""
    year = years[-1]
    if _INSTANT_HEADER_RE.search(text):
        return f"{year}-12-31"
    return f"{year}-01-01..{year}-12-31"


def _is_fee_label(label: str) -> bool:
    return is_fee_fact(label) or bool(_FEE_LABEL_RE.search(label or ""))


# --- fact extraction --------------------------------------------------------


def _xbrl_facts(html: str, *, ticker: str, cik: str, accession: str,
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
        period, dimensions = contexts.get(fact.context_ref or "", ("", ()))
        scoped_id = (
            f"{origin_doc}#{fact.fact_id}" if fact.fact_id
            else f"{origin_doc}#fact{index}"
        )
        facts.append(StatementFact(
            issuer=cik,
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


def _table_facts(primary_html: str, *, ticker: str, cik: str, accession: str,
                 origin_doc: str, xbrl_concepts: Sequence[str]) -> list:
    """Statement-table facts normalized with scale notes and parentheses."""
    facts: list = []
    for table in parse_statement_tables(primary_html):
        scale = table.scale if table.scale is not None else 0
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
                    issuer=cik,
                    concept=concept,
                    unit="USD",
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
            html, ticker=ticker, cik=cik, accession=accession, origin_doc=name,
        ))

    fee_facts, financial_facts = split_fee_vs_financial(all_facts)
    xbrl_concepts = [f.concept for f in financial_facts]
    table_facts = _table_facts(
        primary_html or "",
        ticker=ticker, cik=cik, accession=accession,
        origin_doc=primary_doc, xbrl_concepts=xbrl_concepts,
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
