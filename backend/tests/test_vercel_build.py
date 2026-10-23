import pytest
import importlib.util
from pathlib import Path
from alembic import command
from sqlalchemy import create_engine, inspect, text
from app.config import settings
from test_migrations import alembic_config
_spec = importlib.util.spec_from_file_location('vercel_build', Path(__file__).resolve().parents[1] / 'vercel_build.py')
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
main = _module.main


@pytest.fixture(autouse=True)
def production_security_fixture(monkeypatch):
    from cryptography.fernet import Fernet
    values = dict(mfa_encryption_key=Fernet.generate_key().decode(), mfa_required=True,
        secure_cookies=True, allow_legacy_enrollment=False, bootstrap_admin_force_sync=False,
        bootstrap_admin_reset_password='', bootstrap_recovery_key='',
        frontend_public_url='https://fixture.example', cors_origins='https://fixture.example')
    for key, value in values.items():
        monkeypatch.setattr(settings, key, value)


def test_preview_never_connects(monkeypatch):
    monkeypatch.setenv('VERCEL_ENV', 'preview')
    monkeypatch.setattr(settings, 'database_url', 'invalid://must-not-connect')
    main()


def test_production_migrates_expected_revision_twice(tmp_path, monkeypatch):
    url = 'sqlite:///' + (tmp_path / 'production-simulation.db').as_posix()
    monkeypatch.setattr(settings, 'database_url', url)
    command.upgrade(alembic_config(url), '20260922_0005')
    monkeypatch.setenv('VERCEL_ENV', 'production')
    main()
    main()
    engine = create_engine(url)
    assert 'managed_actions' in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '20261022_0007'
    engine.dispose()


def test_unversioned_database_stops_deployment(tmp_path, monkeypatch):
    url = 'sqlite:///' + (tmp_path / 'unversioned.db').as_posix()
    monkeypatch.setattr(settings, 'database_url', url)
    monkeypatch.setenv('VERCEL_ENV', 'production')
    with pytest.raises(RuntimeError, match='preflight failed'):
        main()
    engine = create_engine(url)
    assert inspect(engine).get_table_names() == []
    engine.dispose()
