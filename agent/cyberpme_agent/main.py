import argparse
import json
import os
import platform
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import psutil


@dataclass(frozen=True)
class Config:
    api_url: str
    name: str
    hostname: str
    interval: int
    enrollment_key: str
    backup_targets: tuple[tuple[str, str, str, int], ...]

    @classmethod
    def from_environment(cls, interval_override: int | None = None) -> "Config":
        hostname = os.getenv("CYBERPME_HOSTNAME", socket.gethostname())
        targets = []
        for kind, variable in (("files", "CYBERPME_FILE_BACKUPS"), ("postgresql", "CYBERPME_POSTGRES_BACKUPS")):
            for item in filter(None, os.getenv(variable, "").split(";")):
                parts = item.split("|")
                if len(parts) != 3:
                    raise ValueError(f"{variable}: format attendu nom|chemin|heures.")
                targets.append((kind, parts[0].strip(), parts[1].strip(), int(parts[2])))
        return cls(
            api_url=os.getenv("CYBERPME_API_URL", "http://localhost:8000").rstrip("/"),
            name=os.getenv("CYBERPME_SERVER_NAME", hostname),
            hostname=hostname,
            interval=interval_override or int(os.getenv("CYBERPME_INTERVAL", "60")),
            enrollment_key=os.getenv("CYBERPME_ENROLLMENT_KEY", ""),
            backup_targets=tuple(targets),
        )


def request_json(method: str, url: str, payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = Request(url, data=data, method=method, headers=request_headers)
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"L’API a répondu {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Impossible de joindre l’API {url}: {exc.reason}") from exc


def discover_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.connect(("8.8.8.8", 80))
            return connection.getsockname()[0]
    except OSError:
        return None


def register_agent(config: Config) -> tuple[str, str]:
    if not config.enrollment_key:
        raise RuntimeError("CYBERPME_ENROLLMENT_KEY doit être configurée.")
    registration = request_json(
        "POST",
        f"{config.api_url}/api/v1/agents/register",
        {"name": config.name, "hostname": config.hostname, "ip_address": discover_ip()},
        {"X-Enrollment-Key": config.enrollment_key},
    )
    return registration["server_id"], registration["agent_token"]


def collect_metrics() -> dict[str, float]:
    return {
        "cpu_percent": round(psutil.cpu_percent(interval=1), 1),
        "memory_percent": round(psutil.virtual_memory().percent, 1),
        "disk_percent": round(psutil.disk_usage(Path.home().anchor).percent, 1),
    }


def send_once(config: Config, server_id: str, agent_token: str) -> dict[str, Any]:
    metrics = collect_metrics()
    result = request_json(
        "POST",
        f"{config.api_url}/api/v1/servers/{server_id}/metrics",
        metrics,
        {"Authorization": f"Bearer {agent_token}"},
    )
    print(
        f"Mesure envoyée — CPU {metrics['cpu_percent']} % | "
        f"RAM {metrics['memory_percent']} % | Disque {metrics['disk_percent']} %",
        flush=True,
    )
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
        return {
            "name": name, "kind": kind, "source": str(path), "exists": False, "size_bytes": None,
            "last_success_at": None, "max_age_hours": max_age_hours, "error": str(exc),
        }


def send_backup_checks(config: Config, server_id: str, agent_token: str) -> None:
    for target in config.backup_targets:
        payload = inspect_backup(*target)
        result = request_json(
            "POST", f"{config.api_url}/api/v1/servers/{server_id}/backup-checks", payload,
            {"Authorization": f"Bearer {agent_token}"},
        )
        print(f"Sauvegarde vérifiée — {payload['name']} : {result['status']}", flush=True)


def run(config: Config, once: bool) -> None:
    print(f"CyberPME Agent 0.1.0 — {platform.system()} {platform.release()}")
    print(f"Serveur: {config.name} ({config.hostname}) | API: {config.api_url}")
    server_id, agent_token = register_agent(config)
    print(f"Enregistrement confirmé — identifiant {server_id}")

    backup_check_due = 0.0
    while True:
        try:
            send_once(config, server_id, agent_token)
            if config.backup_targets and time.monotonic() >= backup_check_due:
                send_backup_checks(config, server_id, agent_token)
                backup_check_due = time.monotonic() + 3600
        except RuntimeError as exc:
            print(f"Erreur temporaire: {exc}", flush=True)
        if once:
            return
        time.sleep(config.interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent de supervision CyberPME Africa")
    parser.add_argument("--once", action="store_true", help="Envoyer une mesure puis s’arrêter")
    parser.add_argument("--interval", type=int, help="Secondes entre deux mesures")
    args = parser.parse_args()
    if args.interval is not None and args.interval < 10:
        parser.error("L’intervalle minimum est de 10 secondes.")
    try:
        run(Config.from_environment(args.interval), args.once)
    except (RuntimeError, ValueError) as exc:
        parser.exit(1, f"Erreur: {exc}\n")


if __name__ == "__main__":
    main()
