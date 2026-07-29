import hashlib
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

os.environ["DATABASE_URL"] = "sqlite:///./cyberpme_test.db"
os.environ["AGENT_ENROLLMENT_KEY"] = "ci-enrollment-secret"
os.environ["NETWORK_SCAN_KEY"] = "ci-network-scan-secret"
os.environ["BOOTSTRAP_ORGANIZATION_NAME"] = "PME Test"
os.environ["BOOTSTRAP_ORGANIZATION_SLUG"] = "pme-test"
os.environ["BOOTSTRAP_ADMIN_EMAIL"] = "owner@example.test"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "Test-password-very-strong-2026"

import pytest
from fastapi.testclient import TestClient

from app.auth import hash_password
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Organization, User, UserInvitation


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def user_headers(client: TestClient):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "pme-test",
            "email": "owner@example.test",
            "password": "Test-password-very-strong-2026",
        },
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_health(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_owner_login_session_and_logout(client: TestClient):
    credentials = {
        "organization_slug": "pme-test",
        "email": "owner@example.test",
        "password": "Test-password-very-strong-2026",
    }
    invalid = client.post("/api/v1/auth/login", json=credentials | {"password": "wrong-password-2026"})
    assert invalid.status_code == 401
    login_response = client.post("/api/v1/auth/login", json=credentials)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    profile = client.get("/api/v1/auth/me", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["organization_name"] == "PME Test"
    assert profile.json()["role"] == "owner"
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_owner_manages_organization_team(client: TestClient, user_headers: dict[str, str]):
    organization = client.get("/api/v1/organization", headers=user_headers)
    assert organization.status_code == 200
    assert organization.json()["slug"] == "pme-test"

    renamed = client.patch(
        "/api/v1/organization",
        json={"name": "PME Test BÃ©nin"},
        headers=user_headers,
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "PME Test BÃ©nin"

    created = client.post(
        "/api/v1/users",
        json={
            "email": "analyst@example.test",
            "password": "Analyst-password-strong-2026",
            "role": "analyst",
        },
        headers=user_headers,
    )
    assert created.status_code == 201
    analyst = created.json()
    assert analyst["email"] == "analyst@example.test"
    assert analyst["is_active"] is True
    assert len(client.get("/api/v1/users", headers=user_headers).json()) == 2

    login = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "pme-test",
            "email": "analyst@example.test",
            "password": "Analyst-password-strong-2026",
        },
    )
    assert login.status_code == 200

    disabled = client.patch(
        f"/api/v1/users/{analyst['id']}",
        json={"is_active": False, "role": "viewer"},
        headers=user_headers,
    )
    assert disabled.status_code == 200
    assert disabled.json()["role"] == "viewer"
    assert disabled.json()["is_active"] is False
    analyst_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=analyst_headers).status_code == 401


def test_team_permissions_and_tenant_isolation(client: TestClient, user_headers: dict[str, str]):
    admin = client.post(
        "/api/v1/users",
        json={
            "email": "admin@example.test",
            "password": "Admin-password-strong-2026",
            "role": "admin",
        },
        headers=user_headers,
    ).json()
    admin_login = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "pme-test",
            "email": "admin@example.test",
            "password": "Admin-password-strong-2026",
        },
    ).json()
    admin_headers = {"Authorization": f"Bearer {admin_login['access_token']}"}

    forbidden = client.post(
        "/api/v1/users",
        json={
            "email": "second-admin@example.test",
            "password": "Second-admin-password-2026",
            "role": "admin",
        },
        headers=admin_headers,
    )
    assert forbidden.status_code == 403
    assert client.patch(
        f"/api/v1/users/{admin['id']}",
        json={"is_active": False},
        headers=admin_headers,
    ).status_code == 400

    with SessionLocal() as db:
        other = Organization(name="Autre PME", slug="autre-equipe")
        db.add(other)
        db.flush()
        outsider = User(
            organization_id=other.id,
            email="viewer@autre.test",
            password_hash=hash_password("Outsider-password-strong-2026"),
            role="viewer",
        )
        db.add(outsider)
        db.commit()
        outsider_id = outsider.id
    assert client.patch(
        f"/api/v1/users/{outsider_id}",
        json={"is_active": False},
        headers=user_headers,
    ).status_code == 404


