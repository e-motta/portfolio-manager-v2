from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.user import User


class Portfolio(SQLModel, table=True):
    __tablename__ = "portfolios"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID | None = Field(default=None, foreign_key="users.id", ondelete="CASCADE")
    name: str = Field(default="My Portfolio")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    user: "User" = Relationship(back_populates="portfolios")
    asset_types: list["AssetType"] = Relationship(back_populates="portfolio")  # noqa: F821
