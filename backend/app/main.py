from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import UUID
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.config import settings
from app.database import Base, engine, get_db
from app.email_notifications import send_alert_email
from app.models import Alert, Metric, Server
from app.schemas import AlertRead, MetricCreate, MetricRead, ServerCreate, ServerRead


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


@app.post("/api/v1/servers/{server_id}/metrics", response_model=MetricRead, status_code=status.HTTP_201_CREATED)
def create_metric(server_id: UUID, payload: MetricCreate, db: Session = Depends(get_db)) -> Metric:
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Serveur introuvable.")
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
