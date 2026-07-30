#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="cyberpme-suricata"
SERVICE_USER="cyberpme-suricata"
SERVICE_GROUP="cyberpme-suricata"
BIN_PATH="/usr/local/bin/cyberpme-suricata"
CONFIG_DIR="/etc/cyberpme-suricata"
DATA_DIR="/var/lib/cyberpme-suricata"
UNIT_DIR="/etc/systemd/system"
purge=false

if [[ ${1:-} == "--purge" ]]; then
  purge=true
elif [[ $# -gt 0 ]]; then
  echo "Usage : sudo ./uninstall.sh [--purge]" >&2
  exit 2
fi
if [[ ${EUID} -ne 0 ]]; then
  echo "Exécutez la désinstallation avec sudo." >&2
  exit 1
fi

systemctl disable --now "${SERVICE_NAME}.timer" >/dev/null 2>&1 || true
systemctl stop "${SERVICE_NAME}.service" >/dev/null 2>&1 || true
rm -f -- \
  "${UNIT_DIR}/${SERVICE_NAME}.timer" \
  "${UNIT_DIR}/${SERVICE_NAME}.service" \
  "${BIN_PATH}"
systemctl daemon-reload
systemctl reset-failed "${SERVICE_NAME}.service" >/dev/null 2>&1 || true

if ${purge}; then
  rm -rf -- "${CONFIG_DIR}" "${DATA_DIR}"
  userdel "${SERVICE_USER}" >/dev/null 2>&1 || true
  groupdel "${SERVICE_GROUP}" >/dev/null 2>&1 || true
  echo "Adaptateur, configuration et file locale supprimés."
else
  echo "Adaptateur désinstallé."
  echo "Configuration et file conservées dans ${CONFIG_DIR} et ${DATA_DIR}."
  echo "Utilisez --purge uniquement pour supprimer également ces données."
fi
