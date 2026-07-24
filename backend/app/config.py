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
    agent_enrollment_key: str
    network_scan_key: str
    bootstrap_organization_name: str = "CyberPME Lab"
    bootstrap_organization_slug: str = "cyberpme-lab"
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
