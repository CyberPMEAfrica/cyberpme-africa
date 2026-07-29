#!/bin/sh
set -eu

echo "Application des migrations de base de données..."
alembic -c /app/alembic.ini upgrade head

echo "Démarrage de l'API CyberPME Africa..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
