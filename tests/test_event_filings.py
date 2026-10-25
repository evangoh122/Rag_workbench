from datetime import date, timedelta
from types import SimpleNamespace

from scripts.event_filings import (
    event_form_for,
    event_period,
    sections_for_event_filing,
    select_recent_filings,
    split_8k_items,
)

TODAY = date(2026, 10, 26)

EIGHT_K = """UNITED STATES SECURITIES AND EXCHANGE COMMISSION
FORM 8-K  Current Report
Item 2.02 Results of Operations and Financial Condition.
The Company reported revenue of $10 billion. See Item 9.01 for exhibits.
Item 5.02. Departure of Directors or Certain Officers.
The CFO resigned effective immediately.
ITEM 9.01 Financial Statements and Exhibits
99.1 Press release
"""


def _f(form, days_ago, acc="0000000000-26-000001"):
    return SimpleNamespace(
        form=form,
        filing_date=TODAY - timedelta(days=days_ago),
        accession_number=acc,
        period_of_report=None,
    )


def test_split_items_labels_and_bodies():
    items = dict(split_8k_items(EIGHT_K))
    assert list(items) == ["item_2.02", "item_5.02", "item_9.01"]
    assert "revenue of $10 billion" in items["item_2.02"]
    assert "CFO resigned" in items["item_5.02"]
    assert "CFO" not in items["item_2.02"]


def test_inline_item_reference_is_not_a_heading():
    labels = [l for l, _ in split_8k_items(EIGHT_K)]
    assert labels.count("item_9.01") == 1  # "See Item 9.01" mid-line ignored


def test_no_items_falls_back_to_full_text():
    assert split_8k_items("plain press release text") == []
    assert sections_for_event_filing("8-K", "plain text") == [("full_text", "plain text")]


def test_6k_is_never_item_split():
    assert sections_for_event_filing("6-K", EIGHT_K) == [("full_text", EIGHT_K)]


def test_empty_text_yields_no_sections():
    assert sections_for_event_filing("8-K", "  ") == []


def test_event_form_for():
    assert event_form_for({"10-K", "10-Q"}) == "8-K"
    assert event_form_for({"20-F"}) == "6-K"
    assert event_form_for({"20-F", "10-K"}) == "8-K"
    assert event_form_for({"S-1"}) is None


def test_select_recent_window_amendments_and_cap():
    filings = [
        _f("8-K", 5, "a1"),
        _f("8-K/A", 6, "a2"),
        _f("8-K", 200, "old"),
        _f("8-K", 40, "a3"),
        _f("8-K", 10, "a4"),
        SimpleNamespace(form="8-K", filing_date=None, accession_number="nodate"),
    ]
    got = select_recent_filings(filings, "8-K", days=180, limit=2, today=TODAY)
    assert [f.accession_number for f in got] == ["a1", "a4"]
    got = select_recent_filings(filings, "8-K", days=180, limit=10, today=TODAY)
    assert [f.accession_number for f in got] == ["a1", "a4", "a3"]


def test_select_accepts_iso_string_dates():
    f = SimpleNamespace(form="6-K", filing_date="2026-10-01", accession_number="x")
    assert select_recent_filings([f], "6-K", 30, 5, today=TODAY) == [f]


def test_event_period_prefers_report_date_then_filing_date():
    f = _f("8-K", 3)
    assert event_period(f, "2026-12-31") == (TODAY - timedelta(days=3)).isoformat()
    f.period_of_report = "2026-10-20"
    assert event_period(f, "2026-12-31") == "2026-10-20"
    assert event_period(SimpleNamespace(), "2026-12-31") == "2026-12-31"


def test_embed_additional_8k_end_to_end_mocked(tmp_path, monkeypatch):
    """main() --forms 8-K with mocked EDGAR/embedder: item ids stored, existing skipped."""
    import sys
    from unittest.mock import MagicMock, patch

    import duckdb

    for mod in ["edgar", "bs4", "sec_edgar_downloader", "langchain_text_splitters"]:
        monkeypatch.setitem(sys.modules, mod, sys.modules.get(mod) or MagicMock())
    if isinstance(sys.modules["bs4"], MagicMock):  # mocked by tests/test_scripts.py
        sys.modules["bs4"].XMLParsedAsHTMLWarning = type("XMLParsedAsHTMLWarning", (Warning,), {})
    import scripts.embed_additional as ea

    db = str(tmp_path / "t.duckdb")
    conn = duckdb.connect(db)
    ea._ensure_schema(conn)
    conn.execute(
        "INSERT INTO edgar_embeddings (ticker, accession, text, embedding, form_type) "
        "VALUES ('AAA','0000000001-26-000010','x',?, '10-K')",
        [[0.0] * 1024],
    )
    conn.commit()
    conn.close()

    new = _f("8-K", 3, "0000000001-26-000011")
    dup = _f("8-K", 4, "0000000001-26-000010")
    filings = MagicMock()
    filings.empty = False
    filings.latest.return_value = [new, dup]
    new.text = lambda: "html"
    dup.text = lambda: "html"

    model = MagicMock()
    model.embed_documents.side_effect = lambda texts: [[0.1] * 1024 for _ in texts]
    chunker = MagicMock()
    chunker.chunk.side_effect = lambda text, section_label, **kw: [
        SimpleNamespace(
            text=text,
            metadata=SimpleNamespace(
                section_label=section_label, chunk_index=0,
                section_type="narrative", content_type="narrative",
            ),
        )
    ]
    monkeypatch.setattr(ea, "DB_PATH", db)
    monkeypatch.setattr(ea, "ROOT", tmp_path)
    monkeypatch.setattr(ea, "ensure_edgar_identity", lambda: None)
    monkeypatch.setattr(ea, "get_embeddings", lambda: model)
    monkeypatch.setattr(ea, "StructureChunker", lambda **kw: chunker)
    monkeypatch.setattr(ea, "parse_html_file", lambda p: (EIGHT_K, ""))
    monkeypatch.setattr(ea, "Company", lambda t: SimpleNamespace(get_filings=lambda form: filings))
    monkeypatch.setattr(sys, "argv", ["embed_additional.py", "--forms", "8-K"])

    ea.main()

    conn = duckdb.connect(db, read_only=True)
    rows = conn.execute(
        "SELECT section_id, form_type, accession, len(embedding) FROM edgar_embeddings "
        "WHERE form_type='8-K' ORDER BY section_id"
    ).fetchall()
    n10k = conn.execute("SELECT count(*) FROM edgar_embeddings WHERE form_type='10-K'").fetchone()[0]
    conn.close()
    assert [r[0] for r in rows] == ["item_2.02", "item_5.02", "item_9.01"]
    assert {r[2] for r in rows} == {"0000000001-26-000011"}  # duplicate accession skipped
    assert {r[3] for r in rows} == {1024}
    assert n10k == 1
