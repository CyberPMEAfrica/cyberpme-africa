# Agent CyberPME

L'agent collecte le CPU, la mémoire et l'espace disque d'une machine, s'enregistre auprès de l'API et envoie une mesure toutes les 60 secondes. Il est compatible avec Python 3.10 à 3.13, notamment Python 3.12 fourni par Ubuntu Server 24.04.

## Installation Windows

Dans le SaaS, ouvrez **Scanner réseau → Connecter un PC Windows** avec un compte
propriétaire ou administrateur. Générez la commande et exécutez-la dans PowerShell
**en administrateur** sur un PC du réseau à analyser (Windows 10/11, accès Internet).
Le jeton est personnel, à usage unique et expire après 15 minutes. Si l’installation
des prérequis prend plus longtemps, générez une nouvelle commande et relancez-la.

L’installateur prépare Python 3.12 pour tous les utilisateurs et Nmap via WinGet.
Validez les fenêtres de Nmap/Npcap et leurs licences. Ces logiciels ne sont pas
redistribués dans CyberPME. Sans WinGet, installez les prérequis depuis
[Python](https://www.python.org/downloads/windows/) et
[Nmap](https://nmap.org/download), puis relancez la commande.

L’agent est installé dans `C:\ProgramData\CyberPME`, protégé pour SYSTEM et les
administrateurs. La tâche planifiée **CyberPME Agent** démarre avec Windows,
y compris sans session utilisateur ouverte. Le jeton d’installation est supprimé
après association; l’identité individuelle du PC est conservée localement.

Revenez dans Scanner réseau après environ 30 secondes, actualisez, sélectionnez
le PC, saisissez son réseau privé et lancez l’audit. Les connexions sont sortantes
en HTTPS vers votre API; aucun port entrant n’est requis. Le PC doit rester allumé.
Les tâches en attente ou interrompues expirent après 10 minutes. Les résultats
non remis à cause d’une coupure sont conservés et renvoyés au cycle suivant.

Diagnostic dans PowerShell administrateur :

```powershell
Get-ScheduledTask -TaskName 'CyberPME Agent'
Get-Content 'C:\ProgramData\CyberPME\agent.log' -Tail 50
Start-ScheduledTask -TaskName 'CyberPME Agent'
```

Pour arrêter/désinstaller l’exécution automatique :

```powershell
Stop-ScheduledTask -TaskName 'CyberPME Agent'
Unregister-ScheduledTask -TaskName 'CyberPME Agent' -Confirm
```

Le dossier et son identité sont conservés. Nmap et Python peuvent être désinstallés
séparément depuis les applications Windows s’ils ne servent plus.

## Installation manuelle (développement)

Depuis la racine du projet :

```powershell
python -m venv .venv-agent
.\.venv-agent\Scripts\python.exe -m pip install -e .\agent
```

Test avec une seule mesure :

```powershell
$env:CYBERPME_SERVER_NAME="Mon PC"
$env:CYBERPME_ENROLLMENT_KEY="votre-cle-enrolement"
$env:CYBERPME_FILE_BACKUPS="Documents|D:\Sauvegardes\Documents|24"
$env:CYBERPME_POSTGRES_BACKUPS="Base CyberPME|D:\Sauvegardes\PostgreSQL|24"
.\.venv-agent\Scripts\cyberpme-agent.exe --once
```

Exécution continue :

```powershell
.\.venv-agent\Scripts\cyberpme-agent.exe
```

Arrêter avec `Ctrl+C`. Les variables disponibles sont décrites dans `.env.example`.

La clé d'enrôlement autorise l'installation initiale. L'API remet ensuite un jeton individuel à l'agent; seul son condensat SHA-256 est conservé dans PostgreSQL.
