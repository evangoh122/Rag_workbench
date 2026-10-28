"""
html_tables.py — Structure-aware HTML table parsing for SEC filings.

Parses ``<table>`` elements into row/column grids that honour ``rowspan`` and
``colspan``, keep caption/header information, and serialize without losing the
row-to-column relationships that ``get_text()`` flattening destroys.

Outputs:
- ``table_to_records``: one dict per data row, keyed by column headers
- ``table_to_pipe``: pipe-delimited text (what the ingestion chunker consumes)
- ``HTMLTable.grid``: expanded cell matrix (each cell keeps its source tag)

Usage:
    from api.services.html_tables import parse_tables, table_to_pipe
    for table in parse_tables(html):
        print(table_to_pipe(table))
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, NavigableString, Tag


@dataclass
class TableCell:
    """One logical cell in a table grid."""
    text: str
    rowspan: int = 1
    colspan: int = 1
    is_header: bool = False
    source: Tag | None = None


@dataclass
class HTMLTable:
    """A parsed table: caption plus an expanded (rowspan/colspan-aware) grid."""
    caption: str = ""
    grid: list[list[TableCell | None]] = field(default_factory=list)
    header_row_count: int = 0

    @property
    def n_rows(self) -> int:
        return len(self.grid)

    @property
    def n_cols(self) -> int:
        return max((len(r) for r in self.grid), default=0)


def _cell_text(tag: Tag) -> str:
    return " ".join(tag.get_text(" ", strip=True).split())


def _direct_rows(table: Tag) -> list[Tag]:
    """``<tr>`` elements belonging to this table (nested tables excluded)."""
    return [
        tr for tr in table.find_all("tr")
        if tr.find_parent("table") is table
    ]


def _parse_table_tag(table: Tag) -> HTMLTable | None:
    caption_tag = table.find("caption")
    caption = _cell_text(caption_tag) if caption_tag and caption_tag.find_parent("table") is table else ""

    rows = _direct_rows(table)
    if not rows:
        return None

    # Expand rowspan/colspan into a dense grid of cells (None = covered span).
    grid: list[list[TableCell | None]] = []
    occupied: dict[tuple[int, int], bool] = {}

    for row in rows:
        row_idx = len(grid)
        grid.append([])
        col_idx = 0
        for cell in row.find_all(["td", "th"], recursive=False):
            while occupied.get((row_idx, col_idx)):
                grid[row_idx].append(None)
                col_idx += 1
            try:
                rowspan = max(1, int(cell.get("rowspan") or 1))
                colspan = max(1, int(cell.get("colspan") or 1))
            except (TypeError, ValueError):
                rowspan, colspan = 1, 1
            parsed = TableCell(
                text=_cell_text(cell),
                rowspan=rowspan,
                colspan=colspan,
                is_header=cell.name == "th",
                source=cell,
            )
            for dr in range(rowspan):
                for dc in range(colspan):
                    occupied[(row_idx + dr, col_idx + dc)] = True
            grid[row_idx].append(parsed)
            col_idx += 1
            for _ in range(colspan - 1):
                grid[row_idx].append(None)
                col_idx += 1

    if not any(cell is not None for row in grid for cell in row):
        return None

    header_row_count = 0
    for row in grid:
        cells = [c for c in row if c is not None]
        if cells and all(c.is_header for c in cells):
            header_row_count += 1
        else:
            break

    return HTMLTable(caption=caption, grid=grid, header_row_count=header_row_count)


def parse_soup_tables(soup: BeautifulSoup | Tag) -> list[HTMLTable]:
    """Parse every ``<table>`` under an existing soup, keeping tag identity."""
    tables = []
    for table in soup.find_all("table"):
        parsed = _parse_table_tag(table)
        if parsed is not None:
            tables.append(parsed)
    return tables


def parse_tables(html: str | Tag) -> list[HTMLTable]:
    """Parse every ``<table>`` in an HTML document or fragment."""
    soup = BeautifulSoup(html if isinstance(html, str) else str(html), "lxml")
    return parse_soup_tables(soup)


_NUMERIC_RE = re.compile(r"^\(?[$]?\s*[\d,.]+\s*[%]?\)?$")


def _looks_numeric(text: str) -> bool:
    return bool(text) and bool(_NUMERIC_RE.match(text))


def _first_cell_is_row_label(row: list[TableCell | None]) -> bool:
    """Financial tables label rows with plain <td>: the leading cell is text
    while the trailing cells carry numbers."""
    cells = [c for c in row if c is not None]
    if len(cells) < 2 or _looks_numeric(cells[0].text):
        return False
    return any(_looks_numeric(c.text) for c in cells[1:])


def table_to_records(table: HTMLTable) -> list[dict[str, str]]:
    """One dict per data row: column-header label -> cell text.

    Leading ``<th>`` cells of a data row — or a text label followed by numeric
    cells — become the ``"Row"`` key so row labels stay attached to their
    values.
    """
    column_labels: list[str] = []
    if table.header_row_count:
        merged: list[str] = []
        for hrow in table.grid[: table.header_row_count]:
            current: list[str] = []
            for cell in hrow:
                if cell is None:
                    continue
                for _ in range(cell.colspan):
                    current.append(cell.text)
            for i, label in enumerate(current):
                if i < len(merged):
                    if label:
                        merged[i] = f"{merged[i]} | {label}" if merged[i] and merged[i] != label else label
                else:
                    merged.append(label)
            while len(merged) < len(current):
                merged.append("")
        column_labels = merged

    records: list[dict[str, str]] = []
    for row in table.grid[table.header_row_count:]:
        record: dict[str, str] = {}
        row_label_parts: list[str] = []
        use_row_key = _first_cell_is_row_label(row)
        first_cell_taken = False
        col_ptr = 0
        for slot in row:
            if slot is None:
                col_ptr += 1
                continue
            if slot.is_header:
                if slot.text:
                    row_label_parts.append(slot.text)
            elif use_row_key and not first_cell_taken:
                first_cell_taken = True
                if slot.text:
                    row_label_parts.append(slot.text)
            else:
                first_cell_taken = True
                key = column_labels[col_ptr] if col_ptr < len(column_labels) and column_labels[col_ptr] else f"col_{col_ptr}"
                record[key] = slot.text
            col_ptr += slot.colspan
        if row_label_parts:
            record["Row"] = " | ".join(row_label_parts)
        if record:
            records.append(record)
    return records


def table_to_pipe(table: HTMLTable) -> str:
    """Serialize a table to pipe-delimited text.

    Header rows are emitted first, then each data row in grid order. Cell
    boundaries (including covered rowspan/colspan slots) are kept so
    downstream chunking retains the row/column structure.
    """
    lines: list[str] = []
    if table.caption:
        lines.append(f"[Table: {table.caption}]")
    for row in table.grid:
        cells = [cell.text if cell is not None else "" for cell in row]
        if not any(cells):
            continue
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def serialize_tables_in_soup(soup: BeautifulSoup) -> int:
    """Replace every ``<table>`` in ``soup`` in place with its pipe form.

    Returns the number of tables replaced. Used by the ingestion text
    extractor so tables survive as structured text instead of flattened
    fragments.
    """
    count = 0
    for table in list(soup.find_all("table")):
        if table.find_parent("table") is not None:
            continue  # replaced together with its outer table
        parsed = _parse_table_tag(table)
        rendered = table_to_pipe(parsed) if parsed else table.get_text(" ", strip=True)
        table.replace_with(NavigableString(f"\n{rendered}\n"))
        count += 1
    return count


def tables_to_text(html: str) -> str:
    """Return ``html`` with every ``<table>`` replaced by its pipe form."""
    soup = BeautifulSoup(html, "lxml")
    if serialize_tables_in_soup(soup) == 0:
        return html
    return str(soup)
