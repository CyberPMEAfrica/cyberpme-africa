from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import DateTime, Float, ForeignKey, String, Text
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
