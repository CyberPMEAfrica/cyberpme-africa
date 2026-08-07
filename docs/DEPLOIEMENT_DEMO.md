# Déploiement public de démonstration

Cette configuration crée un environnement distinct du laboratoire local :

- un frontend public HTTPS ;
- une API FastAPI privée derrière le proxy du frontend ;
- une base PostgreSQL dédiée ;
- des secrets générés par Render.

## Prérequis

1. Publier la branche validée sur GitHub.
2. Créer un compte Render et connecter le dépôt GitHub.
3. Dans Render, choisir **New > Blueprint** et sélectionner ce dépôt.
4. Valider le fichier `render.yaml`.
5. Saisir une adresse propriétaire et un mot de passe unique d'au moins
   12 caractères lorsque Render demande les variables secrètes.

Le lien attendu est `https://cyberpme-africa-demo.onrender.com`. Si Render
attribue un autre nom, mettre à jour `FRONTEND_PUBLIC_URL` et `CORS_ORIGINS`
sur le service API, puis redéployer les deux services.

## Compte du professeur

Ne partagez pas le compte propriétaire. Connectez-vous comme propriétaire,
ouvrez **Paramètres > Équipe**, puis créez une invitation avec le rôle
**Lecture seule**. Envoyez uniquement le lien d'invitation personnel.

## Limites de la démonstration gratuite

- le premier chargement peut prendre environ une minute après une période
  d'inactivité ;
- la base PostgreSQL gratuite expire après 30 jours ;
- aucune donnée réelle du laboratoire, aucun jeton Wazuh/Suricata et aucune
  clé d'audit locale ne doivent être copiés dans cet environnement.

Pour une présentation durable, passez les services et la base sur une offre
payante avant l'expiration de la démonstration.