def test_audit_log_is_append_only_authorized_and_tenant_scoped(
    client: TestClient,
    user_headers: dict[str, str],
):
    created = client.post(
        "/api/v1/users",
        json={
            "email": "audit-viewer@example.test",
            "password": "Audit-viewer-password-2026",
            "role": "viewer",
        },
        headers=user_headers,
    )
    assert created.status_code == 201
    client.patch(
        f"/api/v1/users/{created.json()['id']}",
        json={"is_active": False},
        headers=user_headers,
    )

    audit_response = client.get("/api/v1/audit-entries", headers=user_headers)
    assert audit_response.status_code == 200
    entries = audit_response.json()
    actions = {entry["action"] for entry in entries}
    assert {"auth.login", "user.created", "user.updated"}.issubset(actions)
    assert all(entry["actor_email"] == "owner@example.test" for entry in entries)
    serialized = audit_response.text.lower()
    assert "audit-viewer-password-2026" not in serialized
    assert "access_token" not in serialized
    assert client.patch("/api/v1/audit-entries", json={}, headers=user_headers).status_code == 405
    assert client.delete("/api/v1/audit-entries", headers=user_headers).status_code == 405

    with SessionLocal() as db:
        organization = db.query(Organization).filter_by(slug="pme-test").one()
        viewer = db.query(User).filter_by(
            organization_id=organization.id,
            email="audit-viewer@example.test",
        ).one()
        viewer.is_active = True
        other = Organization(name="PME Audit Isolée", slug="audit-isolee")
        db.add(other)
        db.flush()
        db.add(
            User(
                organization_id=other.id,
                email="owner@audit-isolee.test",
                password_hash=hash_password("Isolated-audit-password-2026"),
                role="owner",
            )
        )
        db.commit()

    viewer_login = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "pme-test",
            "email": "audit-viewer@example.test",
            "password": "Audit-viewer-password-2026",
        },
    ).json()
    viewer_headers = {"Authorization": f"Bearer {viewer_login['access_token']}"}
    assert client.get("/api/v1/audit-entries", headers=viewer_headers).status_code == 403

    isolated_login = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "audit-isolee",
            "email": "owner@audit-isolee.test",
            "password": "Isolated-audit-password-2026",
        },
    ).json()
    isolated_headers = {"Authorization": f"Bearer {isolated_login['access_token']}"}
    isolated_entries = client.get("/api/v1/audit-entries", headers=isolated_headers).json()
    assert len(isolated_entries) == 1
    assert isolated_entries[0]["actor_email"] == "owner@audit-isolee.test"


def test_user_changes_password_and_sessions_are_revoked(client: TestClient, user_headers: dict[str, str]):
    changed = client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "Test-password-very-strong-2026",
            "new_password": "New-owner-password-strong-2026",
        },
        headers=user_headers,
    )
    assert changed.status_code == 204
    assert client.get("/api/v1/auth/me", headers=user_headers).status_code == 401
    old_login = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "pme-test",
            "email": "owner@example.test",
            "password": "Test-password-very-strong-2026",
        },
    )
    assert old_login.status_code == 401
    new_login = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "pme-test",
            "email": "owner@example.test",
            "password": "New-owner-password-strong-2026",
        },
    )
    assert new_login.status_code == 200


