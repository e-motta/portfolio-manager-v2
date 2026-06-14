from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlmodel import select

from app.models.finance import FinanceExpenseEntry, FinanceIncomeEntry
from app.models.investment import Investment
from app.models.user import User
from app.services.cumbuca_oauth import (
    OPEN_FINANCE_SOURCE,
    _access_token_is_valid,
    disconnect_cumbuca,
    user_has_cumbuca,
)
from app.services.cumbuca_sync import (
    build_account_deposit_import_rows,
    build_account_expense_import_rows,
    build_credit_card_expense_import_rows,
    build_expense_import_rows,
    build_investment_import_rows,
    import_selected_expenses,
    import_selected_income,
    import_selected_investments,
    map_category,
    map_payment_account,
    resolve_import_period,
    _transaction_amount,
)
from app.services.finance import (
    BILLS_CATEGORY,
    BILLS_SUBCATEGORY_ALUGUEL,
    load_vendor_category_map,
    save_vendor_category,
)
from app.services.cumbuca_mcp import (
    _extract_json_payload,
    _unwrap_collection,
    format_mcp_error_message,
    _bill_relevant_to_month,
)


class _TextBlock:
    def __init__(self, text: str):
        self.text = text


class _ToolResult:
    def __init__(self, *, content, is_error=False):
        self.content = content
        self.isError = is_error


def test_map_payment_account_nubank_credit():
    account = {"brandName": "Nubank", "name": "example-card"}
    assert map_payment_account(account, source_kind="credit_card") == "Nubank"


def test_map_payment_account_bb_debit():
    account = {"brandName": "Banco do Brasil", "type": "CONTA_CORRENTE"}
    assert map_payment_account(account) == "BB Débito"


def test_map_category_defaults_to_outros():
    assert map_category("Unknown category", "Random merchant") == "Outros"


def test_access_token_is_valid_with_naive_expiry(session):
    user = session.exec(select(User)).one()
    user.cumbuca_access_token = "token"
    user.cumbuca_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    user.cumbuca_token_expires_at = user.cumbuca_token_expires_at.replace(tzinfo=None)
    assert _access_token_is_valid(user)


def test_map_category_transport():
    assert map_category("Transporte", "Uber trip") == "Transporte"


def test_transaction_amount_prefers_brazilian_amount():
    tx = {
        "amount": {"amount": "20.0000", "currency": "USD"},
        "brazilianAmount": {"amount": "112.4500", "currency": "BRL"},
    }
    assert _transaction_amount(tx) == Decimal("112.45")


def test_transaction_amount_skips_foreign_without_brl():
    tx = {"transactionAmount": {"amount": "20.0000", "currency": "USD"}}
    assert _transaction_amount(tx) is None


def test_extract_json_payload_parses_text():
    result = _ToolResult(content=[_TextBlock('{"transactions": []}')])
    assert _extract_json_payload(result) == {"transactions": []}


def test_extract_json_payload_raises_on_error():
    from app.services.cumbuca_mcp import CumbucaMcpError

    result = _ToolResult(content=[_TextBlock("denied")], is_error=True)
    with pytest.raises(CumbucaMcpError, match="denied"):
        _extract_json_payload(result)

    upstream = _ToolResult(
        content=[
            _TextBlock(
                '{"error":"upstream_unavailable","message":"Financial data service is temporarily unavailable."}'
            )
        ],
        is_error=True,
    )
    with pytest.raises(CumbucaMcpError, match="temporarily unavailable"):
        _extract_json_payload(upstream)


def test_unwrap_collection_supports_nested_keys():
    payload = {"data": {"transactions": [{"id": "1"}]}}
    rows = _unwrap_collection(payload, "transactions", "results")
    assert rows == [{"id": "1"}]


def test_format_mcp_error_message_parses_json():
    raw = '{"error":"upstream_unavailable","message":"Financial data service is temporarily unavailable."}'
    assert (
        format_mcp_error_message(raw)
        == "Financial data service is temporarily unavailable."
    )


def test_bill_relevant_to_month():
    bill = {"billClosingDate": "2026-06-01", "dueDate": "2026-06-10"}
    assert _bill_relevant_to_month(bill, 2026, 6)
    assert not _bill_relevant_to_month(bill, 2026, 7)
    assert not _bill_relevant_to_month(bill, 2026, 5)


def test_credit_card_uses_statement_month(session):
    user = session.exec(select(User)).one()
    rows, _ = build_credit_card_expense_import_rows(session, user, year=2026, month=6)
    assert len(rows) == 4
    assert all(row.month == 5 for row in rows)
    assert all(row.payment_account == "Nubank" for row in rows)
    reversal = next(row for row in rows if row.external_id == "tx-002-r")
    assert reversal.is_reversal
    assert reversal.amount == Decimal("28.90")
    assert all(row.external_id != "tx-cc-payment" for row in rows)


