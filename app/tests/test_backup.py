from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import select

from app.models.asset_type import AssetType
from app.models.finance import (
    FinanceExpenseEntry,
    FinanceIncomeEntry,
    FinanceInvestmentEntry,
    FinanceTransferEntry,
)
from app.models.investment import Investment
from app.models.security import SecurityLot
from app.models.user import User
from app.services.backup import (
    BACKUP_VERSION,
    export_portfolio_data,
    export_portfolio_json,
    restore_portfolio_json,
)
from app.services.snapshots import capture_portfolio_snapshot
from app.tests.conftest import make_dividend, make_investment, make_lot


def _test_user(session) -> User:
    return session.exec(select(User)).one()


def test_export_includes_all_portfolio_data(session, exchange_type):
    cash = session.exec(
        select(AssetType).where(
            AssetType.slug == "cash",
            AssetType.portfolio_id == exchange_type.portfolio_id,
        )
    ).one()
    make_lot(
        session,
        exchange_type.id,
        "AAPL",
        Decimal("10"),
        Decimal("150"),
        target_pct=Decimal("0.5"),
    )
    make_dividend(
        session,
        exchange_type.id,
        "AAPL",
        date(2024, 6, 1),
        Decimal("25"),
        import_key="div-1",
    )
    make_investment(session, cash.id, "Savings", Decimal("5000"))
    capture_portfolio_snapshot(session, date(2024, 12, 31))

    payload = export_portfolio_data(session)
    assert payload["version"] == BACKUP_VERSION
    assert len(payload["asset_types"]) == 5
    assert len(payload["securities"]) == 1
    assert len(payload["dividends"]) == 1
    assert len(payload["investments"]) == 1
    assert len(payload["symbol_targets"]) == 1
    assert len(payload["snapshots"]) == 1


def test_restore_replaces_portfolio_data(session, exchange_type):
    cash = session.exec(
        select(AssetType).where(
            AssetType.slug == "cash",
            AssetType.portfolio_id == exchange_type.portfolio_id,
        )
    ).one()
    make_lot(session, exchange_type.id, "AAPL", Decimal("10"), Decimal("150"))
    make_investment(session, cash.id, "Savings", Decimal("5000"))

    raw = export_portfolio_json(session)
    make_lot(session, exchange_type.id, "MSFT", Decimal("5"), Decimal("300"))
    restore_portfolio_json(session, raw)

    securities = session.exec(select(SecurityLot)).all()
    symbols = {lot.symbol for lot in securities}
    assert symbols == {"AAPL"}
    assert not session.exec(select(SecurityLot).where(SecurityLot.symbol == "MSFT")).first()

    investments = session.exec(select(Investment)).all()
    assert len(investments) == 1
    assert investments[0].name == "Savings"


def test_export_includes_finance_data(session):
    user = _test_user(session)
    session.add(
        FinanceIncomeEntry(
            user_id=user.id,
            year=2026,
            month=3,
            description="Salary",
            amount=Decimal("5000"),
        )
    )
    session.add(
        FinanceExpenseEntry(
            user_id=user.id,
            year=2026,
            month=2,
            category="Transporte",
            vendor="Uber",
            payment_account="Nubank",
            amount=Decimal("-42.50"),
        )
    )
    session.add(
        FinanceInvestmentEntry(
            user_id=user.id,
            year=2026,
            month=1,
            broker="nubank",
            amount=Decimal("3300"),
        )
    )
    session.commit()

    payload = export_portfolio_data(session)
    assert len(payload["finance_income"]) == 1
    assert payload["finance_income"][0]["description"] == "Salary"
    assert len(payload["finance_expenses"]) == 1
    assert payload["finance_expenses"][0]["category"] == "Transporte"
    assert payload["finance_expenses"][0]["transaction_date"] is None
    assert len(payload["finance_investments"]) == 1
    assert payload["finance_investments"][0]["broker"] == "nubank"


def test_restore_replaces_finance_data(session):
    user = _test_user(session)
    session.add(
        FinanceIncomeEntry(
            user_id=user.id,
            year=2026,
            month=3,
            description="Salary",
            amount=Decimal("5000"),
        )
    )
    session.commit()

    raw = export_portfolio_json(session)
    session.add(
        FinanceIncomeEntry(
            user_id=user.id,
            year=2026,
            month=4,
            description="Bonus",
            amount=Decimal("1000"),
        )
    )
    session.commit()

    restore_portfolio_json(session, raw)

    income = session.exec(
        select(FinanceIncomeEntry).where(FinanceIncomeEntry.user_id == user.id)
    ).all()
    assert len(income) == 1
    assert income[0].description == "Salary"
    assert income[0].month == 3


def test_export_and_restore_expense_transaction_date(session):
    user = _test_user(session)
    session.add(
        FinanceExpenseEntry(
            user_id=user.id,
            year=2026,
            month=2,
            category="Transporte",
            vendor="Metro",
            payment_account="Nubank",
            amount=Decimal("-5.50"),
            transaction_date=date(2026, 2, 10),
        )
    )
    session.commit()

    raw = export_portfolio_json(session)
    for entry in session.exec(select(FinanceExpenseEntry)).all():
        session.delete(entry)
    session.commit()

    restore_portfolio_json(session, raw)
    entry = session.exec(select(FinanceExpenseEntry)).one()
    assert entry.transaction_date == date(2026, 2, 10)


def test_restore_rejects_unsupported_version(session):
    with pytest.raises(ValueError, match="Unsupported backup version"):
        restore_portfolio_json(session, b'{"version": 99, "asset_types": []}')


