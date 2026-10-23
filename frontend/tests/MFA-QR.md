# Régression QR d’inscription MFA

`npm test` vérifie l’URI TOTP : clé identique à la saisie manuelle, paramètres CyberPME attendus, refus d’une URI externe/ambiguë, limites de taille et repli sans QR.

`mfa-qr-browser.cjs` utilise uniquement des identifiants et une clé **fictifs**. Toutes les API sont simulées dans un contexte de navigateur isolé ; aucun compte réel ni base de données n’est utilisé. Il vérifie :

- aucune image QR avant préparation de l’inscription ;
- lecture des pixels du QR affiché avec le décodeur indépendant jsQR ;
- résultat identique à l’URI serveur dans les trois thèmes et aux largeurs mobiles 390 et 320 px ;
- absence de débordement horizontal et de transmission réseau de la clé ;
- suppression du QR et de la clé manuelle après activation ;
- absence de secret dans localStorage/sessionStorage et saisie manuelle disponible si l’URI est incompatible.

Pour le test navigateur, utiliser Playwright installé dans l’environnement de développement. `CYBERPME_PLAYWRIGHT_PATH` permet de préciser le module Playwright existant ; `CYBERPME_BROWSER_PATH` permet de préciser un exécutable de navigateur compatible. Sans ces variables, le script utilise le module `playwright` et son Chromium habituel.

Dans le dossier `frontend`, démarrer un serveur local :

```sh
npm run dev -- --host 127.0.0.1 --port 5182 --strictPort
```

Puis dans un second terminal, toujours depuis `frontend` :

```sh
node tests/mfa-qr-browser.cjs
```

Les captures dans `tmp/mfa-qr-check/` contiennent uniquement la clé fictive du test. Ne jamais remplacer cette clé par celle d’un utilisateur ni exécuter ce scénario avec une session de production.