def test_credit_card_uses_brazilian_amount_for_usd(session):
    user = session.exec(select(User)).one()
    rows, _ = build_credit_card_expense_import_rows(session, user, year=2026, month=6)
    cursor = next(row for row in rows if row.external_id == "tx-cursor-usd")
    assert cursor.vendor == "Cursor, Ai Powered Ide"
    assert cursor.amount == Decimal("-112.45")


def test_bank_transactions_use_import_month(session):
    user = session.exec(select(User)).one()
    rows, _ = build_account_expense_import_rows(session, user, year=2026, month=6)
    assert len(rows) == 2
    assert all(row.month == 6 for row in rows)


def test_account_deposits_import_credits(session):
    user = session.exec(select(User)).one()
    rows, _ = build_account_deposit_import_rows(session, user, year=2026, month=6)
    assert len(rows) == 1
    assert rows[0].external_id == "tx-005"
    assert rows[0].description == "SALARIO EMPRESA XYZ"
    assert rows[0].amount == Decimal("15000.00")


def test_build_expense_import_rows_from_fixtures(session):
    user = session.exec(select(User)).one()
    cc_rows, _ = build_credit_card_expense_import_rows(session, user, year=2026, month=6)
    bank_rows, _ = build_account_expense_import_rows(session, user, year=2026, month=6)
    rows, warnings = build_expense_import_rows(session, user, year=2026, month=6)
    assert not warnings
    assert len(cc_rows) == 4
    assert len(bank_rows) == 2
    assert len(rows) == 6
    charges = [row for row in rows if not row.is_reversal]
    assert all(row.amount < 0 for row in charges)
    reversals = [row for row in rows if row.is_reversal]
    assert len(reversals) == 1
    assert reversals[0].amount > 0
    assert rows[0].payment_account in {
        "Nubank",
        "Nuconta",
        "BB Débito",
        "XP Crédito",
        "BB Crédito",
        "Wise",
        "Dinheiro",
    }


def test_build_expense_import_rows_skip_existing(session):
    user = session.exec(select(User)).one()
    session.add(
        FinanceExpenseEntry(
            user_id=user.id,
            year=2026,
            month=6,
            category="Transporte",
            vendor="UBER *TRIP",
            payment_account="Nubank",
            amount=Decimal("-28.90"),
            source=OPEN_FINANCE_SOURCE,
            external_id="tx-001",
        )
    )
    session.commit()

    rows, _ = build_expense_import_rows(session, user, year=2026, month=6)
    matched = next(row for row in rows if row.external_id == "tx-001")
    assert matched.already_exists
    assert not matched.selected


def test_import_selected_expenses(session):
    user = session.exec(select(User)).one()
    rows, _ = build_account_expense_import_rows(session, user, year=2026, month=6)
    created = import_selected_expenses(
        session,
        user.id,
        rows,
        {row.row_key for row in rows if not row.already_exists},
    )
    assert created == 2

    again, _ = build_account_expense_import_rows(session, user, year=2026, month=6)
    assert all(row.already_exists for row in again)


def test_import_selected_expenses_saves_vendor_category(session):
    user = session.exec(select(User)).one()
    rows, _ = build_account_expense_import_rows(session, user, year=2026, month=6)
    target = next(row for row in rows if row.external_id == "tx-003")

    created = import_selected_expenses(
        session,
        user.id,
        rows,
        {target.row_key},
        category_overrides={target.row_key: "Assinaturas digitais"},
    )
    assert created == 1

    vendor_map = load_vendor_category_map(session, user.id)
    assert vendor_map[target.vendor.lower()] == "Assinaturas digitais"


def test_import_prefills_bills_subcategory_from_vendor_rule(session):
    user = session.exec(select(User)).one()
    save_vendor_category(
        session,
        user.id,
        "PIX ENVIADO - ALUGUEL",
        BILLS_CATEGORY,
        subcategory=BILLS_SUBCATEGORY_ALUGUEL,
    )
    session.commit()

    rows, _ = build_account_expense_import_rows(session, user, year=2026, month=6)
    target = next(row for row in rows if row.external_id == "tx-003")
    assert target.category == BILLS_CATEGORY
    assert target.subcategory == BILLS_SUBCATEGORY_ALUGUEL


def test_import_selected_expenses_persists_subcategory(session):
    user = session.exec(select(User)).one()
    rows, _ = build_account_expense_import_rows(session, user, year=2026, month=6)
    target = next(row for row in rows if row.external_id == "tx-003")

    created = import_selected_expenses(
        session,
        user.id,
        rows,
        {target.row_key},
        category_overrides={target.row_key: BILLS_CATEGORY},
        subcategory_overrides={target.row_key: BILLS_SUBCATEGORY_ALUGUEL},
    )
    assert created == 1

    entry = session.exec(
        select(FinanceExpenseEntry).where(
            FinanceExpenseEntry.external_id == target.external_id
        )
    ).one()
    assert entry.category == BILLS_CATEGORY
    assert entry.subcategory == BILLS_SUBCATEGORY_ALUGUEL


