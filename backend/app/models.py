from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Server(Base):
    __tablename__ = "servers"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120))
    hostname: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="unknown")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metrics: Mapped[list["Metric"]] = relationship(back_populates="server", cascade="all, delete-orphan")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="server", cascade="all, delete-orphan")
    credential: Mapped["AgentCredential | None"] = relationship(back_populates="server", cascade="all, delete-orphan", uselist=False)


class Metric(Base):
    __tablename__ = "metrics"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    server_id: Mapped[UUID] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"), index=True)
    cpu_percent: Mapped[float] = mapped_column(Float)
    memory_percent: Mapped[float] = mapped_column(Float)
    disk_percent: Mapped[float] = mapped_column(Float)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    server: Mapped[Server] = relationship(back_populates="metrics")


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    server_id: Mapped[UUID] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"), index=True)
    resource: Mapped[str] = mapped_column(String(20), index=True)
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    value: Mapped[float] = mapped_column(Float)
    message: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    server: Mapped[Server] = relationship(back_populates="alerts")


class AgentCredential(Base):
    __tablename__ = "agent_credentials"
    server_id: Mapped[UUID] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    server: Mapped[Server] = relationship(back_populates="credential")


class NetworkScan(Base):
    __tablename__ = "network_scans"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    target: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    results: Mapped[list[dict]] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SslCheck(Base):
    __tablename__ = "ssl_checks"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    hostname: Mapped[str] = mapped_column(String(253), index=True)
    port: Mapped[int]
    status: Mapped[str] = mapped_column(String(20), index=True)
    subject: Mapped[str | None] = mapped_column(String(500))
    issuer: Mapped[str | None] = mapped_column(String(500))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    days_remaining: Mapped[int | None]
    chain_valid: Mapped[bool] = mapped_column(default=False)
    tls_version: Mapped[str | None] = mapped_column(String(30))
    cipher: Mapped[str | None] = mapped_column(String(100))
    error: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class BackupCheck(Base):
    __tablename__ = "backup_checks"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    server_id: Mapped[UUID] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20), index=True)
    source: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), index=True)
    exists: Mapped[bool]
    size_bytes: Mapped[int | None]
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_age_hours: Mapped[int]
    error: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SecurityEvent(Base):
    __tablename__ = "security_events"
    __table_args__ = (UniqueConstraint("server_id", "event_key", name="uq_security_event_server_key"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    server_id: Mapped[UUID] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"), index=True)
    event_key: Mapped[str] = mapped_column(String(128))
    source: Mapped[str] = mapped_column(String(30), index=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    severity: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    source_ip: Mapped[str | None] = mapped_column(String(45), index=True)
    destination_ip: Mapped[str | None] = mapped_column(String(45))
    rule_id: Mapped[str | None] = mapped_column(String(80))
    recommendation: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
