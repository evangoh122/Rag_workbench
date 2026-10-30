"""
sec_reconcile.py — SEC structure-aware financial parsing / XBRL reconciliation.

Contract (fixture-tested in tests/test_sec_reconcile.py):
- ``normalize_numeric`` — exact iXBRL display-attribute normalization (finding 1)
- ``extract_fact_text`` / ``extract_ix_facts`` — ix:exclude-stripped fact text;
  ix:hidden facts stay present and valid (finding 2)
- ``parse_statement_tables`` — structure-aware rows; rowspan/colspan header
  flattening keeps labels in their columns (finding 3) and header detection
  reports ``header_ambiguity`` instead of guessing silently (finding 4)
- ``StatementFact`` / ``FactKey`` — full key + provenance + scoped ids (finding 5)
- ``is_fee_fact`` / ``split_fee_vs_financial`` — fee-taxonomy facts never financials
- ``reconcile`` — equivalent keys only -> MATCH / MISMATCH / UNAVAILABLE /
  AMBIGUOUS (conflicting duplicates are never silently first-wins)
- ``store_reconciliation`` — atomic delete+insert per (ticker, accession) with
  rollback on error (finding 6)
- ``resolve_continuations`` — cycle guard, missing-link tolerance and
  document-scope enforcement (finding 7)

Provenance conventions follow api/models/eval_types.py (Provenance.STRUCTURED_TABLE
for parsed statement rows); fact field names follow api/services/xbrl_client.py
(XBRLFact: concept / value / unit / period / ticker / accession). Values are
exact ``Decimal`` end to end — no float corruption.

Scope note (finding 8 — explicitly NOT a defect here): exhibit facts are
structured SQL rows only in this contract; RAG embedding of exhibits is out of
scope and tracked separately.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from enum import Enum
from typing import Any, Mapping, Optional, Sequence, Tuple

import lxml.html

from api.models.eval_types import Provenance

# --- numeric normalization (finding 1) -------------------------------------

_ZERODASH_FMTS = {"ixt:zerodash"}
_SUPPORTED_FMTS = {
    "ixt:num-dot-decimal", "ixt:num-comma-dot", "ixt:num-dot-comma",
    "ixt:num-comma-thousands", "ixt:num-space-comma", "ixt:num-space-dot",
}
_COMMA_DECIMAL_FMTS = {"ixt:num-dot-comma", "ixt:num-space-comma"}


@dataclass(frozen=True)
class NumericFact:
    """Exact numeric view of one display value plus its iXBRL attributes."""

    raw: str
    value: Optional[Decimal]
    supported: bool
    scale: Optional[int] = None
    sign: Optional[str] = None
    fmt: Optional[str] = None
    decimals: Optional[str] = None


def _parse_display_number(text: str, fmt: Optional[str] = None) -> Optional[Decimal]:
    """Exact Decimal for display content; parentheses mean negative; None if not numeric."""
    s = (text or "").strip()
    if not s:
        return None
    negative = False
    if s.startswith("(") and s.endswith(")") and len(s) > 1:
        negative = True
        s = s[1:-1].strip()
    if (fmt or "").strip().lower() in _COMMA_DECIMAL_FMTS:
        s = s.replace(".", "").replace("\u00a0", "").replace(" ", "").replace(",", ".")
    else:
        s = s.replace(",", "").replace("\u00a0", "").replace(" ", "")
    try:
        value = Decimal(s)
    except InvalidOperation:
        return None
    if not value.is_finite():
        return None
    # copy_negate is exact; unary minus would round the result under the
    # ambient decimal context (a 35-digit parenthesized value lost digits).
    return value.copy_negate() if negative else value


def _scale_exact(value: Decimal, scale: int) -> Decimal:
    """Multiply by an exact power of ten independent of the ambient context.

    The precision is derived from the operand's significant digits, the scale
    magnitude and guard digits so even a 35-digit value scaled by zero is
    returned byte-exact instead of being rounded by the default context.
    """
    digits = len(value.as_tuple().digits)
    precision = max(28, digits + abs(int(scale)) + 4)
    factor = Decimal((0, (1,), int(scale)))
    with localcontext() as ctx:
        ctx.prec = precision
        return value * factor


def _exact_subtract(left: Decimal, right: Decimal) -> Decimal:
    """Subtract two Decimals without ambient-context rounding."""
    left_t = left.as_tuple()
    right_t = right.as_tuple()
    precision = max(
        28,
        len(left_t.digits) + abs(int(left_t.exponent)) + 4,
        len(right_t.digits) + abs(int(right_t.exponent)) + 4,
    )
    with localcontext() as ctx:
        ctx.prec = precision
        return left - right


def normalize_numeric(
    raw: Any,
    scale: Optional[int] = None,
    sign: Optional[str] = None,
    fmt: Optional[str] = None,
    decimals: Optional[str] = None,
) -> NumericFact:
    """Normalize one iXBRL display value to an exact ``Decimal``.

    Applies ``scale`` (value = content * 10**scale), ``sign="-"`` negation and
    ``ixt:zerodash`` -> exact ``Decimal(0)``; ``raw`` is kept byte-identical.
    Unsupported ``fmt`` (or unparseable content) yields an explicit
    ``supported=False``, ``value=None`` result rather than a corrupt number.
    """
    raw_text = "" if raw is None else str(raw)
    fmt_norm = (fmt or "").strip().lower() or None
    if fmt_norm in _ZERODASH_FMTS:
        value: Optional[Decimal] = Decimal(0)
        supported = True
    elif fmt_norm is not None and fmt_norm not in _SUPPORTED_FMTS:
        value = None
        supported = False
    else:
        value = _parse_display_number(raw_text, fmt_norm)
        supported = value is not None
    if value is not None:
        if scale is not None:
            value = _scale_exact(value, int(scale))
        if sign == "-":
            value = value.copy_negate()
    return NumericFact(raw=raw_text, value=value, supported=supported,
                       scale=scale, sign=sign, fmt=fmt, decimals=decimals)

# --- iXBRL fact text (finding 2) -------------------------------------------


def _localname(tag: Any) -> str:
    if not isinstance(tag, str):
        return ""
    if tag.startswith("{"):
        tag = tag.split("}", 1)[1]
    return tag.split(":", 1)[-1].lower()


def _is_ix_named(el: Any, name: str) -> bool:
    tag = getattr(el, "tag", None)
    if not isinstance(tag, str) or _localname(tag) != name.lower():
        return False
    if tag.startswith("{"):
        return "xbrl.org" in tag.split("}", 1)[0]
    return ":" in tag  # html-parsed prefixed name, e.g. "ix:exclude"


def _collect_fact_text(el: Any, parts: list) -> None:
    if _is_ix_named(el, "exclude"):
        return
    if el.text:
        parts.append(el.text)
    for child in el:
        _collect_fact_text(child, parts)
        if child.tail:
            parts.append(child.tail)


def extract_fact_text(element: Any) -> str:
    """Fact text with ``ix:exclude`` descendants stripped.

    ``ix:hidden`` is a rendering-scope marker, not a value filter — hidden
    facts keep their text and stay valid (finding 2).
    """
    parts: list = []
    _collect_fact_text(element, parts)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _spaced_fact_text(element: Any) -> str:
    """Fact text that preserves ONE boundary space at each chunk edge.

    Continuation chains are concatenated literally, so ``"Acme "`` +
    ``"Corporation"`` must keep its separating space while a mid-word split
    (``"Corpo"`` + ``"ration"``) must not gain one.
    """
    parts: list = []
    _collect_fact_text(element, parts)
    raw = "".join(parts)
    normalized = re.sub(r"\s+", " ", raw)
    if raw[:1].isspace():
        normalized = " " + normalized.lstrip(" ")
    if raw[-1:].isspace():
        normalized = normalized.rstrip(" ") + " "
    return normalized


@dataclass(frozen=True)
class IxFact:
    """One iXBRL fact element with the attributes downstream steps consume."""

    concept: str
    text: str
    fact_id: Optional[str] = None
    document_id: str = ""
    context_ref: Optional[str] = None
    unit_ref: Optional[str] = None
    fmt: Optional[str] = None
    scale: Optional[int] = None
    sign: Optional[str] = None
    decimals: Optional[str] = None
    continued_at: Optional[str] = None
    hidden: bool = False
    numeric: bool = False


def _attr(el: Any, *names: str) -> Optional[str]:
    for n in names:
        v = el.get(n)
        if v is not None:
            return v
    return None


def _continuation_index(doc: Any, document_id: str) -> dict:
    """Index ``ix:continuation`` nodes from the SAME parsed document by id."""
    index: dict = {}
    for el in doc.iter():
        if not _is_ix_named(el, "continuation"):
            continue
        cid = _attr(el, "id")
        if not cid:
            continue
        index[cid] = ContinuationNode(
            text=_spaced_fact_text(el),
            continued_at=_attr(el, "continuedAt", "continuedat"),
            document_id=document_id,
        )
    return index


def extract_ix_facts(html: str, document_id: str = "") -> list:
    """Extract ``ix:nonFraction``/``ix:nonNumeric`` facts (hidden ones kept, valid).

    ``continuedAt`` chains are resolved against ``ix:continuation`` nodes in the
    same parsed document, so ``IxFact.text`` is the full rendered fact text.
    """
    if not (html or "").strip():
        return []
    doc = lxml.html.document_fromstring(html)
    continuations = _continuation_index(doc, document_id)
    facts: list = []
    for el in doc.iter():
        is_numeric = _is_ix_named(el, "nonfraction")
        if not (is_numeric or _is_ix_named(el, "nonnumeric")):
            continue
        scale_raw = _attr(el, "scale")
        continued_at = _attr(el, "continuedAt", "continuedat")
        text = extract_fact_text(el)
        if continued_at:
            text = re.sub(
                r"\s+", " ",
                _spaced_fact_text(el)
                + resolve_continuations(continuations, continued_at, document_id),
            ).strip()
        facts.append(IxFact(
            concept=_attr(el, "name") or "",
            text=text,
            fact_id=_attr(el, "id"),
            document_id=document_id,
            context_ref=_attr(el, "contextRef", "contextref"),
            unit_ref=_attr(el, "unitRef", "unitref"),
            fmt=_attr(el, "format"),
            scale=int(scale_raw) if scale_raw not in (None, "") else None,
            sign=_attr(el, "sign"),
            decimals=_attr(el, "decimals"),
            continued_at=continued_at,
            hidden=any(_is_ix_named(a, "hidden") for a in el.iterancestors()),
            numeric=is_numeric,
        ))
    return facts

# --- statement tables (findings 3 and 4) -----------------------------------

_SCALE_NOTE_RE = re.compile(
    r"\(\s*(?:in\s+)?(thousands|millions|billions|units)(?:\s+of\s+[a-z\s]+)?\s*\)",
    re.IGNORECASE,
)
_SCALE_EXPONENTS = {"units": 0, "thousands": 3, "millions": 6, "billions": 9}


@dataclass(frozen=True)
class TableCell:
    """One value cell bound to its flattened column header.

    When the cell contains an inline numeric fact, the fact's concept
    (taxonomy QName), context/unit references and id are retained so ingestion
    can bind the cell to its explicitly sourced identity instead of assuming an
    aggregate or inferring a concept from the row label.
    """

    column: str
    raw: str
    value: Optional[Decimal]  # parentheses -> negative; None when non-numeric
    inline: bool = False
    concept: Optional[str] = None
    context_ref: Optional[str] = None
    unit_ref: Optional[str] = None
    fact_id: Optional[str] = None
    identity_ambiguous: bool = False


@dataclass(frozen=True)
class ParsedRow:
    """One statement row: stub label plus column-aligned value cells."""

    label: str
    cells: Tuple[TableCell, ...]
    provenance: Provenance = Provenance.STRUCTURED_TABLE


@dataclass(frozen=True)
class ParsedTable:
    """Flattened headers, rows, scale note and header_ambiguity for one table.

    Values are as displayed (parenthesized negatives applied); the scale note
    is preserved verbatim and parsed into ``scale`` for later normalization.
    """

    columns: Tuple[str, ...]
    rows: Tuple[ParsedRow, ...]
    scale_note: Optional[str] = None
    scale: Optional[int] = None
    header_ambiguity: bool = False
    provenance: Provenance = Provenance.STRUCTURED_TABLE
    caption: Optional[str] = None


def _cell_text(cell: Any) -> str:
    return re.sub(r"\s+", " ", "".join(cell.itertext())).strip()


def _row_cells(tr: Any) -> list:
    return [c for c in tr
            if isinstance(getattr(c, "tag", None), str) and _localname(c.tag) in ("td", "th")]


def _is_th(cell: Any) -> bool:
    return _localname(getattr(cell, "tag", "")) == "th"


def _is_bold_cell(cell: Any) -> bool:
    style = (cell.get("style") or "").replace(" ", "").lower()
    if "font-weight:bold" in style or "font-weight:bolder" in style:
        return True
    return any(isinstance(getattr(c, "tag", None), str) and _localname(c.tag) in ("b", "strong")
               for c in cell.iter() if c is not cell)


def _span(cell: Any, attr: str) -> int:
    try:
        return max(1, int(str(cell.get(attr))))
    except (TypeError, ValueError):
        return 1


def _grid_for(trs: Sequence[Any]) -> dict:
    """Dense (row, col) -> origin-cell grid over rowspan/colspan spans.

    Span placeholders are materialized in place (never skipped) so labels stay
    in their columns (finding 3); continuation positions repeat their origin.
    """
    grid: dict = {}
    for r, tr in enumerate(trs):
        c = 0
        for cell in _row_cells(tr):
            while (r, c) in grid:
                c += 1
            for dr in range(_span(cell, "rowspan")):
                for dc in range(_span(cell, "colspan")):
                    grid[(r + dr, c + dc)] = cell
            c += _span(cell, "colspan")
    return grid


def _flatten_headers(grid: dict, header_rows: int, width: int) -> Tuple[str, ...]:
    columns = []
    for c in range(width):
        parts: list = []
        seen: set = set()
        for r in range(header_rows):
            cell = grid.get((r, c))
            if cell is None or id(cell) in seen:
                continue
            seen.add(id(cell))
            text = _cell_text(cell)
            if text:
                parts.append(text)
        columns.append(" | ".join(parts))
    return tuple(columns)


def _detect_header_rows(trs: Sequence[Any]) -> Tuple[int, bool]:
    """(header row count, header_ambiguity).

    ``<thead>`` and leading all-``th`` rows are structural evidence; leading
    bold ``td`` rows are conservative evidence only — reported via
    ``header_ambiguity`` instead of accepted silently (finding 4).
    """
    if not trs:
        return 0, False
    thead = 0
    for tr in trs:
        parent = tr.getparent()
        if parent is not None and isinstance(parent.tag, str) and _localname(parent.tag) == "thead":
            thead += 1
        else:
            break
    if thead:
        return thead, False
    count = 0
    ambiguity = False
    for tr in trs:
        cells = _row_cells(tr)
        if not cells:
            break
        if all(_is_th(c) or _is_bold_cell(c) for c in cells):
            ambiguity = ambiguity or any(not _is_th(c) for c in cells)
            count += 1
        else:
            break
    return (count, ambiguity) if count else (0, True)


def _scale_note_in(text: str) -> Optional[Tuple[str, int]]:
    m = _SCALE_NOTE_RE.search(text or "")
    return (m.group(0), _SCALE_EXPONENTS[m.group(1).lower()]) if m else None


def _table_rows(table: Any) -> list:
    rows = []
    for tr in table.iter("tr"):
        parent = tr.getparent()
        while parent is not None and isinstance(parent.tag, str) and _localname(parent.tag) != "table":
            parent = parent.getparent()
        if parent is table:
            rows.append(tr)
    return rows


def _inline_cell_binding(cell: Any) -> Tuple[bool, Optional[str], Optional[str],
                                             Optional[str], Optional[str], bool]:
    """(has_inline_fact, concept, context_ref, unit_ref, fact_id, ambiguous).

    A cell may carry more than one inline numeric fact. The concept, context
    and unit references are read from each fact together, never combined across
    facts: one identical binding is authoritative, while differing concepts or
    binding identities are ambiguous so the cell is never silently bound to one
    of them. A single fact without a ``name`` has no authoritative concept but
    keeps its binding so label inference can apply only as a fallback.
    """
    bindings: list = []
    fact_ids: list = []
    for el in cell.iter():
        if not _is_ix_named(el, "nonfraction"):
            continue
        concept = (_attr(el, "name") or "").strip()
        context_ref = _attr(el, "contextRef", "contextref")
        unit_ref = _attr(el, "unitRef", "unitref")
        binding = (concept, context_ref, unit_ref)
        if binding not in bindings:
            bindings.append(binding)
        fact_id = _attr(el, "id")
        if fact_id and fact_id not in fact_ids:
            fact_ids.append(fact_id)
    if not bindings:
        return False, None, None, None, None, False
    if len(bindings) > 1:
        return True, None, None, None, None, True
    concept, context_ref, unit_ref = bindings[0]
    fact_id = fact_ids[0] if len(fact_ids) == 1 else None
    return True, concept or None, context_ref, unit_ref, fact_id, False


def parse_statement_tables(html: str) -> list:
    """Parse statement tables into structure-aware rows (Provenance.STRUCTURED_TABLE).

    Preserves column headers/periods, scale notes such as ``(In thousands)``
    and signs (parentheses -> negative); multi-row headers flatten without
    column shift and ambiguous bold-``td`` headers are reported (findings 3, 4).
    """
    if not (html or "").strip():
        return []
    doc = lxml.html.document_fromstring(html)
    out: list = []
    for table in doc.iter("table"):
        rows = _table_rows(table)
        if not rows:
            continue
        scale_note: Optional[str] = None
        scale: Optional[int] = None
        caption = table.find("caption")
        if caption is not None:
            hit = _scale_note_in(_cell_text(caption))
            if hit:
                scale_note, scale = hit
        kept: list = []
        for tr in rows:
            text = _cell_text(tr)
            hit = _scale_note_in(text) if scale_note is None else None
            if hit and len(_row_cells(tr)) == 1 and text.strip() == hit[0]:
                scale_note, scale = hit  # full-width note row consumed
                continue
            if hit:
                scale_note, scale = hit
            kept.append(tr)
        if not kept:
            continue
        grid = _grid_for(kept)
        width = max((c for (_r, c) in grid), default=-1) + 1
        if width <= 0:
            continue
        header_rows, ambiguity = _detect_header_rows(kept)
        columns = (_flatten_headers(grid, header_rows, width) if header_rows
                   else tuple(f"col_{i}" for i in range(width)))
        rows_out: list = []
        for r in range(header_rows, len(kept)):
            label_cell = grid.get((r, 0))
            cells_out = []
            for c in range(1, width):
                cell = grid.get((r, c))
                raw = _cell_text(cell) if cell is not None else ""
                inline, concept, context_ref, unit_ref, fact_id, ambiguous = (
                    _inline_cell_binding(cell) if cell is not None
                    else (False, None, None, None, None, False)
                )
                cells_out.append(TableCell(
                    column=columns[c], raw=raw,
                    value=_parse_display_number(raw) if raw else None,
                    inline=inline, concept=concept,
                    context_ref=context_ref, unit_ref=unit_ref,
                    fact_id=fact_id, identity_ambiguous=ambiguous,
                ))
            rows_out.append(ParsedRow(
                label=_cell_text(label_cell) if label_cell is not None else "",
                cells=tuple(cells_out),
            ))
        out.append(ParsedTable(columns=columns, rows=tuple(rows_out),
                               scale_note=scale_note, scale=scale,
                               header_ambiguity=ambiguity,
                               caption=_cell_text(caption) if caption is not None else None))
    return out

# --- fact records (finding 5) ----------------------------------------------


def _normalize_dimensions(dimensions: Any) -> Tuple[Tuple[str, str], ...]:
    if not dimensions:
        return ()
    items = dimensions.items() if isinstance(dimensions, Mapping) else dimensions
    return tuple(sorted((str(k), str(v)) for k, v in items))


@dataclass(frozen=True)
class FactKey:
    """Comparable identity of a fact — the ONLY basis reconciliation uses."""

    issuer: str
    concept: str
    unit: str
    duration: str  # instant date ("2025-12-31") or period ("start..end")
    dimensions: Tuple[Tuple[str, str], ...] = ()
    accession: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "dimensions", _normalize_dimensions(self.dimensions))


@dataclass(frozen=True)
class StatementFact:
    """One financial fact: full key + provenance fields + scoped ids."""

    issuer: str
    concept: str
    unit: str
    duration: str
    value: Decimal
    accession: str = ""
    dimensions: Tuple[Tuple[str, str], ...] = ()
    ticker: str = ""
    origin_doc: Optional[str] = None
    scale: Optional[int] = None
    sign: Optional[str] = None
    decimals: Optional[str] = None
    fact_id: Optional[str] = None
    document_id: Optional[str] = None
    fmt: Optional[str] = None
    raw_text: Optional[str] = None
    context_ref: Optional[str] = None
    unit_ref: Optional[str] = None
    hidden: bool = False
    identity_ambiguous: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "dimensions", _normalize_dimensions(self.dimensions))

    @property
    def key(self) -> FactKey:
        return FactKey(issuer=self.issuer, concept=self.concept, unit=self.unit,
                       duration=self.duration, dimensions=self.dimensions,
                       accession=self.accession)

# --- fee taxonomy (never financials) ---------------------------------------

_FEE_TAXONOMIES = {"ffd"}
_FEE_LOCALNAMES = {
    "feetable", "filingfeetable", "filingfee", "feecalculation",
    "filingfeecalculation", "feeoffset", "filingfeeoffset", "feerate", "filingfeerate",
}


def is_fee_fact(fact: Any) -> bool:
    """True for filing-fee taxonomy / fee-table facts (e.g. ``ffd:*``)."""
    concept = fact if isinstance(fact, str) else getattr(fact, "concept", "")
    norm = str(concept or "").strip().lower().replace("/", ":")
    prefix, _, local = norm.rpartition(":")
    return prefix in _FEE_TAXONOMIES or local in _FEE_LOCALNAMES


def split_fee_vs_financial(facts: Sequence[Any]) -> Tuple[list, list]:
    """Split facts into (fee_facts, financial_facts); fee facts never financials."""
    fee: list = []
    financial: list = []
    for f in facts:
        (fee if is_fee_fact(f) else financial).append(f)
    return fee, financial

# --- reconciliation (equivalent keys only) ---------------------------------


class ReconcileStatus(str, Enum):
    """Outcome of comparing one equivalent key across table and XBRL."""

    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    UNAVAILABLE = "UNAVAILABLE"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class ReconciliationRow:
    """One reconciliation outcome; ``delta = xbrl_value - table_value``."""

    key: FactKey
    status: ReconcileStatus
    ticker: str = ""
    table_value: Optional[Decimal] = None
    xbrl_value: Optional[Decimal] = None
    delta: Optional[Decimal] = None
    table_candidates: Tuple[Decimal, ...] = ()
    xbrl_candidates: Tuple[Decimal, ...] = ()


def _group_by_key(facts: Sequence[StatementFact]) -> dict:
    groups: dict = {}
    for f in facts:
        groups.setdefault(f.key, []).append(f)
    return groups


def _distinct_values(facts: Sequence[StatementFact]) -> Tuple[Decimal, ...]:
    """Distinct values in a stable order, so the outcome is order-independent."""
    seen: set = set()
    values: list = []
    for f in facts:
        if f.value not in seen:
            seen.add(f.value)
            values.append(f.value)
    return tuple(sorted(values))


def reconcile(table_facts: Sequence[StatementFact],
              xbrl_facts: Sequence[StatementFact]) -> list:
    """Compare table facts against XBRL facts on equivalent keys ONLY.

    Keys are (issuer, concept, unit, duration, dimensions, accession). A key
    missing on either side reports UNAVAILABLE; fee facts are split away first
    and never reconcile as financials — a filing whose XBRL carries only fee
    facts reports UNAVAILABLE explicitly, never a match.

    Conflicting duplicates: when one key carries more than one DISTINCT value on
    either side, the outcome is AMBIGUOUS — never a silent first-wins MATCH.
    Duplicates with identical values collapse to one value. The distinct
    candidates are carried on the row; no candidate is chosen as the value.
    """
    _, table_fin = split_fee_vs_financial(table_facts)
    _, xbrl_fin = split_fee_vs_financial(xbrl_facts)
    table_groups = _group_by_key(table_fin)
    xbrl_groups = _group_by_key(xbrl_fin)

    rows: list = []
    for key in list(table_groups) + [k for k in xbrl_groups if k not in table_groups]:
        t_facts = table_groups.get(key, [])
        x_facts = xbrl_groups.get(key, [])
        t = t_facts[0] if t_facts else None
        x = x_facts[0] if x_facts else None
        ticker = (t.ticker if t is not None else x.ticker) or ""
        table_values = _distinct_values(t_facts)
        xbrl_values = _distinct_values(x_facts)
        identity_ambiguous = any(
            getattr(f, "identity_ambiguous", False) for f in list(t_facts) + list(x_facts)
        )
        identity_established = bool(
            key.issuer and key.concept and key.unit and key.duration
        )
        if identity_ambiguous:
            # An unresolved source identity is never a comparison candidate.
            status = ReconcileStatus.UNAVAILABLE
            table_value = xbrl_value = delta = None
        elif len(table_values) > 1 or len(xbrl_values) > 1:
            status = ReconcileStatus.AMBIGUOUS
            table_value = xbrl_value = delta = None
        elif not table_values or not xbrl_values:
            status, delta = ReconcileStatus.UNAVAILABLE, None
            table_value = table_values[0] if table_values else None
            xbrl_value = xbrl_values[0] if xbrl_values else None
        elif not identity_established:
            # Two unknowns are not known to be equivalent: missing issuer /
            # concept / unit / period must never become a MATCH.
            status, delta = ReconcileStatus.UNAVAILABLE, None
            table_value = table_values[0]
            xbrl_value = xbrl_values[0]
        elif table_values[0] == xbrl_values[0]:
            status, delta = ReconcileStatus.MATCH, Decimal(0)
            table_value = xbrl_value = table_values[0]
        else:
            status = ReconcileStatus.MISMATCH
            table_value, xbrl_value = table_values[0], xbrl_values[0]
            delta = _exact_subtract(xbrl_value, table_value)
        rows.append(ReconciliationRow(
            key=key, status=status, ticker=ticker,
            table_value=table_value, xbrl_value=xbrl_value, delta=delta,
            table_candidates=table_values, xbrl_candidates=xbrl_values,
        ))
    return rows

# --- persistence (finding 6) -----------------------------------------------

RECONCILIATION_TABLE = "sec_reconciliation"
RECONCILIATION_DDL = (
    "CREATE TABLE IF NOT EXISTS sec_reconciliation ("
    "ticker VARCHAR NOT NULL, accession VARCHAR NOT NULL, issuer VARCHAR NOT NULL, "
    "concept VARCHAR NOT NULL, unit VARCHAR NOT NULL, duration VARCHAR NOT NULL, "
    "dimensions VARCHAR NOT NULL, status VARCHAR NOT NULL, "
    "table_value VARCHAR, xbrl_value VARCHAR, delta VARCHAR, "
    "table_candidates VARCHAR, xbrl_candidates VARCHAR)"
)
_INSERT_SQL = (
    "INSERT INTO sec_reconciliation "
    "(ticker, accession, issuer, concept, unit, duration, dimensions, "
    " status, table_value, xbrl_value, delta, table_candidates, xbrl_candidates) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def decimal_text(value: Decimal) -> str:
    """Plain fixed-point text for an exact Decimal (never scientific notation)."""
    return format(value, "f")


def _candidates_text(values: Sequence[Decimal]) -> Optional[str]:
    return ";".join(decimal_text(v) for v in values) if values else None


def _row_payload(row: ReconciliationRow) -> tuple:
    dims = ";".join(f"{k}={v}" for k, v in row.key.dimensions)
    return (row.ticker, row.key.accession, row.key.issuer, row.key.concept,
            row.key.unit, row.key.duration, dims, row.status.value,
            None if row.table_value is None else decimal_text(row.table_value),
            None if row.xbrl_value is None else decimal_text(row.xbrl_value),
            None if row.delta is None else decimal_text(row.delta),
            _candidates_text(row.table_candidates),
            _candidates_text(row.xbrl_candidates))


def _insert_rows(conn: Any, payloads: Sequence[tuple]) -> None:
    conn.executemany(_INSERT_SQL, list(payloads))


def delete_and_insert_reconciliation(conn: Any, rows: Sequence[ReconciliationRow]) -> int:
    """Delete-before-insert reconciliation rows inside the caller's transaction.

    Used by ``store_reconciliation`` and by structured ingestion, which needs
    fact rows and reconciliation rows in ONE atomic transaction.
    """
    rows = list(rows)
    if not rows:
        return 0
    payloads = [_row_payload(r) for r in rows]
    for ticker, accession in sorted({(r.ticker, r.key.accession) for r in rows}):
        conn.execute("DELETE FROM sec_reconciliation WHERE ticker = ? AND accession = ?",
                     [ticker, accession])
    _insert_rows(conn, payloads)
    return len(payloads)


def store_reconciliation(conn: Any, rows: Sequence[ReconciliationRow]) -> int:
    """Delete+insert reconciliation rows atomically (finding 6).

    One transaction covers the delete-before-insert for each (ticker,
    accession) in ``rows``: any failure rolls back so prior rows stay intact,
    and a rerun is idempotent. Returns the number of rows stored.
    """
    rows = list(rows)
    if not rows:
        return 0
    conn.execute(RECONCILIATION_DDL)
    conn.execute("BEGIN TRANSACTION")
    try:
        stored = delete_and_insert_reconciliation(conn, rows)
    except Exception:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")
    return stored

# --- continuation chains (finding 7) ---------------------------------------


@dataclass(frozen=True)
class ContinuationNode:
    """One node of an iXBRL continuation chain."""

    text: str = ""
    continued_at: Optional[str] = None
    document_id: str = ""


def _continuation_fields(node: Any) -> Tuple[str, Optional[str], str]:
    if isinstance(node, Mapping):
        text, doc = node.get("text", ""), node.get("document_id", "")
        continued = node.get("continued_at", node.get("continuedAt"))
    else:
        text = getattr(node, "text", "") or ""
        continued = getattr(node, "continued_at", None)
        doc = getattr(node, "document_id", "") or ""
    return str(text), (str(continued) if continued else None), str(doc)


def resolve_continuations(by_id: Mapping[str, Any], start_id: str, document_id: str) -> str:
    """Resolve an iXBRL continuation chain into its full concatenated text.

    Cycle guard (a->b->a terminates), missing-link tolerance (an unknown
    ``continuedAt`` target stops cleanly) and document-scope enforcement
    (finding 7): a cross-document link is refused — its text is never
    included and the chain stops there.
    """
    parts: list = []
    seen: set = set()
    current: Optional[str] = start_id
    while current:
        if current in seen:
            break  # cycle guard — never loop
        seen.add(current)
        node = by_id.get(current)
        if node is None:
            break  # missing link — stop cleanly
        text, continued_at, node_doc = _continuation_fields(node)
        if node_doc != document_id:
            break  # cross-document link refused
        parts.append(text)
        current = continued_at
    return "".join(parts)
