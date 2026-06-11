import sys
from unittest.mock import MagicMock

# Mock edgar module before importing sec_client
mock_edgar = MagicMock()
sys.modules["edgar"] = mock_edgar

import pytest
import polars as pl
import pandas as pd
from unittest.mock import patch
from api.services.xbrl_client import fetch_company_facts, get_fact, XBRLFact
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

@patch("api.services.sec_client.Company")
@patch("api.services.sec_client.ensure_edgar_identity")
def test_get_latest_10k_facts(mock_ensure, mock_company_cls):
    # Mock company and filing
    mock_company = MagicMock()
    mock_filing = MagicMock()
    mock_financials = MagicMock()
    
    mock_company_cls.return_value = mock_company
    mock_company.get_filing.return_value = mock_filing
    mock_filing.financials = mock_financials
    
    # Mock statements
    df_pd = pd.DataFrame({"Concept": ["Revenue"], "Value": [1000], "Unit": ["USD"], "Period": ["2023"]})
    mock_statement = MagicMock()
    mock_statement.to_pandas.return_value = df_pd
    
    mock_financials.balance_sheet = mock_statement
    mock_financials.income_statement = None
    mock_financials.cash_flow_statement = None
    
    df_pl = get_latest_10k_facts("NVDA")
    
    # Check that it returns something that looks like a DataFrame
    assert hasattr(df_pl, "shape")
    assert df_pl.shape[0] == 1
    assert df_pl["Concept"][0] == "Revenue"

@patch("api.services.sec_client.Company")
@patch("api.services.sec_client.ensure_edgar_identity")
def test_chunk_filing_sections(mock_ensure, mock_company_cls):
    mock_company = MagicMock()
    mock_filing = MagicMock()
    
    mock_company_cls.return_value = mock_company
    mock_company.get_filing.return_value = mock_filing
    
    mock_filing.sections = ["Item 1", "Item 1A"]
    mock_filing.get_section.side_effect = ["This is business section.", "This is risk factors."]
    mock_filing.accession_number = "000-111"
    
    chunks = chunk_filing_sections("NVDA")
    
    assert len(chunks) == 2
    assert chunks[0]["metadata"]["section_name"] == "Item 1"
    assert chunks[1]["metadata"]["section_name"] == "Item 1A"
    assert "business" in chunks[0]["chunk_text"]