def test_import_ignores_subcategory_when_category_not_bills(session):
    user = session.exec(select(User)).one()
    rows, _ = build_account_expense_import_rows(session, user, year=2026, month=6)
    target = next(row for row in rows if row.external_id == "tx-003")

    created = import_selected_expenses(
        session,
        user.id,
        rows,
        {target.row_key},
        category_overrides={target.row_key: "Outros"},
        subcategory_overrides={target.row_key: BILLS_SUBCATEGORY_ALUGUEL},
    )
    assert created == 1

    entry = session.exec(
        select(FinanceExpenseEntry).where(
            FinanceExpenseEntry.external_id == target.external_id
        )
    ).one()
    assert entry.category == "Outros"
    assert entry.subcategory is None


def test_vendor_category_suggested_on_future_import(session):
    user = session.exec(select(User)).one()
    save_vendor_category(session, user.id, "UBER *TRIP", "Transporte")
    session.commit()

    rows, _ = build_credit_card_expense_import_rows(session, user, year=2026, month=6)
    uber_row = next(row for row in rows if "UBER" in row.vendor.upper())
    assert uber_row.category == "Transporte"


def test_import_selected_income(session):
    user = session.exec(select(User)).one()
    rows, _ = build_account_deposit_import_rows(session, user, year=2026, month=6)
    created = import_selected_income(
        session,
        user.id,
        rows,
        {row.row_key for row in rows},
    )
    assert created == 1

    income = session.exec(
        select(FinanceIncomeEntry).where(FinanceIncomeEntry.external_id == "tx-005")
    ).one()
    assert income.source == OPEN_FINANCE_SOURCE
    assert income.amount == Decimal("15000.00")

    again, _ = build_account_deposit_import_rows(session, user, year=2026, month=6)
    assert again[0].already_exists


def test_import_selected_expenses_with_period_override(session):
    user = session.exec(select(User)).one()
    rows, _ = build_credit_card_expense_import_rows(session, user, year=2026, month=6)
    target = next(row for row in rows if row.external_id == "tx-001")
    assert target.month == 5

    created = import_selected_expenses(
        session,
        user.id,
        rows,
        {target.row_key},
        period_overrides={target.row_key: (2026, 6)},
    )
    assert created == 1

    entry = session.exec(
        select(FinanceExpenseEntry).where(
            FinanceExpenseEntry.external_id == target.external_id
        )
    ).one()
    assert entry.year == 2026
    assert entry.month == 6


def test_import_selected_income_with_period_override(session):
    user = session.exec(select(User)).one()
    rows, _ = build_account_deposit_import_rows(session, user, year=2026, month=6)
    target = rows[0]
    assert target.month == 6

    created = import_selected_income(
        session,
        user.id,
        rows,
        {target.row_key},
        period_overrides={target.row_key: (2026, 5)},
    )
    assert created == 1

    income = session.exec(
        select(FinanceIncomeEntry).where(FinanceIncomeEntry.external_id == "tx-005")
    ).one()
    assert income.year == 2026
    assert income.month == 5


def test_resolve_import_period_defaults_to_row(session):
    user = session.exec(select(User)).one()
    rows, _ = build_account_expense_import_rows(session, user, year=2026, month=6)
    target = rows[0]
    assert resolve_import_period(target.row_key, target) == (2026, 6)


def test_build_investment_import_rows_filters_equity(session):
    rows = build_investment_import_rows(session)
    names = {row.name for row in rows}
    assert "HGLG11" not in names
    assert "CDB Liquidez Diária" in names


def test_import_selected_investments_create_and_update(session):
    rows = build_investment_import_rows(session)
    created, updated = import_selected_investments(
        session,
        rows,
        {row.row_key for row in rows},
    )
    assert created == 3
    assert updated == 0

    refreshed = build_investment_import_rows(session)
    cdb = next(row for row in refreshed if row.external_id == "inv-cdb-nubank-001")
    assert cdb.is_update

    cdb.current_value = Decimal("50000.00")
    created, updated = import_selected_investments(session, refreshed, {cdb.row_key})
    assert created == 0
    assert updated == 1

    investment = session.exec(
        select(Investment).where(Investment.external_id == "inv-cdb-nubank-001")
    ).one()
    assert investment.current_value == Decimal("50000.00")
    assert investment.source == OPEN_FINANCE_SOURCE


def test_user_has_cumbuca_and_disconnect(session):
    user = session.exec(select(User)).one()
    assert not user_has_cumbuca(user)

    user.cumbuca_refresh_token = "refresh"
    user.cumbuca_access_token = "access"
    user.cumbuca_connected_at = datetime.now(timezone.utc)
    user.cumbuca_oauth_client_id = str(uuid4())
    user.cumbuca_oauth_client_secret = "secret"
    session.add(user)
    session.commit()

    assert user_has_cumbuca(user)
    disconnect_cumbuca(session, user)
    session.refresh(user)
    assert user.cumbuca_refresh_token is None
