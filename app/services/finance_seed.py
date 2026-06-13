import json
import os
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from sqlmodel import Session, select

from app.models.finance import (
    FinanceExpenseEntry,
    FinanceIncomeEntry,
    FinanceSummaryAmount,
)
SEED_FILE = Path(__file__).resolve().parent.parent / "data" / "finance_2026_seed.json"


def finance_data_exists(session: Session) -> bool:
    return session.exec(select(FinanceIncomeEntry).limit(1)).first() is not None


def seed_finance_data(session: Session, user_id: UUID) -> bool:
    """Load the one-time finance seed for a user. Returns True if data was inserted."""
    if os.getenv("TESTING") == "1":
        return False
    if finance_data_exists(session):
        return False
    if not SEED_FILE.is_file():
        return False

    payload = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    year = int(payload["year"])

    for row in payload["income"]:
        session.add(
            FinanceIncomeEntry(
                user_id=user_id,
                year=year,
                month=int(row["month"]),
                description=row["description"],
                amount=Decimal(row["amount"]),
            )
        )

    for row in payload["expenses"]:
        session.add(
            FinanceExpenseEntry(
                user_id=user_id,
                year=year,
                month=int(row["month"]),
                category=row["category"],
                vendor=row["vendor"],
                payment_account=row["payment_account"],
                amount=Decimal(row["amount"]),
            )
        )

    for row in payload["summary"]:
        session.add(
            FinanceSummaryAmount(
                user_id=user_id,
                year=year,
                month=int(row["month"]),
                line_key=row["line_key"],
                amount=Decimal(row["amount"]),
            )
        )

    session.commit()
    return True


def seed_fixos_outros_if_missing(session: Session) -> int:
    """Backfill Fixos and Outros expenses for databases seeded before those categories."""
    if not SEED_FILE.is_file():
        return 0

    payload = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    year = int(payload["year"])
    backfill_categories = {"Fixos", "Outros"}
    inserted = 0

    user_ids = {
        row.user_id
        for row in session.exec(select(FinanceIncomeEntry)).all()
    }
    if not user_ids:
        return 0

    for user_id in user_ids:
        existing = {
            row.category
            for row in session.exec(
                select(FinanceExpenseEntry)
                .where(FinanceExpenseEntry.user_id == user_id)
                .where(FinanceExpenseEntry.year == year)
            ).all()
            if row.category in backfill_categories
        }
        missing = backfill_categories - existing
        if not missing:
            continue

        for row in payload["expenses"]:
            if row["category"] not in missing:
                continue
            session.add(
                FinanceExpenseEntry(
                    user_id=user_id,
                    year=year,
                    month=int(row["month"]),
                    category=row["category"],
                    vendor=row["vendor"],
                    payment_account=row["payment_account"],
                    amount=Decimal(row["amount"]),
                )
            )
            inserted += 1

    if inserted:
        session.commit()
    return inserted
