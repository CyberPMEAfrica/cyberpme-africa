"""Explicitly approved, tenant-scoped local agent operations.

No arbitrary command, path or credential is accepted from the browser.
Local profiles are the final authorization boundary on the agent.
"""
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_serializer
from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, select, update
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.database import Base, get_db
from app.models import Organization, SecurityEvent, Server, utc_now


class ManagedAction(Base):
    __tablename__ = 'managed_actions'
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey('organizations.id'), index=True)
    server_id: Mapped[UUID] = mapped_column(ForeignKey('servers.id'), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24), default='proposed', index=True)
    profile: Mapped[str | None] = mapped_column(String(64))
    snapshot: Mapped[str | None] = mapped_column(String(64))
    source_ip: Mapped[str | None] = mapped_column(String(45))
    event_id: Mapped[UUID | None] = mapped_column(ForeignKey('security_events.id'))
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey('managed_actions.id'))
    duration_minutes: Mapped[int] = mapped_column(default=15)
    reason: Mapped[str] = mapped_column(Text)
    proposed_by: Mapped[str] = mapped_column(String(254))
    approved_by: Mapped[str | None] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict] = mapped_column(JSON, default=dict)


class ActionCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    server_id: UUID
    kind: Literal['backup', 'restore_test', 'firewall_block']
    profile: str | None = Field(default=None, pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    snapshot: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    event_id: UUID | None = None
    duration_minutes: int = Field(default=15, ge=1, le=60)
    reason: str = Field(min_length=10, max_length=1000)

    @model_validator(mode='after')
    def validate_fields(self):
        if self.kind == 'firewall_block':
            if not self.event_id or self.profile or self.snapshot:
                raise ValueError('Le blocage doit être lié à un événement IDS.')
        elif not self.profile or self.event_id:
            raise ValueError('Un profil local de sauvegarde est requis.')
        if (self.kind == 'restore_test') != bool(self.snapshot):
            raise ValueError('Une restauration exige un identifiant complet de snapshot.')
        return self


class ActionResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['completed', 'failed', 'uncertain']
    message: str = Field(max_length=1000)
    snapshot: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')


class ActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    server_id: UUID
    kind: str
    status: str
    profile: str | None
    snapshot: str | None
    source_ip: str | None
    event_id: UUID | None
    parent_id: UUID | None
    duration_minutes: int
    reason: str
    proposed_by: str
    approved_by: str | None
    created_at: datetime
    expires_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    result: dict

    @field_serializer('created_at', 'expires_at', 'started_at', 'completed_at')
    def utc_dates(self, value):
        if value is None: return None
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


def install_routes(app, require_user, require_agent, require_role, record_audit):
    router = APIRouter(prefix='/api/v1')

    def expire(db, org_id):
        now = utc_now()
        db.execute(update(ManagedAction).where(
            ManagedAction.organization_id == org_id,
            ManagedAction.status == 'approved', ManagedAction.expires_at <= now,
        ).values(status='cancelled', result={'message': 'Délai de prise en charge expiré.'}))
        db.execute(update(ManagedAction).where(
            ManagedAction.organization_id == org_id,
            ManagedAction.status == 'running', ManagedAction.started_at < now-timedelta(hours=3),
        ).values(status='uncertain', result={'message': 'Résultat non reçu. Vérifier le journal local avant toute nouvelle action.'}))

    def owned(db, org, action_id):
        row = db.scalar(select(ManagedAction).where(ManagedAction.id == action_id, ManagedAction.organization_id == org.id).with_for_update())
        if not row:
            raise HTTPException(404, 'Action introuvable.')
        return row

    def audit(db, user, org, row, verb):
        record_audit(db, org, user.email, user.role, 'managed_action.'+verb, 'managed_action', row.id,
                     {'kind': row.kind, 'server_id': str(row.server_id)})

    @router.get('/managed-actions', response_model=list[ActionRead])
    def listing(context=Depends(require_user), db: Session=Depends(get_db)):
        _, org = context
        expire(db, org.id)
        db.commit()
        return list(db.scalars(select(ManagedAction).where(ManagedAction.organization_id == org.id).order_by(ManagedAction.created_at.desc()).limit(100)))

    @router.post('/managed-actions', response_model=ActionRead, status_code=201)
    def propose(payload: ActionCreate, context=Depends(require_user), db: Session=Depends(get_db)):
        user, org = context
        require_role(user, 'owner', 'admin', 'analyst')
        server = db.scalar(select(Server).where(Server.id == payload.server_id, Server.organization_id == org.id))
        if not server or not server.credential:
            raise HTTPException(404, 'Agent introuvable.')
        source = None
        if payload.kind == 'firewall_block':
            event = db.scalar(select(SecurityEvent).where(SecurityEvent.id == payload.event_id, SecurityEvent.server_id == server.id))
            if not event or not event.source_ip:
                raise HTTPException(422, 'Événement sans adresse source utilisable pour cet agent.')
            try:
                address = ip_address(event.source_ip)
                if address.version != 4 or not address.is_global or address.is_multicast:
                    raise ValueError()
                source = str(address)
            except ValueError:
                raise HTTPException(422, 'Cette version ne bloque que des IPv4 publiques individuelles ; les réseaux privés restent protégés.')
        row = ManagedAction(**payload.model_dump(), source_ip=source, organization_id=org.id, proposed_by=user.email)
        db.add(row); db.flush(); audit(db, user, org, row, 'proposed'); db.commit(); db.refresh(row)
        return row

    @router.post('/managed-actions/{action_id}/approve', response_model=ActionRead)
    def approve(action_id: UUID, context=Depends(require_user), db: Session=Depends(get_db)):
        user, org = context
        require_role(user, 'owner', 'admin')
        row = owned(db, org, action_id)
        if row.status != 'proposed':
            raise HTTPException(409, 'Cette action ne peut plus être approuvée.')
        if row.kind == 'firewall_block':
            db.scalar(select(Server).where(Server.id == row.server_id).with_for_update())
            duplicate = db.scalar(select(ManagedAction.id).where(
                ManagedAction.server_id == row.server_id,
                ManagedAction.source_ip == row.source_ip,
                ManagedAction.id != row.id,
                ManagedAction.kind.in_(['firewall_block', 'firewall_unblock']),
                ManagedAction.status.in_(['approved', 'running', 'completed', 'uncertain']),
                ManagedAction.expires_at > utc_now()))
            if duplicate:
                raise HTTPException(409, 'Une autorisation existe déjà pour cette adresse. Attendre son échéance.')
        row.status = 'approved'; row.approved_by = user.email; row.approved_at = utc_now()
        row.expires_at = row.approved_at + timedelta(minutes=row.duration_minutes if row.kind == 'firewall_block' else 30)
        audit(db, user, org, row, 'approved'); db.commit(); db.refresh(row)
        return row

    @router.post('/managed-actions/{action_id}/cancel', response_model=ActionRead)
    def cancel(action_id: UUID, context=Depends(require_user), db: Session=Depends(get_db)):
        user, org = context
        require_role(user, 'owner', 'admin')
        row = owned(db, org, action_id)
        if row.status in ('proposed', 'approved'):
            row.status = 'cancelled'
        elif row.kind == 'firewall_block' and row.status in ('running', 'completed', 'uncertain'):
            prior = db.scalar(select(ManagedAction).where(ManagedAction.parent_id == row.id))
            if prior:
                return prior
            row = ManagedAction(organization_id=org.id, server_id=row.server_id, parent_id=row.id,
                kind='firewall_unblock', status='approved', source_ip=row.source_ip, reason='Annulation du blocage temporaire',
                proposed_by=user.email, approved_by=user.email, approved_at=utc_now(), expires_at=row.expires_at)
            db.add(row); db.flush()
        else:
            raise HTTPException(409, 'Opération déjà exécutée ou en cours ; aucune interruption destructive à distance.')
        audit(db, user, org, row, 'cancel_requested'); db.commit(); db.refresh(row)
        return row

    def agent_server(db, server_id, authorization):
        server = db.get(Server, server_id)
        if not server:
            raise HTTPException(404, 'Agent introuvable.')
        require_agent(server, authorization)
        return server

    @router.get('/servers/{server_id}/managed-actions/next', response_model=ActionRead | None)
    def next_action(server_id: UUID, authorization: str | None=Header(default=None), db: Session=Depends(get_db)):
        server = agent_server(db, server_id, authorization)
        db.scalar(select(Server).where(Server.id == server_id).with_for_update())
        expire(db, server.organization_id)
        active = db.scalar(select(ManagedAction.id).where(ManagedAction.server_id == server_id, ManagedAction.status == 'running'))
        if active:
            db.commit(); return None
        row = db.scalar(select(ManagedAction).where(ManagedAction.server_id == server_id, ManagedAction.status == 'approved').order_by(ManagedAction.created_at).limit(1).with_for_update())
        if row:
            claimed = db.execute(update(ManagedAction).where(
                ManagedAction.id == row.id, ManagedAction.status == 'approved'
            ).values(status='running', started_at=utc_now()))
            if claimed.rowcount != 1:
                db.rollback(); return None
        db.commit()
        if row: db.refresh(row)
        return row

    @router.post('/servers/{server_id}/managed-actions/{action_id}/complete', response_model=ActionRead)
    def complete(server_id: UUID, action_id: UUID, payload: ActionResult, authorization: str | None=Header(default=None), db: Session=Depends(get_db)):
        server = agent_server(db, server_id, authorization)
        row = db.scalar(select(ManagedAction).where(ManagedAction.id == action_id, ManagedAction.server_id == server.id).with_for_update())
        if not row: raise HTTPException(404, 'Action introuvable.')
        result = payload.model_dump(exclude={'status'})
        if row.status in ('completed','failed'):
            if row.status == payload.status and row.result == result: return row
            raise HTTPException(409, 'Résultat déjà enregistré.')
        if row.status not in ('running', 'uncertain'): raise HTTPException(409, 'Action non distribuée.')
        row.status=payload.status; row.result=result; row.completed_at=utc_now()
        record_audit(db, db.get(Organization, server.organization_id), 'agent:'+str(server.id), 'agent',
                     'managed_action.'+payload.status, 'managed_action', row.id, {'kind':row.kind})
        db.commit(); db.refresh(row)
        return row

    app.include_router(router)
