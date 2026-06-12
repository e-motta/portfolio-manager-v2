from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel


class SecurityLot(SQLModel, table=True):
    __tablename__ = "securities"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    asset_type_id: UUID = Field(foreign_key="asset_types.id", ondelete="CASCADE")
    symbol: str = Field(index=True)
    name: str = Field(default="")
    position: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=8)
    purchase_date: date = Field(default_factory=date.today)
    purchase_price_usd: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=8)
    purchase_price_brl: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=8)
    usd_brl_rate: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=6)
    provisional_fx: bool = Field(default=False)
    source: str = Field(default="manual", index=True)
    current_price_usd: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=8)
    current_price_brl: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=8)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    asset_type: "AssetType" = Relationship(back_populates="securities")  # noqa: F821

    @property
    def cost_basis_usd(self) -> Decimal:
        return self.position * self.purchase_price_usd

    @property
    def cost_basis_brl(self) -> Decimal:
        return self.position * self.purchase_price_brl

    @property
    def current_value(self) -> Decimal:
        return self.position * self.current_price_brl


# Backwards-compatible alias used across the codebase during refactor.
Security = SecurityLot
