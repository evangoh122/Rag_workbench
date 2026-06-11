import sys
from unittest.mock import MagicMock

# Mock missing modules
for mod in ["sec_edgar_downloader", "langchain_text_splitters", "bs4", "edgar"]:
    sys.modules[mod] = MagicMock()

# Fix broken import in scripts/embed_edgar.py
import scripts.embed_tickers
scripts.embed_tickers._get_embeddings = MagicMock()

from unittest.mock import patch, mock_open

# Now we can import the scripts
from scripts.embed_edgar import run_embed_edgar_etl
from scripts.init_graph_triples import init_graph_triples
from scripts.run_shadow import load_extractions, main as shadow_main

# ── Embed Edgar Script Tests ─────────────────────────────────────────────────

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
