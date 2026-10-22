# Vérifications du socle — 22 octobre 2026

Ces résultats concernent le code de la branche de durcissement, pas une certification ni une validation du VPS client.

## Résultats locaux

- Suite API/backend/agent isolée : **103 tests réussis, 2 ignorés** (concurrence réservée au PostgreSQL CI). Base SQLite de test, aucun accès à une base de production.
- Relance ciblée après les derniers garde-fous : **31 réussis, 2 ignorés** ; couvre notamment le cookie `__Host-`, le refus de preview non isolée, les configurations de publication, la MFA et les restrictions d’agent.
- Frontend : compilation de production réussie ; **8 tests réussis** (calculs des indicateurs et garde-fou de compatibilité de publication).
- Marqueur de protocole API : test dédié réussi ; ne retourne ni secret ni diagnostic interne de base.
- Navigateur Edge automatisé avec une API locale de test et proxy même origine : connexion, inscription MFA obligatoire, sauvegarde des codes, reconnexion avec code de secours, rechargement, cookie HttpOnly invisible à JavaScript, absence de jeton localStorage, rejet CSRF, rafraîchissement automatique, paramètres et réinitialisation MFA authentifiée : **réussis**.
- Dashboard : **20 contrôles réussis** (trois thèmes, filtres, compteurs, plein écran, six largeurs 320–1920, taille de texte, réduction des animations, états vides).
- Compilation Python et analyse de syntaxe de l’installateur PowerShell : réussies. Cela ne remplace pas une installation et un redémarrage réels sous Windows.
- Audit npm après correction : **aucune vulnérabilité connue signalée**.
- Audit Python de l’environnement virtuel local après correction : **aucune vulnérabilité connue signalée** ; notamment cryptography 50.0.2, Pillow 13.0.0 et pytest 9.1.1. L’inventaire local n’est pas un SBOM de la production.

Un avertissement pytest de réécriture des assertions d’un module déjà importé apparaît avec le lanceur local ; il n’a pas empêché les tests. La bibliothèque de test Starlette signale aussi une dépréciation de l’intégration httpx existante.

## CI distante validée

Révision de code vérifiée : `9e5c3cbc5dc3fd19ce548bbad4e1b30812567612`.
[Exécution GitHub Actions réussie](https://github.com/CyberPMEAfrica/cyberpme-africa/actions/runs/39822296612).

- Backend : **66 réussis, 2 ignorés**, puis **23 tests PostgreSQL réussis**, dont les deux tests de consommation concurrente des codes MFA.
- Agent : **38 réussis, 1 ignoré** sur chacune des versions Python 3.10, 3.11, 3.12 et 3.13. Le test Windows spécifique reste ignoré sur le runner Linux.
- Intégrations IDS : **30 réussis**.
- Frontend : compilation et **8 tests réussis** ; audit npm sans vulnérabilité connue signalée.
- Audit Python : aucune vulnérabilité connue signalée.
- Analyse de syntaxe PowerShell 5.1 sur Windows et validation de configuration Docker Compose : réussies.

Les contrôles suivants ont été ajoutés :

- Exécution des tests de sécurité et d’actions sur PostgreSQL 17 jetable.
- Deux tests de concurrence : un code TOTP ou de secours ne doit être accepté qu’une fois entre deux transactions concurrentes.
- Audit Python avec rapport conservé en artifact CI ; audit npm bloquant.
- Tests agent Python 3.10 à 3.13 et syntaxe PowerShell 5.1 sur runner Windows.

Ces résultats ne couvrent ni une installation réelle sur Ubuntu/Debian, ni le comportement du nouveau compte de service Windows après redémarrage, ni les paramètres de production actuellement en ligne.

## Restant avant publication / client

1. Préproduction avec base et secrets propres ; migration sur copie et restauration testées.
2. Clé MFA de production et paramètres de durcissement configurés ; publication coordonnée du frontend et de l’API ; vérification des cookies et en-têtes réellement servis.
3. WAF au point d’entrée, MFA des consoles fournisseurs, journalisation externe et conservation validées.
4. Installation, métriques, coupure réseau, redémarrage et révocation sur **Ubuntu Server 24.04.2**, puis recette **Debian 12**.
5. Revue indépendante et analyse du périmètre des référentiels. Ne pas raccorder le serveur client en considérant ces seuls tests unitaires comme une autorisation de mise en production.
