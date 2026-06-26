import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from api.main import app
from api.middleware.auth import get_read_api_key

client = TestClient(app)

@pytest.fixture
def mock_auth():
    app.dependency_overrides[get_read_api_key] = lambda: "test-key"
    yield
    app.dependency_overrides = {}

@pytest.fixture
def mock_guards():
    with patch('api.routes.chat.check_input') as m_in, \
         patch('api.routes.chat.check_dialog') as m_dia, \
         patch('api.routes.chat.check_output') as m_out:
        
        m_in.return_value = MagicMock(blocked=False)
        m_dia.return_value = MagicMock(off_topic=False, advice=False)
        m_out.return_value = MagicMock(masked_answer=None)
        yield (m_in, m_dia, m_out)

@pytest.mark.usefixtures("mock_auth", "mock_guards")
def test_chat_sql_success():
    with patch('api.routes.chat.chat_sql') as mock_chat:
        mock_chat.return_value = {"type": "sql", "answer": "The revenue is $100M", "query": "SELECT..."}
        
        response = client.post("/api/chat/sql", json={"message": "What is the revenue?"})
        assert response.status_code == 200
        assert response.json()["answer"] == "The revenue is $100M"

@pytest.mark.usefixtures("mock_auth", "mock_guards")
def test_chat_rag_success():
    with patch('api.routes.chat.ask_rag') as mock_rag:
        mock_rag.return_value = "RAG answer"
        
        response = client.post("/api/chat/rag", json={"message": "tell me something"})
        assert response.status_code == 200
        assert response.json()["answer"] == "RAG answer"

@pytest.mark.usefixtures("mock_auth", "mock_guards")
def test_chat_graph_rag_success():
    with patch('api.routes.chat.run_graph_rag') as mock_graph:
        mock_graph.return_value = {
            "final_answer": "Graph answer",
            "search_entities": ["AAPL"],
            "extracted_triples": []
        }
        
        response = client.post("/api/chat/graph-rag", json={"message": "explain AAPL", "ticker": "AAPL"})
        assert response.status_code == 200
        assert response.json()["answer"] == "Graph answer"
        assert response.json()["entities"] == ["AAPL"]

@pytest.mark.usefixtures("mock_auth", "mock_guards")
def test_chat_graph_rag_missing_ticker():
    with patch('api.routes.chat.run_graph_rag') as mock_graph:
        response = client.post("/api/chat/graph-rag", json={"message": "explain AAPL", "ticker": ""})
        assert response.status_code == 400
        assert "Ticker is required" in response.json()["detail"]

@pytest.mark.usefixtures("mock_auth", "mock_guards")
def test_chat_auditable_rag_success():
    with patch('api.routes.chat.run_auditable_rag') as mock_audit:
        mock_audit.return_value = {
            "final_answer": "Audit answer",
            "retrieved_docs": [{"chunk_text": "doc1", "metadata": {}}],
            "xbrl_facts": [],
            "verification_status": "verified",
            "verification_reasoning": "all good",
            "math_steps": [],
            "status": {
                "input": "success",
                "retrieval": "success",
                "classifier": "success",
                "extraction": "success",
                "eval": "success",
                "math": "success",
                "verification": "success",
                "output": "success",
            },
        }
        
        response = client.post(
            "/api/chat/auditable-rag",
            json={"message": "Check TSLA revenue", "ticker": "TSLA"},
        )
        assert response.status_code == 200
        assert response.json()["answer"] == "Audit answer"
        assert response.json()["verification"]["status"] == "verified"

def test_input_rail_blocking():
    app.dependency_overrides[get_read_api_key] = lambda: "test-key"
    with patch('api.routes.chat.check_input') as m_in:
        m_in.return_value = MagicMock(blocked=True, reason="Inappropriate content")
        
        response = client.post("/api/chat/rag", json={"message": "bad word"})
        assert response.status_code == 400
        assert response.json()["detail"] == "Inappropriate content"
    app.dependency_overrides = {}

def test_output_rail_masking():
    app.dependency_overrides[get_read_api_key] = lambda: "test-key"
    with patch('api.routes.chat.check_input') as m_in, \
         patch('api.routes.chat.check_dialog') as m_dia, \
         patch('api.routes.chat.check_output') as m_out, \
         patch('api.routes.chat.ask_rag') as mock_rag:
        
        m_in.return_value = MagicMock(blocked=False)
        m_dia.return_value = MagicMock(off_topic=False, advice=False)
        m_out.return_value = MagicMock(masked_answer="REDACTED ANSWER")
        mock_rag.return_value = "Sensitive answer with PII"
        
        response = client.post("/api/chat/rag", json={"message": "who is this?"})
        assert response.status_code == 200
        assert response.json()["answer"] == "REDACTED ANSWER"
    app.dependency_overrides = {}
