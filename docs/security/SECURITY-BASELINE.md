# CyberPME — socle de sécurité et pilote VPS

Établi le 22 octobre 2026. Périmètre : code du SaaS, API et agent ; hébergeurs, VPS client et procédures internes à valider séparément.

## Statut et limites

Ce document décrit des contrôles techniques et une démarche d’alignement. Il ne constitue ni une certification ISO, ni une attestation PCI DSS, ni une garantie d’absence de vulnérabilité. Ne présenter aucune de ces trois affirmations au séminaire.

Le développement doit être validé en préproduction avant bascule. Un audit indépendant, le périmètre du client et les preuves d’exploitation restent nécessaires. Aucun serveur client n’a été contacté pendant ces tests.

## Les cinq priorités implémentées dans le code

| Priorité | Contrôle | Preuve à conserver |
|---|---|---|
| Monitoring seul | Mode local `monitoring` par défaut ; aucune récupération de tâche réseau ou opération administrée. Permission aussi imposée par l’API, liée au jeton d’association. | Tests agent sans appels de tâches et API refusant les deux files avec 403. |
| Authentification | Mot de passe haché PBKDF2 existant ; MFA TOTP ; secrets MFA chiffrés Fernet ; codes de secours hachés et à usage unique ; anti-rejeu TOTP ; compteurs SQL limitant les tentatives. | Tests inscription MFA, rejet du rejeu, fermeture des sessions, limitation 429. |
| Identités agents | Association unique 15 minutes ; clé partagée désactivée par défaut ; identité individuelle hachée, expiration maximale 90 jours, révocation et rotation. | Tests révocation, expiration, rotation et séparation des organisations. |
| Navigateur et transport | Cookie HttpOnly/Secure/SameSite=Lax ; plus de jeton de session dans localStorage ; API même origine par proxy ; contrôle CSRF ; CSP et en-têtes ; API agent HTTPS et refus des redirections ; DNS SSL épinglé sur IP publique validée. | Tests cookies, origines, connexion SSL et transport ; recette navigateur via proxy. |
| Dépendances | Versions frontend exactes et verrou npm ; versions Python corrigées ; contrôles d’audit en intégration continue. | Rapports npm/pip-audit datés et dépendances exactes du déploiement. |

La MFA TOTP résiste au vol d’un mot de passe seul, mais n’est **pas résistante au phishing** comme une clé FIDO2/WebAuthn. Les secrets sont chiffrés en base, pas dans la mémoire du processus. La protection dépend de la garde séparée de la clé MFA.

La limitation applicative porte sur le compte (8 tentatives dans une fenêtre de 15 minutes), pour éviter de prendre l’adresse d’un proxy Vercel commun pour celle de tous les clients. Configurer et vérifier en plus des règles WAF par IP au point d’entrée de confiance pour les tentatives distribuées, le credential stuffing et les volumes abusifs. Ne pas faire confiance à un en-tête transmis arbitrairement par un client.

L’installateur Windows de monitoring utilise LOCAL SERVICE, sans Nmap ; les modes réseau et administré restent privilégiés et exigent une activation explicite. Cette configuration doit encore être testée en installation réelle Windows. Les commandes de publication épinglent une révision Git complète, pas la branche mutable `main` ; conserver aussi les empreintes et la revue de la publication.

Les identités des anciens agents sont migrées avec une validité bornée à 90 jours. Un ancien scanner conserve son droit de scan pour éviter une coupure imprévue ; cette transition ne le transforme pas en agent de monitoring. Pour un VPS client : nouvelle organisation et nouvelle association explicite `monitoring`, agent 0.4 ou ultérieur.

La révocation coupe les prochains appels API. Elle n’interrompt pas rétroactivement un processus déjà exécuté ni une sauvegarde locale planifiée précédemment : arrêter le service et désactiver les politiques locales si un retrait complet est nécessaire.

## Configuration de production — obligatoire avant bascule

L’API bloque son build Vercel de production si ces prérequis ne sont pas remplis. Les previews ne migrent pas la base de production.

1. Créer et conserver une clé Fernet dans un gestionnaire de secrets : `MFA_ENCRYPTION_KEY`. Ne pas la mettre dans Git, les captures, les logs, une variable `VITE_*` ni dans ce dossier documentaire.
2. `MFA_REQUIRED=true`, `SECURE_COOKIES=true`, `ALLOW_LEGACY_ENROLLMENT=false`.
3. `BOOTSTRAP_ADMIN_FORCE_SYNC=false`. Retirer `BOOTSTRAP_ADMIN_RESET_PASSWORD` et `BOOTSTRAP_RECOVERY_KEY`. Ne pas utiliser de récupération permanente publique en production.
4. `FRONTEND_PUBLIC_URL` et `CORS_ORIGINS` : URL HTTPS exacte du frontend, sans joker. Pour la démo actuelle : `https://cyberpme-demo.vercel.app`.
5. Vérifier `frontend/vercel.json` : `/api/*` doit pointer vers **l’API de cet environnement**. Le domaine de démo est une configuration explicite, pas une valeur à réutiliser pour tous les clients.
6. `SESSION_HOURS` entre 1 et 8 ; `AGENT_TOKEN_DAYS` entre 1 et 90. Prévoir alertes et procédure de renouvellement avant expiration. Pas de renouvellement automatique silencieux d’une identité révoquée.
7. MFA activée aussi sur GitHub, Vercel, OVH et la base managée ; droits minimaux ; revue des collaborateurs ; sauvegarde de la base et restauration testée.
8. Previews : base et secrets distincts. Le démarrage d’une preview est refusé par défaut ; ne définir `PREVIEW_DATABASE_ISOLATED=true` qu’après vérification de la base dédiée. Adapter aussi la destination du proxy frontend au backend de préproduction, jamais à la production cliente.

