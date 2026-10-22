"""Security regression tests: isolated database and no live network scans."""
import hashlib
import time
from datetime import timedelta
from uuid import UUID
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from test_api import clean_database, client, user_headers
from app.config import settings
from app.database import SessionLocal
from app.models import AuditEntry, Organization, User, utc_now
from app.security_models import AccountSecurity, AgentSecurity
from app import security

LOGIN = {"organization_slug": "pme-test", "email": "owner@example.test", "password": "Test-password-very-strong-2026"}


def test_release_readiness_reports_only_protocol(client):
    response = client.get('/api/v1/security/readiness')
    assert response.status_code == 200
    assert response.json() == {'protocol': 'cyberpme-cookie-mfa-v1'}


@pytest.fixture(autouse=True)
def secure_settings(monkeypatch):
    monkeypatch.setattr(settings, 'allow_legacy_enrollment', False)
    monkeypatch.setattr(settings, 'mfa_encryption_key', Fernet.generate_key().decode())


def pair(client, headers, mode='monitoring', hostname='secure-host'):
    issued = client.post('/api/v1/agent-enrollment-tokens', headers=headers, json={'mode': mode})
    assert issued.status_code == 201, issued.text
    registration = client.post('/api/v1/agents/register', headers={'X-Enrollment-Token': issued.json()['enrollment_token']},
        json={'name': 'Secure host', 'hostname': hostname, 'network_scan_capable': True})
    assert registration.status_code == 200, registration.text
    data = registration.json()
    return data, {'Authorization': 'Bearer ' + data['agent_token']}


def test_monitoring_identity_cannot_claim_scans_or_operations(client, user_headers):
    agent, auth = pair(client, user_headers)
    base = '/api/v1/servers/' + agent['server_id']
    assert agent['mode'] == 'monitoring'
    assert client.post(base + '/metrics', headers=auth, json={'cpu_percent': 10, 'memory_percent': 20, 'disk_percent': 30}).status_code == 201
    assert client.get(base + '/network-scan-jobs/next', headers=auth).status_code == 403
    assert client.get(base + '/managed-actions/next', headers=auth).status_code == 403
    server = client.get('/api/v1/servers', headers=user_headers).json()[0]
    assert server['agent_connected'] is True
    assert server['network_scan_capable'] is False
    assert client.post('/api/v1/network-scans', headers=user_headers, json={'target': '192.168.1.0/24', 'agent_server_id': agent['server_id']}).status_code == 409


def test_revocation_expiry_and_tenant_boundary(client, user_headers):
    agent, auth = pair(client, user_headers)
    base = '/api/v1/servers/' + agent['server_id']
    with SessionLocal() as db:
        profile = db.get(AgentSecurity, UUID(agent['server_id']))
        profile.expires_at = utc_now() - timedelta(seconds=1)
        db.commit()
    assert client.post(base + '/metrics', headers=auth, json={'cpu_percent': 1, 'memory_percent': 1, 'disk_percent': 1}).status_code == 401
    agent, auth = pair(client, user_headers)  # Re-pair replaces, not duplicates, the identity.
    with SessionLocal() as db:
        other = Organization(name='Other tenant', slug='other-tenant')
        db.add(other); db.flush()
        user = db.scalar(select(User).where(User.email == LOGIN['email']))
        user.organization_id = other.id
        db.commit()
    assert client.post(base + '/agent-credential/revoke', headers=user_headers).status_code == 404


def test_rotation_invalidates_old_token_and_revoke_invalidates_new(client, user_headers):
    agent, auth = pair(client, user_headers)
    base = '/api/v1/servers/' + agent['server_id']
    rotated = client.post(base + '/agent-credential/rotate', headers=auth)
    assert rotated.status_code == 200
    new_auth = {'Authorization': 'Bearer ' + rotated.json()['agent_token']}
    metric = {'cpu_percent': 1, 'memory_percent': 1, 'disk_percent': 1}
    assert client.post(base + '/metrics', headers=auth, json=metric).status_code == 401
    assert client.post(base + '/metrics', headers=new_auth, json=metric).status_code == 201
    assert client.post(base + '/agent-credential/revoke', headers=user_headers).status_code == 204
    assert client.post(base + '/metrics', headers=new_auth, json=metric).status_code == 401
    assert client.post(base + '/agent-credential/rotate', headers=new_auth).status_code == 401


