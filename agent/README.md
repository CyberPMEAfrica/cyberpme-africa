# Agent CyberPME

L'agent collecte le CPU, la mémoire et l'espace disque d'une machine, s'enregistre auprès de l'API et envoie une mesure toutes les 60 secondes.

## Installation Windows

Depuis la racine du projet :

```powershell
python -m venv .venv-agent
.\.venv-agent\Scripts\python.exe -m pip install -e .\agent
```

Test avec une seule mesure :

```powershell
$env:CYBERPME_SERVER_NAME="Mon PC"
$env:CYBERPME_ENROLLMENT_KEY="votre-cle-enrolement"
.\.venv-agent\Scripts\cyberpme-agent.exe --once
```

Exécution continue :

```powershell
.\.venv-agent\Scripts\cyberpme-agent.exe
```

Arrêter avec `Ctrl+C`. Les variables disponibles sont décrites dans `.env.example`.

La clé d'enrôlement autorise l'installation initiale. L'API remet ensuite un jeton individuel à l'agent; seul son condensat SHA-256 est conservé dans PostgreSQL.
