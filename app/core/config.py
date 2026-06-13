import secrets

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

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


settings = Settings()
