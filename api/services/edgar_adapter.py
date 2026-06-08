"""
edgar_adapter.py — EdgarTools wrapper that produces ExtractionResult.

This is the ONLY place in the codebase that imports edgartools. All
downstream components receive ExtractionResult; they never touch raw
EdgarTools objects. (CONSTRAINT-009: no custom EDGAR/XBRL parser.)

Provenance assignment rules (CONSTRAINT-002):
  - XBRL financials (filing.obj().financials)   → Provenance.XBRL
  - HTML structured tables (filing.obj().*_sheet) → Provenance.STRUCTURED_TABLE
  - LLM-extracted narrative                      → Provenance.NARRATIVE_LLM (future)
"""
from __future__ import annotations

import os
from typing import Optional

import pandas as pd

from api.models.eval_types import (
    ExtractionResult,
    ExtractedField,
    Provenance,
)


class EdgarAdapterError(Exception):
    """Raised when edgartools cannot fetch or parse a filing."""


def _set_edgar_identity() -> None:
    """Configure the EdgarTools identity header before any SEC API call."""
    user_agent = os.getenv("EDGAR_USER_AGENT")
    if not user_agent:
        raise EdgarAdapterError(
            "EDGAR_USER_AGENT environment variable is not set. "
            "Set it to 'Your Name your@email.com' before calling fetch_filing()."
        )
    try:
        import edgar
        edgar.set_identity(user_agent)
    except Exception as exc:
        raise EdgarAdapterError(f"Failed to set EdgarTools identity: {exc}") from exc


def _statement_to_fields(statement) -> list[ExtractedField]:
    """Convert an EdgarTools Statement object to XBRL-tagged ExtractedFields.

    Statement.to_dataframe() returns columns: concept, label, standard_concept,
    <date1>, <date2>, ... (one column per reporting period). We take the most
    recent date column as the primary value and skip abstract/header rows.
    """
    if statement is None:
        return []
    try:
        df: pd.DataFrame = statement.to_dataframe()
    except Exception:
        return []

    if df is None or df.empty:
        return []

    # Find the most recent date column (columns that look like YYYY-MM-DD)
    date_cols = [c for c in df.columns if _is_date_col(c)]
    if not date_cols:
        return []
    value_col = date_cols[0]  # first = most recent (EdgarTools orders desc)

    fields: list[ExtractedField] = []
    for _, row in df.iterrows():
        if row.get("abstract", False):
            continue  # skip header/subtotal rows

        raw_concept = str(row.get("concept", ""))
        # Strip "us-gaap_" prefix to get the canonical GAAP concept name
        concept = raw_concept.replace("us-gaap_", "").replace("dei_", "")
        label = str(row.get("label", concept))
        value = row.get(value_col)

        if pd.isna(value) or value is None:
            continue

        fields.append(
            ExtractedField(
                name=label,
                value=float(value),
                provenance=Provenance.XBRL,
                concept=concept or None,
            )
        )
    return fields


def _xbrl_dataframe_to_fields(df: Optional[pd.DataFrame]) -> list[ExtractedField]:
    """Convert a concept/value DataFrame to XBRL-tagged ExtractedFields.

    Expects columns: 'concept' (str) and 'value' (numeric). Returns [] for
    None or empty input. Use _statement_to_fields() for EdgarTools Statements.
    """
    if df is None or df.empty:
        return []
    if "concept" not in df.columns or "value" not in df.columns:
        return []
    fields: list[ExtractedField] = []
    for _, row in df.iterrows():
        concept = str(row.get("concept", ""))
        value = row.get("value")
        if pd.isna(value) or value is None:
            continue
        fields.append(
            ExtractedField(
                name=concept,
                value=float(value),
                provenance=Provenance.XBRL,
                concept=concept or None,
            )
        )
    return fields


def _is_date_col(col: str) -> bool:
    """Return True if a column name looks like YYYY-MM-DD."""
    parts = col.split("-")
    return len(parts) == 3 and len(parts[0]) == 4 and parts[0].isdigit()


def fetch_filing(cik: str, accession: str) -> ExtractionResult:
    """Fetch a SEC filing via EdgarTools and return a typed ExtractionResult.

    Args:
        cik: SEC Central Index Key, e.g. "0000320193" (Apple).
        accession: SEC accession number, e.g. "0000320193-23-000064".

    Returns:
        ExtractionResult with all extracted fields provenance-tagged.

    Raises:
        EdgarAdapterError: If the filing cannot be fetched or parsed.
    """
    _set_edgar_identity()

    try:
        from edgar import Company
    except ImportError as exc:
        raise EdgarAdapterError(
            "edgartools is not installed. Run: pip install 'edgartools>=2.26.0'"
        ) from exc

    try:
        company = Company(cik)
        # get_filing() was removed in EdgarTools 3.x — use get_filings().filter()
        results = company.get_filings().filter(accession_number=accession)
        if len(results) == 0:
            raise EdgarAdapterError(
                f"No filing found for CIK={cik}, accession={accession}."
            )
        filing = results[0]
    except EdgarAdapterError:
        raise
    except Exception as exc:
        raise EdgarAdapterError(
            f"EdgarTools failed to fetch filing (CIK={cik}, accession={accession}): {exc}"
        ) from exc

    form_type: str = getattr(filing, "form", "UNKNOWN")
    period: Optional[str] = getattr(filing, "period_of_report", None)

    xbrl_fields: list[ExtractedField] = []
    try:
        doc = filing.obj()
        if doc is not None and hasattr(doc, "financials") and doc.financials is not None:
            fin = doc.financials
            for stmt_name in ("balance_sheet", "income_statement", "cash_flow_statement"):
                stmt_fn = getattr(fin, stmt_name, None)
                if callable(stmt_fn):
                    try:
                        xbrl_fields.extend(_statement_to_fields(stmt_fn()))
                    except Exception:
                        pass
    except Exception:
        pass

    return ExtractionResult(
        cik=cik,
        accession=accession,
        form_type=form_type,
        period=period,
        fields=xbrl_fields,
    )
