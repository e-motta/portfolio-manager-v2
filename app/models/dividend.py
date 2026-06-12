from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class Dividend(SQLModel, table=True):
    __tablename__ = "dividends"
    __table_args__ = (
        UniqueConstraint("asset_type_id", "import_key", name="uq_dividend_asset_import_key"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    asset_type_id: UUID = Field(foreign_key="asset_types.id", ondelete="CASCADE")
    symbol: str = Field(index=True)
    pay_date: date
    gross_amount_usd: Decimal = Field(max_digits=18, decimal_places=2)
    withholding_tax_usd: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=2)
    net_amount_usd: Decimal = Field(max_digits=18, decimal_places=2)
    source: str = Field(default="manual", index=True)
    import_key: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
