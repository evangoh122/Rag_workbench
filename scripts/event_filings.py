"""Pure helpers for 8-K / 6-K event-filing ingestion (no torch/edgar/duckdb imports).

Used by scripts/embed_additional.py (--forms 8-K). Kept dependency-free so the
parsing and window logic is unit-testable with mocked EDGAR objects.

Item numbers (e.g. 2.02, 5.02) are stored in the existing `section_id` column as
`item_2.02` — no schema change. 6-K has no item structure and is stored as a
single `full_text` section.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

DEFAULT_8K_DAYS = 180
DEFAULT_8K_MAX = 8

# "Item 2.02", "ITEM 5.02." etc. at the start of a line. 8-K items are N.NN
# (sections 1-9). The same item can be referenced inline ("see Item 2.02"), so
# only line-leading headings count.
_ITEM_RE = re.compile(r"^[ \t]*item\s+(\d{1,2}\.\d{2})\b[.:\s\-–—]*", re.I | re.M)


def split_8k_items(text: str) -> list[tuple[str, str]]:
    """Split 8-K text into [(\"item_2.02\", body), ...].

    Repeated headings for one item (e.g. a TOC-style summary) are merged, keeping
    document order of first appearance. Text before the first item is dropped
    (cover page). Returns [] when no item headings are found so the caller can
    fall back to a single full_text section.
    """
    if not text:
        return []
    matches = list(_ITEM_RE.finditer(text))
    if not matches:
        return []
    bodies: dict[str, list[str]] = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():end].strip()
        if body:
            bodies.setdefault(f"item_{m.group(1)}", []).append(body)
    return [(label, "\n\n".join(parts)) for label, parts in bodies.items()]


def sections_for_event_filing(form_code: str, text: str) -> list[tuple[str, str]]:
    """Sections to chunk for an 8-K / 6-K. Only 8-K is item-split."""
    if form_code == "8-K":
        items = split_8k_items(text)
        if items:
            return items
    return [("full_text", text)] if text and text.strip() else []


def event_form_for(existing_forms: set[str]) -> str | None:
    """8-K for domestic filers, 6-K for foreign private issuers (20-F, no 10-K)."""
    if "10-K" in existing_forms:
        return "8-K"
    if "20-F" in existing_forms:
        return "6-K"
    if "8-K" in existing_forms:
        return "8-K"
    if "6-K" in existing_forms:
        return "6-K"
    return None


def _as_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def filing_date_of(filing) -> date | None:
    return _as_date(getattr(filing, "filing_date", None))


def select_recent_filings(
    filings, form_code: str, days: int, limit: int, today: date | None = None
) -> list:
    """Exact-form filings (drops 8-K/A etc.) filed within `days`, newest first, max `limit`.

    Filings with an unparseable date are excluded rather than assumed recent, so
    the embedding cost bound always holds.
    """
    today = today or date.today()
    cutoff = today - timedelta(days=max(0, days))
    dated = []
    for f in filings:
        if getattr(f, "form", None) != form_code:
            continue
        d = filing_date_of(f)
        if d is None or d < cutoff:
            continue
        dated.append((d, f))
    dated.sort(key=lambda p: p[0], reverse=True)
    return [f for _, f in dated[: max(1, limit)]]


def event_period(filing, fallback: str) -> str:
    """Report date, else filing date (ISO), else the accession-derived fallback."""
    d = _as_date(getattr(filing, "period_of_report", None)) or filing_date_of(filing)
    return d.isoformat() if d else fallback
