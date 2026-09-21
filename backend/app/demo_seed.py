from datetime import datetime, timedelta, timezone
import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    BackupCheck,
    IdsConnector,
    Metric,
    NetworkScan,
    Organization,
    SecurityEvent,
    Server,
    SslCheck,
)


DEMO_MARKER_HOSTNAME = "web-01.cyberpme.demo"


def seed_demo_data(db: Session, organization: Organization) -> bool:
    """Populate one organization with a stable demonstration dataset once."""
    marker = db.scalar(
        select(Server).where(
            Server.organization_id == organization.id,
            Server.hostname == DEMO_MARKER_HOSTNAME,
        )
    )
    if marker is not None:
        return False

    now = datetime.now(timezone.utc)
    servers = [
        Server(
            organization_id=organization.id,
            name="Serveur Web Principal",
            hostname=DEMO_MARKER_HOSTNAME,
            ip_address="10.20.1.10",
            status="online",
            created_at=now - timedelta(days=42),
            last_seen_at=now - timedelta(minutes=2),
        ),
        Server(
            organization_id=organization.id,
            name="Base de données ERP",
            hostname="db-01.cyberpme.demo",
            ip_address="10.20.1.20",
            status="warning",
            created_at=now - timedelta(days=38),
            last_seen_at=now - timedelta(minutes=4),
        ),
        Server(
            organization_id=organization.id,
            name="Passerelle de sécurité",
            hostname="fw-01.cyberpme.demo",
            ip_address="10.20.1.1",
            status="online",
            created_at=now - timedelta(days=51),
            last_seen_at=now - timedelta(minutes=1),
        ),
    ]
    db.add_all(servers)
    db.flush()

    profiles = [
        (servers[0], [(31, 48, 57), (35, 50, 58), (29, 47, 58), (34, 49, 59)]),
        (servers[1], [(67, 81, 72), (71, 84, 73), (64, 82, 74), (69, 86, 75)]),
        (servers[2], [(18, 39, 41), (21, 42, 42), (20, 41, 42), (23, 43, 43)]),
    ]
    for server, values in profiles:
        for index, (cpu, memory, disk) in enumerate(values):
            db.add(
                Metric(
                    server_id=server.id,
                    cpu_percent=cpu,
                    memory_percent=memory,
                    disk_percent=disk,
                    collected_at=now - timedelta(minutes=(len(values) - index) * 15),
                )
            )

    db.add_all(
        [
            Alert(
                server_id=servers[1].id,
                resource="memory",
                severity="warning",
                status="active",
                value=86,
                message="Utilisation mémoire élevée sur le serveur ERP",
                recommendation="Analyser les processus PostgreSQL et ajuster la mémoire disponible.",
                created_at=now - timedelta(hours=3),
            ),
            Alert(
                server_id=servers[0].id,
                resource="disk",
                severity="critical",
                status="active",
                value=91,
                message="Espace disque critique sur le volume des journaux",
                recommendation="Archiver les anciens journaux et étendre le volume sous 24 heures.",
                created_at=now - timedelta(minutes=48),
            ),
        ]
    )

    db.add_all(
        [
            BackupCheck(
                server_id=servers[1].id,
                name="Sauvegarde ERP quotidienne",
                kind="postgresql",
                source="erp_production",
                status="healthy",
                exists=True,
                size_bytes=4_830_511_104,
                last_success_at=now - timedelta(hours=5),
                max_age_hours=24,
                checked_at=now - timedelta(hours=1),
            ),
            BackupCheck(
                server_id=servers[0].id,
                name="Documents commerciaux",
                kind="files",
                source="/srv/documents",
                status="healthy",
                exists=True,
                size_bytes=12_884_901_888,
                last_success_at=now - timedelta(hours=9),
                max_age_hours=24,
                checked_at=now - timedelta(hours=1),
            ),
            BackupCheck(
                server_id=servers[2].id,
                name="Configuration pare-feu",
                kind="files",
                source="/backup/firewall",
                status="stale",
                exists=True,
                size_bytes=18_874_368,
                last_success_at=now - timedelta(days=3),
                max_age_hours=24,
                checked_at=now - timedelta(hours=1),
            ),
        ]
    )

    db.add(
        IdsConnector(
            organization_id=organization.id,
            server_id=servers[2].id,
            name="Wazuh - Agence principale",
            connector_type="wazuh",
            token_hash=hashlib.sha256(f"demo:{organization.id}".encode()).hexdigest(),
            status="active",
            last_event_at=now - timedelta(minutes=23),
            created_at=now - timedelta(days=20),
        )
    )

    events = [
        ("demo-evt-001", "wazuh", "authentication", "high", "Tentatives de connexion répétées", "Plusieurs échecs SSH ont été détectés en moins de cinq minutes.", "198.51.100.42", "10.20.1.10", "5710", "new", None),
        ("demo-evt-002", "suricata", "network", "critical", "Communication vers une adresse malveillante", "Une connexion sortante correspond à un indicateur de compromission connu.", "10.20.1.20", "203.0.113.77", "ET-MALWARE-2041", "acknowledged", None),
        ("demo-evt-003", "agent", "integrity", "medium", "Modification d’un fichier système", "Le fichier de configuration SSH a été modifié hors fenêtre de maintenance.", None, "10.20.1.10", "FIM-550", "new", None),
        ("demo-evt-004", "wazuh", "malware", "high", "Exécutable suspect mis en quarantaine", "L’antivirus a isolé un fichier téléchargé depuis une source non approuvée.", "198.51.100.18", "10.20.1.20", "92001", "resolved", "Fichier supprimé et poste analysé."),
    ]
    for index, event in enumerate(events):
        key, source, category, severity, title, description, source_ip, destination_ip, rule_id, status, note = event
        occurred_at = now - timedelta(hours=index * 7 + 1)
        db.add(
            SecurityEvent(
                server_id=servers[index % len(servers)].id,
                event_key=key,
                source=source,
                category=category,
                severity=severity,
                title=title,
                description=description,
                source_ip=source_ip,
                destination_ip=destination_ip,
                rule_id=rule_id,
                recommendation="Vérifier les journaux associés, isoler l’équipement si nécessaire et documenter l’investigation.",
                status=status,
                handled_by_email="soc@cyberpme.demo" if status != "new" else None,
                acknowledged_at=occurred_at + timedelta(minutes=20) if status != "new" else None,
                resolved_at=occurred_at + timedelta(hours=2) if status == "resolved" else None,
                resolution_note=note,
                occurred_at=occurred_at,
                received_at=occurred_at + timedelta(minutes=1),
            )
        )

    db.add_all(
        [
            NetworkScan(
                organization_id=organization.id,
                target="10.20.1.0/24",
                status="completed",
                results=[
                    {
                        "ip_address": "10.20.1.1",
                        "hostname": "fw-01",
                        "ports": [{"port": 443, "protocol": "tcp", "service": "https", "product": "Administration sécurisée"}],
                    },
                    {
                        "ip_address": "10.20.1.10",
                        "hostname": "web-01",
                        "ports": [{"port": 443, "protocol": "tcp", "service": "https", "product": "Nginx"}],
                    },
                    {
                        "ip_address": "10.20.1.20",
                        "hostname": "db-01",
                        "ports": [{"port": 5432, "protocol": "tcp", "service": "postgresql", "product": "PostgreSQL 17"}],
                    },
                ],
                requested_at=now - timedelta(days=1, minutes=8),
                started_at=now - timedelta(days=1, minutes=7),
                completed_at=now - timedelta(days=1),
            ),
            NetworkScan(
                organization_id=organization.id,
                target="10.20.2.0/24",
                status="completed",
                results=[
                    {
                        "ip_address": "10.20.2.15",
                        "hostname": "nas-01",
                        "ports": [{"port": 445, "protocol": "tcp", "service": "microsoft-ds", "product": "Partage de fichiers"}],
                    }
                ],
                requested_at=now - timedelta(days=7, minutes=4),
                started_at=now - timedelta(days=7, minutes=3),
                completed_at=now - timedelta(days=7),
            ),
        ]
    )

    db.add_all(
        [
            SslCheck(
                organization_id=organization.id,
                hostname="portail.cyberpme.demo",
                port=443,
                status="valid",
                subject="CN=portail.cyberpme.demo",
                issuer="Let's Encrypt R11",
                valid_from=now - timedelta(days=24),
                expires_at=now + timedelta(days=66),
                days_remaining=66,
                chain_valid=True,
                tls_version="TLSv1.3",
                cipher="TLS_AES_256_GCM_SHA384",
                checked_at=now - timedelta(hours=2),
            ),
            SslCheck(
                organization_id=organization.id,
                hostname="vpn.cyberpme.demo",
                port=443,
                status="warning",
                subject="CN=vpn.cyberpme.demo",
                issuer="Let's Encrypt R11",
                valid_from=now - timedelta(days=76),
                expires_at=now + timedelta(days=14),
                days_remaining=14,
                chain_valid=True,
                tls_version="TLSv1.2",
                cipher="ECDHE-RSA-AES256-GCM-SHA384",
                checked_at=now - timedelta(hours=2),
            ),
        ]
    )

    db.commit()
    return True
