from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "suricata" / "cyberpme-suricata"
FIXTURE = Path(__file__).parent / "fixtures" / "suricata-eve.jsonl"
loader = SourceFileLoader("cyberpme_suricata", str(SCRIPT))
spec = spec_from_loader(loader.name, loader)
adapter = module_from_spec(spec)
loader.exec_module(adapter)


def alert_event(**overrides):
    event = {
        "timestamp": "2026-07-30T08:15:00+00:00",
        "flow_id": 42,
        "event_type": "alert",
        "src_ip": "192.0.2.10",
        "src_port": 50000,
        "dest_ip": "10.0.0.10",
        "dest_port": 22,
        "proto": "TCP",
        "alert": {
            "action": "allowed",
            "signature_id": 2001219,
            "signature": "ET SCAN Potential SSH Scan",
            "category": "Attempted Information Leak",
            "severity": 2,
        },
    }
    event.update(overrides)
    return event


def test_normalizes_suricata_alert():
    normalized = adapter.normalize_suricata_alert(alert_event())

    assert normalized["event_key"].startswith("suricata-2001219-")
    assert normalized["source"] == "suricata"
    assert normalized["category"] == "network"
    assert normalized["severity"] == "high"
    assert normalized["title"] == "ET SCAN Potential SSH Scan"
    assert normalized["source_ip"] == "192.0.2.10"
    assert normalized["destination_ip"] == "10.0.0.10"
    assert normalized["rule_id"] == "2001219"
    assert normalized["occurred_at"] == "2026-07-30T08:15:00+00:00"
    assert "192.0.2.10:50000 -> 10.0.0.10:22" in normalized["description"]


def test_event_key_is_deterministic_and_changes_with_the_flow():
    first = adapter.normalize_suricata_alert(alert_event())
    duplicate = adapter.normalize_suricata_alert(alert_event())
    another = adapter.normalize_suricata_alert(alert_event(flow_id=43))

    assert first["event_key"] == duplicate["event_key"]
    assert first["event_key"] != another["event_key"]


@pytest.mark.parametrize(
    ("suricata_level", "expected"),
    [(1, "critical"), (2, "high"), (3, "medium"), (4, "low"), (None, "medium")],
)
def test_maps_suricata_severity(suricata_level, expected):
    assert adapter.severity_from_suricata(suricata_level) == expected


@pytest.mark.parametrize(
    ("suricata_category", "expected"),
    [
        ("Credential Theft", "authentication"),
        ("A Network Trojan was detected", "malware"),
        ("Web Application Attack", "vulnerability"),
        ("Attempted Information Leak", "network"),
    ],
)
def test_maps_suricata_categories(suricata_category, expected):
    assert adapter.category_from_suricata(suricata_category) == expected


def test_fixture_filters_non_alert_events():
    received = []

    stats = adapter.process_file(FIXTURE, received.append)

    assert stats == {"lines": 3, "alerts": 2, "ignored": 1, "invalid": 0}
    assert [event["rule_id"] for event in received] == ["2001219", "2024218"]
    assert received[1]["category"] == "malware"
    assert received[1]["severity"] == "critical"


def test_state_file_prevents_replay_and_resets_after_rotation(tmp_path):
    eve_file = tmp_path / "eve.json"
    state_file = tmp_path / "state.json"
    eve_file.write_bytes(FIXTURE.read_bytes())
    received = []

    first = adapter.process_file(eve_file, received.append, state_file)
    second = adapter.process_file(eve_file, received.append, state_file)
    eve_file.replace(tmp_path / "eve.previous.json")
    eve_file.write_text(json.dumps(alert_event(flow_id=99)) + "\n", encoding="utf-8")
    third = adapter.process_file(eve_file, received.append, state_file)

    assert first["alerts"] == 2
    assert second["lines"] == 0
    assert third["alerts"] == 1
    assert len(received) == 3


def test_invalid_line_is_reported_without_stopping_valid_alerts(tmp_path):
    eve_file = tmp_path / "eve.json"
    eve_file.write_text(
        "not-json\n" + json.dumps(alert_event()) + "\n",
        encoding="utf-8",
    )
    errors = []
    received = []

    stats = adapter.process_file(
        eve_file,
        received.append,
        on_error=lambda line, error: errors.append((line, str(error))),
    )

    assert stats["invalid"] == 1
    assert stats["alerts"] == 1
    assert errors[0][0] == 1
    assert len(received) == 1


def test_failed_delivery_does_not_advance_state(tmp_path):
    eve_file = tmp_path / "eve.json"
    state_file = tmp_path / "state.json"
    eve_file.write_bytes(FIXTURE.read_bytes())

    with pytest.raises(RuntimeError, match="API indisponible"):
        adapter.process_file(
            eve_file,
            lambda event: (_ for _ in ()).throw(RuntimeError("API indisponible")),
            state_file,
        )

    assert not state_file.exists()
    received = []
    stats = adapter.process_file(eve_file, received.append, state_file)
    assert stats["alerts"] == 2
    assert len(received) == 2


