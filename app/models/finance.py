from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class FinanceIncomeEntry(SQLModel, table=True):
    __tablename__ = "finance_income_entries"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", ondelete="CASCADE", index=True)
    year: int = Field(index=True)
    month: int = Field(ge=1, le=12)
    description: str = Field(default="")
    amount: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=2)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class FinanceExpenseEntry(SQLModel, table=True):
    __tablename__ = "finance_expense_entries"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", ondelete="CASCADE", index=True)
    year: int = Field(index=True)
    month: int = Field(ge=1, le=12)
    category: str = Field(index=True)
    vendor: str = Field(default="")
    payment_account: str = Field(default="", index=True)
    amount: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=2)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class FinanceSummaryAmount(SQLModel, table=True):
    __tablename__ = "finance_summary_amounts"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", ondelete="CASCADE", index=True)
    year: int = Field(index=True)
    month: int = Field(ge=1, le=12)
    line_key: str = Field(index=True)
    amount: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=2)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
