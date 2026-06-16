import pytest
from unittest.mock import MagicMock, patch
from api.services.llm_health import LLMHealthTracker, get_llm_tracker
from api.services.drift_detection import check_drift, DriftStatus

# ── LLM Health Tracker Tests ─────────────────────────────────────────────────

def test_llm_health_tracker():
    tracker = LLMHealthTracker()
    tracker.reset()
    
    assert tracker.total_calls == 0
    assert tracker.snapshot()["success_rate"] == 1.0
    
    tracker.record_success()
    tracker.record_success()
    tracker.record_failure("Rate limit exceeded", "chat_endpoint")
    
    snapshot = tracker.snapshot()
    assert snapshot["total_calls"] == 3
    assert snapshot["successful_calls"] == 2
    assert snapshot["failed_calls"] == 1
    assert snapshot["success_rate"] == pytest.approx(0.666, 0.01)
    assert snapshot["last_error"] == "Rate limit exceeded"
    assert len(snapshot["recent_errors"]) == 1
    
    tracker.reset()
    assert tracker.total_calls == 0
    assert tracker.last_error is None

def test_get_llm_tracker():
    t1 = get_llm_tracker()
    t2 = get_llm_tracker()
    assert t1 is t2

# ── Drift Detection Tests ────────────────────────────────────────────────────

@patch("api.services.drift_detection.compute_agreement_rate")
@patch("api.services.drift_detection.count_unrecognized_concepts")
def test_check_drift_no_alert(mock_concepts, mock_agreement):
    # Setup mocks
    mock_agreement.return_value = 0.95
    mock_concepts.return_value = 5
    
    conn = MagicMock()
    status = check_drift(
        conn, 
        agreement_floor=0.8, 
        concept_spike_threshold=10, 
        window=100
    )
    
    assert isinstance(status, DriftStatus)
    assert status.agreement_rate == 0.95
    assert not status.agreement_alert
    assert not status.concept_alert
    assert status.unrecognized_concept_count == 5

@patch("api.services.drift_detection.compute_agreement_rate")
@patch("api.services.drift_detection.count_unrecognized_concepts")
def test_check_drift_agreement_alert(mock_concepts, mock_agreement):
    mock_agreement.return_value = 0.75
    mock_concepts.return_value = 5
    
    conn = MagicMock()
    status = check_drift(
        conn, 
        agreement_floor=0.8, 
        concept_spike_threshold=10
    )
    
    assert status.agreement_alert
    assert not status.concept_alert

@patch("api.services.drift_detection.compute_agreement_rate")
@patch("api.services.drift_detection.count_unrecognized_concepts")
def test_check_drift_concept_alert(mock_concepts, mock_agreement):
    mock_agreement.return_value = 0.95
    mock_concepts.return_value = 15
    
    conn = MagicMock()
    status = check_drift(
        conn, 
        agreement_floor=0.8, 
        concept_spike_threshold=10
    )
    
    assert not status.agreement_alert
    assert status.concept_alert

def test_check_drift_missing_module():
    # Test the RuntimeError when modules are missing
    with patch("api.services.drift_detection.compute_agreement_rate", None):
        with pytest.raises(RuntimeError, match="api.db.review_queue is not yet available"):
            check_drift(MagicMock(), 0.8, 10)


# ── Chart Tool Detection Tests ───────────────────────────────────────────────

def test_detect_chart_request():
    from api.services.chart_tool import detect_chart_request

    # 1. Explicit chart queries (has trigger word + metric)
    assert detect_chart_request("show me the revenue trend") == "revenue"
    assert detect_chart_request("graph operating income over time") == "operating_income"
    assert detect_chart_request("compare gross profit for the last years") == "gross_profit"

    # 2. Direct metric queries without explicit trigger words
    assert detect_chart_request("what is the operating margin?") == "operating_margin"
    assert detect_chart_request("tell me about the net income") == "net_income"
    assert detect_chart_request("gross margin") == "gross_margin"

    # 3. Qualitative conceptual queries (should NOT trigger chart)
    assert detect_chart_request("what is their revenue recognition policy?") is None
    assert detect_chart_request("operating income definition") is None
    assert detect_chart_request("explain the gross margin standard guidelines") is None
    assert detect_chart_request("disclosures regarding executive compensation plans") is None

    # 4. Word boundary / false positive checks
    # "revenue recognition" has "recognition" which is a qualitative marker
    assert detect_chart_request("revenue recognition") is None
    # "revenue" is part of "revenues", make sure prefix/suffix matching doesn't match false patterns
    assert detect_chart_request("someotherwordrevenue") is None

    # 5. Empty and none queries
    assert detect_chart_request("") is None
    assert detect_chart_request(None) is None

