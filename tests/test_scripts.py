import sys
from unittest.mock import MagicMock

# Mock missing modules
for mod in ["sec_edgar_downloader", "langchain_text_splitters", "bs4", "edgar"]:
    sys.modules[mod] = MagicMock()

# Fix broken import in scripts/embed_edgar.py
import scripts.embed_tickers
scripts.embed_tickers.get_embeddings = MagicMock()

from unittest.mock import patch, mock_open

# Now we can import the scripts
from scripts.embed_edgar import _reset_incompatible_embeddings, run_embed_edgar_etl
from scripts.embed_tickers import (
    _load_ticker_rows,
    _reset_incompatible_embeddings as _reset_incompatible_ticker_embeddings,
)
from scripts.init_graph_triples import init_graph_triples
from scripts.run_shadow import load_extractions, main as shadow_main

# ── Embed Edgar Script Tests ─────────────────────────────────────────────────

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
