from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
import ssl
from urllib.parse import quote
from uuid import UUID
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.config import settings
from app.auth import hash_password, hash_session_token, issue_session_token, verify_password
from app.database import get_db
from app.email_notifications import send_alert_email, send_invitation_email
from app.models import AgentCredential, Alert, AuditEntry, BackupCheck, IdsConnector, Metric, NetworkScan, Organization, SecurityEvent, Server, SslCheck, User, UserInvitation, UserSession
from app.network_scanner import run_network_scan, validate_private_target
from app.network_report import build_network_scan_pdf
from app.schemas import (
    AgentRegistration,
    AgentRegistrationRead,
    AlertRead,
    AuditEntryRead,
    BackupCheckCreate,
    BackupCheckRead,
    IdsConnectorCreate,
    IdsConnectorCreated,
    IdsConnectorRead,
    IdsConnectorTokenRotated,
    IdsConnectorTokenRotation,
    InvitationAccept,
    InvitationCreate,
    InvitationCreated,
    InvitationPreview,
    InvitationRead,
    MetricCreate,
    MetricRead,
    NetworkScanCreate,
    NetworkScanRead,
    SecurityEventCreate,
    SecurityEventRead,
    SecurityIncidentUpdate,
    CurrentUserRead,
    LoginRequest,
    OrganizationRead,
    OrganizationUpdate,
    PasswordChange,
    SessionRead,
    ServerCreate,
    ServerRead,
    SslCheckCreate,
    SslCheckRead,
    UserCreate,
    UserRead,
    UserPreferenceUpdate,
    UserUpdate,
)
from app.ssl_monitor import inspect_certificate, validate_public_hostname


@asynccontextmanager
async def lifespan(_: FastAPI):
    with next(get_db()) as db:
        organization = db.scalar(select(Organization).where(Organization.slug == settings.bootstrap_organization_slug))
        if organization is None:
            organization = Organization(
                name=settings.bootstrap_organization_name,
                slug=settings.bootstrap_organization_slug,
            )
            db.add(organization)
            db.flush()
        organization.enrollment_key_hash = token_hash(settings.agent_enrollment_key)
        organization.scan_key_hash = token_hash(settings.network_scan_key)
        db.commit()
    if settings.bootstrap_admin_email and settings.bootstrap_admin_password:
        with next(get_db()) as db:
            organization = db.scalar(select(Organization).where(Organization.slug == settings.bootstrap_organization_slug))
            user = db.scalar(
                select(User).where(
                    User.organization_id == organization.id,
                    User.email == settings.bootstrap_admin_email.lower(),
                )
            )
            if user is None:
                db.add(
                    User(
                        organization_id=organization.id,
                        email=settings.bootstrap_admin_email.lower(),
                        password_hash=hash_password(settings.bootstrap_admin_password),
                        role="owner",
                    )
                )
            elif settings.bootstrap_admin_force_sync:
                password_changed = not verify_password(
                    settings.bootstrap_admin_password,
                    user.password_hash,
                )
                if password_changed:
                    user.password_hash = hash_password(settings.bootstrap_admin_password)
                    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
                user.role = "owner"
                user.is_active = True
            db.commit()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> tuple[User, Organization]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentification requise.")
    supplied = authorization.removeprefix("Bearer ").strip()
    session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_session_token(supplied)))
    now = datetime.now(timezone.utc)
    if session is None:
        raise HTTPException(status_code=401, detail="Session invalide ou expirée.")
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        db.delete(session)
        db.commit()
        raise HTTPException(status_code=401, detail="Session invalide ou expirée.")
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Compte indisponible.")
    organization = db.get(Organization, user.organization_id)
    if organization is None:
        raise HTTPException(status_code=401, detail="Organisation indisponible.")
    return user, organization


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


def backup_response(db: Session, check: BackupCheck) -> BackupCheckRead:
    data = BackupCheckRead.model_validate(check)
    server = db.get(Server, check.server_id)
    return data.model_copy(update={"server_name": server.name if server else ""})


def security_event_response(db: Session, event: SecurityEvent) -> SecurityEventRead:
    data = SecurityEventRead.model_validate(event)
    server = db.get(Server, event.server_id)
    return data.model_copy(update={"server_name": server.name if server else ""})


def ids_connector_response(db: Session, connector: IdsConnector) -> IdsConnectorRead:
    data = IdsConnectorRead.model_validate(connector)
    server = db.get(Server, connector.server_id)
    return data.model_copy(update={"server_name": server.name if server else ""})


def require_role(user: User, *roles: str) -> None:
    if user.role not in roles:
        raise HTTPException(status_code=403, detail="Droits insuffisants pour cette action.")


