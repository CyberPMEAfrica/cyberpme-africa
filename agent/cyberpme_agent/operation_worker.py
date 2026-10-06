"""Single independent worker; durable receipt prevents replay after a crash."""
import json
import os
import platform
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from cyberpme_agent.operations import OperationError, atomic_json, perform


@contextmanager
def exclusive_worker(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as lock:
        lock.seek(0); lock.write(b'0'); lock.flush(); lock.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try: yield
        finally:
            lock.seek(0)
            if os.name == 'nt': msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else: fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def process_action(config, server_id, agent_token, request, executor=perform):
    receipt = config.state_path.with_suffix('.operation.json')
    headers = {'Authorization':'Bearer '+agent_token}
    base = f'{config.api_url}/api/v1/servers/{server_id}/managed-actions'
    if receipt.exists():
        saved = json.loads(receipt.read_text(encoding='utf-8'))
        payload = saved.get('result') or {'status':'uncertain','message':'Agent interrompu pendant une action. Vérifier localement ; aucune répétition automatique.','snapshot':None}
        try:
            request('POST',base+'/'+saved['id']+'/complete',payload,headers)
        except Exception as exc:
            if getattr(exc, 'status', None) not in (404,409): raise
            atomic_json(receipt.with_name('operation-obsolete-'+saved['id']+'.json'), saved)
        receipt.unlink()
        return True
    action = request('GET',base+'/next',headers=headers)
    if not action: return False
    # Commit BEFORE side effects. A process kill may lose a result, never cause replay.
    saved = {'id':action['id'],'result':None}
    atomic_json(receipt,saved)
    try:
        result = executor(action,config.operations,config.state_path.parent,config.hostname+'-'+server_id,config.api_url,platform.system())
    except OperationError as exc:
        result = {'status':'failed','message':str(exc)[:1000],'snapshot':None}
    except Exception:
        result = {'status':'uncertain','message':'Erreur locale inattendue ; vérifier avant de relancer.','snapshot':None}
    saved['result']=result; atomic_json(receipt,saved)
    request('POST',base+'/'+action['id']+'/complete',result,headers)
    receipt.unlink()
    return True


def process_schedule(config, server_id, agent_token, request, executor=perform, clock=time.time):
    """Schedules are explicitly approved in the root/admin-owned local policy."""
    path = config.state_path.with_suffix('.schedule.json')
    outbox = config.state_path.with_suffix('.schedule-report.json')
    if outbox.exists():
        report = json.loads(outbox.read_text(encoding='utf-8'))
        try:
            request('POST',f'{config.api_url}/api/v1/servers/{server_id}/backup-checks',report,{'Authorization':'Bearer '+agent_token})
            outbox.unlink()
        except Exception:
            # Cloud unavailability must not suspend local scheduled backups.
            pass
    state = json.loads(path.read_text()) if path.exists() else {}
    now = clock()
    for name, profile in config.operations.get('backup_profiles',{}).items():
        if profile.get('enabled') is not True or profile.get('schedule_enabled') is not True: continue
        hours = int(profile.get('interval_hours',24))
        if not 1 <= hours <= 8760: continue
        old = state.get(name,{})
        if now-old.get('attempt',0) < hours*3600: continue
        state[name]={'attempt':now,'status':'running'}; atomic_json(path,state)
        action={'id':str(uuid4()),'kind':'backup','profile':name}
        try:
            result=executor(action,config.operations,config.state_path.parent,config.hostname+'-'+server_id,config.api_url,platform.system())
        except Exception:
            result={'status':'failed','message':'Sauvegarde planifiée non confirmée. Vérifier le dépôt et les prérequis.'}
        state[name].update(result); atomic_json(path,state)
        success=result['status']=='completed'
        report={'name':name,'kind':profile['kind'],'source':'Profil local '+name,'exists':success,
                'size_bytes':None,'last_success_at':datetime.now(timezone.utc).isoformat() if success else None,
                'max_age_hours':hours,'error':None if success else result['message']}
        # A transmission failure never repeats a completed backup.
        atomic_json(outbox, report)
        try:
            request('POST',f'{config.api_url}/api/v1/servers/{server_id}/backup-checks',report,{'Authorization':'Bearer '+agent_token})
            outbox.unlink()
        except Exception:
            pass  # Keep the latest monitoring result for the next cycle.
        return True
    return False


def start_worker(config, server_id, agent_token, request):
    def worker():
        try:
            with exclusive_worker(config.state_path.with_suffix('.operations.lock')):
                while True:
                    for cycle in (process_action, process_schedule):
                        try:
                            cycle(config,server_id,agent_token,request)
                        except Exception:
                            print('Actions locales : cycle interrompu, résultat conservé pour reprise.',flush=True)
                    time.sleep(max(10,config.interval))
        except OSError:
            print('Actions locales : un autre worker détient le verrou, ou dossier inaccessible.',flush=True)
    thread=threading.Thread(target=worker,name='cyberpme-operations',daemon=True)
    thread.start()
    return thread
