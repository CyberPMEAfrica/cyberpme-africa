import json
from dataclasses import replace
from uuid import uuid4
import pytest
from cyberpme_agent.main import Config
from cyberpme_agent.operations import atomic_json
from cyberpme_agent.operation_worker import process_action, process_schedule


def config(tmp_path):
    return Config(api_url='https://api.test',name='test',hostname='test',interval=10,
        enrollment_key='',backup_targets=(),state_path=tmp_path/'state.json',
        operations={'enabled':True})


def test_interrupted_receipt_is_not_replayed(tmp_path):
    cfg=config(tmp_path)
    atomic_json(cfg.state_path.with_suffix('.operation.json'),{'id':str(uuid4()),'result':None})
    sent=[]
    def request(method,url,payload=None,headers=None): sent.append((method,payload))
    def execute(*args): pytest.fail('interrupted operation must not repeat')
    assert process_action(cfg,'server','token',request,execute)
    assert sent[0][1]['status']=='uncertain'
    assert not cfg.state_path.with_suffix('.operation.json').exists()


def test_network_failure_retries_result_only(tmp_path):
    cfg=config(tmp_path); executed=[]; sent=[]
    action={'id':str(uuid4()),'kind':'backup','profile':'files'}
    def execute(*args): executed.append(1); return {'status':'completed','message':'ok','snapshot':'a'*64}
    def offline(method,url,payload=None,headers=None):
        if method=='GET': return action
        raise OSError('offline')
    with pytest.raises(OSError): process_action(cfg,'server','token',offline,execute)
    def online(method,url,payload=None,headers=None): sent.append(payload)
    process_action(cfg,'server','token',online,execute)
    assert len(executed)==1
    assert sent[0]['status']=='completed'


def test_schedule_retries_report_not_backup(tmp_path):
    cfg=replace(config(tmp_path),operations={'enabled':True,'backup_profiles':{
        'files':{'enabled':True,'schedule_enabled':True,'kind':'files','interval_hours':24}}})
    executed=[]; sent=[]
    def execute(*args): executed.append(1); return {'status':'completed','message':'ok'}
    def offline(*args,**kw): raise OSError('offline')
    assert process_schedule(cfg,'server','token',offline,execute,lambda:1000000)
    def online(method,url,payload=None,headers=None): sent.append(payload)
    process_schedule(cfg,'server','token',online,execute,lambda:1000001)
    assert len(executed)==1 and sent[0]['exists'] is True
    assert process_schedule(cfg,'server','token',online,execute,lambda:1000002) is False


def test_schedule_disabled_by_default(tmp_path):
    cfg=config(tmp_path)
    def no(*args,**kw): pytest.fail('no operation configured')
    assert process_schedule(cfg,'server','token',no,no) is False


def test_schedule_continues_during_cloud_outage(tmp_path):
    cfg=replace(config(tmp_path),operations={'enabled':True,'backup_profiles':{
        'files':{'enabled':True,'schedule_enabled':True,'kind':'files','interval_hours':1}}})
    executed=[]
    def execute(*args): executed.append(1); return {'status':'completed','message':'ok'}
    def offline(*args,**kw): raise OSError('offline')
    process_schedule(cfg,'server','token',offline,execute,lambda:1000000)
    process_schedule(cfg,'server','token',offline,execute,lambda:1003601)
    assert len(executed)==2
