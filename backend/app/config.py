from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CyberPME Africa"
    database_url: str = "postgresql+psycopg://cyberpme:change-me-in-production@database:5432/cyberpme"
    smtp_host: str = "mailpit"
    smtp_port: int = 1025
    smtp_use_tls: bool = False
    smtp_username: str = ""
    smtp_password: str = ""
    alert_email_from: str = "alerts@cyberpme.local"
    alert_email_to: str = "bocorodrigue43@mail.com"
    frontend_public_url: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173"
    agent_enrollment_key: str
    network_scan_key: str
    bootstrap_organization_name: str = "CyberPME Lab"
    bootstrap_organization_slug: str = "cyberpme-lab"
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""
    bootstrap_admin_force_sync: bool = False
    bootstrap_recovery_key: str = ""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url", mode="before")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        """Render fournit une URL PostgreSQL sans nom de pilote SQLAlchemy."""
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip().rstrip("/")
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]


settings = Settings()
