import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from cyberpme_agent.operations import BackupEngine, FirewallEngine, OperationError, perform


@pytest.fixture
def profile(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    password = tmp_path / 'secret'; password.write_text('test-only')
    return {'backup_profiles': {'documents': {'enabled': True,
        'external_destination_confirmed': True, 'kind': 'files',
        'sources': [str(source)], 'password_file': str(password),
        'restore_root': str(tmp_path / 'restores'), 'repository': str(tmp_path / 'repo')}}}


def test_backup_arguments_and_no_implicit_pruning(profile, tmp_path):
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return json.dumps({'message_type': 'summary', 'snapshot_id': 'a'*64})
    result = BackupEngine(profile, tmp_path/'state', 'host', run).backup('documents', uuid4())
    assert result['snapshot'] == 'a'*64
    assert len(calls) == 2
    assert 'init' not in calls[0][0]
    assert '--exclude' in calls[1][0]
    assert 'RESTIC_PASSWORD_FILE' in calls[1][1]['env']
    assert 'test-only' not in str(calls)


def test_bad_retention_refused_before_any_execution(profile, tmp_path):
    profile['backup_profiles']['documents'].update(retention_enabled=True, keep_last=0)
    def run(*a, **kw): pytest.fail('must validate before execution')
    with pytest.raises(OperationError): BackupEngine(profile,tmp_path,'host',run).backup('documents',uuid4())


def test_restore_foreign_snapshot_rejected(profile, tmp_path):
    calls=[]
    def run(args, **kw): calls.append(args); return '[]'
    with pytest.raises(OperationError):
        BackupEngine(profile,tmp_path,'host',run).restore_test('documents','a'*64,uuid4())
    assert len(calls)==1
    assert not (tmp_path/'restores').exists()


def test_restore_never_reuses_destination(profile,tmp_path):
    targets=[]
    def run(args, **kw):
        if 'snapshots' in args: return json.dumps([{'id':'a'*64}])
        targets.append(args[args.index('--target')+1]); return ''
    engine=BackupEngine(profile,tmp_path,'host',run)
    action_id=uuid4()
    engine.restore_test('documents','a'*64,action_id)
    engine.restore_test('documents','a'*64,action_id)
    assert targets[0]!=targets[1]


def firewall(system='Linux', runner=lambda *a,**k: ''):
    return FirewallEngine({'firewall':{'enabled':True,'protected_networks':['9.9.9.9/32']}},
        'https://api.example.test',system,runner,lambda *a:[(None,None,None,None,('1.1.1.1',443))])


@pytest.mark.parametrize('ip',['192.168.1.1','127.0.0.1','9.9.9.9','1.1.1.1','::1','224.0.0.1'])
def test_protected_ips_refused(ip):
    with pytest.raises(OperationError): firewall().validate(ip)


def test_expired_block_never_runs():
    def run(*a, **kw): pytest.fail('expired block')
    with pytest.raises(OperationError):
        firewall(runner=run).block({'id':str(uuid4()),'source_ip':'8.8.8.8',
            'expires_at':(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()})


@pytest.mark.parametrize('system',['Linux','Windows'])
def test_os_independent_expiration(system):
    calls=[]
    firewall(system,lambda args,**kw:calls.append(args) or '').block({
        'id':str(uuid4()),'source_ip':'8.8.8.8',
        'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()})
    if system=='Linux': assert 'timeout' in calls[0]
    else:
        script=calls[0][-1]
        assert script.index('Register-ScheduledTask') < script.index('New-NetFirewallRule')
        assert '-PolicyStore ActiveStore' in script
        assert "'23-3388','3390-5984','5987-65535'" in script


def test_actions_default_disabled(tmp_path):
    with pytest.raises(OperationError): perform({}, {},tmp_path,'host','https://api.test','Linux')


def test_windows_script_syntax_without_execution():
    import shutil
    import subprocess
    shell=shutil.which('powershell.exe')
    if not shell: pytest.skip('PowerShell parser available on Windows only')
    calls=[]
    firewall('Windows',lambda args,**kw:calls.append(args) or '').block({
        'id':str(uuid4()),'source_ip':'8.8.8.8',
        'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()})
    result=subprocess.run([shell,'-NoProfile','-NonInteractive','-Command',
        '$t=$null; $e=$null; [System.Management.Automation.Language.Parser]::ParseInput([Console]::In.ReadToEnd(),[ref]$t,[ref]$e) | Out-Null; if ($e) { $e | Out-String; exit 1 }'],
        input=calls[0][-1],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'Remove-NetFirewallRule -PolicyStore ActiveStore' in calls[0][-1]
