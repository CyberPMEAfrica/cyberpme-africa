import os
from uuid import uuid4

os.environ["DATABASE_URL"] = "sqlite:///./cyberpme_test.db"
os.environ["AGENT_ENROLLMENT_KEY"] = "ci-enrollment-secret"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_server_metrics_and_alert_lifecycle(client: TestClient):
    hostname = f"ci-server-{uuid4().hex[:8]}"
    registration_response = client.post(
        "/api/v1/agents/register",
        json={"name": "Serveur CI", "hostname": hostname, "ip_address": "127.0.0.1"},
        headers={"X-Enrollment-Key": "ci-enrollment-secret"},
    )
    assert registration_response.status_code == 200
    registration = registration_response.json()
    server_id = registration["server_id"]
    auth_headers = {"Authorization": f"Bearer {registration['agent_token']}"}

    unauthorized_response = client.post(
        f"/api/v1/servers/{server_id}/metrics",
        json={"cpu_percent": 95, "memory_percent": 80, "disk_percent": 40},
    )
    assert unauthorized_response.status_code == 401

    critical_response = client.post(
        f"/api/v1/servers/{server_id}/metrics",
        json={"cpu_percent": 95, "memory_percent": 80, "disk_percent": 40},
        headers=auth_headers,
    )
    assert critical_response.status_code == 201

    active_alerts = client.get("/api/v1/alerts").json()
    assert {(alert["resource"], alert["severity"]) for alert in active_alerts} == {
        ("cpu", "critical"),
        ("memory", "warning"),
    }

    recovery_response = client.post(
        f"/api/v1/servers/{server_id}/metrics",
        json={"cpu_percent": 30, "memory_percent": 45, "disk_percent": 40},
        headers=auth_headers,
    )
    assert recovery_response.status_code == 201
    assert client.get("/api/v1/alerts").json() == []

    history = client.get("/api/v1/alerts?active_only=false").json()
    assert len(history) == 2
    assert all(alert["status"] == "resolved" for alert in history)
