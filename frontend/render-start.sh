#!/bin/sh
set -eu

backend_host="${BACKEND_HOST:-backend}"
attempt=1
max_attempts=90

while ! getent hosts "$backend_host" >/dev/null 2>&1; do
    if [ "$attempt" -ge "$max_attempts" ]; then
        echo "L'API $backend_host reste introuvable après $max_attempts tentatives." >&2
        exit 1
    fi

    echo "Attente de l'API $backend_host ($attempt/$max_attempts)..."
    attempt=$((attempt + 1))
    sleep 2
done

echo "API $backend_host détectée. Démarrage de Nginx."
exec /docker-entrypoint.sh "$@"
