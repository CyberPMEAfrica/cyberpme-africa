#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="cyberpme-suricata"
SERVICE_USER="cyberpme-suricata"
SERVICE_GROUP="cyberpme-suricata"
BIN_PATH="/usr/local/bin/cyberpme-suricata"
CONFIG_DIR="/etc/cyberpme-suricata"
CONFIG_FILE="${CONFIG_DIR}/adapter.env"
DATA_DIR="/var/lib/cyberpme-suricata"
UNIT_DIR="/etc/systemd/system"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ADAPTER="${SCRIPT_DIR}/cyberpme-suricata"

if [[ ${EUID} -ne 0 ]]; then
  echo "Exécutez l'installateur avec sudo." >&2
  exit 1
fi
if [[ ! -f "${SOURCE_ADAPTER}" ]]; then
  echo "Adaptateur introuvable à côté de l'installateur : ${SOURCE_ADAPTER}" >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 est requis." >&2
  exit 1
fi
if ! command -v systemctl >/dev/null 2>&1; then
  echo "Cet installateur nécessite systemd." >&2
  exit 1
fi

python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10 ou plus récent est requis.")
PY

CYBERPME_SURICATA_ENDPOINT="${CYBERPME_SURICATA_ENDPOINT:-}"
CYBERPME_SURICATA_TOKEN="${CYBERPME_SURICATA_TOKEN:-}"
CYBERPME_SURICATA_EVE_FILE="${CYBERPME_SURICATA_EVE_FILE:-/var/log/suricata/eve.json}"
CYBERPME_SURICATA_MAX_QUEUE_MB="${CYBERPME_SURICATA_MAX_QUEUE_MB:-50}"
CYBERPME_SURICATA_MAX_DELIVERIES="${CYBERPME_SURICATA_MAX_DELIVERIES:-500}"
CYBERPME_SURICATA_INTERVAL="${CYBERPME_SURICATA_INTERVAL:-15s}"

if [[ -z "${CYBERPME_SURICATA_ENDPOINT}" ]]; then
  read -r -p "URL d'ingestion CyberPME : " CYBERPME_SURICATA_ENDPOINT
fi
if [[ -z "${CYBERPME_SURICATA_TOKEN}" ]]; then
  read -r -s -p "Jeton du connecteur (masqué) : " CYBERPME_SURICATA_TOKEN
  echo
fi
read -r -p "Fichier EVE JSON [${CYBERPME_SURICATA_EVE_FILE}] : " entered_eve
CYBERPME_SURICATA_EVE_FILE="${entered_eve:-${CYBERPME_SURICATA_EVE_FILE}}"

