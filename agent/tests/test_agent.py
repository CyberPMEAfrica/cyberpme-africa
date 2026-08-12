import os

from cyberpme_agent.main import Config, collect_metrics, inspect_backup


def test_config_supports_ubuntu_environment(monkeypatch):
    monkeypatch.setenv("CYBERPME_API_URL", "http://10.0.2.2:8000/")
    monkeypatch.setenv("CYBERPME_SERVER_NAME", "Ubuntu Wazuh Lab")
    monkeypatch.setenv("CYBERPME_HOSTNAME", "soc-vrt")
    monkeypatch.setenv("CYBERPME_ENROLLMENT_KEY", "test-secret")

    config = Config.from_environment(interval_override=30)

    assert config.api_url == "http://10.0.2.2:8000"
    assert config.name == "Ubuntu Wazuh Lab"
    assert config.hostname == "soc-vrt"
    assert config.enrollment_key == "test-secret"
    assert config.interval == 30


def test_collected_metrics_are_percentages():
    metrics = collect_metrics()

    assert set(metrics) == {"cpu_percent", "memory_percent", "disk_percent"}
    assert all(0 <= value <= 100 for value in metrics.values())


def test_inspect_backup_selects_latest_postgresql_dump(tmp_path):
    old = tmp_path / "old.sql"
    latest = tmp_path / "latest.dump"
    ignored = tmp_path / "notes.txt"
    old.write_text("old")
    latest.write_text("database")
    ignored.write_text("ignore")
    os.utime(old, (1, 1))
    os.utime(latest, (2, 2))
    result = inspect_backup("postgresql", "Base PME", str(tmp_path), 24)
    assert result["exists"] is True
    assert result["size_bytes"] == len("database")
    assert result["error"] is None
