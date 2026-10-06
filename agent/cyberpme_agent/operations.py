"""Opt-in local operations. All privileged subprocesses are injectable for tests."""
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
from datetime import datetime, timezone
from ipaddress import ip_address, ip_network
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID


class OperationError(RuntimeError):
    pass


class OperationUncertain(RuntimeError):
    """A timed out command may have partially applied its side effects."""
    pass


def execute(args, *, env=None, input=None, timeout=7200):
    try:
        result = subprocess.run(args, input=input, capture_output=True, text=True,
                                env=env, timeout=timeout, shell=False, check=False)
    except subprocess.TimeoutExpired as exc:
        raise OperationUncertain('Délai dépassé ; vérifier les effets locaux avant de relancer.') from exc
    except OSError as exc:
        raise OperationError('Outil indisponible ; vérifier le poste local.') from exc
    if result.returncode:
        # External stderr may contain passwords, database URLs or file contents.
        raise OperationError(f'Opération refusée par {Path(args[0]).name} (code {result.returncode}).')
    return result.stdout


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.cyberpme-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value):
        raise OperationError('Identifiant de profil invalide.')
    return value


def absolute_path(value, exists=False):
    path = Path(value)
    if not path.is_absolute() or path == Path(path.anchor):
        raise OperationError('Un chemin absolu dédié est requis, jamais une racine disque.')
    if path.is_symlink():
        raise OperationError('Un chemin de configuration ne doit pas être un lien symbolique.')
    return path.resolve(strict=exists)


class BackupEngine:
    def __init__(self, policy, state_dir, hostname, runner=execute):
        self.policy, self.state_dir, self.hostname, self.run = policy, Path(state_dir), hostname, runner

    def profile(self, name):
        identifier(name)
        profile = self.policy.get('backup_profiles', {}).get(name)
        if not profile or profile.get('enabled') is not True:
            raise OperationError('Profil absent ou désactivé dans la configuration locale.')
        if profile.get('external_destination_confirmed') is not True:
            raise OperationError('Confirmer localement une destination distincte de la machine sauvegardée.')
        repo = str(profile.get('repository', ''))
        if not repo or '\n' in repo:
            raise OperationError('Dépôt Restic manquant.')
        password = absolute_path(profile['password_file'], exists=True)
        if not password.is_file(): raise OperationError('Fichier de mot de passe Restic requis.')
        restore = absolute_path(profile['restore_root'])
        sources = [absolute_path(s, exists=True) for s in profile.get('sources', [])]
        if profile.get('kind') not in ('files', 'postgresql'):
            raise OperationError('Type de sauvegarde invalide.')
        if profile['kind'] == 'files' and not sources:
            raise OperationError('Au moins un dossier source est requis.')
        for source in sources:
            if not source.is_dir(): raise OperationError('Cette version sauvegarde des dossiers sélectionnés.')
            if source == restore or source in restore.parents or restore in source.parents:
                raise OperationError('Le dossier de restauration doit être séparé des sources.')
            if not re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', repo) or Path(repo).is_absolute():
                destination = absolute_path(repo)
                if source == destination or source in destination.parents or destination in source.parents:
                    raise OperationError('Le dépôt ne doit pas recouvrir un dossier source.')
        env = os.environ.copy()
        # Prevent ambient Restic variables from overriding the configured repository.
        env = {k:v for k,v in env.items() if not k.startswith('RESTIC_')}
        env['RESTIC_PASSWORD_FILE'] = str(password)
        # Backend credentials stay local; only explicit string variables are accepted.
        for key, value in profile.get('storage_environment', {}).items():
            if key not in ('AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','AWS_DEFAULT_REGION','AZURE_ACCOUNT_NAME','AZURE_ACCOUNT_KEY'):
                raise OperationError('Variable de stockage non autorisée.')
            env[key] = str(value)
        return profile, ['restic','--repo',repo], env, restore, sources, password

    def backup(self, name, action_id):
        profile, cmd, env, _, sources, password = self.profile(name)
        keep = int(profile.get('keep_last', 7))
        if profile.get('retention_enabled') is True and not 2 <= keep <= 365:
            raise OperationError('Conservation autorisée entre 2 et 365 versions.')
        tag = 'cyberpme-profile-'+name
        operation_tag = 'cyberpme-job-'+str(action_id)
        # Check existence of the encrypted repository; never silently initialize one.
        self.run(cmd+['cat','config'], env=env)
        arguments = ['backup','--json','--host',self.hostname,'--tag',tag,'--tag',operation_tag]
        if profile['kind'] == 'postgresql':
            service = identifier(profile.get('postgres_service', ''))
            service_file = absolute_path(profile['pg_service_file'], exists=True)
            pass_file = absolute_path(profile['pg_pass_file'], exists=True)
            env['PGSERVICEFILE']=str(service_file); env['PGPASSFILE']=str(pass_file)
            # stdin-from-command propagates pg_dump failure to Restic: no successful partial dump.
            arguments += ['--stdin-filename','database.dump','--stdin-from-command','--',
                          'pg_dump','--no-password','--format=custom','--dbname=service='+service]
        else:
            for excluded in (self.state_dir.resolve(), password):
                arguments += ['--exclude', str(excluded)]
            arguments += ['--', *map(str,sources)]
        output = self.run(cmd+arguments, env=env)
        summaries = [json.loads(line) for line in output.splitlines() if line.strip().startswith('{')]
        snapshot = next((r.get('snapshot_id') for r in reversed(summaries) if r.get('message_type')=='summary'), None)
        if not snapshot or not re.fullmatch('[a-f0-9]{64}',snapshot):
            raise OperationError('Sauvegarde non confirmée par Restic.')
        # Pruning requires a second, explicit local opt-in. It never runs during restore.
        message = 'Sauvegarde chiffrée créée.'
        if profile.get('retention_enabled') is True:
            try:
                self.run(cmd+['forget','--host',self.hostname,'--tag',tag,'--group-by','host',
                              '--keep-last',str(keep),'--prune'], env=env)
            except OperationError:
                message += ' Conservation non appliquée ; vérifier le dépôt.'
        return {'status':'completed','message':message,'snapshot':snapshot}

    def restore_test(self, name, snapshot, action_id):
        if not re.fullmatch('[a-f0-9]{64}',str(snapshot)):
            raise OperationError('Identifiant complet du snapshot requis.')
        profile, cmd, env, root, _, _ = self.profile(name)
        listing = json.loads(self.run(cmd+['snapshots','--json','--host',self.hostname,'--tag','cyberpme-profile-'+name],env=env))
        if not any(x.get('id') == snapshot for x in listing):
            raise OperationError('Snapshot étranger au profil ou à cette machine.')
        root.mkdir(parents=True, exist_ok=True)
        # Unique empty directory: production files and databases are never overwritten.
        target = Path(tempfile.mkdtemp(prefix='test-'+str(UUID(str(action_id)))+'-', dir=root))
        self.run(cmd+['restore',snapshot,'--target',str(target),'--verify'], env=env)
        if profile['kind'] == 'postgresql':
            dumps = list(target.rglob('database.dump'))
            if len(dumps)!=1: raise OperationError('Archive PostgreSQL absente après restauration.')
            self.run(['pg_restore','--list',str(dumps[0])])
        return {'status':'completed','message':'Copie restaurée et vérifiée dans un nouveau dossier local. PostgreSQL : aucune base active modifiée.','snapshot':snapshot}