def test_secure_invitation_creates_account_only_after_acceptance(
    client: TestClient,
    user_headers: dict[str, str],
    monkeypatch,
):
    sent = {}

    def fake_send_invitation_email(**kwargs):
        sent.update(kwargs)
        return True

    monkeypatch.setattr("app.main.send_invitation_email", fake_send_invitation_email)
    created = client.post(
        "/api/v1/invitations",
        json={"email": "invitee@example.test", "role": "analyst"},
        headers=user_headers,
    )
    assert created.status_code == 201
    assert created.json()["email_sent"] is True
    assert created.json()["status"] == "pending"
    assert sent["recipient"] == "invitee@example.test"
    raw_token = parse_qs(urlparse(sent["invitation_url"]).fragment.split("?", 1)[1])["token"][0]

    assert len(client.get("/api/v1/users", headers=user_headers).json()) == 1
    listed = client.get("/api/v1/invitations", headers=user_headers)
    assert listed.status_code == 200
    assert raw_token not in listed.text

    preview = client.get("/api/v1/invitations/preview", params={"token": raw_token})
    assert preview.status_code == 200
    assert preview.json()["organization_slug"] == "pme-test"
    assert preview.json()["role"] == "analyst"

    accepted = client.post(
        "/api/v1/invitations/accept",
        json={"token": raw_token, "password": "Invitee-password-strong-2026"},
    )
    assert accepted.status_code == 200
    invitee_headers = {"Authorization": f"Bearer {accepted.json()['access_token']}"}
    profile = client.get("/api/v1/auth/me", headers=invitee_headers)
    assert profile.status_code == 200
    assert profile.json()["email"] == "invitee@example.test"
    assert profile.json()["role"] == "analyst"
    assert client.post(
        "/api/v1/invitations/accept",
        json={"token": raw_token, "password": "Another-password-strong-2026"},
    ).status_code == 410


def test_reinvitation_revokes_previous_link_and_expired_link_is_rejected(
    client: TestClient,
    user_headers: dict[str, str],
    monkeypatch,
):
    links = []

    def capture_invitation(**kwargs):
        links.append(kwargs["invitation_url"])
        return True

    monkeypatch.setattr("app.main.send_invitation_email", capture_invitation)
    payload = {"email": "pending@example.test", "role": "viewer"}
    assert client.post("/api/v1/invitations", json=payload, headers=user_headers).status_code == 201
    assert client.post("/api/v1/invitations", json=payload, headers=user_headers).status_code == 201
    first_token = parse_qs(urlparse(links[0]).fragment.split("?", 1)[1])["token"][0]
    second_token = parse_qs(urlparse(links[1]).fragment.split("?", 1)[1])["token"][0]
    assert client.get("/api/v1/invitations/preview", params={"token": first_token}).status_code == 410

    with SessionLocal() as db:
        invitation = db.query(UserInvitation).filter_by(
            token_hash=hashlib.sha256(second_token.encode()).hexdigest()
        ).one()
        invitation.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    expired = client.get("/api/v1/invitations/preview", params={"token": second_token})
    assert expired.status_code == 410
    assert "expir" in expired.json()["detail"].lower()


def test_disabled_existing_account_can_be_reinvited(
    client: TestClient,
    user_headers: dict[str, str],
    monkeypatch,
):
    created_user = client.post(
        "/api/v1/users",
        json={
            "email": "legacy-user@example.test",
            "password": "Legacy-password-strong-2026",
            "role": "viewer",
        },
        headers=user_headers,
    ).json()
    active_invitation = client.post(
        "/api/v1/invitations",
        json={"email": "legacy-user@example.test", "role": "analyst"},
        headers=user_headers,
    )
    assert active_invitation.status_code == 409

    client.patch(
        f"/api/v1/users/{created_user['id']}",
        json={"is_active": False},
        headers=user_headers,
    )
    sent = {}
    monkeypatch.setattr(
        "app.main.send_invitation_email",
        lambda **kwargs: sent.update(kwargs) is None,
    )
    reinvited = client.post(
        "/api/v1/invitations",
        json={"email": "legacy-user@example.test", "role": "analyst"},
        headers=user_headers,
    )
    assert reinvited.status_code == 201
    token = parse_qs(urlparse(sent["invitation_url"]).fragment.split("?", 1)[1])["token"][0]
    accepted = client.post(
        "/api/v1/invitations/accept",
        json={"token": token, "password": "Replacement-password-2026"},
    )
    assert accepted.status_code == 200
    profile = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {accepted.json()['access_token']}"},
    )
    assert profile.json()["role"] == "analyst"
    assert profile.json()["email"] == "legacy-user@example.test"


