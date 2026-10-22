"""Authentication, least privilege and browser-session boundaries.

No token, TOTP secret, password or recovery code is written to the audit log.
Rate counters live in SQL, not in an individual serverless worker's memory.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlsplit
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, object_session
from app.auth import hash_session_token, verify_password
from app.config import settings
from app.database import get_db
from app.models import AgentCredential, Organization, Server, User, UserSession
from app.security_models import AccountSecurity, AgentSecurity, AuthRateBucket

COOKIE_NAME = "cyberpme_session"


def cookie_name():
    # __Host- forbids Domain= and requires Secure + Path=/ in production.
    return "__Host-" + COOKIE_NAME if settings.secure_cookies else COOKIE_NAME


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def validate_browser_origin(request: Request):
    origin = request.headers.get("origin")
    trusted = {settings.frontend_public_url.rstrip("/"), *settings.cors_origin_list}
    if origin and origin not in trusted:
        raise HTTPException(403, "Origine de la requête refusée.")
    if request.cookies.get(cookie_name()) and request.method not in {"GET", "HEAD", "OPTIONS"}:
        if not origin or request.headers.get("x-cyberpme-browser") != "1":
            raise HTTPException(403, "Protection CSRF : origine et en-tête requis.")


def supplied_session(request: Request, authorization: str | None):
    cookie = request.cookies.get(cookie_name())
    if cookie:
        validate_browser_origin(request)
        return cookie
    return authorization.removeprefix("Bearer ").strip() if authorization and authorization.startswith("Bearer ") else ""


def browser_session(request: Request, response: Response, token: str, expires_at: datetime) -> str:
    validate_browser_origin(request)
    if request.headers.get("x-cyberpme-browser") != "1":
        return token  # CLI/API compatibility, never used by the web application.
    response.set_cookie(cookie_name(), token, max_age=max(0, int((utc(expires_at) - datetime.now(timezone.utc)).total_seconds())),
                        httponly=True, secure=settings.secure_cookies, samesite="lax", path="/")
    response.headers["Cache-Control"] = "no-store"
    return ""


def account_security(db: Session, user: User):
    profile = db.scalar(select(AccountSecurity).where(AccountSecurity.user_id == user.id).with_for_update())
    if profile is None:
        profile = AccountSecurity(user_id=user.id, enabled=False, last_counter=-1, recovery_hashes=[])
        db.add(profile)
        db.flush()
    return profile


def cipher():
    try:
        return Fernet(settings.mfa_encryption_key.encode())
    except (ValueError, TypeError):
        raise HTTPException(503, "La clé de chiffrement MFA doit être configurée par l’exploitant.") from None


def decrypt_secret(value):
    try:
        return cipher().decrypt(value.encode()).decode()
    except InvalidToken:
        raise HTTPException(503, "Secret MFA indisponible : vérifiez la clé de chiffrement.") from None


def totp(secret: str, counter: int):
    digest = hmac.new(base64.b32decode(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 15
    return f"{(struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7fffffff) % 1_000_000:06d}"


def consume_mfa(db: Session, profile: AccountSecurity, code: str):
    code = code.strip().replace(" ", "")
    if len(code) == 6 and code.isascii() and code.isdigit():
        counter = int(time.time() // 30)
        secret = decrypt_secret(profile.secret_encrypted)
        matched = next((c for c in (counter - 1, counter, counter + 1) if c > profile.last_counter and hmac.compare_digest(totp(secret, c), code)), None)
        if matched is not None:
            consumed = db.execute(update(AccountSecurity).where(AccountSecurity.user_id == profile.user_id, AccountSecurity.last_counter < matched).values(last_counter=matched))
            return consumed.rowcount == 1
    # Each recovery code is consumed atomically, even across serverless workers.
    digest = hashlib.sha256(code.encode()).hexdigest()
    hashes = list(profile.recovery_hashes or [])
    if any(hmac.compare_digest(digest, value) for value in hashes):
        consumed = db.execute(update(AccountSecurity).where(AccountSecurity.user_id == profile.user_id, AccountSecurity.recovery_revision == profile.recovery_revision).values(recovery_hashes=[h for h in hashes if h != digest], recovery_revision=profile.recovery_revision + 1))
        return consumed.rowcount == 1
    return False


def charge_auth_attempt(db: Session, request: Request, account: str):
    # Fixed 15-minute windows: pre-charge every attempt to avoid a concurrent bypass.
    # Protection is account-scoped, independent of spoofable forwarded headers.
    # Per-IP rules belong at the trusted ingress/WAF: behind two proxies a peer
    # address can represent many unrelated clients and must not lock them all.
    window = int(time.time() // 900)
    for subject, limit in (("account:" + account.casefold(), 8),):
        key = hashlib.sha256(subject.encode()).hexdigest()
        table = AuthRateBucket.__table__
        if db.bind.dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        stmt = insert(table).values(key=key, window=window, attempts=1)
        count = db.execute(stmt.on_conflict_do_update(index_elements=[table.c.key, table.c.window], set_={"attempts": table.c.attempts + 1}).returning(table.c.attempts)).scalar_one()
        if secrets.randbelow(64) == 0:
            db.execute(delete(AuthRateBucket).where(AuthRateBucket.window < window - 96))
        db.commit()
        if count > limit:
            raise HTTPException(429, "Trop de tentatives. Réessayez dans 15 minutes.", headers={"Retry-After": "900"})


def verify_login_mfa(db, user, code):
    profile = db.get(AccountSecurity, user.id)
    if profile and profile.enabled:
        if not code:
            raise HTTPException(401, "MFA_REQUIRED")
        if not consume_mfa(db, profile, code):
            raise HTTPException(401, "Code MFA invalide, expiré ou déjà utilisé.")


def enforce_mfa_setup(db, user, request):
    profile = db.get(AccountSecurity, user.id)
    if settings.mfa_required and not (profile and profile.enabled):
        if request.url.path not in {"/api/v1/auth/me", "/api/v1/auth/logout"} and not request.url.path.startswith("/api/v1/auth/mfa/"):
            raise HTTPException(403, "MFA_SETUP_REQUIRED")


def check_agent_scope(server, scope="monitoring"):
    db = object_session(server)
    profile = db.get(AgentSecurity, server.id) if db else None
    if profile is None or profile.revoked_at or utc(profile.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(401, "Identité agent expirée ou révoquée. Réassociez l’agent.")
    allowed = {"monitoring"}
    if profile.mode in {"network", "managed"}:
        allowed.add("network")
    if profile.mode == "managed":
        allowed.add("managed")
    if scope not in allowed:
        raise HTTPException(403, "Cette identité agent est limitée au monitoring.")


class MfaProof(BaseModel):
    password: str = Field(min_length=12, max_length=256)
    code: str = Field(default="", max_length=64)


class PairingPolicy(BaseModel):
    mode: str = Field(default="monitoring", pattern="^(monitoring|network|managed)$")


def install_routes(app, require_user, require_role, record_audit):
    router = APIRouter(prefix="/api/v1")

    @router.get("/auth/mfa/status")
    def mfa_status(context=Depends(require_user), db: Session = Depends(get_db)):
        profile = db.get(AccountSecurity, context[0].id)
        return {"enabled": bool(profile and profile.enabled), "required": settings.mfa_required,
                "recovery_codes_remaining": len(profile.recovery_hashes) if profile else 0}

    @router.post("/auth/mfa/setup")
    def mfa_setup(payload: MfaProof, request: Request, context=Depends(require_user), db: Session = Depends(get_db)):
        user, org = context
        charge_auth_attempt(db, request, str(user.id) + ":mfa-setup")
        if not verify_password(payload.password, user.password_hash):
            raise HTTPException(401, "Mot de passe incorrect.")
        profile = account_security(db, user)
        if profile.enabled:
            raise HTTPException(409, "MFA déjà activée.")
        secret = base64.b32encode(secrets.token_bytes(20)).decode()
        profile.pending_encrypted = cipher().encrypt(secret.encode()).decode()
        profile.pending_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        db.commit()
        return {"secret": secret, "otpauth_uri": f"otpauth://totp/{quote('CyberPME:' + org.slug + ':' + user.email, safe='')}?secret={secret}&issuer=CyberPME&algorithm=SHA1&digits=6&period=30"}

    @router.post("/auth/mfa/enable")
    def mfa_enable(payload: MfaProof, request: Request, context=Depends(require_user), db: Session = Depends(get_db)):
        user, org = context
        charge_auth_attempt(db, request, str(user.id) + ":mfa-enable")
        profile = account_security(db, user)
        if profile.enabled or not profile.pending_encrypted or utc(profile.pending_expires_at) <= datetime.now(timezone.utc):
            raise HTTPException(400, "Préparation MFA absente ou expirée.")
        if not verify_password(payload.password, user.password_hash):
            raise HTTPException(401, "Mot de passe incorrect.")
        counter = int(time.time() // 30)
        secret = decrypt_secret(profile.pending_encrypted)
        matched = next((c for c in (counter - 1, counter, counter + 1) if hmac.compare_digest(totp(secret, c), payload.code.strip())), None)
        if matched is None:
            raise HTTPException(401, "Code MFA incorrect.")
        codes = [secrets.token_hex(16) for _ in range(10)]
        profile.secret_encrypted = profile.pending_encrypted
        profile.pending_encrypted = None
        profile.pending_expires_at = None
        profile.enabled = True
        profile.last_counter = matched
        profile.recovery_hashes = [hashlib.sha256(code.encode()).hexdigest() for code in codes]
        db.execute(delete(UserSession).where(UserSession.user_id == user.id))
        record_audit(db, org, user.email, user.role, "auth.mfa_enabled", "user", user.id)
        db.commit()
        return {"recovery_codes": codes, "reconnect": True}

    @router.post("/auth/mfa/disable", status_code=204)
    def mfa_disable(payload: MfaProof, request: Request, context=Depends(require_user), db: Session = Depends(get_db)):
        user, org = context
        charge_auth_attempt(db, request, str(user.id) + ":mfa-disable")
        if settings.mfa_required:
            raise HTTPException(403, "MFA obligatoire : désactivation refusée.")
        profile = account_security(db, user)
        if not profile.enabled or not verify_password(payload.password, user.password_hash) or not consume_mfa(db, profile, payload.code):
            raise HTTPException(401, "Preuve d’authentification incorrecte.")
        profile.enabled = False
        profile.secret_encrypted = None
        profile.recovery_hashes = []
        db.execute(delete(UserSession).where(UserSession.user_id == user.id))
        record_audit(db, org, user.email, user.role, "auth.mfa_disabled", "user", user.id)
        db.commit()
        return Response(status_code=204)

    @router.post("/auth/mfa/reset", status_code=204)
    def mfa_reset(payload: MfaProof, request: Request, context=Depends(require_user), db: Session = Depends(get_db)):
        user, org = context
        charge_auth_attempt(db, request, str(user.id) + ":mfa-reset")
        profile = account_security(db, user)
        if not profile.enabled or not verify_password(payload.password, user.password_hash) or not consume_mfa(db, profile, payload.code):
            raise HTTPException(401, "Mot de passe et code MFA ou de secours valides requis.")
        profile.enabled = False
        profile.secret_encrypted = None
        profile.pending_encrypted = None
        profile.pending_expires_at = None
        profile.last_counter = -1
        profile.recovery_hashes = []
        profile.recovery_revision += 1
        # Retain only the current session, now restricted to MFA enrollment.
        digest = hash_session_token(supplied_session(request, request.headers.get('authorization')))
        db.execute(delete(UserSession).where(UserSession.user_id == user.id, UserSession.token_hash != digest))
        record_audit(db, org, user.email, user.role, "auth.mfa_reset", "user", user.id)
        db.commit()
        return Response(status_code=204)

    @router.get("/agent-security")
    def list_agents(context=Depends(require_user), db: Session = Depends(get_db)):
        user, org = context
        require_role(user, "owner", "admin")
        rows = db.execute(select(Server, AgentSecurity).outerjoin(AgentSecurity, AgentSecurity.server_id == Server.id).where(Server.organization_id == org.id)).all()
        return [{"server_id": server.id, "name": server.name, "hostname": server.hostname,
                 "mode": profile.mode if profile else "unpaired", "expires_at": profile.expires_at if profile else None,
                 "revoked_at": profile.revoked_at if profile else None} for server, profile in rows]

    @router.post("/servers/{server_id}/agent-credential/revoke", status_code=204)
    def revoke_agent(server_id: UUID, context=Depends(require_user), db: Session = Depends(get_db)):
        user, org = context
        require_role(user, "owner", "admin")
        server = db.get(Server, server_id)
        if not server or server.organization_id != org.id:
            raise HTTPException(404, "Agent introuvable.")
        profile = db.get(AgentSecurity, server.id)
        if profile:
            profile.revoked_at = datetime.now(timezone.utc)
        server.network_scan_capable = False
        record_audit(db, org, user.email, user.role, "agent.revoked", "server", server.id)
        db.commit()
        return Response(status_code=204)

    app.include_router(router)
