# Recette pilote — Ubuntu 24.04.2 puis Debian 12

Ne pas connecter le VPS client avant validation du pilote Ubuntu et des prérequis de publication de `SECURITY-BASELINE.md`. Ces instructions ne sont pas un compte rendu d’installation : aucun des deux serveurs n’a encore été testé dans cette intervention.

## Étape 1 — état initial Ubuntu, sans modification

Sur le serveur Ubuntu de test, relever :

```bash
cat /etc/os-release
uname -m
python3 --version
systemctl --version | head -n 1
timedatectl status
```

Ne pas transmettre de secrets. Ces informations permettent de préparer le paquet correspondant à l’architecture et de vérifier l’horloge, importante pour les certificats et la MFA.

## Étape 2 — préparer l’environnement SaaS pilote

- Organisation dédiée au test, aucune donnée du client.
- Publication coordonnée API + frontend, migration validée sur copie, sauvegarde de la base et procédure de reprise vérifiées.
- Clé de chiffrement MFA enregistrée dans le gestionnaire de secrets ; MFA de l’administrateur activée et codes de secours conservés.
- Jeton d’association unique de type `monitoring`, valable 15 minutes, généré juste avant l’association.
- Paquet agent 0.4+ provenant de la révision publiée et revue ; empreintes conservées. Ne pas installer depuis une copie non vérifiée.

## Étape 3 — installation minimale

Le compte `cyberpme` n’a ni shell interactif ni sudo. Le programme et le venv sont détenus par root et non modifiables par le service. Seul `/var/lib/cyberpme` est accessible en écriture au service ; les fichiers d’état sont privés.

Utiliser le fichier d’exemple `agent/deploy/monitoring-config.example.json` et le service `agent/deploy/cyberpme-monitor.service`. L’association se fait avec le compte de service, pas avec une clé SSH du client dans le SaaS. Le jeton d’association doit ensuite être retiré de la configuration par l’administrateur.

Les commandes d’association et d’exécution utilisent le venv installé :

```bash
sudo -u cyberpme /opt/cyberpme/venv/bin/python -m cyberpme_agent.main --config /etc/cyberpme/agent.json --register-only
sudo systemctl daemon-reload
sudo systemctl enable --now cyberpme-monitor
sudo systemctl status cyberpme-monitor --no-pager
sudo journalctl -u cyberpme-monitor --since '-5 minutes' --no-pager
sudo systemd-analyze security cyberpme-monitor
```

Ces commandes supposent que le paquet, le compte, les dossiers, la configuration et l’unité ont été préparés selon la procédure précédente. Elles ne constituent pas un installateur universel et ne doivent pas être collées sur un serveur non préparé.

## Étape 4 — preuves attendues

| Contrôle | Résultat attendu |
|---|---|
| Trois cycles de collecte | CPU, mémoire et disque remontent ; dates de collecte progressent |
| Compte du processus | `cyberpme`, pas root ; aucune capacité ajoutée |
| Service réseau | Aucun port entrant ajouté par l’agent |
| Scan et opérations | Permissions refusées côté API ; aucun appel de file côté agent monitoring |
| Coupure Internet temporaire | Erreur explicite ; reprise des nouvelles mesures après retour du réseau |
| Redémarrage complet Ubuntu | Service redémarré automatiquement et nouvelles mesures reçues |
| Révocation d’une identité pilote | Appels suivants refusés ; anciennes données conservées |
| Réassociation | Nouveau jeton, ancien jeton inutilisable, pas de doublon de serveur pour le même nom d’hôte |

Ne pas modifier le pare-feu ni provoquer de saturation sur une machine de production pour simuler une alerte. Réaliser les tests d’alerte par fixtures ou sur une VM dédiée.

## Étape 5 — passage Debian 12

Après validation d’Ubuntu, reproduire la recette sur Debian 12 de test ou sur un instantané contrôlé. Vérifier l’architecture, Python (agent compatible à partir de 3.10), systemd, les droits de fichiers, la sortie HTTPS et le redémarrage. La disponibilité d’un paquet sur Ubuntu ne prouve pas sa disponibilité sur Debian.

Pour le VPS client : accord du propriétaire, créneau validé, accès de secours OVH disponible, configuration sauvegardée, organisation cliente distincte de la démo et surveillance des premières 24 heures. N’activer ni mode `network` ni mode `managed` à cette étape.

## Retrait / incident

Révoquer l’identité dans le SaaS, puis arrêter et désactiver `cyberpme-monitor` sur le serveur. Conserver les journaux utiles et appliquer la politique convenue de conservation/suppression des données. Ne pas effacer des éléments de preuve avant analyse. Toute désinstallation définitive doit viser uniquement les fichiers CyberPME après vérification de leurs chemins et de leur propriétaire.