def test_organizations_cannot_read_each_others_servers(client: TestClient, user_headers: dict[str, str]):
    with SessionLocal() as db:
        other = Organization(name="Autre PME", slug="autre-pme")
        db.add(other)
        db.flush()
        db.add(
            User(
                organization_id=other.id,
                email="owner@autre.test",
                password_hash=hash_password("Another-strong-password-2026"),
                role="owner",
            )
        )
        db.commit()
    login = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "autre-pme",
            "email": "owner@autre.test",
            "password": "Another-strong-password-2026",
        },
    ).json()
    other_headers = {"Authorization": f"Bearer {login['access_token']}"}
    created = client.post(
        "/api/v1/servers",
        json={"name": "Serveur privé", "hostname": "private-host", "ip_address": "10.10.0.2"},
        headers=other_headers,
    )
    assert created.status_code == 201
    assert len(client.get("/api/v1/servers", headers=other_headers).json()) == 1
    assert client.get("/api/v1/servers", headers=user_headers).json() == []


def test_server_metrics_and_alert_lifecycle(client: TestClient, user_headers: dict[str, str]):
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

    assert client.get("/api/v1/alerts").status_code == 401
    active_alerts = client.get("/api/v1/alerts", headers=user_headers).json()
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
    assert client.get("/api/v1/alerts", headers=user_headers).json() == []

    history = client.get("/api/v1/alerts?active_only=false", headers=user_headers).json()
    assert len(history) == 2
    assert all(alert["status"] == "resolved" for alert in history)


def test_network_scan_requires_key_and_private_limited_target(client: TestClient, monkeypatch, user_headers: dict[str, str]):
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

    history = client.get("/api/v1/network-scans", headers=user_headers)
    assert history.status_code == 200
    assert len(history.json()) == 1


def test_ssl_check_requires_key_and_records_result(client: TestClient, monkeypatch, user_headers: dict[str, str]):
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
    assert len(client.get("/api/v1/ssl-checks", headers=user_headers).json()) == 1


def test_backup_checks_require_agent_and_evaluate_freshness(client: TestClient, user_headers: dict[str, str]):
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
    assert len(client.get("/api/v1/backup-checks", headers=user_headers).json()) == 2


