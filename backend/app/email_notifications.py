import logging
import smtplib
from email.message import EmailMessage

from app.config import settings
from app.models import Alert


logger = logging.getLogger(__name__)


def deliver_email(message: EmailMessage) -> bool:
    if not settings.smtp_host.strip():
        logger.info("Notification e-mail non envoyée : aucun serveur SMTP configuré")
        return False
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
        return True
    except (OSError, smtplib.SMTPException):
        logger.exception("Échec de l’envoi de la notification e-mail")
        return False


def send_alert_email(alert: Alert, server_name: str, event: str) -> bool:
    resolved = event == "resolved"
    subject = (
        f"[RÉSOLU] {server_name} — {alert.resource.upper()}"
        if resolved
        else f"[{alert.severity.upper()}] {server_name} — {alert.resource.upper()} à {alert.value:.1f} %"
    )
    title = "Incident résolu" if resolved else "Une intervention peut être nécessaire"
    body = f"""CyberPME Africa

{title}

Serveur : {server_name}
Ressource : {alert.resource.upper()}
Valeur observée : {alert.value:.1f} %
État : {'Résolu' if resolved else alert.severity.capitalize()}

{alert.message}

Recommandation :
{alert.recommendation}

Ce message a été généré automatiquement par CyberPME Africa.
"""
    message = EmailMessage()
    message["From"] = settings.alert_email_from
    message["To"] = settings.alert_email_to
    message["Subject"] = subject
    message.set_content(body)
    return deliver_email(message)


def send_invitation_email(
    recipient: str,
    organization_name: str,
    role: str,
    invited_by: str,
    invitation_url: str,
) -> bool:
    role_label = {
        "admin": "Administrateur",
        "analyst": "Analyste",
        "viewer": "Lecture seule",
    }.get(role, role)
    body = f"""CyberPME Africa

Vous avez été invité à rejoindre {organization_name}.

Rôle proposé : {role_label}
Invitation envoyée par : {invited_by}

Choisissez votre mot de passe en ouvrant ce lien :
{invitation_url}

Ce lien est personnel et expire dans 24 heures. Ne le transférez à personne.
Si vous n’attendiez pas cette invitation, ignorez simplement ce message.

CyberPME Africa
"""
    message = EmailMessage()
    message["From"] = settings.alert_email_from
    message["To"] = recipient
    message["Subject"] = f"Invitation à rejoindre {organization_name} sur CyberPME Africa"
    message.set_content(body)
    return deliver_email(message)