class FirewallEngine:
    """Temporary inbound TCP restrictions, with independent OS expiry."""
    def __init__(self, policy, api_url, system, runner=execute, resolver=socket.getaddrinfo):
        self.policy, self.api_url, self.system, self.run, self.resolve = policy, api_url, system, runner, resolver

    def validate(self, address):
        fw = self.policy.get('firewall', {})
        if fw.get('enabled') is not True or not fw.get('protected_networks'):
            raise OperationError('Pare-feu désactivé ou exclusions administrateur non configurées localement.')
        ip = ip_address(address)
        if ip.version != 4 or not ip.is_global or ip.is_multicast:
            raise OperationError('Seules les IPv4 publiques individuelles sont acceptées.')
        if any(ip in ip_network(n) for n in fw['protected_networks']):
            raise OperationError('Adresse protégée par la politique locale.')
        hostname = urlparse(self.api_url).hostname
        if not hostname: raise OperationError('URL API invalide.')
        try:
            api_ips = {item[4][0] for item in self.resolve(hostname,443)}
        except OSError as exc:
            raise OperationError('Résolution API impossible ; blocage refusé par précaution.') from exc
        if str(ip) in api_ips: raise OperationError('Adresse utilisée par CyberPME ; blocage refusé.')
        return str(ip)

    def block(self, action):
        address = self.validate(action['source_ip'])
        expires = datetime.fromisoformat(action['expires_at'].replace('Z','+00:00'))
        seconds = int((expires-datetime.now(timezone.utc)).total_seconds())
        if not 1 <= seconds <= 3600: raise OperationError('Autorisation de blocage expirée ou durée invalide.')
        name = 'cyberpme-'+UUID(str(action['id'])).hex
        if self.system == 'Linux':
            # Dedicated table/set must be provisioned explicitly by the local admin.
            # Kernel timeout remains effective when the SaaS or agent goes offline.
            self.run(['nft','add','element','inet','cyberpme_guard','blocked_v4',
                      '{',address,'timeout',f'{seconds}s','}'],timeout=30)
        elif self.system == 'Windows':
            epoch = int(expires.timestamp())
            # Cleanup task is registered BEFORE the rule. ActiveStore is not persistent
            # over reboot; the task also expires a rule if the agent crashes.
            script = rf"""$ErrorActionPreference='Stop'
$name='{name}'
$deadline=[DateTimeOffset]::FromUnixTimeSeconds({epoch}).LocalDateTime
if ($deadline -le (Get-Date)) {{ throw 'Autorisation expiree' }}
$cleanup='Remove-NetFirewallRule -PolicyStore ActiveStore -Name {name} -ErrorAction Stop; Unregister-ScheduledTask -TaskName {name} -Confirm:$false -ErrorAction SilentlyContinue'
$action=New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -Command "'+$cleanup+'"')
$trigger=New-ScheduledTaskTrigger -Once -At $deadline
$principal=New-ScheduledTaskPrincipal -UserId SYSTEM -LogonType ServiceAccount -RunLevel Highest
$settings=New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
if ($deadline -le (Get-Date)) {{ throw 'Autorisation expiree' }}
New-NetFirewallRule -Name $name -DisplayName $name -Direction Inbound -Action Block -Protocol TCP -RemoteAddress '{address}' -LocalPort '1-21','23-3388','3390-5984','5987-65535' -PolicyStore ActiveStore | Out-Null
if ($deadline -le (Get-Date)) {{ Remove-NetFirewallRule -PolicyStore ActiveStore -Name $name -ErrorAction SilentlyContinue; throw 'Autorisation expiree' }}
"""
            self.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],timeout=45)
        else: raise OperationError('Pare-feu non pris en charge sur ce système.')
        return {'status':'completed','message':'Blocage TCP entrant temporaire appliqué ; ports administratifs exclus.','snapshot':None}

    def unblock(self, action):
        # Never remove a newer Linux rule for the same IP after this grant expired.
        expiry = datetime.fromisoformat(action['expires_at'].replace('Z','+00:00'))
        if expiry <= datetime.now(timezone.utc):
            return {'status':'completed','message':'Autorisation expirée ; aucune règle plus récente modifiée.','snapshot':None}
        address = str(ip_address(action['source_ip']))
        name = 'cyberpme-'+UUID(str(action['parent_id'])).hex
        if self.system == 'Linux':
            # A missing element is already unblocked, but distinguish other failures.
            listing = json.loads(self.run(['nft','-j','list','set','inet','cyberpme_guard','blocked_v4'],timeout=30))
            def contains_exact(value):
                if isinstance(value, dict): return any(contains_exact(v) for v in value.values())
                if isinstance(value, list): return any(contains_exact(v) for v in value)
                return value == address
            if contains_exact(listing):
                self.run(['nft','delete','element','inet','cyberpme_guard','blocked_v4','{',address,'}'],timeout=30)
        elif self.system == 'Windows':
            script=f"$ErrorActionPreference='Stop'; Get-NetFirewallRule -PolicyStore ActiveStore -Name '{name}' -ErrorAction SilentlyContinue | Remove-NetFirewallRule; Get-ScheduledTask -TaskName '{name}' -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false"
            self.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],timeout=30)
        else: raise OperationError('Pare-feu non pris en charge.')
        return {'status':'completed','message':'Annulation locale traitée.','snapshot':None}


def perform(action, policy, state_dir, hostname, api_url, system, runner=execute):
    if policy.get('enabled') is not True: raise OperationError('Actions actives désactivées sur cet agent.')
    kind=action['kind']
    if kind in ('backup','restore_test'):
        engine=BackupEngine(policy,state_dir,hostname,runner)
        if kind=='backup': return engine.backup(action['profile'],action['id'])
        return engine.restore_test(action['profile'],action['snapshot'],action['id'])
    engine=FirewallEngine(policy,api_url,system,runner)
    if kind=='firewall_block': return engine.block(action)
    if kind=='firewall_unblock': return engine.unblock(action)
    raise OperationError('Action non autorisée.')
