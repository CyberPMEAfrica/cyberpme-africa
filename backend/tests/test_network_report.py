from datetime import datetime, timezone
from types import SimpleNamespace

from app.network_report import build_network_scan_pdf


def test_build_network_scan_pdf():
    scan = SimpleNamespace(
        target="192.168.1.0/24",
        completed_at=datetime(2026, 7, 24, 10, 30, tzinfo=timezone.utc),
        results=[
            {
                "ip_address": "192.168.1.10",
                "hostname": "serveur-pme",
                "ports": [
                    {"port": 22, "protocol": "tcp", "service": "ssh", "product": "OpenSSH", "version": "9.6"},
                    {"port": 443, "protocol": "tcp", "service": "https", "product": "nginx", "version": "1.27"},
                ],
                "recommendations": [
                    "Limitez SSH aux administrateurs, utilisez des clés et désactivez les mots de passe.",
                    "Vérifiez le certificat TLS et les protocoles cryptographiques autorisés.",
                ],
            }
        ],
    )
    content = build_network_scan_pdf(scan)
    assert content.startswith(b"%PDF")
    assert len(content) > 2_000