if [[ ! ${CYBERPME_SURICATA_ENDPOINT} =~ ^https?://[^[:space:]]+/api/v1/ids-connectors/[^/[:space:]]+/events$ ]]; then
  echo "L'URL d'ingestion CyberPME n'est pas valide." >&2
  exit 1
fi
if [[ ! ${CYBERPME_SURICATA_TOKEN} =~ ^[A-Za-z0-9_-]{32,}$ ]]; then
  echo "Le jeton du connecteur n'est pas valide." >&2
  exit 1
fi
if [[ ${CYBERPME_SURICATA_EVE_FILE} != /* ]]; then
  echo "Le chemin EVE doit être absolu." >&2
  exit 1
fi
if ! [[ ${CYBERPME_SURICATA_MAX_QUEUE_MB} =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "CYBERPME_SURICATA_MAX_QUEUE_MB doit être un nombre positif." >&2
  exit 1
fi
if ! python3 - "${CYBERPME_SURICATA_MAX_QUEUE_MB}" <<'PY'
import sys
raise SystemExit(0 if float(sys.argv[1]) > 0 else 1)
PY
then
  echo "CYBERPME_SURICATA_MAX_QUEUE_MB doit être supérieur à zéro." >&2
  exit 1
fi
if ! [[ ${CYBERPME_SURICATA_MAX_DELIVERIES} =~ ^[1-9][0-9]*$ ]]; then
  echo "CYBERPME_SURICATA_MAX_DELIVERIES doit être un entier positif." >&2
  exit 1
fi
if [[ ! ${CYBERPME_SURICATA_INTERVAL} =~ ^[1-9][0-9]*(s|min|h)$ ]]; then
  echo "CYBERPME_SURICATA_INTERVAL doit ressembler à 15s, 2min ou 1h." >&2
  exit 1
fi

if ! getent group "${SERVICE_GROUP}" >/dev/null; then
  groupadd --system "${SERVICE_GROUP}"
fi
if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  useradd \
    --system \
    --gid "${SERVICE_GROUP}" \
    --home-dir "${DATA_DIR}" \
    --shell /usr/sbin/nologin \
    "${SERVICE_USER}"
fi

suricata_group="${CYBERPME_SURICATA_LOG_GROUP:-}"
if [[ -z "${suricata_group}" && -e "${CYBERPME_SURICATA_EVE_FILE}" ]]; then
  suricata_group="$(stat -c '%G' "${CYBERPME_SURICATA_EVE_FILE}")"
fi
if [[ -z "${suricata_group}" ]] && getent group suricata >/dev/null; then
  suricata_group="suricata"
fi
if [[ -n "${suricata_group}" && "${suricata_group}" != "root" ]]; then
  if ! getent group "${suricata_group}" >/dev/null; then
    echo "Le groupe de lecture EVE '${suricata_group}' n'existe pas." >&2
    exit 1
  fi
  usermod -a -G "${suricata_group}" "${SERVICE_USER}"
fi

install -o root -g root -m 0755 "${SOURCE_ADAPTER}" "${BIN_PATH}"
install -d -o root -g "${SERVICE_GROUP}" -m 0750 "${CONFIG_DIR}"
install -d -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" -m 0750 "${DATA_DIR}"
install -d -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" -m 0700 "${DATA_DIR}/queue"

if [[ -f "${CONFIG_FILE}" ]]; then
  cp -a "${CONFIG_FILE}" "${CONFIG_FILE}.bak-$(date +%Y%m%d-%H%M%S)"
fi

export CONFIG_FILE DATA_DIR
export CYBERPME_SURICATA_ENDPOINT CYBERPME_SURICATA_TOKEN
export CYBERPME_SURICATA_EVE_FILE CYBERPME_SURICATA_MAX_QUEUE_MB
export CYBERPME_SURICATA_MAX_DELIVERIES
python3 - <<'PY'
from pathlib import Path
import os

def quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

values = {
    "CYBERPME_SURICATA_ENDPOINT": os.environ["CYBERPME_SURICATA_ENDPOINT"],
    "CYBERPME_SURICATA_TOKEN": os.environ["CYBERPME_SURICATA_TOKEN"],
    "CYBERPME_SURICATA_EVE_FILE": os.environ["CYBERPME_SURICATA_EVE_FILE"],
    "CYBERPME_SURICATA_STATE_FILE": f'{os.environ["DATA_DIR"]}/state.json',
    "CYBERPME_SURICATA_QUEUE_DIR": f'{os.environ["DATA_DIR"]}/queue',
    "CYBERPME_SURICATA_MAX_QUEUE_MB": os.environ["CYBERPME_SURICATA_MAX_QUEUE_MB"],
    "CYBERPME_SURICATA_MAX_DELIVERIES": os.environ["CYBERPME_SURICATA_MAX_DELIVERIES"],
}
path = Path(os.environ["CONFIG_FILE"])
temporary = path.with_suffix(".tmp")
temporary.write_text(
    "".join(f"{key}={quote(value)}\n" for key, value in values.items()),
    encoding="utf-8",
)
os.chmod(temporary, 0o600)
temporary.replace(path)
PY
chown root:"${SERVICE_GROUP}" "${CONFIG_FILE}"

cat >"${UNIT_DIR}/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Adaptateur Suricata vers CyberPME Africa
Wants=network-online.target
After=network-online.target suricata.service

[Service]
Type=oneshot
User=${SERVICE_USER}
Group=${SERVICE_GROUP}
SupplementaryGroups=${suricata_group:-${SERVICE_GROUP}}
EnvironmentFile=${CONFIG_FILE}
ExecStart=${BIN_PATH}
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=${DATA_DIR}

[Install]
WantedBy=multi-user.target
EOF

cat >"${UNIT_DIR}/${SERVICE_NAME}.timer" <<EOF
[Unit]
Description=Collecte régulière des alertes Suricata pour CyberPME

[Timer]
OnBootSec=30s
OnUnitActiveSec=${CYBERPME_SURICATA_INTERVAL}
AccuracySec=1s
RandomizedDelaySec=2s
Persistent=true
Unit=${SERVICE_NAME}.service

[Install]
WantedBy=timers.target
EOF

chmod 0644 \
  "${UNIT_DIR}/${SERVICE_NAME}.service" \
  "${UNIT_DIR}/${SERVICE_NAME}.timer"
unset CYBERPME_SURICATA_TOKEN

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}.timer"
if ! systemctl start "${SERVICE_NAME}.service"; then
  echo "L'adaptateur est installé, mais sa première livraison a échoué." >&2
  echo "La file locale sera retentée automatiquement. Consultez :" >&2
  echo "  journalctl -u ${SERVICE_NAME}.service -n 50 --no-pager" >&2
fi

echo "Adaptateur Suricata CyberPME installé."
echo "Minuteur : $(systemctl is-active "${SERVICE_NAME}.timer")"
echo "Configuration protégée : ${CONFIG_FILE}"
echo "File persistante : ${DATA_DIR}/queue"