def test_persistent_queue_deduplicates_and_delivers_events(tmp_path):
    queue_dir = tmp_path / "queue"
    event = adapter.normalize_suricata_alert(alert_event())

    assert adapter.enqueue_event(queue_dir, event, 1024 * 1024) is True
    assert adapter.enqueue_event(queue_dir, event, 1024 * 1024) is False
    assert len(adapter.queue_entries(queue_dir)) == 1

    received = []
    stats = adapter.flush_queue(queue_dir, received.append)

    assert stats == {"delivered": 1, "invalid": 0, "remaining": 0}
    assert received == [event]
    assert adapter.queue_entries(queue_dir) == []


def test_delivery_failure_keeps_queue_and_later_retry_succeeds(tmp_path):
    queue_dir = tmp_path / "queue"
    event = adapter.normalize_suricata_alert(alert_event())
    adapter.enqueue_event(queue_dir, event, 1024 * 1024)

    with pytest.raises(RuntimeError, match="API indisponible"):
        adapter.flush_queue(
            queue_dir,
            lambda queued: (_ for _ in ()).throw(RuntimeError("API indisponible")),
        )

    assert len(adapter.queue_entries(queue_dir)) == 1
    received = []
    stats = adapter.flush_queue(queue_dir, received.append)
    assert stats["delivered"] == 1
    assert stats["remaining"] == 0
    assert received == [event]


def test_queue_full_does_not_advance_eve_state(tmp_path):
    eve_file = tmp_path / "eve.json"
    state_file = tmp_path / "state.json"
    queue_dir = tmp_path / "queue"
    eve_file.write_text(json.dumps(alert_event()) + "\n", encoding="utf-8")

    with pytest.raises(adapter.QueueFullError, match="File locale pleine"):
        adapter.process_file(
            eve_file,
            lambda event: adapter.enqueue_event(queue_dir, event, 10),
            state_file,
        )

    assert not state_file.exists()
    assert adapter.queue_entries(queue_dir) == []


def test_corrupted_queue_entry_is_quarantined_without_blocking_valid_event(tmp_path):
    queue_dir = tmp_path / "queue"
    queue_dir.mkdir()
    corrupted = queue_dir / "000-corrupted.json"
    corrupted.write_text("not-json", encoding="utf-8")
    event = adapter.normalize_suricata_alert(alert_event())
    adapter.enqueue_event(queue_dir, event, 1024 * 1024)
    errors = []
    received = []

    stats = adapter.flush_queue(
        queue_dir,
        received.append,
        on_invalid=lambda path, error: errors.append((path.name, str(error))),
    )

    assert stats == {"delivered": 1, "invalid": 1, "remaining": 0}
    assert received == [event]
    assert errors[0][0] == "000-corrupted.json"
    assert len(list((queue_dir / "quarantine").glob("*.invalid"))) == 1


def test_flush_queue_honors_delivery_limit(tmp_path):
    queue_dir = tmp_path / "queue"
    for flow_id in range(3):
        event = adapter.normalize_suricata_alert(alert_event(flow_id=flow_id))
        adapter.enqueue_event(queue_dir, event, 1024 * 1024)

    received = []
    stats = adapter.flush_queue(queue_dir, received.append, max_deliveries=2)

    assert stats["delivered"] == 2
    assert stats["remaining"] == 1
    assert len(received) == 2


def test_cli_keeps_events_offline_then_flushes_without_rereading_eve(tmp_path, monkeypatch):
    eve_file = tmp_path / "eve.json"
    state_file = tmp_path / "state.json"
    queue_dir = tmp_path / "queue"
    eve_file.write_text(json.dumps(alert_event()) + "\n", encoding="utf-8")
    common_args = [
        "--eve-file",
        str(eve_file),
        "--state-file",
        str(state_file),
        "--queue-dir",
        str(queue_dir),
        "--endpoint",
        "https://cyberpme.example.test/api/v1/ids-connectors/test/events",
        "--token",
        "x" * 32,
    ]

    monkeypatch.setattr(
        adapter,
        "post_event",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("hors ligne")),
    )
    assert adapter.main(common_args) == 1
    assert state_file.exists()
    assert len(adapter.queue_entries(queue_dir)) == 1

    received = []
    monkeypatch.setattr(
        adapter,
        "post_event",
        lambda event, *args, **kwargs: received.append(event),
    )
    assert adapter.main(common_args + ["--flush-only"]) == 0
    assert len(received) == 1
    assert adapter.queue_entries(queue_dir) == []


def test_posts_normalized_event_with_connector_token(monkeypatch):
    captured = {}

    class Response:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(adapter, "urlopen", fake_urlopen)
    event = adapter.normalize_suricata_alert(alert_event())

    adapter.post_event(event, "https://cyberpme.example.test/events", "secret-token")

    request = captured["request"]
    assert request.full_url == "https://cyberpme.example.test/events"
    assert request.get_header("Authorization") == "Bearer secret-token"
    assert request.get_header("Content-type") == "application/json"
    assert json.loads(request.data) == event
    assert captured["timeout"] == 10


@pytest.mark.parametrize(
    "endpoint",
    ["", "localhost:8000/events", "ftp://example.test/events", "https:///events"],
)
def test_rejects_invalid_ingestion_endpoint(endpoint):
    with pytest.raises(ValueError, match="n'est pas valide"):
        adapter.validate_endpoint(endpoint)


def test_rejects_non_alert_payload():
    with pytest.raises(ValueError, match="n'est pas une alerte"):
        adapter.normalize_suricata_alert({"event_type": "dns"})
