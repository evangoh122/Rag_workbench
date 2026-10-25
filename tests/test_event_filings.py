from datetime import date, timedelta
from types import SimpleNamespace

from scripts.event_filings import (
    event_form_for,
    event_period,
    sections_for_event_filing,
    select_recent_filings,
    split_8k_items,
)

TODAY = date.today()

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
    assert list(items) == ["item_preamble", "item_2.02", "item_5.02", "item_9.01"]
    assert "revenue of $10 billion" in items["item_2.02"]
    assert "CFO resigned" in items["item_5.02"]
    assert "CFO" not in items["item_2.02"]


def test_inline_item_reference_is_not_a_heading():
    text = "Item 2.02 Results.\nRevenue grew; see Item 7.01 and Item 9.01 for more.\n"
    items = dict(split_8k_items(text))
    assert list(items) == ["item_2.02"]  # inline refs create no sections
    assert "see Item 7.01 and Item 9.01 for more." in items["item_2.02"]


def test_repeated_heading_bodies_are_merged_under_one_label():
    text = "Item 5.02 Departure.\nFirst part.\nItem 8.01 Other.\nx\nItem 5.02 Departure (cont).\nSecond part.\n"
    items = split_8k_items(text)
    assert [label for label, _ in items] == ["item_5.02", "item_8.01"]
    body = dict(items)["item_5.02"]
    assert "First part." in body and "Second part." in body


def test_text_before_first_heading_is_kept_as_preamble():
    items = dict(split_8k_items(EIGHT_K))
    assert list(items)[0] == "item_preamble"
    assert "Current Report" in items["item_preamble"]


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
    f = SimpleNamespace(form="6-K", filing_date=(TODAY - timedelta(days=5)).isoformat(), accession_number="x")
    assert select_recent_filings([f], "6-K", 30, 5, today=TODAY) == [f]


def test_event_period_prefers_report_date_then_filing_date():
    f = _f("8-K", 3)
    assert event_period(f, "2026-12-31") == (TODAY - timedelta(days=3)).isoformat()
    f.period_of_report = "2026-10-20"
    assert event_period(f, "2026-12-31") == "2026-10-20"
    assert event_period(SimpleNamespace(), "2026-12-31") == "2026-12-31"


def _run_main(tmp_path, monkeypatch, filing_objs, argv_extra=()):
    """Run embed_additional.main() --forms 8-K with mocked EDGAR/embedder; return (db, ea)."""
    import sys
    from unittest.mock import MagicMock

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

    filings = MagicMock()
    filings.empty = False
    filings.latest.return_value = filing_objs

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
    monkeypatch.setattr(ea, "Company", lambda t: SimpleNamespace(get_filings=lambda **kw: filings))
    monkeypatch.setattr(sys, "argv", ["embed_additional.py", "--forms", "8-K", *argv_extra])

    ea.main()
    return db


def test_embed_additional_8k_end_to_end_mocked(tmp_path, monkeypatch):
    """item ids stored, existing accession skipped."""
    import duckdb

    new = _f("8-K", 3, "0000000001-26-000011")
    dup = _f("8-K", 4, "0000000001-26-000010")
    new.text = lambda: "html"
    dup.text = lambda: "html"
    db = _run_main(tmp_path, monkeypatch, [new, dup])

    conn = duckdb.connect(db, read_only=True)
    rows = conn.execute(
        "SELECT section_id, form_type, accession, len(embedding) FROM edgar_embeddings "
        "WHERE form_type='8-K' ORDER BY section_id"
    ).fetchall()
    n10k = conn.execute("SELECT count(*) FROM edgar_embeddings WHERE form_type='10-K'").fetchone()[0]
    conn.close()
    assert [r[0] for r in rows] == ["item_2.02", "item_5.02", "item_9.01", "item_preamble"]
    assert {r[2] for r in rows} == {"0000000001-26-000011"}
    assert {r[3] for r in rows} == {1024}
    assert n10k == 1


