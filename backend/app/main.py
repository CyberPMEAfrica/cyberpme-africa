from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import secrets
from uuid import UUID
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.config import settings
from app.database import Base, engine, get_db
from app.email_notifications import send_alert_email
from app.models import AgentCredential, Alert, Metric, NetworkScan, Server
from app.network_scanner import run_network_scan, validate_private_target
from app.network_report import build_network_scan_pdf
from app.schemas import (
    AgentRegistration,
    AgentRegistrationRead,
    AlertRead,
    MetricCreate,
    MetricRead,
    NetworkScanCreate,
    NetworkScanRead,
    ServerCreate,
    ServerRead,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def server_response(db: Session, server: Server) -> ServerRead:
    latest = db.scalar(select(Metric).where(Metric.server_id == server.id).order_by(Metric.collected_at.desc()).limit(1))
    data = ServerRead.model_validate(server)
    return data.model_copy(update={"latest_metric": MetricRead.model_validate(latest) if latest else None})


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def require_agent(server: Server, authorization: str | None) -> None:
    if not authorization or not authorization.startswith("Bearer ") or server.credential is None:
        raise HTTPException(status_code=401, detail="Jeton agent requis.")
    supplied_hash = token_hash(authorization.removeprefix("Bearer ").strip())
    if not hmac.compare_digest(supplied_hash, server.credential.token_hash):
        raise HTTPException(status_code=401, detail="Jeton agent invalide.")


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Bienvenue sur CyberPME Africa"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/servers", response_model=ServerRead, status_code=status.HTTP_201_CREATED)
def create_server(payload: ServerCreate, db: Session = Depends(get_db)) -> ServerRead:
    server = Server(**payload.model_dump())
    db.add(server)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ce hostname existe déjà.") from exc
    db.refresh(server)
    return server_response(db, server)


@app.get("/api/v1/servers", response_model=list[ServerRead])
def list_servers(db: Session = Depends(get_db)) -> list[ServerRead]:
    servers = db.scalars(select(Server).order_by(Server.created_at.desc())).all()
    return [server_response(db, server) for server in servers]


@app.post("/api/v1/agents/register", response_model=AgentRegistrationRead)
def register_agent(payload: AgentRegistration, x_enrollment_key: str | None = Header(default=None), db: Session = Depends(get_db)) -> AgentRegistrationRead:
    if not x_enrollment_key or not hmac.compare_digest(x_enrollment_key, settings.agent_enrollment_key):
        raise HTTPException(status_code=401, detail="Clé d’enrôlement invalide.")
    server = db.scalar(select(Server).where(Server.hostname == payload.hostname))
    if server is None:
        server = Server(**payload.model_dump())
        db.add(server)
        db.flush()
    else:
        server.name = payload.name
        server.ip_address = payload.ip_address
    raw_token = secrets.token_urlsafe(32)
    if server.credential is None:
        server.credential = AgentCredential(token_hash=token_hash(raw_token))
    else:
        server.credential.token_hash = token_hash(raw_token)
        server.credential.created_at = datetime.now(timezone.utc)
    db.commit()
    return AgentRegistrationRead(server_id=server.id, agent_token=raw_token)


ALERT_RULES = {
    "cpu": ("son processeur", "Vérifiez les processus les plus actifs et arrêtez les applications inutiles."),
    "memory": ("sa mémoire vive", "Fermez les applications inutiles ou augmentez la mémoire disponible."),
    "disk": ("son espace disque", "Supprimez ou archivez les fichiers inutiles afin de libérer de l’espace."),
}


