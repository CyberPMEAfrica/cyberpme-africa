import pytest
from cryptography.fernet import Fernet
from app.config import settings
from app.security_preflight import validate_production_security


def test_production_security_preflight_rejects_insecure_flags(monkeypatch):
    monkeypatch.setattr(settings, 'mfa_encryption_key', '')
    monkeypatch.setattr(settings, 'mfa_required', False)
    monkeypatch.setattr(settings, 'secure_cookies', False)
    with pytest.raises(RuntimeError, match='MFA_REQUIRED'):
        validate_production_security()


def test_production_security_preflight_accepts_complete_config(monkeypatch):
    values = dict(mfa_encryption_key=Fernet.generate_key().decode(), mfa_required=True,
                  secure_cookies=True, allow_legacy_enrollment=False,
                  bootstrap_admin_force_sync=False, bootstrap_admin_reset_password='', bootstrap_recovery_key='',
                  frontend_public_url='https://pilot.example.com', cors_origins='https://pilot.example.com')
    for key, value in values.items():
        monkeypatch.setattr(settings, key, value)
    validate_production_security()
    monkeypatch.setattr(settings, 'bootstrap_recovery_key', 'not-allowed-in-production')
    with pytest.raises(RuntimeError, match='bootstrap'):
        validate_production_security()


def test_preview_refuses_startup_without_explicit_database_isolation(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setenv('VERCEL_ENV', 'preview')
    monkeypatch.delenv('PREVIEW_DATABASE_ISOLATED', raising=False)
    with pytest.raises(RuntimeError, match='Preview refusée'):
        with TestClient(app):
            pytest.fail('preview startup must be denied')
