from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class FinanceIncomeEntry(SQLModel, table=True):
    __tablename__ = "finance_income_entries"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", ondelete="CASCADE", index=True)
    year: int = Field(index=True)
    month: int = Field(ge=1, le=12)
    category: str = Field(default="Outros", index=True)
    description: str = Field(default="")
    amount: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=2)
    source: str = Field(default="manual", index=True)
    external_id: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class FinanceExpenseEntry(SQLModel, table=True):
    __tablename__ = "finance_expense_entries"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", ondelete="CASCADE", index=True)
    year: int = Field(index=True)
    month: int = Field(ge=1, le=12)
    transaction_date: date | None = Field(default=None, index=True)
    category: str = Field(index=True)
    vendor: str = Field(default="")
    payment_account: str = Field(default="", index=True)
    amount: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=2)
    source: str = Field(default="manual", index=True)
    external_id: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class FinanceInvestmentEntry(SQLModel, table=True):
    __tablename__ = "finance_investment_entries"
    __table_args__ = (UniqueConstraint("user_id", "year", "month", "broker"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", ondelete="CASCADE", index=True)
    year: int = Field(index=True)
    month: int = Field(ge=1, le=12)
    broker: str = Field(index=True)
    amount: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=2)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class FinanceVendorCategory(SQLModel, table=True):
    __tablename__ = "finance_vendor_categories"
    __table_args__ = (UniqueConstraint("user_id", "vendor_key"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", ondelete="CASCADE", index=True)
    vendor_key: str = Field(index=True)
    category: str = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
