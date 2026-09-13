import os
import secrets
import sys

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _load_vault_secrets_to_env() -> None:
    """Load OCI Vault secrets into environment variables before Settings init.

    Only runs when OCI_VAULT_OCID is configured. Secrets are loaded into
    os.environ so pydantic-settings picks them up. Falls back gracefully
    if Vault is unavailable.
    """
    if not os.environ.get("OCI_VAULT_OCID"):
        return

    if os.environ.get("TESTING") == "1":
        return

    try:
        from app.core.vault import load_vault_secrets

        vault_secrets = load_vault_secrets()
        for key, value in vault_secrets.items():
            if key not in os.environ:
                os.environ[key] = value
    except Exception as e:
        print(f"WARNING: Failed to load OCI Vault secrets: {e}", file=sys.stderr)


_load_vault_secrets_to_env()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: str = "development"
    DATABASE_URL: str = "sqlite:///./local.db"
    TEST_DATABASE_URL: str = "sqlite:///:memory:"
    DISPLAY_TIMEZONE: str = "America/Sao_Paulo"
    DISPLAY_TIMEZONE_LABEL: str = "BRT"
    SECRET_KEY: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://127.0.0.1:8000/auth/callback"
    CUMBUCA_MCP_URL: str = "https://mcp.cumbuca.com/mcp"
    CUMBUCA_AUTH_SERVER: str = "https://idc.cumbuca.com/realms/cumbuca-mcp"
    CUMBUCA_REDIRECT_URI: str = "http://127.0.0.1:8000/auth/cumbuca/callback"
    CUMBUCA_OAUTH_SCOPES: str = "openid profile offline_access open-finance"
    ALLOWED_GOOGLE_EMAILS: str = ""

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def allowed_emails_set(self) -> set[str]:
        if not self.ALLOWED_GOOGLE_EMAILS:
            return set()
        return {e.strip().lower() for e in self.ALLOWED_GOOGLE_EMAILS.split(",") if e.strip()}

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if not self.is_production:
            return self
        missing = []
        if self.SECRET_KEY == "" or len(self.SECRET_KEY) < 32:
            missing.append("SECRET_KEY (must be at least 32 characters)")
        if not self.GOOGLE_CLIENT_ID:
            missing.append("GOOGLE_CLIENT_ID")
        if not self.GOOGLE_CLIENT_SECRET:
            missing.append("GOOGLE_CLIENT_SECRET")
        if self.DATABASE_URL.startswith("sqlite"):
            missing.append("DATABASE_URL (must use Postgres in production)")
        if missing:
            print(f"FATAL: Missing required production secrets: {', '.join(missing)}", file=sys.stderr)
            sys.exit(1)
        return self


settings = Settings()
