# CyberPME Africa

Prototype de supervision simple destiné aux PME africaines.

## Démarrage

Ouvrez Docker Desktop, puis lancez :

```powershell
Copy-Item .env.example .env
docker compose up --build
```

- Dashboard : http://localhost:5173
- API : http://localhost:8000
- Documentation API : http://localhost:8000/docs
- Boîte e-mail de test : http://localhost:8025

Le prototype permet d'enregistrer des serveurs, recevoir leurs métriques CPU, RAM et disque, calculer leur état et les afficher dans le dashboard.

## Agent de monitoring

Le dossier `agent` contient le collecteur Python. Consultez `agent/README.md` pour l'installation et l'envoi de vraies métriques.

## Envoi e-mail réel

La configuration SMTP se fait uniquement dans le fichier `.env`. Le mode par défaut utilise Mailpit et ne livre aucun message sur Internet. Pour un fournisseur réel, renseignez `SMTP_HOST`, `SMTP_PORT`, `SMTP_USE_TLS`, `SMTP_USERNAME`, `SMTP_PASSWORD` et `ALERT_EMAIL_FROM`, puis recréez le conteneur backend.