def record_audit(
    db: Session,
    organization: Organization,
    actor_email: str,
    actor_role: str,
    action: str,
    target_type: str,
    target_id: UUID | str | None = None,
    details: dict | None = None,
) -> AuditEntry:
    entry = AuditEntry(
        organization_id=organization.id,
        actor_email=actor_email,
        actor_role=actor_role,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        details=details or {},
    )
    db.add(entry)
    return entry


def invitation_state(invitation: UserInvitation) -> str:
    now = datetime.now(timezone.utc)
    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if invitation.accepted_at is not None:
        return "accepted"
    if invitation.revoked_at is not None:
        return "revoked"
    if expires_at <= now:
        return "expired"
    return "pending"


def invitation_response(
    invitation: UserInvitation,
    email_sent: bool | None = None,
    invitation_url: str | None = None,
) -> InvitationRead | InvitationCreated:
    values = {
        "id": invitation.id,
        "email": invitation.email,
        "role": invitation.role,
        "invited_by_email": invitation.invited_by_email,
        "status": invitation_state(invitation),
        "expires_at": invitation.expires_at,
        "accepted_at": invitation.accepted_at,
        "created_at": invitation.created_at,
    }
    if email_sent is not None:
        return InvitationCreated(
            **values,
            email_sent=email_sent,
            invitation_url=invitation_url,
        )
    return InvitationRead(**values)


SECURITY_RECOMMENDATIONS = {
    "authentication": "Vérifiez le compte ciblé, changez les identifiants compromis et activez l’authentification multifacteur.",
    "malware": "Isolez la machine concernée, lancez une analyse antivirus complète et conservez les éléments de preuve.",
    "network": "Vérifiez les flux réseau et les ports concernés. Ne bloquez l’adresse source qu’après validation.",
    "vulnerability": "Confirmez la vulnérabilité, appliquez le correctif disponible et limitez temporairement l’exposition du service.",
}


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Bienvenue sur CyberPME Africa"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/auth/login", response_model=SessionRead)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> SessionRead:
    organization = db.scalar(select(Organization).where(Organization.slug == payload.organization_slug.lower()))
    user = None
    if organization:
        user = db.scalar(
            select(User).where(
                User.organization_id == organization.id,
                User.email == payload.email.lower(),
            )
        )
    bootstrap_recovery = (
        settings.bootstrap_admin_force_sync
        and organization is not None
        and payload.organization_slug.lower() == settings.bootstrap_organization_slug.lower()
        and payload.email.lower() == settings.bootstrap_admin_email.lower()
        and bool(settings.bootstrap_admin_password)
        and hmac.compare_digest(payload.password, settings.bootstrap_admin_password)
    )
    if bootstrap_recovery:
        if user is None:
            user = User(
                organization_id=organization.id,
                email=payload.email.lower(),
                password_hash=hash_password(settings.bootstrap_admin_password),
                role="owner",
            )
            db.add(user)
            db.flush()
        else:
            user.password_hash = hash_password(settings.bootstrap_admin_password)
            user.role = "owner"
            user.is_active = True
            db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Identifiants invalides.")
    raw_token, token_digest = issue_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=12)
    db.add(UserSession(user_id=user.id, token_hash=token_digest, expires_at=expires_at))
    record_audit(
        db,
        organization,
        user.email,
        user.role,
        "auth.login",
        "user",
        user.id,
    )
    db.commit()
    return SessionRead(access_token=raw_token, expires_at=expires_at)


@app.get("/api/v1/auth/me", response_model=CurrentUserRead)
def current_user(context: tuple[User, Organization] = Depends(require_user)) -> CurrentUserRead:
    user, organization = context
    return CurrentUserRead(
        id=user.id,
        organization_id=organization.id,
        organization_name=organization.name,
        email=user.email,
        role=user.role,
        theme=user.theme,
    )


@app.patch("/api/v1/auth/preferences", response_model=CurrentUserRead)
def update_user_preferences(
    payload: UserPreferenceUpdate,
    context: tuple[User, Organization] = Depends(require_user),
    db: Session = Depends(get_db),
) -> CurrentUserRead:
    user, organization = context
    previous_theme = user.theme
    user.theme = payload.theme
    if previous_theme != payload.theme:
        record_audit(
            db,
            organization,
            user.email,
            user.role,
            "user.theme_changed",
            "user",
            user.id,
            {"previous_theme": previous_theme, "theme": payload.theme},
        )
    db.commit()
    db.refresh(user)
    return CurrentUserRead(
        id=user.id,
        organization_id=organization.id,
        organization_name=organization.name,
        email=user.email,
        role=user.role,
        theme=user.theme,
    )


