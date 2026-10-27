import sys
from unittest.mock import MagicMock

import pytest

# Mock missing modules
for mod in ["sec_edgar_downloader", "langchain_text_splitters", "bs4", "edgar"]:
    sys.modules[mod] = MagicMock()

# Fix broken import in scripts/embed_edgar.py
import scripts.embed_tickers  # noqa: E402
scripts.embed_tickers.get_embeddings = MagicMock()

from unittest.mock import patch, mock_open  # noqa: E402

# Now we can import the scripts
from scripts.embed_edgar import (  # noqa: E402
    _TICKER_CIK,
    _downloader_filing_dir,
    _fetch_filing_with_downloader,
    _fetch_filing_with_edgartools,
    _filing_lookup_key,
    _reset_incompatible_embeddings,
    run_embed_edgar_etl,
)
from scripts.embed_tickers import (  # noqa: E402
    _load_ticker_rows,
    _reset_incompatible_embeddings as _reset_incompatible_ticker_embeddings,
)
from scripts.init_graph_triples import init_graph_triples  # noqa: E402
from scripts.run_shadow import load_extractions, main as shadow_main  # noqa: E402

# ── Embed Edgar Script Tests ─────────────────────────────────────────────────

def test_internal_alias_lookup_only_changes_anthropic():
    assert _filing_lookup_key("ANTH") == "0002130357"
    assert _filing_lookup_key("SPCX") == "SPCX"
    assert _filing_lookup_key("NVDA") == "NVDA"


def test_anthropic_cik_comes_from_central_config():
    from api.config import TICKER_TO_CIK

    assert TICKER_TO_CIK.get("ANTH") == "0002130357"
    assert _TICKER_CIK.get("ANTH") == TICKER_TO_CIK.get("ANTH")


@pytest.mark.parametrize(
    ("ticker", "expected_lookup"),
    [("ANTH", "0002130357"), ("SPCX", "SPCX"), ("NVDA", "NVDA")],
)
def test_embed_additional_uses_cik_lookup_key(ticker, expected_lookup, monkeypatch):
    import duckdb

    monkeypatch.setenv("EDGAR_USER_AGENT", "Test User test@example.com")

    sys.modules["bs4"].XMLParsedAsHTMLWarning = UserWarning  # mocked bs4 stub
    import scripts.embed_additional as module

    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE edgar_embeddings (ticker VARCHAR, form_type VARCHAR, accession VARCHAR)")
    conn.execute("INSERT INTO edgar_embeddings VALUES (?, '10-K', 'a')", [ticker])
    company = MagicMock()
    company.get_filings.return_value = MagicMock(empty=True)
    with (
        patch.object(sys, "argv", ["embed_additional", "--dry-run", "--tickers", ticker]),
        patch.object(module, "ensure_edgar_identity"),
        patch.object(module, "get_embeddings", return_value=MagicMock()),
        patch.object(module, "StructureChunker"),
        patch.object(module.duckdb, "connect", return_value=conn),
        patch.object(module, "Company", return_value=company) as company_cls,
    ):
        module.main()

    company_cls.assert_called_once_with(expected_lookup)


@pytest.mark.parametrize("value", [None, "", "   "])
def test_embed_additional_requires_edgar_user_agent_before_any_work(monkeypatch, value):
    sys.modules["bs4"].XMLParsedAsHTMLWarning = UserWarning
    import scripts.embed_additional as module

    if value is None:
        monkeypatch.delenv("EDGAR_USER_AGENT", raising=False)
    else:
        monkeypatch.setenv("EDGAR_USER_AGENT", value)
    with (
        patch.object(sys, "argv", ["embed_additional", "--dry-run"]),
        patch.object(module, "ensure_edgar_identity") as ident,
        patch.object(module, "get_embeddings") as model,
        patch.object(module.duckdb, "connect") as connect,
    ):
        with pytest.raises(SystemExit) as exc:
            module.main()
    assert "EDGAR_USER_AGENT is not set" in str(exc.value)
    ident.assert_not_called()
    model.assert_not_called()
    connect.assert_not_called()


def test_embed_additional_has_no_hardcoded_identity():
    import pathlib

    src = (pathlib.Path(__file__).resolve().parent.parent / "scripts" / "embed_additional.py").read_text(encoding="utf-8")
    assert "gmail.com" not in src and 'setdefault("EDGAR_USER_AGENT"' not in src


def test_downloader_path_uses_zero_padded_anthropic_cik(tmp_path):
    import scripts.embed_edgar as module

    with patch.object(module, "_DOWNLOAD_DIR", tmp_path):
        path = _downloader_filing_dir(_filing_lookup_key("ANTH"), "S-1")

    assert path == tmp_path / "sec-edgar-filings" / "0002130357" / "S-1"


