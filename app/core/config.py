import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./local.db")
    TEST_DATABASE_URL: str = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")
    DISPLAY_TIMEZONE: str = os.getenv("DISPLAY_TIMEZONE", "America/Sao_Paulo")
    DISPLAY_TIMEZONE_LABEL: str = os.getenv("DISPLAY_TIMEZONE_LABEL", "BRT")


settings = Settings()
