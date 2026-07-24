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

## Audit réseau autorisé

Le dashboard intègre un scanner réseau pour les infrastructures administrées par la PME :

- cible limitée aux réseaux IPv4 privés ;
- taille maximale `/24` (256 adresses) ;
- détection des équipements actifs et des 100 ports TCP les plus courants ;
- identification légère des services et versions avec Nmap ;
- recommandations de sécurité ;
- historique PostgreSQL et rapport PDF téléchargeable.

Ajoutez une clé différente de la clé d'enrôlement dans `.env` :

```env
NETWORK_SCAN_KEY=une-longue-cle-secrete-differente
```

Le lancement d'un audit exige cette clé et une confirmation explicite d'autorisation dans le dashboard. N'analysez jamais un réseau sans l'accord de son propriétaire.

## Agent de monitoring

Le dossier `agent` contient le collecteur Python. Consultez `agent/README.md` pour l'installation et l'envoi de vraies métriques.

Chaque agent doit fournir `CYBERPME_ENROLLMENT_KEY` lors de son enregistrement. L'API délivre ensuite un jeton individuel exigé pour chaque envoi de métriques; le jeton brut n'est jamais stocké dans la base.

## Envoi e-mail réel

La configuration SMTP se fait uniquement dans le fichier `.env`. Le mode par défaut utilise Mailpit et ne livre aucun message sur Internet. Pour un fournisseur réel, renseignez `SMTP_HOST`, `SMTP_PORT`, `SMTP_USE_TLS`, `SMTP_USERNAME`, `SMTP_PASSWORD` et `ALERT_EMAIL_FROM`, puis recréez le conteneur backend.