def update_alerts(db: Session, server: Server, values: dict[str, float], now: datetime) -> list[tuple[str, Alert]]:
    events: list[tuple[str, Alert]] = []
    for resource, value in (("cpu", values["cpu_percent"]), ("memory", values["memory_percent"]), ("disk", values["disk_percent"])):
        active = db.scalar(select(Alert).where(Alert.server_id == server.id, Alert.resource == resource, Alert.status == "active"))
        label, recommendation = ALERT_RULES[resource]
        if value >= 75:
            severity = "critical" if value >= 90 else "warning"
            message = f"{server.name} utilise {value:.1f} % de {label}."
            if active:
                active.value, active.severity, active.message = value, severity, message
            else:
                alert = Alert(server_id=server.id, resource=resource, severity=severity, value=value, message=message, recommendation=recommendation)
                db.add(alert)
                events.append(("created", alert))
        elif active:
            active.status, active.resolved_at = "resolved", now
            events.append(("resolved", active))
    return events


@app.get("/api/v1/alerts", response_model=list[AlertRead])
def list_alerts(active_only: bool = True, db: Session = Depends(get_db)) -> list[AlertRead]:
    query = select(Alert).order_by(Alert.created_at.desc())
    if active_only:
        query = query.where(Alert.status == "active")
    alerts = db.scalars(query).all()
    return [AlertRead.model_validate(alert).model_copy(update={"server_name": alert.server.name}) for alert in alerts]


def require_scan_key(x_scan_key: str | None) -> None:
    if not x_scan_key or not hmac.compare_digest(x_scan_key, settings.network_scan_key):
        raise HTTPException(status_code=401, detail="Clé d’audit réseau invalide.")


@app.post("/api/v1/network-scans", response_model=NetworkScanRead, status_code=status.HTTP_202_ACCEPTED)
def create_network_scan(
    payload: NetworkScanCreate,
    background_tasks: BackgroundTasks,
    x_scan_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> NetworkScan:
    require_scan_key(x_scan_key)
    try:
        target = validate_private_target(payload.target)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    active_scan = db.scalar(select(NetworkScan).where(NetworkScan.status.in_(("pending", "running"))))
    if active_scan is not None:
        raise HTTPException(status_code=409, detail="Un audit réseau est déjà en cours.")
    scan = NetworkScan(target=target)
    db.add(scan)
    db.commit()
    db.refresh(scan)
    background_tasks.add_task(run_network_scan, scan.id)
    return scan


@app.get("/api/v1/network-scans", response_model=list[NetworkScanRead])
def list_network_scans(db: Session = Depends(get_db)) -> list[NetworkScan]:
    return list(db.scalars(select(NetworkScan).order_by(NetworkScan.requested_at.desc())).all())


@app.get("/api/v1/network-scans/{scan_id}", response_model=NetworkScanRead)
def get_network_scan(scan_id: UUID, db: Session = Depends(get_db)) -> NetworkScan:
    scan = db.get(NetworkScan, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Audit réseau introuvable.")
    return scan


@app.get("/api/v1/network-scans/{scan_id}/report")
def get_network_scan_report(scan_id: UUID, db: Session = Depends(get_db)) -> Response:
    scan = db.get(NetworkScan, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Audit réseau introuvable.")
    if scan.status != "completed":
        raise HTTPException(status_code=409, detail="Le rapport sera disponible une fois l’audit terminé.")
    content = build_network_scan_pdf(scan)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="audit-reseau-{scan.id}.pdf"'},
    )


@app.post("/api/v1/servers/{server_id}/metrics", response_model=MetricRead, status_code=status.HTTP_201_CREATED)
def create_metric(
    server_id: UUID,
    payload: MetricCreate,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Metric:
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Serveur introuvable.")
    require_agent(server, authorization)
    values = payload.model_dump()
    metric = Metric(server_id=server.id, **values)
    highest = max(values.values())
    server.status = "critical" if highest >= 90 else "warning" if highest >= 75 else "online"
    now = datetime.now(timezone.utc)
    server.last_seen_at = now
    alert_events = update_alerts(db, server, values, now)
    db.add(metric)
    db.commit()
    db.refresh(metric)
    for event, alert in alert_events:
        send_alert_email(alert, server.name, event)
    return metric
