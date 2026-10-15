from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


ProviderType = Literal["cumbuca", "pluggy"]


class OpenFinanceConnection(SQLModel, table=True):
    """Stores Open Finance provider connections per user.

    Each row represents a single bank/institution connection through a provider.
    Cumbuca uses OAuth tokens per user (one connection per user).
    Pluggy uses itemId as external_id (multiple connections per user possible).
    """

    __tablename__ = "open_finance_connections"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", "external_id", name="uq_connection_identity"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", ondelete="CASCADE", index=True)
    provider: str = Field(index=True)
    external_id: str = Field(default="", index=True)
    institution_name: str = Field(default="")
    institution_id: str | None = Field(default=None)
    status: str = Field(default="active", index=True)
    last_synced_at: datetime | None = Field(default=None)

    # Cumbuca OAuth tokens (stored only for provider='cumbuca')
    oauth_client_id: str | None = Field(default=None)
    oauth_client_secret: str | None = Field(default=None)
    refresh_token: str | None = Field(default=None)
    access_token: str | None = Field(default=None)
    token_expires_at: datetime | None = Field(default=None)

    # Pluggy item access token (stored only for provider='pluggy')
    item_access_token: str | None = Field(default=None)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
