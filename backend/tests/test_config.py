from app.config import Settings


def settings_for(database_url: str) -> Settings:
    return Settings(
        database_url=database_url,
        agent_enrollment_key="test-enrollment-key",
        network_scan_key="test-network-scan-key",
    )


def test_render_postgresql_url_uses_psycopg_driver():
    settings = settings_for("postgresql://user:secret@db.example.test:5432/cyberpme")

    assert settings.database_url == (
        "postgresql+psycopg://user:secret@db.example.test:5432/cyberpme"
    )


def test_explicit_sqlalchemy_driver_is_preserved():
    url = "postgresql+psycopg://user:secret@database:5432/cyberpme"

    assert settings_for(url).database_url == url
