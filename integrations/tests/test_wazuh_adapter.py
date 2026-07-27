from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "wazuh" / "custom-cyberpme"
loader = SourceFileLoader("custom_cyberpme", str(SCRIPT))
spec = spec_from_loader(loader.name, loader)
adapter = module_from_spec(spec)
loader.exec_module(adapter)


def test_normalizes_authentication_alert():
    event = adapter.normalize_wazuh_alert({
        "id": "1700000000.123",
        "timestamp": "2026-07-27T14:00:00+00:00",
        "rule": {
            "id": "5710",
            "level": 10,
            "description": "Tentatives SSH répétées",
            "groups": ["sshd", "authentication_failed"],
        },
        "agent": {"id": "001", "ip": "10.0.2.15"},
        "data": {"srcip": "203.0.113.10"},
        "full_log": "Failed password for invalid user",
    })
    assert event["event_key"] == "wazuh-1700000000.123"
    assert event["source"] == "wazuh"
    assert event["category"] == "authentication"
    assert event["severity"] == "high"
    assert event["source_ip"] == "203.0.113.10"
    assert event["destination_ip"] == "10.0.2.15"
    assert event["rule_id"] == "5710"


def test_maps_wazuh_levels_to_cyberpme_severities():
    expected = {0: "low", 6: "low", 7: "medium", 9: "medium", 10: "high", 12: "high", 13: "critical", 16: "critical"}
    for level, severity in expected.items():
        assert adapter.severity_from_level(level) == severity


def test_falls_back_for_sparse_alerts():
    event = adapter.normalize_wazuh_alert({"rule": {"level": 3}})
    assert event["category"] == "network"
    assert event["severity"] == "low"
    assert event["title"] == "Alerte Wazuh"
    assert event["event_key"].startswith("wazuh-unknown-manager-")