Le cookie de production utilise le préfixe `__Host-`, sans attribut Domain. La publication d’une commande Windows nécessite la révision Git complète fournie par Vercel (`VERCEL_GIT_COMMIT_SHA`) ou explicitement au build (`CYBERPME_AGENT_REVISION`).

Génération locale possible, dans un terminal de confiance :

```text
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

La valeur générée est un secret : la transférer directement dans le gestionnaire de secrets, jamais dans le chat. Sauvegarder cette clé séparément de la base chiffrée. La perdre rend les secrets TOTP existants inutilisables ; ne pas la remplacer sans migration chiffrée et procédure de récupération vérifiée.

L’environnement local HTTP doit utiliser `SECURE_COOKIES=false`, uniquement en local. Le frontend Vite propose un proxy `/api` vers `127.0.0.1:8000`. Ne pas exposer ce serveur de développement sur Internet.

## Démarrage contrôlé sur VPS Linux

Ordre de recette retenu : **serveur de test Ubuntu Server 24.04.2**, puis **VPS client Debian 12**. La réussite sur Ubuntu ne remplace pas la validation de Debian et de ses règles d’accès.

Ne pas utiliser la machine cliente comme premier environnement d’essai. Reproduire d’abord son OS et sa version sur un VPS de test. Obtenir l’accord du propriétaire et les plages horaires ; sauvegarder la configuration et vérifier le moyen de reprise OVH.

Le service fourni dans `agent/deploy/cyberpme-monitor.service` est destiné au monitoring seul : utilisateur système `cyberpme`, aucune capacité Linux, aucun port d’écoute, système de fichiers en lecture seule sauf son état local, connexions HTTPS sortantes vers l’API. CPU, mémoire, occupation disque, nom d’hôte et adresse locale sont les données attendues. Aucune clé SSH root du client n’est envoyée au SaaS.

Procédure opérateur (à adapter à la distribution, ne pas exécuter sans revue) :

1. Préparer une version agent 0.4+ revue, son empreinte SHA-256 et des dépendances verrouillées. Vérifier les empreintes à destination. Ne pas exécuter une archive `main` mutable en root sur le VPS client.
2. Créer un compte système sans shell `cyberpme`, `/opt/cyberpme/venv` administré par root et `/var/lib/cyberpme` détenu par `cyberpme`, mode 0700.
3. Installer le paquet dans ce venv. Créer `/etc/cyberpme/agent.json`, root:cyberpme 0640, à partir de l’exemple de monitoring ; nom d’hôte unique ; API HTTPS propre à l’environnement.
4. Générer dans l’organisation cliente un jeton d’association **monitoring**. Associer sous le compte `cyberpme` avec `python -m cyberpme_agent.main --config /etc/cyberpme/agent.json --register-only`. Retirer ensuite le jeton à usage unique du fichier de configuration (l’identité persistante est dans le fichier d’état protégé).
5. Installer le fichier service fourni, faire `systemctl daemon-reload`, puis `systemctl enable --now cyberpme-monitor`. Examiner `systemctl status`, `journalctl -u cyberpme-monitor` et `systemd-analyze security cyberpme-monitor`.
6. Vérifier trois remontées de métriques, un redémarrage complet, puis trois nouvelles remontées. Ne pas confondre un ancien résultat de scan avec une preuve de présence actuelle.
7. Tester la révocation sur l’agent **pilote**, vérifier le refus des nouvelles mesures ; réassocier. Tester aussi le rejet d’une tâche réseau et d’une tâche administrée.

Rotation volontaire : arrêter le service, lancer l’agent sous son compte avec `--rotate-token`, puis redémarrer le service. Le jeton précédent est invalidé immédiatement. Si la réponse de rotation est perdue ou si l’identité a expiré : nouvelle association par un administrateur, pas de contournement par clé commune.

## Recette et décision avant client

- [ ] Base sauvegardée, restauration isolée réussie et horodatée.
- [ ] Migration 0006 → 0007 sur copie de préproduction, volumes de données contrôlés.
- [ ] Connexion via domaine frontend et proxy, cookie Secure/HttpOnly, aucun jeton de session dans localStorage.
- [ ] Inscription MFA, codes sauvegardés hors du navigateur, reconnexion, rejet d’un code rejoué.
- [ ] Droits propriétaire/admin/analyste/lecteur ; aucune lecture inter-organisations.
- [ ] Vérification des en-têtes réellement servis, pas seulement des fichiers du dépôt.
- [ ] Agent Linux non root en monitoring, aucune écoute entrante, aucune tâche distante.
- [ ] Test de redémarrage réel, coupure réseau et reprise sans duplication.
- [ ] Révocation et renouvellement avant expiration testés.
- [ ] Accord et périmètre du client, confidentialité, durée de conservation et suppression validés.
- [ ] Revue indépendante des changements et test d’intrusion cadré terminés.

Un audit de dépendances sans avis connu n’est pas une preuve d’absence de vulnérabilité. La recette Linux réelle et les preuves des hébergeurs ne peuvent pas être remplacées par les tests unitaires Windows/SQLite.
