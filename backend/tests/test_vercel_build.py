import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text
from app.config import settings
from test_migrations import alembic_config
from vercel_build import main


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
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '20260924_0006'
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
