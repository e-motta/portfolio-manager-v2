from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(unique=True, index=True)
    google_sub: str = Field(unique=True, index=True)
    name: str = Field(default="")
    picture_url: str = Field(default="")
    google_refresh_token: str | None = Field(default=None)
    google_drive_folder_id: str | None = Field(default=None)
    cumbuca_refresh_token: str | None = Field(default=None)
    cumbuca_access_token: str | None = Field(default=None)
    cumbuca_token_expires_at: datetime | None = Field(default=None)
    cumbuca_oauth_client_id: str | None = Field(default=None)
    cumbuca_oauth_client_secret: str | None = Field(default=None)
    cumbuca_connected_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    portfolios: list["Portfolio"] = Relationship(back_populates="user")  # noqa: F821