class _EntityFilingLike:
    """EntityFiling-like: report_date is submissions-backed; period_of_report may raise."""

    def __init__(self, acc, days_ago, report_date=None, period_raises=False):
        self.form = "8-K"
        self.accession_number = acc
        self.filing_date = TODAY - timedelta(days=days_ago)
        self.report_date = report_date
        self._period_raises = period_raises

    @property
    def period_of_report(self):
        if self._period_raises:
            raise RuntimeError("SGML submission download failed")
        return "2020-01-01"

    def text(self):
        return "html"


def test_event_period_survives_raising_period_of_report():
    f = _EntityFilingLike("a", 3, period_raises=True)
    assert event_period(f, "2026-12-31") == (TODAY - timedelta(days=3)).isoformat()
    g = _EntityFilingLike("b", 3, report_date=date(2026, 10, 20), period_raises=True)
    assert event_period(g, "2026-12-31") == "2026-10-20"  # period_of_report never touched


def test_bad_period_of_report_does_not_stop_refresh(tmp_path, monkeypatch):
    import duckdb

    bad = _EntityFilingLike("0000000001-26-000020", 2, period_raises=True)
    good = _EntityFilingLike("0000000001-26-000021", 3, report_date=date(2026, 10, 20))
    later = _EntityFilingLike("0000000001-26-000022", 4)
    db = _run_main(tmp_path, monkeypatch, [bad, good, later])

    conn = duckdb.connect(db, read_only=True)
    got = dict(
        conn.execute(
            "SELECT accession, min(period_of_report) FROM edgar_embeddings "
            "WHERE form_type='8-K' GROUP BY 1"
        ).fetchall()
    )
    conn.close()
    assert set(got) == {bad.accession_number, good.accession_number, later.accession_number}
    assert got[bad.accession_number] == (TODAY - timedelta(days=2)).isoformat()
    assert got[good.accession_number] == "2026-10-20"
    assert got[later.accession_number] == (TODAY - timedelta(days=4)).isoformat()


def test_max_chunks_per_filing_caps_chunks(tmp_path, monkeypatch):
    import duckdb

    f = _EntityFilingLike("0000000001-26-000030", 2)
    db = _run_main(tmp_path, monkeypatch, [f], ("--max-chunks-per-filing", "2"))
    conn = duckdb.connect(db, read_only=True)
    n = conn.execute("SELECT count(*) FROM edgar_embeddings WHERE form_type='8-K'").fetchone()[0]
    conn.close()
    assert n == 2


def test_empty_report_date_is_missing_not_fallthrough_to_period_of_report():
    f = _EntityFilingLike("e", 3, report_date="")
    # period_of_report would give 2020-01-01; empty report_date must use filing date
    assert event_period(f, "2026-12-31") == (TODAY - timedelta(days=3)).isoformat()
    # attribute entirely absent -> period_of_report is tried
    g = SimpleNamespace(period_of_report="2026-10-01", filing_date=TODAY)
    assert event_period(g, "x") == "2026-10-01"


def test_invalid_cli_bounds_error(tmp_path, monkeypatch):
    import pytest

    for flag in ("--max-filings", "--days"):
        with pytest.raises(SystemExit) as e:
            _run_main(tmp_path, monkeypatch, [], (flag, "0"))
        assert e.value.code == 2


def test_get_filings_called_without_amendments(tmp_path, monkeypatch):
    calls = []
    f = _EntityFilingLike("0000000001-26-000040", 2)
    import sys
    _run_main(tmp_path, monkeypatch, [f])
    ea = sys.modules["scripts.embed_additional"]
    # re-run with a recording Company
    from types import SimpleNamespace as NS
    from unittest.mock import MagicMock
    filings = MagicMock()
    filings.empty = False
    filings.latest.return_value = []
    monkeypatch.setattr(ea, "Company", lambda t: NS(get_filings=lambda **kw: calls.append(kw) or filings))
    monkeypatch.setattr(sys, "argv", ["embed_additional.py", "--forms", "8-K", "--dry-run"])
    ea.DB_PATH = ea.DB_PATH
    ea.main()
    assert calls and calls[0]["amendments"] is False and calls[0]["form"] == "8-K"
    assert calls[0]["filing_date"].endswith(":")