@app.post("/api/v1/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    authorization: str | None = Header(default=None),
    context: tuple[User, Organization] = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    user, organization = context
    token = authorization.removeprefix("Bearer ").strip() if authorization else ""
    session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_session_token(token)))
    if session:
        db.delete(session)
    record_audit(
        db,
        organization,
        user.email,
        user.role,
        "auth.logout",
        "user",
        user.id,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/v1/auth/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChange,
    context: tuple[User, Organization] = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    user, organization = context
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Le mot de passe actuel est incorrect.")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="Le nouveau mot de passe doit Ãªtre diffÃ©rent.")
    user.password_hash = hash_password(payload.new_password)
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    record_audit(
        db,
        organization,
        user.email,
        user.role,
        "auth.password_changed",
        "user",
        user.id,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/v1/organization", response_model=OrganizationRead)
def get_organization(
    context: tuple[User, Organization] = Depends(require_user),
) -> OrganizationRead:
    _, organization = context
    return OrganizationRead.model_validate(organization)


@app.get("/api/v1/audit-entries", response_model=list[AuditEntryRead])
def list_audit_entries(
    limit: int = 100,
    context: tuple[User, Organization] = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[AuditEntry]:
    user, organization = context
    require_role(user, "owner", "admin")
    safe_limit = max(1, min(limit, 250))
    return list(
        db.scalars(
            select(AuditEntry)
            .where(AuditEntry.organization_id == organization.id)
            .order_by(AuditEntry.created_at.desc())
            .limit(safe_limit)
        )
    )


@app.patch("/api/v1/organization", response_model=OrganizationRead)
def update_organization(
    payload: OrganizationUpdate,
    context: tuple[User, Organization] = Depends(require_user),
    db: Session = Depends(get_db),
) -> OrganizationRead:
    user, organization = context
    require_role(user, "owner")
    normalized_name = payload.name.strip()
    if len(normalized_name) < 2:
        raise HTTPException(status_code=422, detail="Le nom de la PME doit contenir au moins 2 caractÃ¨res.")
    previous_name = organization.name
    organization.name = normalized_name
    record_audit(
        db,
        organization,
        user.email,
        user.role,
        "organization.renamed",
        "organization",
        organization.id,
        {"previous_name": previous_name, "new_name": normalized_name},
    )
    db.commit()
    db.refresh(organization)
    return OrganizationRead.model_validate(organization)


@app.get("/api/v1/users", response_model=list[UserRead])
def list_users(
    context: tuple[User, Organization] = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[User]:
    user, organization = context
    require_role(user, "owner", "admin")
    return list(
        db.scalars(
            select(User)
            .where(User.organization_id == organization.id)
            .order_by(User.created_at.asc())
        )
    )


@app.post("/api/v1/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    context: tuple[User, Organization] = Depends(require_user),
    db: Session = Depends(get_db),
) -> User:
    actor, organization = context
    require_role(actor, "owner", "admin")
    if actor.role == "admin" and payload.role == "admin":
        raise HTTPException(status_code=403, detail="Seul le propriÃ©taire peut nommer un administrateur.")
    user = User(
        organization_id=organization.id,
        email=payload.email.strip().lower(),
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    try:
        db.flush()
        record_audit(
            db,
            organization,
            actor.email,
            actor.role,
            "user.created",
            "user",
            user.id,
            {"email": user.email, "role": user.role},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Cette adresse e-mail existe dÃ©jÃ  dans la PME.") from exc
    db.refresh(user)
    return user


@app.patch("/api/v1/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: UUID,
    payload: UserUpdate,
    context: tuple[User, Organization] = Depends(require_user),
    db: Session = Depends(get_db),
) -> User:
    actor, organization = context
    require_role(actor, "owner", "admin")
    target = db.scalar(
        select(User).where(User.id == user_id, User.organization_id == organization.id)
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
    if target.id == actor.id or target.role == "owner":
        raise HTTPException(status_code=400, detail="Le compte propriÃ©taire actif ne peut pas Ãªtre modifiÃ© ici.")
    if actor.role == "admin" and (target.role == "admin" or payload.role == "admin"):
        raise HTTPException(status_code=403, detail="Seul le propriÃ©taire peut gÃ©rer les administrateurs.")
    previous_role = target.role
    previous_active = target.is_active
    if payload.role is not None:
        target.role = payload.role
    if payload.is_active is not None:
        target.is_active = payload.is_active
        if not target.is_active:
            db.execute(delete(UserSession).where(UserSession.user_id == target.id))
    changes = {}
    if target.role != previous_role:
        changes["role"] = {"from": previous_role, "to": target.role}
    if target.is_active != previous_active:
        changes["is_active"] = {"from": previous_active, "to": target.is_active}
    if changes:
        record_audit(
            db,
            organization,
            actor.email,
            actor.role,
            "user.updated",
            "user",
            target.id,
            {"email": target.email, "changes": changes},
        )
    db.commit()
    db.refresh(target)
    return target


@app.get("/api/v1/invitations", response_model=list[InvitationRead])
def list_invitations(
    context: tuple[User, Organization] = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[InvitationRead]:
    actor, organization = context
    require_role(actor, "owner", "admin")
    invitations = db.scalars(
        select(UserInvitation)
        .where(UserInvitation.organization_id == organization.id)
        .order_by(UserInvitation.created_at.desc())
        .limit(50)
    )
    return [invitation_response(invitation) for invitation in invitations]


@app.post("/api/v1/invitations", response_model=InvitationCreated, status_code=status.HTTP_201_CREATED)
def create_invitation(
    payload: InvitationCreate,
    context: tuple[User, Organization] = Depends(require_user),
    db: Session = Depends(get_db),
) -> InvitationCreated:
    actor, organization = context
    require_role(actor, "owner", "admin")
    if actor.role == "admin" and payload.role == "admin":
        raise HTTPException(status_code=403, detail="Seul le propriÃ©taire peut inviter un administrateur.")
    email = payload.email.strip().lower()
    existing_user = db.scalar(
        select(User).where(User.organization_id == organization.id, User.email == email)
    )
    if existing_user is not None and existing_user.is_active:
        raise HTTPException(
            status_code=409,
            detail="Ce compte est dÃ©jÃ  actif. DÃ©sactivez-le d'abord pour lui envoyer une invitation de rÃ©activation.",
        )

    now = datetime.now(timezone.utc)
    previous_invitations = db.scalars(
        select(UserInvitation).where(
            UserInvitation.organization_id == organization.id,
            UserInvitation.email == email,
            UserInvitation.accepted_at.is_(None),
            UserInvitation.revoked_at.is_(None),
        )
    )
    for previous in previous_invitations:
        previous.revoked_at = now

    raw_token = secrets.token_urlsafe(32)
    invitation = UserInvitation(
        organization_id=organization.id,
        email=email,
        role=payload.role,
        token_hash=token_hash(raw_token),
        invited_by_email=actor.email,
        expires_at=now + timedelta(hours=24),
    )
    db.add(invitation)
    db.flush()
    record_audit(
        db,
        organization,
        actor.email,
        actor.role,
        "invitation.created",
        "invitation",
        invitation.id,
        {"email": email, "role": payload.role, "expires_at": invitation.expires_at.isoformat()},
    )
    db.commit()
    db.refresh(invitation)

    invitation_url = (
        f"{settings.frontend_public_url.rstrip('/')}/#/invite?token={quote(raw_token, safe='')}"
    )
    email_sent = send_invitation_email(
        recipient=email,
        organization_name=organization.name,
        role=payload.role,
        invited_by=actor.email,
        invitation_url=invitation_url,
    )
    return invitation_response(
        invitation,
        email_sent=email_sent,
        invitation_url=None if email_sent else invitation_url,
    )


def get_valid_invitation(raw_token: str, db: Session) -> tuple[UserInvitation, Organization]:
    invitation = db.scalar(
        select(UserInvitation).where(UserInvitation.token_hash == token_hash(raw_token))
    )
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation introuvable.")
    state = invitation_state(invitation)
    if state != "pending":
        messages = {
            "accepted": "Cette invitation a dÃ©jÃ  Ã©tÃ© utilisÃ©e.",
            "revoked": "Cette invitation a Ã©tÃ© remplacÃ©e ou rÃ©voquÃ©e.",
            "expired": "Cette invitation a expirÃ©. Demandez-en une nouvelle.",
        }
        raise HTTPException(status_code=410, detail=messages[state])
    organization = db.get(Organization, invitation.organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organisation introuvable.")
    return invitation, organization


@app.get("/api/v1/invitations/preview", response_model=InvitationPreview)
def preview_invitation(
    token: str,
    db: Session = Depends(get_db),
) -> InvitationPreview:
    invitation, organization = get_valid_invitation(token, db)
    return InvitationPreview(
        organization_name=organization.name,
        organization_slug=organization.slug,
        email=invitation.email,
        role=invitation.role,
        expires_at=invitation.expires_at,
    )


@app.post("/api/v1/invitations/accept", response_model=SessionRead)
def accept_invitation(
    payload: InvitationAccept,
    db: Session = Depends(get_db),
) -> SessionRead:
    invitation, organization = get_valid_invitation(payload.token, db)
    existing_user = db.scalar(
        select(User).where(
            User.organization_id == organization.id,
            User.email == invitation.email,
        )
    )
    if existing_user is not None and existing_user.is_active:
        raise HTTPException(status_code=409, detail="Un compte actif existe dÃ©jÃ  pour cette adresse.")
    if existing_user is None:
        user = User(
            organization_id=organization.id,
            email=invitation.email,
            password_hash=hash_password(payload.password),
            role=invitation.role,
        )
        db.add(user)
        db.flush()
    else:
        user = existing_user
        user.password_hash = hash_password(payload.password)
        user.role = invitation.role
        user.is_active = True
    invitation.accepted_at = datetime.now(timezone.utc)
    raw_session, session_digest = issue_session_token()
    session_expires_at = datetime.now(timezone.utc) + timedelta(hours=12)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=session_digest,
            expires_at=session_expires_at,
        )
    )
    record_audit(
        db,
        organization,
        user.email,
        user.role,
        "invitation.accepted",
        "invitation",
        invitation.id,
        {"email": user.email, "role": user.role},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Un compte existe dÃ©jÃ  pour cette adresse.") from exc
    return SessionRead(access_token=raw_session, expires_at=session_expires_at)


@app.post("/api/v1/servers", response_model=ServerRead, status_code=status.HTTP_201_CREATED)
def create_server(
    payload: ServerCreate,
    context: tuple[User, Organization] = Depends(require_user),
    db: Session = Depends(get_db),
) -> ServerRead:
    _, organization = context
    server = Server(organization_id=organization.id, **payload.model_dump())
    db.add(server)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ce hostname existe déjà.") from exc
    db.refresh(server)
    return server_response(db, server)


@app.get("/api/v1/servers", response_model=list[ServerRead])
def list_servers(
    context: tuple[User, Organization] = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[ServerRead]:
    _, organization = context
    servers = db.scalars(
        select(Server).where(Server.organization_id == organization.id).order_by(Server.created_at.desc())
    ).all()
    return [server_response(db, server) for server in servers]


@app.post("/api/v1/agents/register", response_model=AgentRegistrationRead)
def register_agent(payload: AgentRegistration, x_enrollment_key: str | None = Header(default=None), db: Session = Depends(get_db)) -> AgentRegistrationRead:
    supplied_hash = token_hash(x_enrollment_key or "")
    organization = db.scalar(select(Organization).where(Organization.enrollment_key_hash == supplied_hash))
    if organization is None or not x_enrollment_key or not hmac.compare_digest(supplied_hash, organization.enrollment_key_hash or ""):
        raise HTTPException(status_code=401, detail="Clé d’enrôlement invalide.")
    server = db.scalar(
        select(Server).where(Server.organization_id == organization.id, Server.hostname == payload.hostname)
    )
    if server is None:
        server = Server(organization_id=organization.id, **payload.model_dump())
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
def list_alerts(
    active_only: bool = True,
    context: tuple[User, Organization] = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[AlertRead]:
    _, organization = context
    query = (
        select(Alert)
        .join(Server, Alert.server_id == Server.id)
        .where(Server.organization_id == organization.id)
        .order_by(Alert.created_at.desc())
    )
    if active_only:
        query = query.where(Alert.status == "active")
    alerts = db.scalars(query).all()
    return [AlertRead.model_validate(alert).model_copy(update={"server_name": alert.server.name}) for alert in alerts]


def require_scan_key(db: Session, x_scan_key: str | None) -> Organization:
    supplied_hash = token_hash(x_scan_key or "")
    organization = db.scalar(select(Organization).where(Organization.scan_key_hash == supplied_hash))
    if organization is None or not x_scan_key or not hmac.compare_digest(supplied_hash, organization.scan_key_hash or ""):
        raise HTTPException(status_code=401, detail="Clé d’audit réseau invalide.")
    return organization


@app.post("/api/v1/network-scans", response_model=NetworkScanRead, status_code=status.HTTP_202_ACCEPTED)
def create_network_scan(
    payload: NetworkScanCreate,
    background_tasks: BackgroundTasks,
    x_scan_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> NetworkScan:
    organization = require_scan_key(db, x_scan_key)
    try:
        target = validate_private_target(payload.target)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    active_scan = db.scalar(
        select(NetworkScan).where(
            NetworkScan.organization_id == organization.id,
            NetworkScan.status.in_(("pending", "running")),
        )
    )
    if active_scan is not None:
        raise HTTPException(status_code=409, detail="Un audit réseau est déjà en cours.")
    scan = NetworkScan(organization_id=organization.id, target=target)
    db.add(scan)
    db.commit()
    db.refresh(scan)
    background_tasks.add_task(run_network_scan, scan.id)
    return scan


@app.get("/api/v1/network-scans", response_model=list[NetworkScanRead])
def list_network_scans(
    context: tuple[User, Organization] = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[NetworkScan]:
    _, organization = context
    return list(
        db.scalars(
            select(NetworkScan)
            .where(NetworkScan.organization_id == organization.id)
            .order_by(NetworkScan.requested_at.desc())
        ).all()
    )


@app.get("/api/v1/network-scans/{scan_id}", response_model=NetworkScanRead)
def get_network_scan(
    scan_id: UUID,
    context: tuple[User, Organization] = Depends(require_user),
    db: Session = Depends(get_db),
) -> NetworkScan:
    _, organization = context
    scan = db.scalar(
        select(NetworkScan).where(NetworkScan.id == scan_id, NetworkScan.organization_id == organization.id)
    )
    if scan is None:
        raise HTTPException(status_code=404, detail="Audit réseau introuvable.")
    return scan


@app.get("/api/v1/network-scans/{scan_id}/report")
def get_network_scan_report(
    scan_id: UUID,
    context: tuple[User, Organization] = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    _, organization = context
    scan = db.scalar(
        select(NetworkScan).where(NetworkScan.id == scan_id, NetworkScan.organization_id == organization.id)
    )
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


@app.post("/api/v1/ssl-checks", response_model=SslCheckRead, status_code=status.HTTP_201_CREATED)
def create_ssl_check(
    payload: SslCheckCreate,
    x_scan_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> SslCheck:
    organization = require_scan_key(db, x_scan_key)
    try:
        hostname, _ = validate_public_hostname(payload.hostname, payload.port)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        result = inspect_certificate(hostname, payload.port)
    except (OSError, ssl.SSLError, ValueError) as exc:
        result = {
            "status": "failed",
            "subject": None,
            "issuer": None,
            "valid_from": None,
            "expires_at": None,
            "days_remaining": None,
            "chain_valid": False,
            "tls_version": None,
            "cipher": None,
            "error": str(exc),
        }
    check = SslCheck(organization_id=organization.id, hostname=hostname, port=payload.port, **result)
    db.add(check)
    db.commit()
    db.refresh(check)
    return check


@app.get("/api/v1/ssl-checks", response_model=list[SslCheckRead])
def list_ssl_checks(
    context: tuple[User, Organization] = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[SslCheck]:
    _, organization = context
    return list(
        db.scalars(
            select(SslCheck)
            .where(SslCheck.organization_id == organization.id)
            .order_by(SslCheck.checked_at.desc())
        ).all()
    )


@app.post("/api/v1/servers/{server_id}/backup-checks", response_model=BackupCheckRead, status_code=status.HTTP_201_CREATED)
def create_backup_check(
    server_id: UUID,
    payload: BackupCheckCreate,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> BackupCheckRead:
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Serveur introuvable.")
    require_agent(server, authorization)
    now = datetime.now(timezone.utc)
    last_success = payload.last_success_at
    if last_success and last_success.tzinfo is None:
        last_success = last_success.replace(tzinfo=timezone.utc)
    fresh = bool(last_success and (now - last_success).total_seconds() <= payload.max_age_hours * 3600)
    check_status = "healthy" if payload.exists and payload.size_bytes and fresh and not payload.error else "critical"
    check = BackupCheck(server_id=server.id, status=check_status, **payload.model_dump(exclude={"last_success_at"}), last_success_at=last_success)
    db.add(check)
    db.commit()
    db.refresh(check)
    return backup_response(db, check)


@app.get("/api/v1/backup-checks", response_model=list[BackupCheckRead])
def list_backup_checks(
    context: tuple[User, Organization] = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[BackupCheckRead]:
    _, organization = context
    checks = db.scalars(
        select(BackupCheck)
        .join(Server, BackupCheck.server_id == Server.id)
        .where(Server.organization_id == organization.id)
        .order_by(BackupCheck.checked_at.desc())
        .limit(200)
    ).all()
    return [backup_response(db, check) for check in checks]


@app.post("/api/v1/servers/{server_id}/security-events", response_model=SecurityEventRead, status_code=status.HTTP_201_CREATED)
def create_security_event(
    server_id: UUID,
    payload: SecurityEventCreate,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> SecurityEventRead:
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Serveur introuvable.")
    require_agent(server, authorization)
    existing = db.scalar(select(SecurityEvent).where(SecurityEvent.server_id == server.id, SecurityEvent.event_key == payload.event_key))
    if existing:
        return security_event_response(db, existing)
    recommendation = SECURITY_RECOMMENDATIONS.get(
        payload.category.lower(),
        "Analysez l’événement, confirmez son origine et documentez toute action avant d’appliquer un blocage.",
    )
    event = SecurityEvent(server_id=server.id, recommendation=recommendation, **payload.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    return security_event_response(db, event)


@app.get("/api/v1/security-events", response_model=list[SecurityEventRead])
def list_security_events(
    context: tuple[User, Organization] = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[SecurityEventRead]:
    _, organization = context
    events = db.scalars(
        select(SecurityEvent)
        .join(Server, SecurityEvent.server_id == Server.id)
        .where(Server.organization_id == organization.id)
        .order_by(SecurityEvent.occurred_at.desc())
        .limit(500)
    ).all()
    return [security_event_response(db, event) for event in events]


@app.patch("/api/v1/security-events/{event_id}", response_model=SecurityEventRead)
def update_security_incident(
    event_id: UUID,
    payload: SecurityIncidentUpdate,
    context: tuple[User, Organization] = Depends(require_user),
    db: Session = Depends(get_db),
) -> SecurityEventRead:
    user, organization = context
    require_role(user, "owner", "admin", "analyst")
    event = db.scalar(
        select(SecurityEvent)
        .join(Server, SecurityEvent.server_id == Server.id)
        .where(SecurityEvent.id == event_id, Server.organization_id == organization.id)
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Incident introuvable.")
    now = datetime.now(timezone.utc)
    previous_status = event.status
    if payload.status == "resolved":
        note = (payload.resolution_note or "").strip()
        if len(note) < 3:
            raise HTTPException(status_code=422, detail="Un commentaire de résolution est requis.")
        event.status = "resolved"
        event.handled_by_email = user.email
        event.acknowledged_at = event.acknowledged_at or now
        event.resolved_at = now
        event.resolution_note = note
    elif payload.status == "acknowledged":
        if event.status == "resolved":
            raise HTTPException(status_code=409, detail="Rouvrez l’incident avant de le reprendre.")
        event.status = "acknowledged"
        event.handled_by_email = user.email
        event.acknowledged_at = event.acknowledged_at or now
        event.resolved_at = None
        event.resolution_note = None
    else:
        event.status = "new"
        event.handled_by_email = user.email
        event.acknowledged_at = None
        event.resolved_at = None
        event.resolution_note = (payload.resolution_note or "").strip() or None
    record_audit(
        db,
        organization,
        user.email,
        user.role,
        "security_incident.status_changed",
        "security_event",
        event.id,
        {
            "from": previous_status,
            "to": event.status,
            "rule_id": event.rule_id,
            "server_id": str(event.server_id),
        },
    )
    db.commit()
    db.refresh(event)
    return security_event_response(db, event)


@app.get("/api/v1/ids-connectors", response_model=list[IdsConnectorRead])
def list_ids_connectors(
    context: tuple[User, Organization] = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[IdsConnectorRead]:
    _, organization = context
    connectors = db.scalars(
        select(IdsConnector)
        .where(IdsConnector.organization_id == organization.id)
        .order_by(IdsConnector.created_at.desc())
    ).all()
    return [ids_connector_response(db, connector) for connector in connectors]


@app.post("/api/v1/ids-connectors", response_model=IdsConnectorCreated, status_code=status.HTTP_201_CREATED)
def create_ids_connector(
    payload: IdsConnectorCreate,
    context: tuple[User, Organization] = Depends(require_user),
    db: Session = Depends(get_db),
) -> IdsConnectorCreated:
    user, organization = context
    require_role(user, "owner", "admin")
    server = db.scalar(
        select(Server).where(Server.id == payload.server_id, Server.organization_id == organization.id)
    )
    if server is None:
        raise HTTPException(status_code=404, detail="Serveur introuvable dans cette organisation.")
    raw_token = secrets.token_urlsafe(48)
    connector = IdsConnector(
        organization_id=organization.id,
        server_id=server.id,
        name=payload.name,
        connector_type=payload.connector_type,
        token_hash=token_hash(raw_token),
    )
    db.add(connector)
    try:
        db.flush()
        record_audit(
            db,
            organization,
            user.email,
            user.role,
            "ids_connector.created",
            "ids_connector",
            connector.id,
            {
                "name": connector.name,
                "connector_type": connector.connector_type,
                "server_id": str(connector.server_id),
            },
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Un connecteur porte déjà ce nom.")
    db.refresh(connector)
    data = ids_connector_response(db, connector)
    return IdsConnectorCreated(
        **data.model_dump(),
        ingest_token=raw_token,
        ingest_path=f"/api/v1/ids-connectors/{connector.id}/events",
    )


@app.delete("/api/v1/ids-connectors/{connector_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ids_connector(
    connector_id: UUID,
    context: tuple[User, Organization] = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    user, organization = context
    require_role(user, "owner", "admin")
    connector = db.scalar(
        select(IdsConnector).where(
            IdsConnector.id == connector_id,
            IdsConnector.organization_id == organization.id,
        )
    )
    if connector is None:
        raise HTTPException(status_code=404, detail="Connecteur introuvable.")
    record_audit(
        db,
        organization,
        user.email,
        user.role,
        "ids_connector.revoked",
        "ids_connector",
        connector.id,
        {"name": connector.name, "connector_type": connector.connector_type},
    )
    db.delete(connector)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/api/v1/ids-connectors/{connector_id}/rotate-token",
    response_model=IdsConnectorTokenRotated,
)
def rotate_ids_connector_token(
    connector_id: UUID,
    payload: IdsConnectorTokenRotation,
    context: tuple[User, Organization] = Depends(require_user),
    db: Session = Depends(get_db),
) -> IdsConnectorTokenRotated:
    user, organization = context
    require_role(user, "owner", "admin")
    connector = db.scalar(
        select(IdsConnector).where(
            IdsConnector.id == connector_id,
            IdsConnector.organization_id == organization.id,
        )
    )
    if connector is None:
        raise HTTPException(status_code=404, detail="Connecteur introuvable.")

    now = datetime.now(timezone.utc)
    raw_token = secrets.token_urlsafe(48)
    if payload.grace_period_minutes > 0:
        connector.previous_token_hash = connector.token_hash
        connector.previous_token_expires_at = now + timedelta(
            minutes=payload.grace_period_minutes
        )
    else:
        connector.previous_token_hash = None
        connector.previous_token_expires_at = None
    connector.token_hash = token_hash(raw_token)
    connector.token_rotated_at = now
    record_audit(
        db,
        organization,
        user.email,
        user.role,
        "ids_connector.token_rotated",
        "ids_connector",
        connector.id,
        {
            "name": connector.name,
            "connector_type": connector.connector_type,
            "grace_period_minutes": payload.grace_period_minutes,
            "previous_token_expires_at": (
                connector.previous_token_expires_at.isoformat()
                if connector.previous_token_expires_at
                else None
            ),
        },
    )
    db.commit()
    db.refresh(connector)
    data = ids_connector_response(db, connector)
    return IdsConnectorTokenRotated(
        **data.model_dump(),
        ingest_token=raw_token,
        ingest_path=f"/api/v1/ids-connectors/{connector.id}/events",
    )


@app.delete(
    "/api/v1/ids-connectors/{connector_id}/previous-token",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_previous_ids_connector_token(
    connector_id: UUID,
    context: tuple[User, Organization] = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    user, organization = context
    require_role(user, "owner", "admin")
    connector = db.scalar(
        select(IdsConnector).where(
            IdsConnector.id == connector_id,
            IdsConnector.organization_id == organization.id,
        )
    )
    if connector is None:
        raise HTTPException(status_code=404, detail="Connecteur introuvable.")
    if connector.previous_token_hash is None:
        raise HTTPException(status_code=409, detail="Aucun ancien jeton n’est encore actif.")
    connector.previous_token_hash = None
    connector.previous_token_expires_at = None
    record_audit(
        db,
        organization,
        user.email,
        user.role,
        "ids_connector.previous_token_revoked",
        "ids_connector",
        connector.id,
        {"name": connector.name, "connector_type": connector.connector_type},
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/api/v1/ids-connectors/{connector_id}/events",
    response_model=SecurityEventRead,
    status_code=status.HTTP_201_CREATED,
)
def ingest_ids_connector_event(
    connector_id: UUID,
    payload: SecurityEventCreate,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> SecurityEventRead:
    connector = db.get(IdsConnector, connector_id)
    if connector is None or connector.status != "active":
        raise HTTPException(status_code=404, detail="Connecteur introuvable ou désactivé.")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Jeton du connecteur requis.")
    supplied_hash = token_hash(authorization.removeprefix("Bearer ").strip())
    current_token_valid = hmac.compare_digest(supplied_hash, connector.token_hash)
    now = datetime.now(timezone.utc)
    previous_expires_at = connector.previous_token_expires_at
    if previous_expires_at is not None and previous_expires_at.tzinfo is None:
        previous_expires_at = previous_expires_at.replace(tzinfo=timezone.utc)
    previous_token_valid = bool(
        connector.previous_token_hash
        and previous_expires_at
        and previous_expires_at > now
        and hmac.compare_digest(supplied_hash, connector.previous_token_hash)
    )
    if not current_token_valid and not previous_token_valid:
        raise HTTPException(status_code=401, detail="Jeton du connecteur invalide.")
    if payload.source != connector.connector_type and connector.connector_type != "other":
        raise HTTPException(status_code=422, detail="La source ne correspond pas au type du connecteur.")
    existing = db.scalar(
        select(SecurityEvent).where(
            SecurityEvent.server_id == connector.server_id,
            SecurityEvent.event_key == payload.event_key,
        )
    )
    if existing:
        return security_event_response(db, existing)
    recommendation = SECURITY_RECOMMENDATIONS.get(
        payload.category.lower(),
        "Analysez l’événement, confirmez son origine et documentez toute action avant d’appliquer un blocage.",
    )
    event = SecurityEvent(
        server_id=connector.server_id,
        recommendation=recommendation,
        **payload.model_dump(),
    )
    connector.last_event_at = datetime.now(timezone.utc)
    db.add(event)
    db.commit()
    db.refresh(event)
    return security_event_response(db, event)


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
