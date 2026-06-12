from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.asset_type import AssetType


class Investment(SQLModel, table=True):
    __tablename__ = "investments"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    asset_type_id: UUID = Field(foreign_key="asset_types.id", ondelete="CASCADE")
    institution: str = Field(default="", index=True)
    name: str
    current_value: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=2)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    asset_type: "AssetType" = Relationship(back_populates="investments")