@pytest.mark.parametrize(
    ("ticker", "expected_lookup"),
    [("ANTH", "0002130357"), ("SPCX", "SPCX"), ("NVDA", "NVDA")],
)
def test_edgartools_uses_expected_lookup_key(tmp_path, ticker, expected_lookup):
    import scripts.embed_edgar as module

    filing = MagicMock(accession_number="0001628280-26-067168")
    filing.text.return_value = "Anthropic S-1"
    filings = MagicMock(empty=False)
    filings.latest.return_value = filing
    company = MagicMock()
    company.get_filings.return_value = filings
    with (
        patch.object(module, "_DOWNLOAD_DIR", tmp_path),
        patch("edgar.Company", return_value=company) as company_cls,
        patch("api.services._edgar_identity.ensure_edgar_identity"),
    ):
        path, form, accession = _fetch_filing_with_edgartools(ticker, ["S-1"])

    company_cls.assert_called_once_with(expected_lookup)
    assert form == "S-1"
    assert accession == "000162828026067168"
    assert path.endswith(f"{ticker}/S-1/000162828026067168/primary-document.html")


@pytest.mark.parametrize(
    ("ticker", "expected_lookup"),
    [("ANTH", "0002130357"), ("SPCX", "SPCX"), ("NVDA", "NVDA")],
)
def test_downloader_uses_expected_lookup_key(tmp_path, ticker, expected_lookup):
    import scripts.embed_edgar as module

    primary = tmp_path / "sec-edgar-filings" / expected_lookup / "S-1" / "accession" / "primary-document.html"
    primary.parent.mkdir(parents=True)
    primary.write_text("Anthropic S-1", encoding="utf-8")
    downloader = MagicMock()
    downloader.get.return_value = 1
    with patch.object(module, "_DOWNLOAD_DIR", tmp_path), patch.object(module, "Downloader", return_value=downloader):
        path, form = _fetch_filing_with_downloader(ticker, ["S-1"])

    downloader.get.assert_called_once_with("S-1", expected_lookup, limit=1, download_details=True)
    assert (path, form) == (str(primary), "S-1")


def test_reset_incompatible_embeddings_clears_mixed_dimensions():
    import duckdb

    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE edgar_embeddings (embedding FLOAT[])")
    conn.execute("INSERT INTO edgar_embeddings VALUES ([1, 2]), ([1, 2, 3])")

    assert _reset_incompatible_embeddings(conn, expected_dim=3) is True
    assert conn.execute("SELECT COUNT(*) FROM edgar_embeddings").fetchone()[0] == 0


def test_reset_incompatible_embeddings_keeps_matching_corpus():
    import duckdb

    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE edgar_embeddings (embedding FLOAT[])")
    conn.execute("INSERT INTO edgar_embeddings VALUES ([1, 2, 3]), ([4, 5, 6])")

    assert _reset_incompatible_embeddings(conn, expected_dim=3) is False
    assert conn.execute("SELECT COUNT(*) FROM edgar_embeddings").fetchone()[0] == 2


