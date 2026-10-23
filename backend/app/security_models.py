"""Additive security state, separate from customer monitoring records."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models import utc_now


class AccountSecurity(Base):
    __tablename__ = "account_security"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    secret_encrypted: Mapped[str | None] = mapped_column(String(512))
    pending_encrypted: Mapped[str | None] = mapped_column(String(512))
    pending_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enabled: Mapped[bool] = mapped_column(default=False)
    last_counter: Mapped[int] = mapped_column(default=-1)
    recovery_hashes: Mapped[list] = mapped_column(JSON, default=list)
    recovery_revision: Mapped[int] = mapped_column(default=0)


class AuthRateBucket(Base):
    __tablename__ = "auth_rate_buckets"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window: Mapped[int] = mapped_column(primary_key=True)
    attempts: Mapped[int] = mapped_column(default=0)


class AgentSecurity(Base):
    __tablename__ = "agent_security"
    server_id: Mapped[UUID] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"), primary_key=True)
    mode: Mapped[str] = mapped_column(String(24), default="monitoring")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rotated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EnrollmentPolicy(Base):
    __tablename__ = "enrollment_policies"
    enrollment_id: Mapped[UUID] = mapped_column(ForeignKey("agent_enrollment_tokens.id", ondelete="CASCADE"), primary_key=True)
    mode: Mapped[str] = mapped_column(String(24), default="monitoring")
