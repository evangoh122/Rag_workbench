import sys
from unittest.mock import MagicMock

# Mock edgar module before importing sec_client
mock_edgar = MagicMock()
sys.modules["edgar"] = mock_edgar

import pandas as pd
from unittest.mock import patch
from api.services.xbrl_client import fetch_company_facts, get_fact
from api.services.sec_client import get_latest_10k_facts, chunk_filing_sections

# ── XBRL Client Tests ────────────────────────────────────────────────────────

@patch("api.services.xbrl_client.requests.get")
def test_fetch_company_facts(mock_get):
    # Mock response
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"cik": "12345", "facts": {"us-gaap": {}}}
    mock_get.return_value = mock_resp
    
    # Clear cache for testing
    fetch_company_facts.cache_clear()
    
    facts = fetch_company_facts("12345")
    assert facts["cik"] == "12345"
    mock_get.assert_called_once()

@patch("api.services.xbrl_client.fetch_company_facts")
def test_get_fact(mock_fetch):
    mock_fetch.return_value = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "label": "Revenue",
                    "units": {
                        "USD": [
                            {"end": "2023-12-31", "val": 1000000, "form": "10-K", "accn": "001-123"}
                        ]
                    }
                }
            }
        }
    }
    
    fact = get_fact("12345", "Revenues", "2023-12-31")
    assert fact is not None
    assert fact.value == 1000000.0
    assert fact.unit == "USD"
    assert fact.concept == "us-gaap/Revenues"

# ── SEC Client Tests ─────────────────────────────────────────────────────────

@patch("api.db.database.db_manager.get_connection")
def test_get_latest_10k_facts_preserves_period_metadata(mock_get_connection):
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = [
        ("Revenues", 1000, "USD", None, "10-K", 2025, "FY", "2026-02-01")
    ]
    mock_get_connection.return_value = conn
    get_latest_10k_facts.cache_clear()

    df = get_latest_10k_facts("NVDA")

    assert df["fiscal_year"][0] == 2025
    assert df["fiscal_period"][0] == "FY"
    assert df["filed"][0] == "2026-02-01"

@patch("api.db.database.db_manager.get_connection")
def test_get_latest_10k_facts(mock_get_connection):
    # Mock DuckDB connection
    mock_conn = MagicMock()
    mock_get_connection.return_value = mock_conn
    mock_conn.execute.return_value.fetchall.return_value = [
        ("Revenue", 1000.0, "USD", "2023-12-31", "10-K", 2023, "FY", "2024-02-01")
    ]
    get_latest_10k_facts.cache_clear()

    df_pl = get_latest_10k_facts("NVDA")

    # Check that it returns something that looks like a DataFrame
    assert hasattr(df_pl, "shape")
    assert df_pl.shape[0] == 1
    assert df_pl["concept"][0] == "Revenue"

@patch("api.services.sec_client.Company")
@patch("api.services.sec_client.ensure_edgar_identity")
def test_chunk_filing_sections(mock_ensure, mock_company_cls):
    mock_company = MagicMock()
    mock_filing = MagicMock()

    mock_company_cls.return_value = mock_company
    mock_company.get_filings.return_value.latest.return_value = mock_filing

    mock_filing.sections.return_value = ["Item 1", "Item 1A"]
    mock_filing.get_section.side_effect = ["This is business section.", "This is risk factors."]
    mock_filing.accession_number = "000-111"

    chunk_filing_sections.cache_clear()
    chunks = chunk_filing_sections("NVDA")

    assert len(chunks) == 2
    assert chunks[0]["metadata"]["section_name"] == "Item 1"
    assert chunks[1]["metadata"]["section_name"] == "Item 1A"
    assert "business" in chunks[0]["chunk_text"]
