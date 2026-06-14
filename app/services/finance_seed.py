import json
import os
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from sqlmodel import Session, select

from app.models.finance import (
    FinanceExpenseEntry,
    FinanceIncomeEntry,
    FinanceInvestmentEntry,
)
from app.services.finance import (
    BILLS_CATEGORY,
    BILLS_PAYMENT_ACCOUNT,
    MIGRATED_SUMMARY_SOURCE,
    SUMMARY_BILL_LINE_LABELS,
    SUMMARY_CC_LINE_ACCOUNTS,
    SUMMARY_INCOME_LINE_CATEGORIES,
    SUMMARY_INVESTMENT_BROKERS,
    _summary_external_id,
)

SEED_FILE = Path(__file__).resolve().parent.parent / "data" / "finance_2026_seed.json"


def finance_data_exists(session: Session) -> bool:
    return session.exec(select(FinanceIncomeEntry).limit(1)).first() is not None


def _seed_summary_row(
    session: Session,
    user_id: UUID,
    year: int,
    row: dict,
) -> None:
    line_key = row["line_key"]
    month = int(row["month"])
    amount = Decimal(row["amount"])
    external_id = _summary_external_id(line_key, year, month)

    if line_key in SUMMARY_INCOME_LINE_CATEGORIES:
        session.add(
            FinanceIncomeEntry(
                user_id=user_id,
                year=year,
                month=month,
                category=SUMMARY_INCOME_LINE_CATEGORIES[line_key],
                description=SUMMARY_INCOME_LINE_CATEGORIES[line_key],
                amount=abs(amount),
                source=MIGRATED_SUMMARY_SOURCE,
                external_id=external_id,
            )
        )
    elif line_key in SUMMARY_BILL_LINE_LABELS:
        normalized = amount if amount < 0 else -abs(amount)
        session.add(
            FinanceExpenseEntry(
                user_id=user_id,
                year=year,
                month=month,
                category=BILLS_CATEGORY,
                vendor=SUMMARY_BILL_LINE_LABELS[line_key],
                payment_account=BILLS_PAYMENT_ACCOUNT,
                amount=normalized,
                source=MIGRATED_SUMMARY_SOURCE,
                external_id=external_id,
            )
        )
    elif line_key in SUMMARY_CC_LINE_ACCOUNTS:
        normalized = amount if amount < 0 else -abs(amount)
        session.add(
            FinanceExpenseEntry(
                user_id=user_id,
                year=year,
                month=month,
                category="Outros",
                vendor=line_key.replace("_", " ").title(),
                payment_account=SUMMARY_CC_LINE_ACCOUNTS[line_key],
                amount=normalized,
                source=MIGRATED_SUMMARY_SOURCE,
                external_id=external_id,
            )
        )
    elif line_key in SUMMARY_INVESTMENT_BROKERS:
        session.add(
            FinanceInvestmentEntry(
                user_id=user_id,
                year=year,
                month=month,
                broker=SUMMARY_INVESTMENT_BROKERS[line_key],
                amount=abs(amount),
            )
        )


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
                category=row.get("category", "Outros"),
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

    for row in payload.get("investments", []):
        session.add(
            FinanceInvestmentEntry(
                user_id=user_id,
                year=year,
                month=int(row["month"]),
                broker=row["broker"],
                amount=Decimal(row["amount"]),
            )
        )

    for row in payload.get("summary", []):
        _seed_summary_row(session, user_id, year, row)

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
