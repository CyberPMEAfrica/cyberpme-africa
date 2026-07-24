from datetime import datetime, timezone
from ipaddress import IPv4Network, ip_network
import subprocess
import xml.etree.ElementTree as ET
from uuid import UUID

from app.database import SessionLocal
from app.models import NetworkScan


SCAN_TIMEOUT_SECONDS = 180

RECOMMENDATIONS = {
    21: "Désactivez FTP ou remplacez-le par SFTP.",
    22: "Limitez SSH aux administrateurs, utilisez des clés et désactivez les mots de passe.",
    23: "Désactivez Telnet et utilisez SSH.",
    25: "Vérifiez que le serveur SMTP n’autorise pas le relais ouvert.",
    53: "Limitez les transferts de zone DNS et maintenez le service à jour.",
    80: "Redirigez HTTP vers HTTPS et protégez l’interface d’administration.",
    110: "Évitez POP3 non chiffré et privilégiez POP3S ou IMAPS.",
    139: "Désactivez NetBIOS/SMBv1 et limitez l’accès au réseau interne.",
    443: "Vérifiez le certificat TLS et les protocoles cryptographiques autorisés.",
    445: "Désactivez SMBv1, appliquez les correctifs et limitez les partages.",
    3306: "N’exposez pas MySQL au réseau général et limitez les adresses autorisées.",
    3389: "Protégez RDP par VPN, MFA et limitation des sources.",
    5432: "N’exposez pas PostgreSQL au réseau général et limitez les adresses autorisées.",
    5900: "Protégez VNC par VPN et authentification forte.",
    6379: "N’exposez pas Redis sans authentification ni filtrage réseau.",
}


def validate_private_target(value: str) -> str:
    try:
        network = ip_network(value, strict=True)
    except ValueError as exc:
        raise ValueError("Saisissez un réseau IPv4 valide, par exemple 192.168.1.0/24.") from exc
    if not isinstance(network, IPv4Network):
        raise ValueError("Seuls les réseaux IPv4 privés sont acceptés pour le moment.")
    if not network.is_private:
        raise ValueError("La cible doit être un réseau IPv4 privé.")
    if network.prefixlen < 24:
        raise ValueError("Un audit est limité à un réseau /24 ou plus petit.")
    return str(network)


def parse_nmap_xml(xml_output: str) -> list[dict]:
    root = ET.fromstring(xml_output)
    hosts: list[dict] = []
    for host_node in root.findall("host"):
        status_node = host_node.find("status")
        if status_node is None or status_node.get("state") != "up":
            continue
        address_node = host_node.find("address[@addrtype='ipv4']")
        if address_node is None:
            continue
        hostname_node = host_node.find("hostnames/hostname")
        ports: list[dict] = []
        recommendations: list[str] = []
        for port_node in host_node.findall("ports/port"):
            state_node = port_node.find("state")
            if state_node is None or state_node.get("state") != "open":
                continue
            service_node = port_node.find("service")
            port = int(port_node.get("portid", "0"))
            service = service_node.get("name", "inconnu") if service_node is not None else "inconnu"
            product = service_node.get("product", "") if service_node is not None else ""
            version = service_node.get("version", "") if service_node is not None else ""
            ports.append(
                {
                    "port": port,
                    "protocol": port_node.get("protocol", "tcp"),
                    "service": service,
                    "product": product,
                    "version": version,
                }
            )
            recommendation = RECOMMENDATIONS.get(port)
            if recommendation and recommendation not in recommendations:
                recommendations.append(recommendation)
        hosts.append(
            {
                "ip_address": address_node.get("addr"),
                "hostname": hostname_node.get("name") if hostname_node is not None else None,
                "ports": ports,
                "recommendations": recommendations,
            }
        )
    return hosts


def parse_up_hosts(xml_output: str, target: str) -> list[str]:
    root = ET.fromstring(xml_output)
    network = IPv4Network(target)
    excluded = {str(network.network_address), str(network.broadcast_address)}
    addresses: list[str] = []
    for host_node in root.findall("host"):
        status_node = host_node.find("status")
        address_node = host_node.find("address[@addrtype='ipv4']")
        if status_node is None or status_node.get("state") != "up" or address_node is None:
            continue
        address = address_node.get("addr")
        if address and address not in excluded:
            addresses.append(address)
    return addresses


def execute_nmap(command: list[str], timeout: int) -> str:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        shell=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Nmap n’a pas pu terminer l’audit.")
    return result.stdout


def run_network_scan(scan_id: UUID) -> None:
    with SessionLocal() as db:
        scan = db.get(NetworkScan, scan_id)
        if scan is None:
            return
        scan.status = "running"
        scan.started_at = datetime.now(timezone.utc)
        db.commit()
        try:
            discovery_xml = execute_nmap(
                [
                    "nmap",
                    "-sn",
                    "-PE",
                    "-n",
                    "--max-retries",
                    "1",
                    "-oX",
                    "-",
                    scan.target,
                ],
                timeout=60,
            )
            active_hosts = parse_up_hosts(discovery_xml, scan.target)
            if not active_hosts:
                scan.results = []
                scan.status = "completed"
                return
            command = [
                "nmap",
                "-n",
                "-sT",
                "-sV",
                "--version-light",
                "--top-ports",
                "100",
                "-T3",
                "--max-retries",
                "1",
                "--host-timeout",
                "30s",
                "-oX",
                "-",
                *active_hosts,
            ]
            scan.results = parse_nmap_xml(execute_nmap(command, timeout=SCAN_TIMEOUT_SECONDS))
            scan.status = "completed"
        except subprocess.TimeoutExpired:
            scan.status = "failed"
            scan.error = "L’audit a dépassé la durée maximale autorisée."
        except (OSError, RuntimeError, ET.ParseError) as exc:
            scan.status = "failed"
            scan.error = str(exc)
        finally:
            scan.completed_at = datetime.now(timezone.utc)
            db.commit()
