import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///./cyberpme_test.db")
os.environ.setdefault("AGENT_ENROLLMENT_KEY", "ci-enrollment-secret")
os.environ.setdefault("NETWORK_SCAN_KEY", "ci-network-scan-secret")

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base
from app.models import Organization, User


def alembic_config(database_url: str) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def upgrade_database(database_url: str) -> None:
    previous_url = settings.database_url
    settings.database_url = database_url
    try:
        command.upgrade(alembic_config(database_url), "head")
    finally:
        settings.database_url = previous_url


def test_migration_creates_a_fresh_schema_and_is_idempotent(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}"

    upgrade_database(database_url)
    upgrade_database(database_url)

    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert {
        "alembic_version",
        "organizations",
        "users",
        "servers",
        "security_events",
        "audit_entries",
    }.issubset(set(inspector.get_table_names()))
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one() == "20260729_0002"
    assert {column["name"] for column in inspector.get_columns("users")} >= {"theme"}
    engine.dispose()


def test_migration_adopts_existing_schema_without_losing_data(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'existing.db').as_posix()}"
    engine = create_engine(database_url)
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        organization = Organization(name="PME existante", slug="pme-existante")
        db.add(organization)
        db.flush()
        db.add(
            User(
                organization_id=organization.id,
                email="owner@existante.test",
                password_hash="hash-de-test",
                role="owner",
            )
        )
        db.commit()

    with engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE users DROP COLUMN theme")

    upgrade_database(database_url)

    with Session(engine) as db:
        organization = db.scalar(
            select(Organization).where(Organization.slug == "pme-existante")
        )
        assert organization is not None
        assert organization.name == "PME existante"
        existing_user = db.scalar(
            select(User).where(User.organization_id == organization.id)
        )
        assert existing_user.email == "owner@existante.test"
        assert existing_user.theme == "dark"
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one() == "20260729_0002"
    engine.dispose()
