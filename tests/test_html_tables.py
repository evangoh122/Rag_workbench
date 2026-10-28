"""Real-bs4 tests for structure-aware HTML table parsing."""
import sys

import bs4
import pytest

from api.services.html_tables import (
    parse_tables,
    serialize_tables_in_soup,
    table_to_pipe,
    table_to_records,
    tables_to_text,
)

_REAL_BS4 = bs4


@pytest.fixture(autouse=True)
def _real_bs4(monkeypatch):
    # tests/test_scripts.py replaces sys.modules["bs4"] with a MagicMock when it
    # is collected; keep the real library for this module's tests.
    monkeypatch.setitem(sys.modules, "bs4", _REAL_BS4)


SIMPLE_TABLE = """
<table>
  <caption>Filing fees</caption>
  <tr><th>Line</th><th>Amount</th><th>Rate</th></tr>
  <tr><td>Proposed Maximum Aggregate Offering Price</td>
      <td>$1,000,000,000.00</td><td>0.000087</td></tr>
  <tr><td>Total Fee</td><td>$87,000.00</td><td></td></tr>
</table>
"""

SPAN_TABLE = """
<table>
  <tr><th rowspan="2">Item</th><th colspan="2">Year</th></tr>
  <tr><th>2026</th><th>2025</th></tr>
  <tr><td>Revenue</td><td>10</td><td>8</td></tr>
</table>
"""

NESTED_TABLE = """
<table>
  <tr><td>outer</td><td><table><tr><td>inner</td><td>2</td></tr></table></td></tr>
</table>
"""


def test_parse_tables_finds_caption_and_dimensions():
    tables = parse_tables(SIMPLE_TABLE)
    assert len(tables) == 1
    t = tables[0]
    assert t.caption == "Filing fees"
    assert t.n_rows == 3
    assert t.n_cols == 3
    assert t.header_row_count == 1


def test_table_to_records_keeps_header_association():
    records = table_to_records(parse_tables(SIMPLE_TABLE)[0])
    assert records == [
        {
            "Row": "Proposed Maximum Aggregate Offering Price",
            "Amount": "$1,000,000,000.00",
            "Rate": "0.000087",
        },
        {"Row": "Total Fee", "Amount": "$87,000.00", "Rate": ""},
    ]


def test_rowspan_colspan_expand_to_dense_grid():
    t = parse_tables(SPAN_TABLE)[0]
    assert t.n_rows == 3
    assert t.n_cols == 3
    assert t.grid[0][0].text == "Item"
    assert t.grid[0][0].rowspan == 2
    assert t.grid[0][1] is not None and t.grid[0][1].colspan == 2
    assert t.grid[1][0] is None  # covered by rowspan
    assert t.grid[1][1].text == "2026"


def test_table_to_pipe_preserves_cell_boundaries():
    pipe = table_to_pipe(parse_tables(SPAN_TABLE)[0])
    lines = pipe.splitlines()
    assert lines[0] == "| Item | Year |  |"
    assert lines[1] == "|  | 2026 | 2025 |"
    assert lines[2] == "| Revenue | 10 | 8 |"


def test_nested_tables_parsed_independently():
    tables = parse_tables(NESTED_TABLE)
    assert len(tables) == 2  # outer and inner
    outer = tables[0]
    # Outer grid contains the inner cell's text but not the inner rows as rows.
    assert outer.n_rows == 1
    assert "inner" in outer.grid[0][1].text


def test_serialize_tables_replaces_table_with_pipe_text():
    html = f"<html><body><p>before</p>{SIMPLE_TABLE}<p>after</p></body></html>"
    out = tables_to_text(html)
    assert "before" in out and "after" in out
    assert "| Total Fee | $87,000.00 |  |" in out
    assert "<table" not in out


def test_serialize_tables_in_soup_counts_only_outer_tables():
    soup = _REAL_BS4.BeautifulSoup(NESTED_TABLE, "lxml")
    assert serialize_tables_in_soup(soup) == 1
    assert soup.find("table") is None
    assert "inner" in soup.get_text()
