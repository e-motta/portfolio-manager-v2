from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class SymbolTarget(SQLModel, table=True):
    __tablename__ = "symbol_targets"
    __table_args__ = (
        UniqueConstraint("asset_type_id", "symbol", name="uq_symbol_target_asset_symbol"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    asset_type_id: UUID = Field(foreign_key="asset_types.id", ondelete="CASCADE")
    symbol: str = Field(index=True)
    name: str = Field(default="")
    target_pct: Decimal = Field(default=Decimal("0"), max_digits=5, decimal_places=4)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
