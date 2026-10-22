"""Fail a production build before switching traffic if hardening is incomplete."""
from urllib.parse import urlsplit
from cryptography.fernet import Fernet
from app.config import settings


def validate_production_security():
    failures = []
    if not settings.mfa_required:
        failures.append("MFA_REQUIRED doit être true")
    if not settings.secure_cookies:
        failures.append("SECURE_COOKIES doit être true")
    if settings.allow_legacy_enrollment:
        failures.append("ALLOW_LEGACY_ENROLLMENT doit être false")
    if settings.bootstrap_admin_force_sync or settings.bootstrap_admin_reset_password or settings.bootstrap_recovery_key:
        failures.append("désactiver BOOTSTRAP_ADMIN_FORCE_SYNC et retirer les secrets de récupération/reset bootstrap")
    try:
        Fernet(settings.mfa_encryption_key.encode())
    except (ValueError, TypeError):
        failures.append("configurer MFA_ENCRYPTION_KEY avec une clé Fernet valide")
    origins = [settings.frontend_public_url.rstrip('/'), *settings.cors_origin_list]
    if not origins or any(urlsplit(value).scheme != 'https' or not urlsplit(value).hostname or '*' in value or urlsplit(value).path not in {'', '/'} for value in origins):
        failures.append("FRONTEND_PUBLIC_URL et CORS_ORIGINS doivent être des origines HTTPS explicites")
    if failures:
        raise RuntimeError("Préparation sécurité incomplète : " + "; ".join(failures))
