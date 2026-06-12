from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.investment import Investment
    from app.models.portfolio import Portfolio
    from app.models.security import SecurityLot


DEFAULT_ASSET_TYPES = [
    {
        "name": "Cash",
        "slug": "cash",
        "is_exchange_traded": False,
        "target_pct": Decimal("0.05"),
        "current_value": Decimal("0"),
    },
    {
        "name": "Bonds",
        "slug": "bonds",
        "is_exchange_traded": False,
        "target_pct": Decimal("0.20"),
        "current_value": Decimal("0"),
    },
    {
        "name": "Listed Securities",
        "slug": "exchange-traded",
        "is_exchange_traded": True,
        "target_pct": Decimal("0.60"),
        "current_value": Decimal("0"),
    },
    {
        "name": "Crypto",
        "slug": "crypto",
        "is_exchange_traded": False,
        "target_pct": Decimal("0.05"),
        "current_value": Decimal("0"),
    },
    {
        "name": "Real Estate",
        "slug": "real-estate",
        "is_exchange_traded": False,
        "target_pct": Decimal("0.10"),
        "current_value": Decimal("0"),
    },
]


class AssetType(SQLModel, table=True):
    __tablename__ = "asset_types"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    portfolio_id: UUID = Field(foreign_key="portfolios.id", ondelete="CASCADE")
    name: str
    slug: str
    target_pct: Decimal | None = Field(default=None, max_digits=5, decimal_places=4)
    current_value: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=2)
    is_exchange_traded: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    portfolio: "Portfolio" = Relationship(back_populates="asset_types")
    securities: list["SecurityLot"] = Relationship(back_populates="asset_type")
    investments: list["Investment"] = Relationship(back_populates="asset_type")
