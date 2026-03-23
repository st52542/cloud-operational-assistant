import json
import os
import sys
import pytest

os.environ["DB_PATH"] = "/tmp/test_operational_assistant.db"

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import app
from app.storage.database import init_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    yield


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


def test_version():
    response = client.get("/version")
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "1.0.0"
    assert data["service"] == "cloud-operational-assistant"


def test_create_request_check_service_status():
    payload = {
        "request_type": "check_service_status",
        "target_service": "payment-service",
        "environment": "staging",
        "parameters": {},
    }
    response = client.post("/request", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert data["request_type"] == "check_service_status"
    assert data["status"] in ("completed", "failed")
    assert "request_id" in data


def test_create_request_get_logs():
    payload = {
        "request_type": "get_logs",
        "target_service": "auth-service",
        "environment": "production",
        "parameters": {"limit": 5},
    }
    response = client.post("/request", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "completed"
    assert data["result"] is not None


def test_get_request_by_id():
    payload = {
        "request_type": "get_deployment_info",
        "target_service": "api-gateway",
        "environment": "development",
        "parameters": {},
    }
    create_resp = client.post("/request", json=payload)
    assert create_resp.status_code == 202
    request_id = create_resp.json()["request_id"]

    get_resp = client.get(f"/requests/{request_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["request_id"] == request_id


def test_get_request_not_found():
    response = client.get("/requests/nonexistent-id-12345")
    assert response.status_code == 404


def test_metrics_endpoint():
    response = client.get("/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "total_requests" in data
    assert "uptime_seconds" in data


def test_invalid_target_service():
    payload = {
        "request_type": "check_service_status",
        "target_service": "service with spaces!",
        "environment": "staging",
    }
    response = client.post("/request", json=payload)
    assert response.status_code == 422


def test_simulate_restart():
    payload = {
        "request_type": "simulate_restart",
        "target_service": "worker-service",
        "environment": "staging",
        "parameters": {},
    }
    response = client.post("/request", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "completed"


def test_summarize_incident():
    payload = {
        "request_type": "summarize_incident",
        "target_service": "notification-service",
        "environment": "production",
        "parameters": {},
    }
    response = client.post("/request", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "completed"
    result = data["result"]
    assert "data" in result