def test_shared_legacy_enrollment_is_disabled(client):
    response = client.post('/api/v1/agents/register', json={'name': 'Denied', 'hostname': 'denied'}, headers={'X-Enrollment-Key': 'ci-enrollment-secret'})
    assert response.status_code == 401


def test_login_throttle_is_persisted_and_generic(client):
    bad = LOGIN | {'password': 'not-the-password-1234'}
    for _ in range(8):
        assert client.post('/api/v1/auth/login', json=bad).status_code == 401
    response = client.post('/api/v1/auth/login', json=LOGIN)
    assert response.status_code == 429
    assert response.headers['retry-after'] == '900'
    # Successful credentials do not bypass the shared counter.
    assert client.post('/api/v1/auth/login', json=LOGIN).status_code == 429


def test_mfa_required_restricts_session_until_enrolled(client, user_headers, monkeypatch):
    monkeypatch.setattr(settings, 'mfa_required', True)
    assert client.get('/api/v1/auth/me', headers=user_headers).json()['mfa_setup_required'] is True
    assert client.get('/api/v1/servers', headers=user_headers).status_code == 403
    assert client.get('/api/v1/auth/mfa/status', headers=user_headers).status_code == 200


def test_mfa_encryption_recovery_and_session_revocation(client, user_headers):
    setup = client.post('/api/v1/auth/mfa/setup', headers=user_headers, json={'password': LOGIN['password']})
    assert setup.status_code == 200, setup.text
    secret = setup.json()['secret']
    code = security.totp(secret, int(time.time() // 30))
    enabled = client.post('/api/v1/auth/mfa/enable', headers=user_headers, json={'password': LOGIN['password'], 'code': code})
    assert enabled.status_code == 200, enabled.text
    codes = enabled.json()['recovery_codes']
    assert len(codes) == 10
    assert client.get('/api/v1/auth/me', headers=user_headers).status_code == 401
    assert client.post('/api/v1/auth/login', json=LOGIN).json()['detail'] == 'MFA_REQUIRED'
    # Setup code is marked used; it cannot be replayed during login.
    assert client.post('/api/v1/auth/login', json=LOGIN | {'mfa_code': code}).status_code == 401
    assert client.post('/api/v1/auth/login', json=LOGIN | {'mfa_code': codes[0]}).status_code == 200
    assert client.post('/api/v1/auth/login', json=LOGIN | {'mfa_code': codes[0]}).status_code == 401
    with SessionLocal() as db:
        profile = db.scalar(select(AccountSecurity))
        assert secret not in profile.secret_encrypted
        assert codes[0] not in str(profile.recovery_hashes)
        audit = str([row.details for row in db.scalars(select(AuditEntry))])
        assert secret not in audit and codes[0] not in audit


def test_mfa_missing_encryption_key_fails_closed(client, user_headers, monkeypatch):
    monkeypatch.setattr(settings, 'mfa_encryption_key', '')
    response = client.post('/api/v1/auth/mfa/setup', headers=user_headers, json={'password': LOGIN['password']})
    assert response.status_code == 503


def test_mfa_reset_requires_second_factor_and_restricts_remaining_session(client, user_headers, monkeypatch):
    setup = client.post('/api/v1/auth/mfa/setup', headers=user_headers, json={'password': LOGIN['password']}).json()
    code = security.totp(setup['secret'], int(time.time() // 30))
    enabled = client.post('/api/v1/auth/mfa/enable', headers=user_headers, json={'password': LOGIN['password'], 'code': code}).json()
    codes = enabled['recovery_codes']
    login = client.post('/api/v1/auth/login', json=LOGIN | {'mfa_code': codes[0]}).json()
    auth = {'Authorization': 'Bearer ' + login['access_token']}
    monkeypatch.setattr(settings, 'mfa_required', True)
    assert client.post('/api/v1/auth/mfa/reset', headers=auth, json={'password': LOGIN['password'], 'code': 'bad'}).status_code == 401
    assert client.post('/api/v1/auth/mfa/reset', headers=auth, json={'password': LOGIN['password'], 'code': codes[1]}).status_code == 204
    assert client.get('/api/v1/servers', headers=auth).status_code == 403
    assert client.get('/api/v1/auth/me', headers=auth).json()['mfa_setup_required'] is True
    assert client.get('/api/v1/auth/mfa/status', headers=auth).json()['recovery_codes_remaining'] == 0


def test_cookie_session_is_httponly_and_csrf_protected(client, monkeypatch):
    monkeypatch.setattr(settings, 'secure_cookies', False)  # HTTP TestClient only.
    headers = {'X-CyberPME-Browser': '1', 'Origin': settings.frontend_public_url}
    response = client.post('/api/v1/auth/login', headers=headers, json=LOGIN)
    assert response.status_code == 200
    assert response.json()['access_token'] == ''
    assert 'httponly' in response.headers['set-cookie'].lower()
    assert 'samesite=lax' in response.headers['set-cookie'].lower()
    assert client.get('/api/v1/auth/me').status_code == 200
    assert client.patch('/api/v1/auth/preferences', json={'theme': 'dark'}).status_code == 403
    assert client.patch('/api/v1/auth/preferences', headers=headers | {'Origin': 'https://evil.example'}, json={'theme': 'dark'}).status_code == 403
    assert client.patch('/api/v1/auth/preferences', headers=headers, json={'theme': 'light'}).status_code == 200
    assert client.post('/api/v1/auth/logout', headers=headers).status_code == 204
    assert client.get('/api/v1/auth/me').status_code == 401


def test_secure_cookie_default_and_response_headers(client):
    response = client.post('/api/v1/auth/login', headers={'X-CyberPME-Browser': '1'}, json=LOGIN)
    assert 'secure' in response.headers['set-cookie'].lower()
    assert response.headers['set-cookie'].startswith('__Host-cyberpme_session=')
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['x-frame-options'] == 'DENY'


def test_ssl_connection_uses_validated_numeric_address(monkeypatch):
    from app import ssl_monitor
    calls = []
    monkeypatch.setattr(ssl_monitor.socket, 'getaddrinfo', lambda *a, **k: [(2, 1, 6, '', ('93.184.216.34', 443))])
    def capture(address, **kwargs):
        calls.append(address)
        raise OSError('test: no real connection')
    monkeypatch.setattr(ssl_monitor.socket, 'create_connection', capture)
    with pytest.raises(OSError):
        ssl_monitor.inspect_certificate('example.com', 443)
    assert calls == [('93.184.216.34', 443)]


def test_ssl_private_dns_answer_never_connects(monkeypatch):
    from app import ssl_monitor
    monkeypatch.setattr(ssl_monitor.socket, 'getaddrinfo', lambda *a, **k: [(2, 1, 6, '', ('127.0.0.1', 443))])
    monkeypatch.setattr(ssl_monitor.socket, 'create_connection', lambda *a, **k: pytest.fail('private address must not be contacted'))
    with pytest.raises(ValueError):
        ssl_monitor.inspect_certificate('example.com', 443)


@pytest.mark.skipif(not __import__('os').environ.get('TEST_POSTGRES_URL'), reason='Disposable PostgreSQL CI only')
@pytest.mark.parametrize('proof', ['totp', 'recovery'])
def test_concurrent_mfa_proof_is_consumed_once_on_postgres(client, user_headers, proof):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    secret = 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP'
    code = security.totp(secret, int(time.time() // 30)) if proof == 'totp' else 'abcdef0123456789'
    with SessionLocal() as db:
        user_id = db.scalar(select(User.id).where(User.email == LOGIN['email']))
        profile = AccountSecurity(user_id=user_id, enabled=True, secret_encrypted=security.cipher().encrypt(secret.encode()).decode(),
            last_counter=-1, recovery_hashes=[hashlib.sha256(code.encode()).hexdigest()] if proof == 'recovery' else [])
        db.add(profile); db.commit()
    barrier = Barrier(2)
    def consume():
        with SessionLocal() as db:
            profile = db.get(AccountSecurity, user_id)
            barrier.wait(timeout=10)
            accepted = security.consume_mfa(db, profile, code)
            db.commit()
            return accepted
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: consume(), range(2)))
    assert sorted(results) == [False, True]
