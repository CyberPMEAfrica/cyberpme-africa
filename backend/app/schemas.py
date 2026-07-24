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


class AgentRegistration(ServerCreate):
    pass


class AgentRegistrationRead(BaseModel):
    server_id: UUID
    agent_token: str


class NetworkScanCreate(BaseModel):
    target: str = Field(
        min_length=9,
        max_length=18,
        examples=["192.168.1.0/24"],
        description="Réseau IPv4 privé autorisé, limité à 256 adresses.",
    )


class NetworkScanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    target: str
    status: str
    results: list[dict]
    error: str | None
    requested_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class SslCheckCreate(BaseModel):
    hostname: str = Field(min_length=4, max_length=253, examples=["example.com"])
    port: int = Field(default=443)


class SslCheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    hostname: str
    port: int
    status: str
    subject: str | None
    issuer: str | None
    valid_from: datetime | None
    expires_at: datetime | None
    days_remaining: int | None
    chain_valid: bool
    tls_version: str | None
    cipher: str | None
    error: str | None
    checked_at: datetime


class BackupCheckCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    kind: str = Field(pattern="^(files|postgresql)$")
    source: str = Field(min_length=1, max_length=500)
    exists: bool
    size_bytes: int | None = Field(default=None, ge=0)
    last_success_at: datetime | None = None
    max_age_hours: int = Field(default=24, ge=1, le=8760)
    error: str | None = Field(default=None, max_length=1000)


class BackupCheckRead(BackupCheckCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    server_id: UUID
    server_name: str = ""
    status: str
    checked_at: datetime


class SecurityEventCreate(BaseModel):
    event_key: str = Field(min_length=1, max_length=128)
    source: str = Field(pattern="^(wazuh|suricata|agent|other)$")
    category: str = Field(min_length=2, max_length=50)
    severity: str = Field(pattern="^(low|medium|high|critical)$")
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    source_ip: str | None = Field(default=None, max_length=45)
    destination_ip: str | None = Field(default=None, max_length=45)
    rule_id: str | None = Field(default=None, max_length=80)
    occurred_at: datetime


class SecurityEventRead(SecurityEventCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    server_id: UUID
    server_name: str = ""
    recommendation: str
    status: str
    received_at: datetime


class LoginRequest(BaseModel):
    organization_slug: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=12, max_length=256)


class SessionRead(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class CurrentUserRead(BaseModel):
    id: UUID
    organization_id: UUID
    organization_name: str
    email: str
    role: str
