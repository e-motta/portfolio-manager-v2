from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    pass


class PortfolioSnapshot(SQLModel, table=True):
    __tablename__ = "portfolio_snapshots"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    snapshot_date: date = Field(index=True, unique=True)
    total_value: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=2)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    asset_classes: list["SnapshotAssetClass"] = Relationship(
        back_populates="snapshot",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    investments: list["SnapshotInvestment"] = Relationship(
        back_populates="snapshot",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    holdings: list["SnapshotHolding"] = Relationship(
        back_populates="snapshot",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class SnapshotAssetClass(SQLModel, table=True):
    __tablename__ = "snapshot_asset_classes"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    snapshot_id: UUID = Field(foreign_key="portfolio_snapshots.id", ondelete="CASCADE")
    asset_type_id: UUID | None = Field(default=None, foreign_key="asset_types.id", ondelete="SET NULL")
    name: str
    current_value: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=2)
    current_weight: Decimal = Field(default=Decimal("0"), max_digits=7, decimal_places=6)
    target_weight: Decimal | None = Field(default=None, max_digits=5, decimal_places=4)

    snapshot: PortfolioSnapshot = Relationship(back_populates="asset_classes")


class SnapshotInvestment(SQLModel, table=True):
    __tablename__ = "snapshot_investments"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    snapshot_id: UUID = Field(foreign_key="portfolio_snapshots.id", ondelete="CASCADE")
    institution: str = Field(default="")
    name: str
    asset_type_name: str
    current_value: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=2)

    snapshot: PortfolioSnapshot = Relationship(back_populates="investments")


class SnapshotHolding(SQLModel, table=True):
    __tablename__ = "snapshot_holdings"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    snapshot_id: UUID = Field(foreign_key="portfolio_snapshots.id", ondelete="CASCADE")
    symbol: str
    name: str = Field(default="")
    total_position: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=8)
    current_value_brl: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=2)

    snapshot: PortfolioSnapshot = Relationship(back_populates="holdings")
