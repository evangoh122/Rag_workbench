import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from api.main import app
from api.db.database import db_manager

client = TestClient(app)

@pytest.fixture
def mock_db():
    mock_conn = MagicMock()
    # Mocking _count calls
    # edgar_embeddings, companies_with_chunks, xbrl_facts, companies_with_xbrl, graph_triples, ticker_embeddings
    # + 1 for tickers_embedded list
    # + 4 for review connection calls
    mock_conn.execute.return_value.fetchone.side_effect = [
        (100,), (10,), (50,), (5,), (200,), (150,)
    ]
    mock_conn.execute.return_value.fetchall.side_effect = [
        [("AAPL",), ("MSFT",)], # tickers_embedded
        [("auto", 10), ("escalate", 2)] # routing_distribution in metrics or something else?
        # actually stats.py does:
        # total_decisions, total_verdicts, pending, escalated
    ]
    
    with patch.object(db_manager, 'get_connection', return_value=mock_conn), \
         patch.object(db_manager, 'get_review_connection', return_value=mock_conn):
        yield mock_conn

@pytest.fixture
def mock_llm_tracker():
    with patch('api.routes.stats.get_llm_tracker') as mock:
        tracker = MagicMock()
        tracker.snapshot.return_value = {
            "total_calls": 100,
            "failed_calls": 5,
            "success_rate": 0.95,
            "last_error": "Timeout",
            "last_error_time": "2023-10-27T10:00:00",
            "recent_errors": ["Timeout"]
        }
        mock.return_value = tracker
        yield tracker

def test_get_stats_success(mock_db, mock_llm_tracker):
    # We need to bypass auth if it's applied, but stats doesn't have auth in the route definition
    # App-level middleware might apply auth? No, auth is dependency-based in routes.
    # api/routes/stats.py doesn't have Depends(get_read_api_key)
    
    # We need to make sure _count side effects are correct for the calls in stats.py
    # data: 6 counts + 1 stored-dim fetchone + 1 fetchall
    # review: 4 counts
    mock_db.execute.return_value.fetchone.side_effect = [
        (100,), (10,), (50,), (5,), (200,), (150,), # data counts
        (1024,),                                     # embedding_dim_stored
        (20,), (15,), (5,), (2,) # review
    ]
    mock_db.execute.return_value.fetchall.side_effect = [
        [("AAPL",), ("MSFT",)] # tickers_embedded
    ]

    response = client.get("/api/stats")
    assert response.status_code == 200
    res_data = response.json()

    assert res_data["data"]["filing_chunks"] == 100
    assert res_data["data"]["embedding_dim_stored"] == 1024
    assert res_data["data"]["tickers_embedded"] == ["AAPL", "MSFT"]
    assert res_data["review"]["total_decisions"] == 20
    assert res_data["llm"]["total_calls"] == 100
    assert res_data["database"]["main_connected"] is True
    assert res_data["database"]["review_connected"] is True

def test_get_stats_db_error(mock_llm_tracker):
    with patch.object(db_manager, 'get_connection', side_effect=Exception("DB Down")), \
         patch.object(db_manager, 'get_review_connection', side_effect=Exception("Review DB Down")):
        response = client.get("/api/stats")
        assert response.status_code == 200
        res_data = response.json()
        assert "error" in res_data["data"]
        assert "error" in res_data["review"]
        assert res_data["database"]["main_connected"] is False
        assert res_data["database"]["review_connected"] is False