def test_security_event_ingestion_is_authenticated_and_idempotent(client: TestClient, user_headers: dict[str, str]):
    registration = client.post(
        "/api/v1/agents/register",
        json={"name": "Capteur IDS", "hostname": f"ids-{uuid4().hex}", "ip_address": "10.0.2.15"},
        headers={"X-Enrollment-Key": "ci-enrollment-secret"},
    ).json()
    endpoint = f"/api/v1/servers/{registration['server_id']}/security-events"
    payload = {
        "event_key": "wazuh-100001", "source": "wazuh", "category": "authentication",
        "severity": "high", "title": "Échecs de connexion répétés",
        "description": "Plusieurs tentatives SSH ont échoué.", "source_ip": "192.168.1.50",
        "destination_ip": "10.0.2.15", "rule_id": "5710",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }
    assert client.post(endpoint, json=payload).status_code == 401
    headers = {"Authorization": f"Bearer {registration['agent_token']}"}
    created = client.post(endpoint, json=payload, headers=headers)
    duplicate = client.post(endpoint, json=payload, headers=headers)
    assert created.status_code == 201
    assert created.json()["id"] == duplicate.json()["id"]
    assert created.json()["server_name"] == "Capteur IDS"
    assert "multifacteur" in created.json()["recommendation"]
    assert created.json()["status"] == "new"
    assert len(client.get("/api/v1/security-events", headers=user_headers).json()) == 1

    event_id = created.json()["id"]
    acknowledged = client.patch(
        f"/api/v1/security-events/{event_id}",
        json={"status": "acknowledged"},
        headers=user_headers,
    )
    assert acknowledged.status_code == 200
    assert acknowledged.json()["status"] == "acknowledged"
    assert acknowledged.json()["handled_by_email"] == "owner@example.test"
    assert acknowledged.json()["acknowledged_at"] is not None

    missing_note = client.patch(
        f"/api/v1/security-events/{event_id}",
        json={"status": "resolved"},
        headers=user_headers,
    )
    assert missing_note.status_code == 422
    resolved = client.patch(
        f"/api/v1/security-events/{event_id}",
        json={"status": "resolved", "resolution_note": "Compte vérifié et accès SSH durci."},
        headers=user_headers,
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert resolved.json()["resolved_at"] is not None
    assert resolved.json()["resolution_note"] == "Compte vérifié et accès SSH durci."

    reopened = client.patch(
        f"/api/v1/security-events/{event_id}",
        json={"status": "new", "resolution_note": "Nouvelle activité observée."},
        headers=user_headers,
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "new"
    assert reopened.json()["resolved_at"] is None


def test_viewer_cannot_handle_security_incidents(client: TestClient, user_headers: dict[str, str]):
    registration = client.post(
        "/api/v1/agents/register",
        json={"name": "Capteur lecture", "hostname": f"viewer-ids-{uuid4().hex}"},
        headers={"X-Enrollment-Key": "ci-enrollment-secret"},
    ).json()
    created = client.post(
        f"/api/v1/servers/{registration['server_id']}/security-events",
        json={
            "event_key": "viewer-event", "source": "agent", "category": "network",
            "severity": "medium", "title": "Événement en lecture",
            "description": "Événement réservé aux opérateurs.",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        },
        headers={"Authorization": f"Bearer {registration['agent_token']}"},
    ).json()
    with SessionLocal() as db:
        organization = db.query(Organization).filter_by(slug="pme-test").one()
        db.add(User(
            organization_id=organization.id,
            email="viewer@example.test",
            password_hash=hash_password("Viewer-password-strong-2026"),
            role="viewer",
        ))
        db.commit()
    login = client.post("/api/v1/auth/login", json={
        "organization_slug": "pme-test",
        "email": "viewer@example.test",
        "password": "Viewer-password-strong-2026",
    }).json()
    response = client.patch(
        f"/api/v1/security-events/{created['id']}",
        json={"status": "acknowledged"},
        headers={"Authorization": f"Bearer {login['access_token']}"},
    )
    assert response.status_code == 403


def test_ids_connector_is_tenant_scoped_and_uses_a_dedicated_token(client: TestClient, user_headers: dict[str, str]):
    registration = client.post(
        "/api/v1/agents/register",
        json={"name": "SOC principal", "hostname": f"soc-{uuid4().hex}", "ip_address": "10.10.0.5"},
        headers={"X-Enrollment-Key": "ci-enrollment-secret"},
    ).json()
    created = client.post(
        "/api/v1/ids-connectors",
        json={"name": "Wazuh siège", "connector_type": "wazuh", "server_id": registration["server_id"]},
        headers=user_headers,
    )
    assert created.status_code == 201
    connector = created.json()
    assert connector["ingest_token"]
    assert connector["server_name"] == "SOC principal"
    assert "ingest_token" not in client.get("/api/v1/ids-connectors", headers=user_headers).text

    event = {
        "event_key": "wazuh-connector-1", "source": "wazuh", "category": "authentication",
        "severity": "high", "title": "Tentatives SSH répétées",
        "description": "Plusieurs échecs ont été détectés.", "source_ip": "203.0.113.10",
        "destination_ip": "10.10.0.5", "rule_id": "5710",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }
    endpoint = connector["ingest_path"]
    assert client.post(endpoint, json=event).status_code == 401
    assert client.post(endpoint, json=event, headers={"Authorization": "Bearer incorrect"}).status_code == 401
    ingested = client.post(
        endpoint,
        json=event,
        headers={"Authorization": f"Bearer {connector['ingest_token']}"},
    )
    duplicate = client.post(
        endpoint,
        json=event,
        headers={"Authorization": f"Bearer {connector['ingest_token']}"},
    )
    assert ingested.status_code == 201
    assert ingested.json()["id"] == duplicate.json()["id"]
    listed = client.get("/api/v1/ids-connectors", headers=user_headers).json()
    assert listed[0]["last_event_at"] is not None

    with SessionLocal() as db:
        other = Organization(name="PME isolée", slug="pme-isolee")
        db.add(other)
        db.flush()
        db.add(User(
            organization_id=other.id,
            email="owner@isolee.test",
            password_hash=hash_password("Isolated-password-strong-2026"),
            role="owner",
        ))
        db.commit()
    other_login = client.post("/api/v1/auth/login", json={
        "organization_slug": "pme-isolee",
        "email": "owner@isolee.test",
        "password": "Isolated-password-strong-2026",
    }).json()
    other_headers = {"Authorization": f"Bearer {other_login['access_token']}"}
    assert client.get("/api/v1/ids-connectors", headers=other_headers).json() == []
