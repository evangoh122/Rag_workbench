"""
ixbrl_parser.py — Direct Inline XBRL (iXBRL) parsing for SEC filings.

Extracts ``ix:nonFraction`` / ``ix:nonNumeric`` facts from filing HTML with
exhibit-level provenance: taxonomy-qualified concept name, context (period,
entity, dimensions), unit, scale/sign/decimals, and — structure-aware — the
row/column labels of the HTML table cell each fact is rendered in (so a filing
fee table parses into per-offering rows, not a flat fact soup).

Also resolves ``ix:exclude`` (hidden facts are skipped) and ``continuedAt``
chains for long non-numeric values.

Usage:
    from api.services.ixbrl_parser import parse_ixbrl
    doc = parse_ixbrl(html)
    for fact in doc.facts:
        print(fact.name, fact.value, fact.row_labels, fact.col_labels)
    for row in doc.fact_rows():
        print(row)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag

from api.services.html_tables import parse_soup_tables

_NUMERIC_CHARS = str.maketrans({c: None for c in "$, \t"})


@dataclass
class IXBRLContext:
    """A single ``xbrli:context`` definition."""
    id: str
    entity: str = ""
    instant: str = ""
    start: str = ""
    end: str = ""
    dimensions: dict[str, str] = field(default_factory=dict)

    @property
    def period(self) -> str:
        if self.instant:
            return self.instant
        if self.start or self.end:
            return f"{self.start}..{self.end}"
        return ""


@dataclass
class IXBRLUnit:
    """A single ``xbrli:unit`` definition (measures and/or divide)."""
    id: str
    measures: tuple[str, ...] = ()


@dataclass
class IXBRLFact:
    """One inline XBRL fact as rendered in the filing document."""
    element: str                 # "nonFraction" | "nonNumeric"
    name: str                    # e.g. "ffd:FeeAmt"
    context_ref: str
    unit_ref: str = ""
    decimals: str = ""
    scale: str = ""
    sign: str = ""
    fmt: str = ""
    raw_text: str = ""
    text_value: str = ""
    value: float | None = None   # numeric interpretation of the rendered text
    row_labels: tuple[str, ...] = ()
    col_labels: tuple[str, ...] = ()
    continued_at: str = ""

    @property
    def taxonomy(self) -> str:
        return self.name.split(":", 1)[0] if ":" in self.name else ""

    @property
    def concept(self) -> str:
        return self.name.split(":", 1)[1] if ":" in self.name else self.name


@dataclass
class IXBRLDocument:
    """All facts and XBRL metadata parsed from one document."""
    facts: list[IXBRLFact] = field(default_factory=list)
    contexts: dict[str, IXBRLContext] = field(default_factory=dict)
    units: dict[str, IXBRLUnit] = field(default_factory=dict)

    def fact_rows(self) -> list[dict[str, object]]:
        """Group facts into structure-aware rows keyed by their table labels.

        Facts rendered in tables group under ``row_labels``; facts outside any
        table group under their context period so nothing is dropped.
        """
        rows: dict[tuple[str, ...], dict[str, object]] = {}
        for fact in self.facts:
            if fact.row_labels:
                key = fact.row_labels
            else:
                ctx = self.contexts.get(fact.context_ref)
                key = ((ctx.period if ctx else "") or fact.context_ref,)
            row = rows.setdefault(key, {"row": " | ".join(key), "facts": []})
            row["facts"].append(fact)
        return list(rows.values())


def _tag_local(name: str) -> str:
    return name.split(":", 1)[-1].lower()


def _is_fact_tag(tag: Tag) -> str | None:
    local = _tag_local(tag.name)
    if local == "nonfraction":
        return "nonFraction"
    if local == "nonnumeric":
        return "nonNumeric"
    return None


def _parse_numeric(text: str) -> float | None:
    stripped = text.strip().translate(_NUMERIC_CHARS)
    if not stripped:
        return None
    negative = stripped.startswith("(") and stripped.endswith(")")
    stripped = stripped.strip("()")
    if not stripped or not stripped.replace(".", "", 1).replace("-", "", 1).isdigit():
        return None
    try:
        value = float(stripped)
    except ValueError:
        return None
    return -value if negative else value


def _parse_contexts(soup: BeautifulSoup) -> dict[str, IXBRLContext]:
    contexts: dict[str, IXBRLContext] = {}
    for tag in soup.find_all(True):
        if _tag_local(tag.name) != "context":
            continue
        ctx = IXBRLContext(id=tag.get("id", ""))
        entity = tag.find(lambda t: _tag_local(t.name) == "identifier")
        if entity is not None:
            ctx.entity = entity.get_text(strip=True)
        period = tag.find(lambda t: _tag_local(t.name) == "period")
        if period is not None:
            instant = period.find(lambda t: _tag_local(t.name) == "instant")
            start = period.find(lambda t: _tag_local(t.name) == "startdate")
            end = period.find(lambda t: _tag_local(t.name) == "enddate")
            ctx.instant = instant.get_text(strip=True) if instant else ""
            ctx.start = start.get_text(strip=True) if start else ""
            ctx.end = end.get_text(strip=True) if end else ""
        for member in tag.find_all(True):
            local = _tag_local(member.name)
            if local in ("explicitmember", "typedmember"):
                ctx.dimensions[member.get("dimension", "")] = member.get_text(strip=True)
        if ctx.id:
            contexts[ctx.id] = ctx
    return contexts


def _parse_units(soup: BeautifulSoup) -> dict[str, IXBRLUnit]:
    units: dict[str, IXBRLUnit] = {}
    for tag in soup.find_all(True):
        if _tag_local(tag.name) != "unit":
            continue
        measures = tuple(
            m.get_text(strip=True)
            for m in tag.find_all(True)
            if _tag_local(m.name) in ("measure", "unitnumerator", "unitdenominator")
        )
        unit = IXBRLUnit(id=tag.get("id", ""), measures=measures)
        if unit.id:
            units[unit.id] = unit
    return units


def _in_exclude(tag: Tag) -> bool:
    return any(_tag_local(getattr(parent, "name", "") or "") == "exclude" for parent in tag.parents)


def _nearest_cell(tag: Tag) -> Tag | None:
    for parent in tag.parents:
        if parent.name in ("td", "th"):
            return parent
    return None


def _resolve_continued(soup: BeautifulSoup, continued_at: str) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    next_id = continued_at
    while next_id and next_id not in seen:
        seen.add(next_id)
        cont = soup.find(
            lambda t: _tag_local(t.name) == "continuation" and t.get("id") == next_id
        )
        if cont is None:
            break
        parts.append(cont.get_text(" ", strip=True))
        next_id = cont.get("continuedat", "") or ""
    return " ".join(parts)


def _fact_label_map(
    soup: BeautifulSoup,
    fact_tags: list[Tag],
) -> dict[int, tuple[tuple[str, ...], tuple[str, ...]]]:
    """Map id(fact-tag) -> (row_labels, col_labels) from HTML table position.

    Header cells of the same row to the left of the fact's cell form the row
    labels; distinct header cells in the same column above it form the column
    labels. Facts outside tables are absent from the map.
    """
    labels: dict[int, tuple[tuple[str, ...], tuple[str, ...]]] = {}
    if not fact_tags:
        return labels
    facts_by_cell: dict[int, list[Tag]] = {}
    for tag in fact_tags:
        cell = _nearest_cell(tag)
        if cell is not None:
            facts_by_cell.setdefault(id(cell), []).append(tag)

    for table in parse_soup_tables(soup):
        # Row labels: leading cells of a row that are header cells or carry no
        # facts (SEC fee/statement tables label rows with plain <td>).
        row_headers: list[tuple[str, ...]] = []
        for row in table.grid:
            run: list[str] = []
            for cell in row:
                if cell is None:
                    continue  # covered by a rowspan label above
                cell_facts = facts_by_cell.get(id(cell.source), [])
                if cell.is_header or not cell_facts:
                    if cell.text:
                        run.append(cell.text)
                    continue
                break
            row_headers.append(tuple(run))

        # Column labels: the contiguous header rows above the data rows.
        header_rows: list[list[str]] = []
        for i, row in enumerate(table.grid[: table.header_row_count]):
            expanded: list[str] = []
            for cell in row:
                if cell is None:
                    continue
                for _ in range(cell.colspan):
                    expanded.append(cell.text)
            header_rows.append(expanded)

        for r, row in enumerate(table.grid):
            col_ptr = 0
            for cell in row:
                if cell is None:
                    col_ptr += 1
                    continue
                for tag in facts_by_cell.get(id(cell.source), []):
                    col_labels: list[str] = []
                    for hrow in header_rows:
                        if col_ptr < len(hrow) and hrow[col_ptr] and hrow[col_ptr] not in col_labels:
                            col_labels.append(hrow[col_ptr])
                    row_label = row_headers[r] if r < len(row_headers) else ()
                    if not row_label and r > 0 and row and row[0] is None:
                        # Row label rendered via rowspan above this row.
                        row_label = row_headers[r - 1] if r - 1 < len(row_headers) else ()
                    labels[id(tag)] = (row_label, tuple(col_labels))
                col_ptr += cell.colspan
    return labels


def parse_ixbrl(html: str) -> IXBRLDocument:
    """Parse an Inline XBRL document into facts, contexts and units."""
    soup = BeautifulSoup(html, "lxml")
    fact_tags = [
        tag for tag in soup.find_all(["ix:nonfraction", "ix:nonnumeric"])
        if _is_fact_tag(tag) is not None and not _in_exclude(tag) and tag.get("name")
    ]
    doc = IXBRLDocument(
        contexts=_parse_contexts(soup),
        units=_parse_units(soup),
    )
    label_map = _fact_label_map(soup, fact_tags)

    for tag in fact_tags:
        kind = _is_fact_tag(tag) or ""
        raw_text = tag.get_text(" ", strip=True)
        text_value = " ".join(raw_text.split())
        continued_at = tag.get("continuedat", "") or ""
        if kind == "nonNumeric" and continued_at:
            extra = _resolve_continued(soup, continued_at)
            if extra:
                text_value = f"{text_value} {extra}".strip()

        row_labels, col_labels = label_map.get(id(tag), ((), ()))
        doc.facts.append(IXBRLFact(
            element=kind,
            name=tag.get("name", ""),
            context_ref=tag.get("contextref", "") or "",
            unit_ref=tag.get("unitref", "") or "",
            decimals=tag.get("decimals", "") or "",
            scale=tag.get("scale", "") or "",
            sign=(tag.get("sign") or "").strip(),
            fmt=tag.get("format", "") or "",
            raw_text=raw_text,
            text_value=text_value,
            value=_parse_numeric(text_value) if kind == "nonFraction" else None,
            row_labels=row_labels,
            col_labels=col_labels,
            continued_at=continued_at,
        ))
    return doc
