import os
import secrets
import sys

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Sentinel to detect if SECRET_KEY was explicitly provided
_SECRET_KEY_NOT_SET = "__NOT_SET__"

# Track if Vault loading failed (for fail-fast in production)
_vault_load_error: str | None = None


def _load_vault_secrets_to_env() -> None:
    """Load OCI Vault secrets into environment variables before Settings init.

    Only runs when OCI_VAULT_OCID is configured. Secrets are loaded into
    os.environ so pydantic-settings picks them up.

    In production, Vault failures are fatal for required secrets.
    """
    global _vault_load_error

    if not os.environ.get("OCI_VAULT_OCID"):
        return

    if os.environ.get("TESTING") == "1":
        return

    try:
        from app.core.vault import load_vault_secrets, VaultError

        vault_secrets = load_vault_secrets()
        for key, value in vault_secrets.items():
            if key not in os.environ:
                os.environ[key] = value
    except VaultError as e:
        _vault_load_error = str(e)
    except Exception as e:
        _vault_load_error = str(e)


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
    SECRET_KEY: str = _SECRET_KEY_NOT_SET
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://127.0.0.1:8000/auth/callback"
    CUMBUCA_MCP_URL: str = "https://mcp.cumbuca.com/mcp"
    CUMBUCA_AUTH_SERVER: str = "https://idc.cumbuca.com/realms/cumbuca-mcp"
    CUMBUCA_REDIRECT_URI: str = "http://127.0.0.1:8000/auth/cumbuca/callback"
    CUMBUCA_OAUTH_SCOPES: str = "openid profile offline_access open-finance"
    ALLOWED_GOOGLE_EMAILS: str = ""

    # Pluggy (Meu Pluggy) - optional, app starts without them
    PLUGGY_CLIENT_ID: str = ""
    PLUGGY_CLIENT_SECRET: str = ""
    PLUGGY_API_URL: str = "https://api.pluggy.ai"

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
            # In development, generate a random SECRET_KEY if not provided
            if self.SECRET_KEY == _SECRET_KEY_NOT_SET:
                object.__setattr__(self, "SECRET_KEY", secrets.token_urlsafe(32))
            return self

        # In production with OCI Vault configured, fail if Vault loading failed
        if os.environ.get("OCI_VAULT_OCID") and _vault_load_error:
            print(
                f"FATAL: OCI Vault is configured but secrets failed to load: {_vault_load_error}",
                file=sys.stderr,
            )
            sys.exit(1)

        missing = []
        # SECRET_KEY must be explicitly provided in production (not auto-generated)
        if self.SECRET_KEY == _SECRET_KEY_NOT_SET:
            missing.append("SECRET_KEY (must be explicitly set, not auto-generated)")
        elif len(self.SECRET_KEY) < 32:
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
