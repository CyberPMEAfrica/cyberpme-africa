import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from ipaddress import IPv4Network, ip_network
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import psutil


class ApiError(RuntimeError):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(message)


RECOMMENDATIONS = {
    21: "Désactivez FTP ou remplacez-le par SFTP.", 22: "Limitez SSH aux administrateurs et utilisez des clés.",
    23: "Désactivez Telnet et utilisez SSH.", 25: "Vérifiez que SMTP n’autorise pas le relais ouvert.",
    53: "Limitez les transferts de zone DNS.", 80: "Redirigez HTTP vers HTTPS.",
    110: "Évitez POP3 non chiffré.", 139: "Désactivez NetBIOS/SMBv1.",
    443: "Vérifiez le certificat TLS et les protocoles autorisés.",
    445: "Désactivez SMBv1, appliquez les correctifs et limitez les partages.",
    3306: "N’exposez pas MySQL au réseau général.", 3389: "Protégez RDP par VPN et MFA.",
    5432: "N’exposez pas PostgreSQL au réseau général.", 5900: "Protégez VNC par VPN.",
    6379: "N’exposez pas Redis sans authentification ni filtrage réseau.",
}


def default_data_dir() -> Path:
    base = os.getenv("PROGRAMDATA") if platform.system() == "Windows" else None
    return Path(base or Path.home() / ".local" / "share") / "CyberPME"


@dataclass(frozen=True)
class Config:
    api_url: str
    name: str
    hostname: str
    interval: int
    enrollment_key: str
    backup_targets: tuple[tuple[str, str, str, int], ...]
    enrollment_token: str = ""
    state_path: Path = default_data_dir() / "agent-state.json"
    config_path: Path | None = None

    @classmethod
    def from_environment(cls, interval_override: int | None = None) -> "Config":
        return cls.from_sources(None, interval_override)

    @classmethod
    def from_sources(cls, config_path: Path | None, interval_override: int | None = None) -> "Config":
        stored: dict[str, Any] = {}
        if config_path is not None:
            stored = json.loads(config_path.read_text(encoding="utf-8-sig"))
        hostname = os.getenv("CYBERPME_HOSTNAME", stored.get("hostname", socket.gethostname()))
        targets = []
        target_values = {
            "files": os.getenv("CYBERPME_FILE_BACKUPS", stored.get("file_backups", "")),
            "postgresql": os.getenv("CYBERPME_POSTGRES_BACKUPS", stored.get("postgres_backups", "")),
        }
        for kind, value in target_values.items():
            for item in filter(None, value.split(";")):
                parts = item.split("|")
                if len(parts) != 3:
                    raise ValueError(f"Sauvegarde {kind}: format attendu nom|chemin|heures.")
                targets.append((kind, parts[0].strip(), parts[1].strip(), int(parts[2])))
        configured_state = os.getenv("CYBERPME_STATE_PATH", stored.get("state_path", ""))
        return cls(
            api_url=os.getenv("CYBERPME_API_URL", stored.get("api_url", "http://localhost:8000")).rstrip("/"),
            name=os.getenv("CYBERPME_SERVER_NAME", stored.get("name", hostname)), hostname=hostname,
            interval=interval_override or int(os.getenv("CYBERPME_INTERVAL", stored.get("interval", 60))),
            enrollment_key=os.getenv("CYBERPME_ENROLLMENT_KEY", stored.get("enrollment_key", "")),
            backup_targets=tuple(targets),
            enrollment_token=os.getenv("CYBERPME_ENROLLMENT_TOKEN", stored.get("enrollment_token", "")),
            state_path=Path(configured_state) if configured_state else default_data_dir() / "agent-state.json",
            config_path=config_path,
        )