def test_reset_incompatible_ticker_embeddings_preserves_metadata():
    import duckdb

    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE ticker_embeddings (
            ticker VARCHAR, description VARCHAR, text VARCHAR,
            embedding FLOAT[], updated_at VARCHAR
        )
    """)
    conn.execute("INSERT INTO ticker_embeddings VALUES ('AMD', 'Advanced Micro Devices', 'old', [1, 2], 'old')")

    assert _reset_incompatible_ticker_embeddings(conn, expected_dim=3) is True
    row = conn.execute(
        "SELECT ticker, description, text, embedding, updated_at FROM ticker_embeddings"
    ).fetchone()
    assert row == ("AMD", "Advanced Micro Devices", None, None, None)


def test_load_ticker_rows_without_polygon_table():
    import duckdb

    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE ticker_embeddings (ticker VARCHAR, description VARCHAR)")
    conn.execute("INSERT INTO ticker_embeddings VALUES ('AMD', 'Advanced Micro Devices'), ('EMPTY', '')")

    assert _load_ticker_rows(conn) == [{
        "ticker": "AMD",
        "name": "Advanced Micro Devices",
        "description": "Advanced Micro Devices",
    }]

@patch("scripts.embed_edgar.Downloader")
@patch("scripts.embed_edgar.duckdb.connect")
@patch("scripts.embed_edgar._get_model")
@patch("scripts.embed_edgar.parse_html_file")
@patch("scripts.embed_edgar.BeautifulSoup")
def test_run_embed_edgar_etl(mock_bs, mock_parse, mock_get_model, mock_db, mock_downloader_cls):
    mock_downloader = MagicMock()
    mock_downloader_cls.return_value = mock_downloader
    mock_downloader.get.return_value = 1
    
    mock_conn = MagicMock()
    mock_db.return_value.__enter__.return_value = mock_conn
    
    mock_parse.return_value = ("Extracted text", "<html>raw</html>")
    
    # Mock BeautifulSoup to return a string when get_text is called
    mock_bs.return_value.get_text.return_value = "Sample clean text for re.sub to work with."
    
    mock_model = MagicMock()
    mock_get_model.return_value = mock_model
    mock_model.embed_documents.return_value = [[0.1, 0.2]]
    
    # Mock file paths
    with patch("scripts.embed_edgar.Path") as mock_path:
        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_file.parent.name = "0001045810-24-000029"
        mock_path.return_value = mock_file
        
        # Mock _fetch_filing_with_downloader to return a fake path
        with patch("scripts.embed_edgar._fetch_filing_with_downloader") as mock_fetch:
            mock_fetch.return_value = ("fake/path/primary-document.html", "10-K")
            
            # Use a small subset of tickers for speed
            result = run_embed_edgar_etl(tickers=["NVDA"])
            
            assert result >= 0
            mock_conn.execute.assert_called()

# ── Init Graph Triples Script Tests ──────────────────────────────────────────

@patch("scripts.init_graph_triples.duckdb.connect")
@patch("glob.glob")
@patch("builtins.open", new_callable=mock_open, read_data='{"edges": [{"source": "A", "relation": "B", "target": "C"}]}')
def test_init_graph_triples(mock_file, mock_glob, mock_db):
    mock_glob.return_value = ["chunk_1.json"]
    mock_conn = MagicMock()
    mock_db.return_value = mock_conn
    
    init_graph_triples("fake.db", "fake_dir", ticker="NVDA")
    
    # Check if table creation and insertion were called
    calls = [call[0][0] for call in mock_conn.execute.call_args_list]
    assert any("CREATE TABLE" in c for c in calls)
    assert any("INSERT OR IGNORE" in c for c in calls)

# ── Run Shadow Script Tests ──────────────────────────────────────────────────

@patch("scripts.run_shadow.duckdb.connect")
def test_load_extractions(mock_db):
    mock_conn = MagicMock()
    mock_db.return_value = mock_conn
    
    # Mock rows for tickers and facts
    # We call load_extractions(mock_conn, ["NVDA"])
    # So it skips the first execute() which is for all tickers
    # The first fetchall() will be for periods
    # The second fetchall() will be for facts
    mock_conn.execute.return_value.fetchall.side_effect = [
        [("2023-12-31", "000-111", "10-K")], # periods
        [("Revenues", 1000.0, "USD")] # facts
    ]
    
    from api.models.eval_types import ExtractionResult
    extractions = load_extractions(mock_conn, ["NVDA"])
    
    assert len(extractions) == 1
    assert isinstance(extractions[0], ExtractionResult)
    assert extractions[0].period == "2023-12-31"
    assert extractions[0].fields[0].name == "Revenues"

@patch("scripts.run_shadow.duckdb.connect")
@patch("scripts.run_shadow.run_shadow_pipeline")
@patch("scripts.run_shadow.report_to_json")
@patch("builtins.open", new_callable=mock_open)
@patch("sys.argv", ["run_shadow.py", "--tickers", "NVDA"])
def test_shadow_main(mock_file, mock_report_json, mock_pipeline, mock_db):
    mock_conn = MagicMock()
    mock_db.return_value = mock_conn
    
    # Mock load_extractions to return something
    with patch("scripts.run_shadow.load_extractions") as mock_load:
        mock_load.return_value = [MagicMock()]
        
        mock_report = MagicMock()
        mock_report.total_processed = 1
        mock_report.errors = 0
        mock_report.auto_count = 1
        mock_report.confidence_histogram = {}
        mock_report.trigger_counts = {}
        mock_pipeline.return_value = mock_report
        mock_report_json.return_value = "{}"
        
        shadow_main()
        
        mock_pipeline.assert_called_once()
        mock_file().write.assert_called_once_with("{}")


def test_extract_sections_longest_match():
    from scripts.embed_edgar import _extract_sections_with_labels
    # Simulating a Table of Contents entry followed by the actual section body
    fake_text = """
    TABLE OF CONTENTS
    Item 7. Management's Discussion and Analysis of Financial Condition .... 35
    ...
    Item 7. Management's Discussion and Analysis of Financial Condition
    This is the actual section body which contains a lot of text and details about the company's financial performance. It is much longer than the table of contents entry.
    """
    sections = _extract_sections_with_labels(fake_text)
    # Check if Item 7 was extracted and matches the longer body
    item_7_sections = [text for label, text in sections if label == "item_7"]
    assert len(item_7_sections) == 1
    assert "actual section body" in item_7_sections[0]
    assert "35" not in item_7_sections[0]
