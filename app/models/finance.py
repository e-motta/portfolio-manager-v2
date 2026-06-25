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
    description: str = Field(default="")
    payment_account: str = Field(default="", index=True)
    amount: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=2)
    subcategory: str | None = Field(default=None, index=True)
    source: str = Field(default="manual", index=True)
    external_id: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class FinanceInvestmentEntry(SQLModel, table=True):
    __tablename__ = "finance_investment_entries"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", ondelete="CASCADE", index=True)
    year: int = Field(index=True)
    month: int = Field(ge=1, le=12)
    broker: str = Field(index=True)
    amount: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=2)
    source: str = Field(default="manual", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class FinanceInvestmentOpenFinanceImport(SQLModel, table=True):
    __tablename__ = "finance_investment_open_finance_imports"
    __table_args__ = (UniqueConstraint("user_id", "external_id"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", ondelete="CASCADE", index=True)
    external_id: str = Field(index=True)
    year: int = Field(index=True)
    month: int = Field(ge=1, le=12)
    broker: str = Field(index=True)
    amount: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=2)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FinanceTransferEntry(SQLModel, table=True):
    __tablename__ = "finance_transfer_entries"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", ondelete="CASCADE", index=True)
    year: int = Field(index=True)
    month: int = Field(ge=1, le=12)
    transaction_date: date | None = Field(default=None, index=True)
    from_account: str = Field(index=True)
    to_account: str = Field(index=True)
    amount: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=2)
    description: str = Field(default="")
    source: str = Field(default="manual", index=True)
    external_id: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class FinanceVendorCategory(SQLModel, table=True):
    __tablename__ = "finance_vendor_categories"
    __table_args__ = (UniqueConstraint("user_id", "vendor_key"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", ondelete="CASCADE", index=True)
    vendor_key: str = Field(index=True)
    category: str = Field(index=True)
    subcategory: str | None = Field(default=None)
    description: str = Field(default="")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
