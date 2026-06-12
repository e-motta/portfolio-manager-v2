from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel


class Portfolio(SQLModel, table=True):
    __tablename__ = "portfolios"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(default="My Portfolio")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    asset_types: list["AssetType"] = Relationship(back_populates="portfolio")  # noqa: F821
