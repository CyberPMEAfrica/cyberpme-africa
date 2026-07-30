# Adaptateur Suricata CyberPME

Cet adaptateur lit progressivement le fichier EVE JSON produit par Suricata,
ignore les événements non liés à une alerte et transmet les détections
normalisées au connecteur CyberPME de l'organisation.

Suricata reste optionnel et s'exécute sur un capteur réseau de la PME. Le SaaS
CyberPME ne reçoit que les événements normalisés.

## Essai sans Suricata ni réseau

Le mode `--dry-run` transforme un petit fichier EVE sans appeler l'API et sans
écrire de fichier d'état :

```bash
python3 integrations/suricata/cyberpme-suricata \
  --eve-file integrations/tests/fixtures/suricata-eve.jsonl \
  --dry-run
```

Seules les lignes dont `event_type` vaut `alert` sont affichées. Les événements
DNS, HTTP, TLS, flow et stats sont ignorés pour limiter la charge et le volume.

## Configuration du connecteur

Dans **IDS / IPS**, créer un connecteur de type **Suricata**, l'associer au
capteur concerné et conserver immédiatement l'URL d'ingestion et le jeton.

Sur le capteur Linux, fournir les paramètres par variables d'environnement afin
que le jeton ne soit pas placé dans l'historique du shell :

```bash
export CYBERPME_SURICATA_ENDPOINT="https://api.example.com/api/v1/ids-connectors/CONNECTOR_ID/events"
export CYBERPME_SURICATA_TOKEN="CONNECTOR_TOKEN"
export CYBERPME_SURICATA_EVE_FILE="/var/log/suricata/eve.json"
export CYBERPME_SURICATA_STATE_FILE="/var/lib/cyberpme-suricata/state.json"

python3 /usr/local/bin/cyberpme-suricata
```

Le fichier d'état conserve l'identité du fichier EVE et le dernier octet traité.
Un second lancement ne renvoie donc pas les anciennes alertes. En cas de
rotation de `eve.json`, la lecture reprend automatiquement au début du nouveau
fichier. L'API CyberPME reste également idempotente grâce à la clé stable de
chaque événement.

En cas d'échec réseau, l'événement fautif n'est pas validé dans le fichier
d'état et sera retenté au prochain lancement. La file locale persistante et le
service automatique seront ajoutés dans l'étape suivante de l'intégration.

## Ressources et stockage

L'adaptateur ne capture aucun paquet et n'exécute aucune règle IDS. Il lit le
fichier ligne par ligne et ne conserve pas son contenu complet en mémoire.

La rotation et la rétention des journaux Suricata doivent néanmoins être
configurées sur le capteur. Pour les premiers déploiements, CyberPME recommande
de limiter EVE aux alertes nécessaires et de ne pas activer la journalisation
complète des flux.
