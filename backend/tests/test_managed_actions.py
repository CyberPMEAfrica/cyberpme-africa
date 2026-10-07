from datetime import timedelta
from uuid import UUID

from test_api import clean_database, client, user_headers
from app.database import SessionLocal
from app.models import User, Organization, SecurityEvent, utc_now
from app.auth import hash_password
from app.managed_actions import ManagedAction
from sqlalchemy import select


def register(client, name='action-host'):
    result=client.post('/api/v1/agents/register',json={'name':name,'hostname':name},
        headers={'X-Enrollment-Key':'ci-enrollment-secret'})
    assert result.status_code==200, result.text
    data=result.json()
    return data['server_id'], {'Authorization':'Bearer '+data['agent_token']}


def propose(client, headers, server):
    result=client.post('/api/v1/managed-actions',headers=headers,json={
        'server_id':server,'kind':'backup','profile':'documents','reason':'Test sauvegarde autorisee'})
    assert result.status_code==201, result.text
    return result.json()['id']


def test_approval_claim_and_idempotent_completion(client,user_headers):
    server,auth=register(client)
    action=propose(client,user_headers,server)
    base=f'/api/v1/servers/{server}/managed-actions'
    assert client.get(base+'/next',headers=auth).json() is None
    assert client.post(f'/api/v1/managed-actions/{action}/approve',headers=user_headers).status_code==200
    assert client.get(base+'/next',headers=auth).json()['status']=='running'
    assert client.get(base+'/next',headers=auth).json() is None
    result={'status':'completed','message':'Sauvegarde OK','snapshot':'a'*64}
    assert client.post(base+f'/{action}/complete',headers=auth,json=result).status_code==200
    assert client.post(base+f'/{action}/complete',headers=auth,json=result).status_code==200
    assert client.post(base+f'/{action}/complete',headers=auth,json=result|{'message':'Different'}).status_code==409


def test_other_agent_cannot_complete(client,user_headers):
    server,auth=register(client)
    other,otherauth=register(client,'other')
    action=propose(client,user_headers,server)
    assert client.get(f'/api/v1/servers/{server}/managed-actions/next',headers=otherauth).status_code==401
    assert client.post(f'/api/v1/servers/{other}/managed-actions/{action}/complete',headers=otherauth,
        json={'status':'completed','message':'forbidden'}).status_code==404


def test_expired_approval_not_dispatched(client,user_headers):
    server,auth=register(client)
    action=propose(client,user_headers,server)
    client.post(f'/api/v1/managed-actions/{action}/approve',headers=user_headers)
    with SessionLocal() as db:
        db.get(ManagedAction,UUID(action)).expires_at=utc_now()-timedelta(seconds=1)
        db.commit()
    assert client.get(f'/api/v1/servers/{server}/managed-actions/next',headers=auth).json() is None
    assert client.get('/api/v1/managed-actions',headers=user_headers).json()[0]['status']=='cancelled'


def test_analyst_cannot_approve(client,user_headers):
    server,_=register(client)
    action=propose(client,user_headers,server)
    with SessionLocal() as db:
        db.scalar(select(User).where(User.email=='owner@example.test')).role='analyst'
        db.commit()
    assert client.post(f'/api/v1/managed-actions/{action}/approve',headers=user_headers).status_code==403


def test_arbitrary_commands_and_paths_not_accepted(client,user_headers):
    server,_=register(client)
    payload={'server_id':server,'kind':'backup','profile':'documents','reason':'Test refuse avec commande'}
    assert client.post('/api/v1/managed-actions',headers=user_headers,json=payload|{'command':'whoami'}).status_code==422
    assert client.post('/api/v1/managed-actions',headers=user_headers,json=payload|{'profile':'../../secrets'}).status_code==422


def test_actions_are_tenant_scoped(client,user_headers):
    server,_=register(client)
    action=propose(client,user_headers,server)
    with SessionLocal() as db:
        org=Organization(name='Autre entreprise',slug='actions-other')
        db.add(org); db.flush()
        db.add(User(organization_id=org.id,email='other@actions.test',role='owner',
            password_hash=hash_password('Test-password-other-2026')))
        db.commit()
    token=client.post('/api/v1/auth/login',json={'organization_slug':'actions-other',
        'email':'other@actions.test','password':'Test-password-other-2026'}).json()['access_token']
    other={'Authorization':'Bearer '+token}
    assert client.get('/api/v1/managed-actions',headers=other).json()==[]
    assert client.post(f'/api/v1/managed-actions/{action}/approve',headers=other).status_code==404
    assert client.post('/api/v1/managed-actions',headers=other,json={
        'server_id':server,'kind':'backup','profile':'documents','reason':'Action autre organisation'}).status_code==404


def test_firewall_requires_event_approval_and_supports_undo(client,user_headers):
    server,auth=register(client)
    with SessionLocal() as db:
        event=SecurityEvent(server_id=UUID(server),event_key='unit-test',source='test',category='network',
            severity='high',title='Test IDS',description='Evenement de test',source_ip='8.8.8.8',
            recommendation='Examiner',occurred_at=utc_now())
        db.add(event); db.commit(); event_id=str(event.id)
    payload={'server_id':server,'kind':'firewall_block','event_id':event_id,
        'duration_minutes':10,'reason':'Blocage test explicitement autorise'}
    action=client.post('/api/v1/managed-actions',headers=user_headers,json=payload)
    assert action.status_code==201,action.text
    action_id=action.json()['id']
    approved=client.post(f'/api/v1/managed-actions/{action_id}/approve',headers=user_headers)
    assert approved.status_code==200
    duplicate=client.post('/api/v1/managed-actions',headers=user_headers,json=payload).json()['id']
    assert client.post(f'/api/v1/managed-actions/{duplicate}/approve',headers=user_headers).status_code==409
    base=f'/api/v1/servers/{server}/managed-actions'
    assert client.get(base+'/next',headers=auth).json()['source_ip']=='8.8.8.8'
    assert client.post(base+f'/{action_id}/complete',headers=auth,
        json={'status':'completed','message':'Test simule'}).status_code==200
    undo=client.post(f'/api/v1/managed-actions/{action_id}/cancel',headers=user_headers)
    assert undo.status_code==200,undo.text
    assert undo.json()['kind']=='firewall_unblock'
    assert undo.json()['expires_at']==approved.json()['expires_at']
    assert client.get(base+'/next',headers=auth).json()['parent_id']==action_id