def test_export_includes_open_finance_metadata(session, exchange_type):
    user = _test_user(session)
    cash = session.exec(
        select(AssetType).where(
            AssetType.slug == "cash",
            AssetType.portfolio_id == exchange_type.portfolio_id,
        )
    ).one()
    session.add(
        FinanceExpenseEntry(
            user_id=user.id,
            year=2026,
            month=6,
            category="Transporte",
            vendor="Uber",
            payment_account="Nubank",
            amount=Decimal("-20"),
            source="open_finance",
            external_id="tx-abc",
        )
    )
    session.add(
        Investment(
            asset_type_id=cash.id,
            institution="Nubank",
            name="CDB",
            current_value=Decimal("1000"),
            source="open_finance",
            external_id="inv-abc",
        )
    )
    session.commit()

    payload = export_portfolio_data(session)
    assert payload["finance_expenses"][0]["source"] == "open_finance"
    assert payload["finance_expenses"][0]["external_id"] == "tx-abc"
    assert payload["investments"][0]["source"] == "open_finance"
    assert payload["investments"][0]["external_id"] == "inv-abc"


def test_backup_restore_roundtrip_with_finance_investments(session):
    """Backup and restore preserves finance investment entries with source field."""
    user = _test_user(session)
    session.add(
        FinanceInvestmentEntry(
            user_id=user.id,
            year=2026,
            month=5,
            broker="interactive_brokers",
            amount=Decimal("5000.00"),
            source="manual",
        )
    )
    session.add(
        FinanceInvestmentEntry(
            user_id=user.id,
            year=2026,
            month=6,
            broker="nubank",
            amount=Decimal("2500.00"),
            source="open_finance",
        )
    )
    session.commit()

    raw = export_portfolio_json(session)

    session.add(
        FinanceInvestmentEntry(
            user_id=user.id,
            year=2026,
            month=7,
            broker="xp",
            amount=Decimal("1000.00"),
        )
    )
    session.commit()

    restore_portfolio_json(session, raw)

    entries = session.exec(
        select(FinanceInvestmentEntry)
        .where(FinanceInvestmentEntry.user_id == user.id)
        .order_by(FinanceInvestmentEntry.month)
    ).all()

    assert len(entries) == 2
    assert entries[0].broker == "interactive_brokers"
    assert entries[0].amount == Decimal("5000.00")
    assert entries[0].source == "manual"
    assert entries[1].broker == "nubank"
    assert entries[1].amount == Decimal("2500.00")
    assert entries[1].source == "open_finance"


def test_restore_dedupes_duplicate_external_ids(session):
    """Older backups can contain duplicate (user_id, external_id) rows."""
    import json

    from app.services.backup import export_portfolio_data

    payload = export_portfolio_data(session)
    payload["finance_expenses"] = [
        {
            "year": 2026,
            "month": 6,
            "transaction_date": "2026-06-01",
            "category": "Outros",
            "vendor": "Older",
            "description": "",
            "payment_account": "Nuconta",
            "amount": "-10.00",
            "subcategory": None,
            "source": "pluggy",
            "external_id": "pluggy:dup",
            "created_at": "2026-06-01T10:00:00+00:00",
            "updated_at": "2026-06-01T10:00:00+00:00",
        },
        {
            "year": 2026,
            "month": 6,
            "transaction_date": "2026-06-02",
            "category": "Outros",
            "vendor": "Newer",
            "description": "",
            "payment_account": "Nuconta",
            "amount": "-20.00",
            "subcategory": None,
            "source": "pluggy",
            "external_id": "pluggy:dup",
            "created_at": "2026-06-02T10:00:00+00:00",
            "updated_at": "2026-06-02T10:00:00+00:00",
        },
    ]
    payload["finance_income"] = [
        {
            "year": 2026,
            "month": 6,
            "category": "Outros",
            "description": "Older income",
            "amount": "100.00",
            "source": "pluggy",
            "external_id": "pluggy:inc",
            "created_at": "2026-06-01T10:00:00+00:00",
            "updated_at": "2026-06-01T10:00:00+00:00",
        },
        {
            "year": 2026,
            "month": 6,
            "category": "Outros",
            "description": "Newer income",
            "amount": "200.00",
            "source": "pluggy",
            "external_id": "pluggy:inc",
            "created_at": "2026-06-02T10:00:00+00:00",
            "updated_at": "2026-06-02T10:00:00+00:00",
        },
    ]
    payload["finance_transfers"] = [
        {
            "year": 2026,
            "month": 6,
            "transaction_date": "2026-06-01",
            "from_account": "Nuconta",
            "to_account": "Nubank",
            "amount": "50.00",
            "description": "Older transfer",
            "source": "pluggy",
            "external_id": "pluggy:tr",
            "created_at": "2026-06-01T10:00:00+00:00",
            "updated_at": "2026-06-01T10:00:00+00:00",
        },
        {
            "year": 2026,
            "month": 6,
            "transaction_date": "2026-06-02",
            "from_account": "Nuconta",
            "to_account": "Nubank",
            "amount": "75.00",
            "description": "Newer transfer",
            "source": "pluggy",
            "external_id": "pluggy:tr",
            "created_at": "2026-06-02T10:00:00+00:00",
            "updated_at": "2026-06-02T10:00:00+00:00",
        },
    ]

    restore_portfolio_json(session, json.dumps(payload).encode("utf-8"))

    expenses = session.exec(select(FinanceExpenseEntry)).all()
    assert len(expenses) == 1
    assert expenses[0].vendor == "Older"
    assert expenses[0].external_id == "pluggy:dup"

    income = session.exec(select(FinanceIncomeEntry)).all()
    assert len(income) == 1
    assert income[0].description == "Older income"

    transfers = session.exec(select(FinanceTransferEntry)).all()
    assert len(transfers) == 1
    assert transfers[0].description == "Older transfer"
