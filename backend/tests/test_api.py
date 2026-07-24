import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

os.environ["DATABASE_URL"] = "sqlite:///./cyberpme_test.db"
os.environ["AGENT_ENROLLMENT_KEY"] = "ci-enrollment-secret"
os.environ["NETWORK_SCAN_KEY"] = "ci-network-scan-secret"

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


def test_network_scan_requires_key_and_private_limited_target(client: TestClient, monkeypatch):
    unauthorized = client.post("/api/v1/network-scans", json={"target": "192.168.1.0/24"})
    assert unauthorized.status_code == 401

    headers = {"X-Scan-Key": "ci-network-scan-secret"}
    public_target = client.post("/api/v1/network-scans", json={"target": "8.8.8.0/24"}, headers=headers)
    assert public_target.status_code == 422

    large_target = client.post("/api/v1/network-scans", json={"target": "10.0.0.0/16"}, headers=headers)
    assert large_target.status_code == 422

    monkeypatch.setattr("app.main.run_network_scan", lambda _: None)
    accepted = client.post("/api/v1/network-scans", json={"target": "192.168.1.0/24"}, headers=headers)
    assert accepted.status_code == 202
    assert accepted.json()["target"] == "192.168.1.0/24"
    assert accepted.json()["status"] == "pending"

    history = client.get("/api/v1/network-scans")
    assert history.status_code == 200
    assert len(history.json()) == 1


def test_ssl_check_requires_key_and_records_result(client: TestClient, monkeypatch):
    unauthorized = client.post("/api/v1/ssl-checks", json={"hostname": "example.com", "port": 443})
    assert unauthorized.status_code == 401
    headers = {"X-Scan-Key": "ci-network-scan-secret"}
    monkeypatch.setattr("app.main.validate_public_hostname", lambda hostname, port: ("example.com", ["93.184.216.34"]))
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(
        "app.main.inspect_certificate",
        lambda hostname, port: {
            "status": "valid", "subject": "example.com", "issuer": "Example CA",
            "valid_from": now - timedelta(days=30), "expires_at": now + timedelta(days=60),
            "days_remaining": 59, "chain_valid": True, "tls_version": "TLSv1.3",
            "cipher": "TLS_AES_256_GCM_SHA384", "error": None,
        },
    )
    response = client.post("/api/v1/ssl-checks", json={"hostname": "example.com", "port": 443}, headers=headers)
    assert response.status_code == 201
    assert response.json()["status"] == "valid"
    assert response.json()["days_remaining"] == 59
    assert len(client.get("/api/v1/ssl-checks").json()) == 1


def test_backup_checks_require_agent_and_evaluate_freshness(client: TestClient):
    registration = client.post(
        "/api/v1/agents/register",
        json={"name": "Serveur sauvegarde", "hostname": f"backup-{uuid4().hex}", "ip_address": "127.0.0.1"},
        headers={"X-Enrollment-Key": "ci-enrollment-secret"},
    ).json()
    endpoint = f"/api/v1/servers/{registration['server_id']}/backup-checks"
    payload = {
        "name": "Documents", "kind": "files", "source": "/backups/documents",
        "exists": True, "size_bytes": 4096,
        "last_success_at": datetime.now(timezone.utc).isoformat(), "max_age_hours": 24,
    }
    assert client.post(endpoint, json=payload).status_code == 401
    created = client.post(endpoint, json=payload, headers={"Authorization": f"Bearer {registration['agent_token']}"})
    assert created.status_code == 201
    assert created.json()["status"] == "healthy"
    assert created.json()["server_name"] == "Serveur sauvegarde"

    stale = payload | {"name": "PostgreSQL", "kind": "postgresql", "last_success_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()}
    response = client.post(endpoint, json=stale, headers={"Authorization": f"Bearer {registration['agent_token']}"})
    assert response.json()["status"] == "critical"
    assert len(client.get("/api/v1/backup-checks").json()) == 2
