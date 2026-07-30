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
export CYBERPME_SURICATA_QUEUE_DIR="/var/lib/cyberpme-suricata/queue"

python3 /usr/local/bin/cyberpme-suricata
```

Le fichier d'état conserve l'identité du fichier EVE et le dernier octet traité.
Un second lancement ne renvoie donc pas les anciennes alertes. En cas de
rotation de `eve.json`, la lecture reprend automatiquement au début du nouveau
fichier. L'API CyberPME reste également idempotente grâce à la clé stable de
chaque événement.

Chaque alerte est d'abord écrite atomiquement dans une file locale, puis la
progression EVE est validée. Elle n'est supprimée de la file qu'après une
réponse positive de l'API. Une coupure Internet, un redémarrage du capteur ou
une indisponibilité temporaire du SaaS ne provoque donc pas de perte.

La file est limitée à 50 Mio par défaut. Si elle atteint cette limite,
l'adaptateur arrête de valider la progression du journal plutôt que de supprimer
des alertes silencieusement. Les valeurs suivantes peuvent être adaptées à la
taille et au débit du capteur :

```bash
export CYBERPME_SURICATA_MAX_QUEUE_MB="100"
export CYBERPME_SURICATA_MAX_DELIVERIES="1000"
```

Une entrée locale illisible est déplacée dans le sous-répertoire
`queue/quarantine` afin de ne pas bloquer les autres alertes. Les doublons sont
coalescés grâce à la clé stable de l'événement et l'API reste idempotente.

## Installation Linux automatisée

L'installateur fonctionne sur une distribution Linux utilisant systemd et
Python 3.10 ou plus récent. Sur le capteur Suricata :

```bash
cd integrations/suricata
sudo ./install.sh
```

Il demande l'URL d'ingestion, le jeton masqué et le chemin EVE. Il crée ensuite :

- un compte système sans shell ;
- une configuration protégée dans `/etc/cyberpme-suricata/adapter.env` ;
- une file privée dans `/var/lib/cyberpme-suricata/queue` ;
- un service `oneshot` renforcé et un minuteur systemd exécuté toutes les
  15 secondes.

Le groupe propriétaire du fichier EVE est détecté automatiquement. Pour une
installation non interactive ou un chemin atypique, les mêmes variables
d'environnement peuvent être fournies avant `sudo -E ./install.sh`. La variable
`CYBERPME_SURICATA_LOG_GROUP` permet de préciser explicitement le groupe ayant
accès au journal.

Commandes d'exploitation :

```bash
systemctl status cyberpme-suricata.timer --no-pager
journalctl -u cyberpme-suricata.service -n 50 --no-pager
sudo systemctl start cyberpme-suricata.service
```

La désinstallation conserve la configuration et la file par défaut :

```bash
sudo ./uninstall.sh
```

La suppression complète est volontairement explicite :

```bash
sudo ./uninstall.sh --purge
```

Ne lancez `--purge` qu'après avoir vérifié que la file ne contient plus
d'alertes à transmettre.

## Ressources et stockage

L'adaptateur ne capture aucun paquet et n'exécute aucune règle IDS. Il lit le
fichier ligne par ligne et ne conserve pas son contenu complet en mémoire.

La rotation et la rétention des journaux Suricata doivent néanmoins être
configurées sur le capteur. Pour les premiers déploiements, CyberPME recommande
de limiter EVE aux alertes nécessaires et de ne pas activer la journalisation
complète des flux.
