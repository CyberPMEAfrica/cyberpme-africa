"""Local agent least-privilege tests."""
from dataclasses import replace
import pytest
from cyberpme_agent import main as agent
from cyberpme_agent.operation_worker import process_action, process_schedule


@pytest.mark.parametrize('url', ['http://api.example.com', 'http://192.168.1.5', 'ftp://api.example.com', 'https://name:secret@api.example.com', 'https://api.example.com#fragment'])
def test_agent_rejects_insecure_api_urls(url):
    with pytest.raises(ValueError):
        agent.validate_api_url(url)


@pytest.mark.parametrize('url', ['https://api.example.com', 'http://localhost:8000', 'http://127.0.0.1:8000'])
def test_agent_allows_https_and_loopback_development(url):
    agent.validate_api_url(url)


def test_monitoring_never_claims_or_executes_jobs(tmp_path, monkeypatch):
    config = replace(agent.Config.from_environment(), state_path=tmp_path / 'state.json')
    assert config.mode == 'monitoring'
    def no(*a, **k):
        pytest.fail('monitoring must not request or execute a remote task')
    monkeypatch.setattr(agent, 'request_json', no)
    monkeypatch.setattr(agent, 'run_network_scan', no)
    assert agent.process_scan_job(config, 'server', 'token') is False
    assert process_action(config, 'server', 'token', no, no) is False
    assert process_schedule(config, 'server', 'token', no, no) is False
    monkeypatch.setattr(agent, 'load_state', lambda _: ('server', 'token'))
    monkeypatch.setattr(agent, 'send_once', lambda *a: {})
    monkeypatch.setattr(agent, 'process_scan_job', no)
    agent.run(config, once=True)


def test_monitoring_cannot_enable_operations_by_accident():
    with pytest.raises(ValueError):
        replace(agent.Config.from_environment(), operations={'enabled': True})


def test_redirect_cannot_leak_agent_authorization():
    with pytest.raises(RuntimeError):
        agent.NoRedirects().redirect_request(None, None, 302, '', {}, 'https://another-host.example')


def test_monitoring_service_has_no_root_or_capabilities():
    from pathlib import Path
    service = (Path(__file__).resolve().parents[1] / 'deploy/cyberpme-monitor.service').read_text()
    for setting in ('User=cyberpme', 'NoNewPrivileges=true', 'CapabilityBoundingSet=\n',
                    'ProtectSystem=strict', 'ReadWritePaths=/var/lib/cyberpme', 'UMask=0077'):
        assert setting in service
    assert 'User=root' not in service
