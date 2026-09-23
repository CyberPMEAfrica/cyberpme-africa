import os
import json
from dataclasses import replace
import pytest

from cyberpme_agent.main import Config, collect_metrics, inspect_backup
from cyberpme_agent import main as agent


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


def test_registration_persists_credentials_and_removes_pairing_token(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"enrollment_token": "once", "state_path": str(tmp_path / "state.json")}), encoding="utf-8-sig")
    config = Config.from_sources(path)
    monkeypatch.setattr(agent, "discover_ip", lambda: "192.168.1.2")
    calls = []
    def request(*args, **kwargs):
        calls.append(args)
        return {"server_id": "id", "agent_token": "persistent"}
    monkeypatch.setattr(agent, "request_json", request)
    assert agent.register_agent(config) == ("id", "persistent")
    assert agent.load_state(config.state_path) == ("id", "persistent")
    assert calls[0][3] == {"X-Enrollment-Token": "once"}
    assert "enrollment_token" not in json.loads(path.read_text())


def test_scan_results_retry_after_network_failure(tmp_path, monkeypatch):
    config = replace(Config.from_environment(), state_path=tmp_path / "state.json")
    monkeypatch.setattr(agent, "run_network_scan", lambda _: [{"ip_address": "192.168.1.2"}])
    def offline(method, *args, **kwargs):
        if method == "POST":
            raise RuntimeError("offline")
        return {"id": "job", "target": "192.168.1.0/24"}
    monkeypatch.setattr(agent, "request_json", offline)
    with pytest.raises(RuntimeError):
        agent.process_scan_job(config, "pc", "token")
    assert config.state_path.with_suffix(".result.json").exists()
    sent = []
    def online(method, url, payload=None, headers=None):
        if method == "POST":
            sent.append(payload)
        return None
    monkeypatch.setattr(agent, "request_json", online)
    assert agent.process_scan_job(config, "pc", "token") is False
    assert sent[0]["status"] == "completed"
    assert not config.state_path.with_suffix(".result.json").exists()


def test_local_scan_rejects_public_and_loopback_targets():
    for target in ["8.8.8.0/24", "127.0.0.0/24", "169.254.1.0/24", "10.0.0.0/8"]:
        with pytest.raises(RuntimeError):
            agent.run_network_scan(target)


def test_local_scan_uses_discovered_hosts_and_parses_services(monkeypatch):
    monkeypatch.setattr(agent, "find_nmap", lambda: "nmap")
    xml = '<nmaprun><host><status state="up"/><address addr="192.168.1.2" addrtype="ipv4"/><ports><port portid="443" protocol="tcp"><state state="open"/><service name="https"/></port></ports></host></nmaprun>'
    commands = []
    def nmap(command, timeout):
        commands.append(command)
        return xml
    monkeypatch.setattr(agent, "execute_nmap", nmap)
    result = agent.run_network_scan("192.168.1.0/24")
    assert commands[1][-1] == "192.168.1.2"
    assert result[0]["ports"][0]["port"] == 443
    assert result[0]["recommendations"]
    assert agent.parse_up_hosts(xml, "192.168.1.2/32") == ["192.168.1.2"]
