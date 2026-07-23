from cyberpme_agent.main import Config, collect_metrics


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
