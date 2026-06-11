import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from api.main import app
from api.middleware.auth import get_write_api_key

client = TestClient(app)

@pytest.fixture
def mock_auth_write():
    app.dependency_overrides[get_write_api_key] = lambda: "test-write-key"
    yield
    app.dependency_overrides = {}

@pytest.fixture
def mock_db_review():
    mock_conn = MagicMock()
    with patch('api.db.database.db_manager.get_review_connection', return_value=mock_conn):
        yield mock_conn

@pytest.mark.usefixtures("mock_auth_write")
def test_list_review_queue(mock_db_review):
    with patch('api.routes.review.list_decisions') as mock_list:
        mock_list.return_value = [
            {"id": "1", "cik": "123", "accession": "acc1", "form_type": "10-K", "route": "ESCALATE", "status": "pending", "confidence": 0.5, "created_at": datetime(2026, 6, 11, 12, 0, 0), "triggers_fired": []}
        ]
        
        response = client.get("/api/review/queue")
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["id"] == "1"

@pytest.mark.usefixtures("mock_auth_write")
def test_add_review_decision(mock_db_review):
    with patch('api.routes.review.insert_decision') as mock_insert:
        mock_insert.return_value = "new-id"
        
        payload = {
            "cik": "123",
            "accession": "acc1",
            "form_type": "10-K",
            "route": "ESCALATE",
            "confidence": 0.4,
            "triggers_fired": ["low_confidence"]
        }
        response = client.post("/api/review/queue", json=payload)
        assert response.status_code == 201
        assert response.json()["id"] == "new-id"

@pytest.mark.usefixtures("mock_auth_write")
def test_record_reviewer_verdict_success(mock_db_review):
    with patch('api.routes.review.get_decision') as mock_get, \
         patch('api.routes.review.insert_verdict') as mock_insert:
        
        mock_get.return_value = {"id": "1", "status": "pending"}
        
        response = client.post("/api/review/decisions/1/verdict", json={"reviewer_agrees": True, "notes": "Looks ok"})
        assert response.status_code == 204
        mock_insert.assert_called_once()

@pytest.mark.usefixtures("mock_auth_write")
def test_record_reviewer_verdict_not_found(mock_db_review):
    with patch('api.routes.review.get_decision', return_value=None):
        response = client.post("/api/review/decisions/999/verdict", json={"reviewer_agrees": True})
        assert response.status_code == 404

@pytest.mark.usefixtures("mock_auth_write")
def test_get_pipeline_metrics(mock_db_review):
    with patch('api.routes.review.compute_agreement_rate', return_value=0.85):
        # Mock cursor for routes distribution
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [("auto", 80), ("escalate", 20)]
        mock_db_review.execute.return_value = mock_cursor
        
        response = client.get("/api/review/metrics")
        assert response.status_code == 200
        data = response.json()
        assert data["agreement_rate"] == 0.85
        assert data["routing_distribution"]["auto"] == 80
        assert data["escalation_rate"] == 0.2

@pytest.mark.usefixtures("mock_auth_write")
def test_get_drift_status(mock_db_review):
    with patch('api.routes.review.check_drift') as mock_check:
        mock_check.return_value = MagicMock(
            agreement_rate=0.7,
            agreement_floor=0.8,
            agreement_alert=True,
            unrecognized_concept_count=5,
            concept_spike_threshold=10,
            concept_alert=False,
            window_size=100,
            last_updated=datetime(2026, 6, 11, 12, 0, 0)
        )
        
        response = client.get("/api/review/drift")
        assert response.status_code == 200
        assert response.json()["agreement_alert"] is True

@pytest.mark.usefixtures("mock_auth_write")
def test_run_calibration(mock_db_review):
    with patch('api.routes.review.get_calibration_data', return_value={}), \
         patch('api.routes.review.recalibrate_thresholds') as mock_recal, \
         patch('api.routes.review.persist_calibration_result'):
        
        mock_recal.return_value = {
            "message": "Success",
            "verdicts_used": 50,
            "high_threshold": 0.9,
            "medium_threshold": 0.7,
            "projected_agreement_rate": 0.88
        }
        
        response = client.post("/api/review/calibrate")
        assert response.status_code == 200
        assert response.json()["high_threshold"] == 0.9
