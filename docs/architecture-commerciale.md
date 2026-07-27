# Architecture commerciale de CyberPME Africa

## Principe

L'infrastructure du poste de développement (Windows, Ubuntu, Kali, Wazuh,
Docker et réseau `192.168.202.0/24`) est un laboratoire. Aucune adresse, aucun
chemin et aucun outil de ce laboratoire ne doit être requis par le produit.

## Isolation multi-tenant

Chaque donnée métier appartient à une organisation (`tenant`) :

- utilisateurs et rôles ;
- serveurs et jetons d'agents ;
- métriques, alertes et événements IDS ;
- audits réseau, contrôles TLS et rapports ;
- politiques et contrôles de sauvegarde ;
- connecteurs Wazuh, Suricata ou fournisseurs futurs.

Une requête authentifiée ne peut lire ou modifier que les données de son
organisation. Cette règle est appliquée dans l'API et testée automatiquement.

## Identités et secrets

- Les utilisateurs se connectent avec un mot de passe haché et reçoivent une
  session courte.
- Les rôles minimaux sont `owner`, `admin`, `analyst` et `viewer`.
- Chaque organisation possède ses propres clés d'enrôlement d'agents.
- Chaque agent possède ensuite un jeton individuel révocable.
- Les secrets de connecteurs sont chiffrés et ne sont jamais envoyés au
  navigateur.
- Les clés globales de laboratoire sont supprimées avant la production.

## Connecteurs

Le SaaS reçoit un format d'événement normalisé. Des adaptateurs convertissent
les formats externes sans modifier le cœur :

```text
Wazuh --------\
Suricata ------> Adaptateur -> Événement CyberPME -> API -> Organisation
Autre SIEM ----/
```

Un connecteur est configuré par organisation. `Wazuh` et `Suricata` ne sont
donc jamais des dépendances obligatoires.

## Déploiement client

L'agent fonctionne sous Windows et Linux et utilise uniquement :

- l'URL publique de l'API ;
- une clé d'enrôlement temporaire ;
- des politiques reçues depuis le SaaS ;
- une file locale en cas de coupure Internet.

Les chemins de sauvegarde, intervalles et capteurs sont configurables par
machine. Les valeurs du laboratoire ne servent que dans la documentation de
test.

## IDS puis IPS

1. Collecte et normalisation des événements.
2. Corrélation et recommandations.
3. Simulation d'une règle de blocage.
4. Approbation par un utilisateur autorisé.
5. Application par un connecteur local avec durée et retour arrière.

Le blocage automatique est désactivé par défaut. Toute action est journalisée.

## Étapes avant production

1. Organisations, utilisateurs, rôles et isolation des requêtes.
2. Migrations de base versionnées.
3. Connecteurs et secrets chiffrés.
4. Journal d'audit immuable.
5. HTTPS, domaine, rotation des secrets et sauvegarde hors machine.
6. Tests de charge, restauration, reprise après incident et sécurité.
7. Abonnements, quotas, facturation et support.