def request_json(method: str, url: str, payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(url, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urlopen(request, timeout=30) as response:
            content = response.read()
            return json.loads(content.decode("utf-8")) if content else None
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ApiError(exc.code, f"L’API a répondu {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Impossible de joindre l’API {url}: {exc.reason}") from exc


def discover_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.connect(("8.8.8.8", 80))
            return connection.getsockname()[0]
    except OSError:
        return None


def load_state(path: Path) -> tuple[str, str] | None:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        return state["server_id"], state["agent_token"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return None


def save_state(path: Path, server_id: str, agent_token: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".new")
    temporary.write_text(json.dumps({"server_id": server_id, "agent_token": agent_token}), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def clear_one_time_token(config: Config) -> None:
    if config.config_path is None:
        return
    try:
        stored = json.loads(config.config_path.read_text(encoding="utf-8-sig"))
        stored.pop("enrollment_token", None)
        config.config_path.write_text(json.dumps(stored, indent=2), encoding="utf-8")
    except (OSError, json.JSONDecodeError):
        pass


def register_agent(config: Config) -> tuple[str, str]:
    if config.enrollment_token:
        headers = {"X-Enrollment-Token": config.enrollment_token}
    elif config.enrollment_key:
        headers = {"X-Enrollment-Key": config.enrollment_key}
    else:
        raise RuntimeError("Un jeton d’installation CyberPME est requis lors du premier démarrage.")
    registration = request_json(
        "POST", f"{config.api_url}/api/v1/agents/register",
        {"name": config.name, "hostname": config.hostname, "ip_address": discover_ip(), "network_scan_capable": True}, headers,
    )
    save_state(config.state_path, registration["server_id"], registration["agent_token"])
    clear_one_time_token(config)
    return registration["server_id"], registration["agent_token"]


def collect_metrics() -> dict[str, float]:
    return {
        "cpu_percent": round(psutil.cpu_percent(interval=1), 1),
        "memory_percent": round(psutil.virtual_memory().percent, 1),
        "disk_percent": round(psutil.disk_usage(Path.home().anchor).percent, 1),
    }


def send_once(config: Config, server_id: str, agent_token: str) -> dict[str, Any]:
    metrics = collect_metrics()
    result = request_json("POST", f"{config.api_url}/api/v1/servers/{server_id}/metrics", metrics, {"Authorization": f"Bearer {agent_token}"})
    print(f"Mesure envoyée — CPU {metrics['cpu_percent']} % | RAM {metrics['memory_percent']} % | Disque {metrics['disk_percent']} %", flush=True)
    return result


def inspect_backup(kind: str, name: str, source: str, max_age_hours: int) -> dict[str, Any]:
    path = Path(source).expanduser()
    try:
        candidates = [path] if path.is_file() else [item for item in path.rglob("*") if item.is_file()] if path.is_dir() else []
        if kind == "postgresql":
            candidates = [item for item in candidates if item.suffix.lower() in {".sql", ".dump", ".backup", ".gz"}]
        latest = max(candidates, key=lambda item: item.stat().st_mtime) if candidates else None
        return {
            "name": name, "kind": kind, "source": str(path), "exists": latest is not None,
            "size_bytes": latest.stat().st_size if latest else None,
            "last_success_at": datetime.fromtimestamp(latest.stat().st_mtime, timezone.utc).isoformat() if latest else None,
            "max_age_hours": max_age_hours, "error": None if latest else "Aucun fichier de sauvegarde trouvé.",
        }
    except OSError as exc:
        return {"name": name, "kind": kind, "source": str(path), "exists": False, "size_bytes": None, "last_success_at": None, "max_age_hours": max_age_hours, "error": str(exc)}


def send_backup_checks(config: Config, server_id: str, agent_token: str) -> None:
    for target in config.backup_targets:
        payload = inspect_backup(*target)
        result = request_json("POST", f"{config.api_url}/api/v1/servers/{server_id}/backup-checks", payload, {"Authorization": f"Bearer {agent_token}"})
        print(f"Sauvegarde vérifiée — {payload['name']} : {result['status']}", flush=True)


def find_nmap() -> str:
    executable = shutil.which("nmap")
    if executable:
        return executable
    candidates = [Path(os.getenv("ProgramFiles", "C:/Program Files")) / "Nmap" / "nmap.exe", Path(os.getenv("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Nmap" / "nmap.exe"]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    raise RuntimeError("Nmap est absent. Relancez l’installateur CyberPME en mode administrateur.")


def execute_nmap(command: list[str], timeout: int) -> str:
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False, shell=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Nmap n’a pas pu terminer l’audit.")
    return result.stdout


def parse_up_hosts(xml_output: str, target: str) -> list[str]:
    root, network = ET.fromstring(xml_output), IPv4Network(target)
    excluded = {str(network.network_address), str(network.broadcast_address)} if network.prefixlen < 31 else set()
    addresses = []
    for host in root.findall("host"):
        status, address = host.find("status"), host.find("address[@addrtype='ipv4']")
        if status is not None and status.get("state") == "up" and address is not None and address.get("addr") not in excluded and ip_network(address.get("addr")).network_address in network:
            addresses.append(address.get("addr"))
    return addresses


def parse_nmap_xml(xml_output: str) -> list[dict]:
    hosts = []
    for host in ET.fromstring(xml_output).findall("host"):
        status, address = host.find("status"), host.find("address[@addrtype='ipv4']")
        if status is None or status.get("state") != "up" or address is None:
            continue
        hostname, ports, recommendations = host.find("hostnames/hostname"), [], []
        for node in host.findall("ports/port"):
            state, service = node.find("state"), node.find("service")
            if state is None or state.get("state") != "open":
                continue
            port = int(node.get("portid", "0"))
            ports.append({"port": port, "protocol": node.get("protocol", "tcp"), "service": service.get("name", "inconnu") if service is not None else "inconnu", "product": service.get("product", "") if service is not None else "", "version": service.get("version", "") if service is not None else ""})
            if port in RECOMMENDATIONS and RECOMMENDATIONS[port] not in recommendations:
                recommendations.append(RECOMMENDATIONS[port])
        hosts.append({"ip_address": address.get("addr"), "hostname": hostname.get("name") if hostname is not None else None, "ports": ports, "recommendations": recommendations})
    return hosts


def run_network_scan(target: str) -> list[dict]:
    network = ip_network(target, strict=True)
    private_ranges = [IPv4Network("10.0.0.0/8"), IPv4Network("172.16.0.0/12"), IPv4Network("192.168.0.0/16")]
    if not isinstance(network, IPv4Network) or not any(network.subnet_of(n) for n in private_ranges) or network.prefixlen < 24:
        raise RuntimeError("La tâche reçue ne cible pas un réseau IPv4 privé autorisé.")
    nmap = find_nmap()
    discovery = execute_nmap([nmap, "-sn", "-PE", "-n", "--max-retries", "1", "-oX", "-", target], 60)
    active_hosts = parse_up_hosts(discovery, target)
    if not active_hosts:
        return []
    command = [nmap, "-n", "-sT", "-sV", "--version-light", "--top-ports", "100", "-T3", "--max-retries", "1", "--host-timeout", "30s", "-oX", "-", *active_hosts]
    return parse_nmap_xml(execute_nmap(command, 180))


def process_scan_job(config: Config, server_id: str, agent_token: str) -> bool:
    headers = {"Authorization": f"Bearer {agent_token}"}
    outbox = config.state_path.with_suffix(".result.json")
    if outbox.exists():
        saved = json.loads(outbox.read_text(encoding="utf-8"))
        try:
            request_json("POST", f"{config.api_url}/api/v1/servers/{server_id}/network-scan-jobs/{saved['id']}/complete", saved["payload"], headers)
        except ApiError as exc:
            if exc.status not in {404, 409}:
                raise
            print("Résultat devenu obsolète après interruption, prêt pour un nouvel audit.", flush=True)
        outbox.unlink()
    job = request_json("GET", f"{config.api_url}/api/v1/servers/{server_id}/network-scan-jobs/next", headers=headers)
    if job is None:
        return False
    print(f"Audit réseau reçu — {job['target']}", flush=True)
    try:
        payload = {"status": "completed", "results": run_network_scan(job["target"]), "error": None}
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, ET.ParseError) as exc:
        payload = {"status": "failed", "results": [], "error": str(exc)[:2000]}
    outbox.parent.mkdir(parents=True, exist_ok=True)
    outbox.write_text(json.dumps({"id": job["id"], "payload": payload}), encoding="utf-8")
    request_json("POST", f"{config.api_url}/api/v1/servers/{server_id}/network-scan-jobs/{job['id']}/complete", payload, headers)
    outbox.unlink()
    print(f"Audit réseau terminé — {payload['status']}", flush=True)
    return True


def run(config: Config, once: bool) -> None:
    print(f"CyberPME Agent 0.2.0 — {platform.system()} {platform.release()}")
    print(f"Serveur: {config.name} ({config.hostname}) | API: {config.api_url}")
    credentials = load_state(config.state_path)
    if credentials is None:
        credentials = register_agent(config)
        print(f"Enregistrement confirmé — identifiant {credentials[0]}")
    else:
        print(f"Identité locale chargée — identifiant {credentials[0]}")
    server_id, agent_token = credentials
    backup_check_due = 0.0
    while True:
        try:
            send_once(config, server_id, agent_token)
            while process_scan_job(config, server_id, agent_token):
                pass
            if config.backup_targets and time.monotonic() >= backup_check_due:
                send_backup_checks(config, server_id, agent_token)
                backup_check_due = time.monotonic() + 3600
        except (RuntimeError, OSError, ValueError) as exc:
            print(f"Erreur temporaire: {exc}", flush=True)
        if once:
            return
        time.sleep(config.interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent local CyberPME Africa")
    parser.add_argument("--once", action="store_true", help="Exécuter un cycle puis s’arrêter")
    parser.add_argument("--interval", type=int, help="Secondes entre deux cycles")
    parser.add_argument("--config", type=Path, help="Chemin du fichier de configuration JSON")
    parser.add_argument("--register-only", action="store_true", help="Associer ce PC sans lancer de tâche")
    args = parser.parse_args()
    if args.interval is not None and args.interval < 10:
        parser.error("L’intervalle minimum est de 10 secondes.")
    try:
        config = Config.from_sources(args.config, args.interval)
        if config.interval < 10:
            raise ValueError("L’intervalle minimum est de 10 secondes.")
        if args.register_only:
            register_agent(config)
        else:
            run(config, args.once)
    except (RuntimeError, ValueError, OSError, json.JSONDecodeError) as exc:
        parser.exit(1, f"Erreur: {exc}\n")


if __name__ == "__main__":
    main()
