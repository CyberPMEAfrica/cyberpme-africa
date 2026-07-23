from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class MetricCreate(BaseModel):
    cpu_percent: float = Field(ge=0, le=100)
    memory_percent: float = Field(ge=0, le=100)
    disk_percent: float = Field(ge=0, le=100)


class MetricRead(MetricCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    collected_at: datetime


class ServerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    hostname: str = Field(min_length=1, max_length=255)
    ip_address: str | None = Field(default=None, max_length=45)


class ServerRead(ServerCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    status: str
    created_at: datetime
    last_seen_at: datetime | None
    latest_metric: MetricRead | None = None


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    server_id: UUID
    server_name: str = ""
    resource: str
    severity: str
    status: str
    value: float
    message: str
    recommendation: str
    created_at: datetime
    resolved_at: datetime | None
