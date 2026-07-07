from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlmodel import select

from app.models.finance import (
    FinanceExpenseEntry,
    FinanceIncomeEntry,
    FinanceInvestmentEntry,
    FinanceInvestmentOpenFinanceImport,
    FinanceTransferEntry,
    FinanceVendorCategory,
)
from app.models.investment import Investment
from app.models.user import User
from app.services.cumbuca_oauth import (
    OPEN_FINANCE_SOURCE,
    _access_token_is_valid,
    disconnect_cumbuca,
    user_has_cumbuca,
)
from app.services.cumbuca_sync import (
    build_account_credit_import_rows,
    build_account_expense_import_rows,
    build_credit_card_expense_import_rows,
    build_expense_import_rows,
    build_investment_import_rows,
    import_selected_account_credits,
    import_selected_account_debits,
    import_selected_expenses,
    import_selected_income,
    import_selected_investments,
    map_category,
    map_payment_account,
    resolve_import_period,
    suggest_account_credit_import_kind,
    suggest_account_debit_import_kind,
    suggest_transfer_to_account,
    _month_bounds,
    _transaction_amount,
)
from app.services.finance import (
    BILLS_CATEGORY,
    suggest_investment_broker,
    BILLS_SUBCATEGORY_ALUGUEL,
    load_vendor_category_map,
    load_vendor_rule_map,
    normalize_vendor_key,
    save_vendor_category,
)
from app.services.cumbuca_mcp import (
    _account_transaction_query_end,
    _extract_json_payload,
    _iter_account_transaction_windows,
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
        "brazilianAmount": {"amount": "100.0000", "currency": "BRL"},
    }
    assert _transaction_amount(tx) == Decimal("100.00")


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


def test_month_bounds_caps_end_date_to_today_for_current_month(monkeypatch):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 7)

    monkeypatch.setattr("app.services.cumbuca_sync.date", FixedDate)
    start, end = _month_bounds(2026, 7)
    assert start == "2026-07-01"
    assert end == "2026-07-07"


def test_month_bounds_uses_last_day_for_completed_month(monkeypatch):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 7)

    monkeypatch.setattr("app.services.cumbuca_sync.date", FixedDate)
    start, end = _month_bounds(2026, 6)
    assert start == "2026-06-01"
    assert end == "2026-06-30"


def test_account_transaction_windows_keep_short_ranges_in_one_request(monkeypatch):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 7)

    monkeypatch.setattr("app.services.cumbuca_mcp.date", FixedDate)
    start = date(2026, 7, 1)
    end = date(2026, 7, 7)
    assert _iter_account_transaction_windows(start, end) == [
        (start, end),
        (end, end),
    ]


def test_account_transaction_windows_split_ranges_longer_than_thirty_days(monkeypatch):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 7)

    monkeypatch.setattr("app.services.cumbuca_mcp.date", FixedDate)
    start = date(2026, 6, 1)
    end = date(2026, 7, 7)
    assert _iter_account_transaction_windows(start, end) == [
        (date(2026, 6, 1), date(2026, 7, 1)),
        (date(2026, 7, 1), date(2026, 7, 7)),
        (date(2026, 7, 7), date(2026, 7, 7)),
    ]


def test_account_transaction_windows_add_tail_day_for_completed_month(monkeypatch):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 7)

    monkeypatch.setattr("app.services.cumbuca_mcp.date", FixedDate)
    assert _iter_account_transaction_windows(date(2026, 6, 1), date(2026, 6, 30)) == [
        (date(2026, 6, 1), date(2026, 6, 30)),
        (date(2026, 6, 30), date(2026, 6, 30)),
    ]


def test_account_transaction_query_end_extends_window_when_possible(monkeypatch):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 7)

    monkeypatch.setattr("app.services.cumbuca_mcp.date", FixedDate)
    assert _account_transaction_query_end(date(2026, 6, 30)) == date(2026, 7, 1)


def test_account_transaction_query_end_stays_on_today_for_current_window(monkeypatch):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 7)

    monkeypatch.setattr("app.services.cumbuca_mcp.date", FixedDate)
    assert _account_transaction_query_end(date(2026, 7, 7)) == date(2026, 7, 7)


def test_credit_card_uses_statement_month(session):
    user = session.exec(select(User)).one()
    rows, _ = build_credit_card_expense_import_rows(session, user, year=2026, month=6)
    assert len(rows) == 6
    assert all(row.month == 6 for row in rows)
    assert all(row.payment_account == "Nubank" for row in rows)
    reversal = next(row for row in rows if row.external_id == "tx-002-r")
    assert reversal.is_reversal
    assert reversal.amount == Decimal("30.00")
    assert all(row.external_id != "tx-cc-payment" for row in rows)


def test_credit_card_uses_brazilian_amount_for_usd(session):
    user = session.exec(select(User)).one()
    rows, _ = build_credit_card_expense_import_rows(session, user, year=2026, month=6)
    saas = next(row for row in rows if row.external_id == "tx-saas-usd")
    assert saas.vendor == "SAAS SUBSCRIPTION"
    assert saas.amount == Decimal("-100.00")


def test_bank_transactions_use_import_month(session):
    user = session.exec(select(User)).one()
    rows, _ = build_account_expense_import_rows(session, user, year=2026, month=6)
    assert len(rows) == 5
    assert all(row.month == 6 for row in rows)


def test_account_debit_transfer_suggestions():
    tx = {
        "type": "TRANSFERENCIA",
        "transactionName": "Transferencia enviada para Nubank",
    }
    assert suggest_account_debit_import_kind(tx, tx["transactionName"]) == "transfer"
    assert suggest_transfer_to_account(tx["transactionName"], "Nuconta", tx) == "Nubank"


def test_account_debit_investment_suggestions():
    tx = {
        "type": "APLICACAO",
        "transactionName": "Aplicacao em CDB",
    }
    assert suggest_account_debit_import_kind(tx, tx["transactionName"]) == "investment"
    assert suggest_investment_broker("Nuconta", tx["transactionName"]) == "nubank"

    resgate = {
        "type": "RESGATE_APLIC_FINANCEIRA",
        "transactionName": "Resgate CDB",
    }
    assert suggest_account_debit_import_kind(resgate, resgate["transactionName"]) == "investment"


def test_account_credit_investment_suggestions():
    tx = {
        "type": "RESGATE_APLIC_FINANCEIRA",
        "transactionName": "Resgate CDB",
    }
    assert suggest_account_credit_import_kind(tx, tx["transactionName"]) == "investment"
    assert suggest_investment_broker("Nuconta", tx["transactionName"]) == "nubank"


def test_pagamento_de_fatura_suggested_as_transfer():
    tx = {
        "type": "PAGAMENTO",
        "transactionName": "Pagamento de fatura",
    }
    assert suggest_account_debit_import_kind(tx, "Pagamento de fatura") == "transfer"
    assert suggest_transfer_to_account("Pagamento de fatura", "Nuconta", tx) == "Nubank"


def test_account_debit_import_marks_transfer_rows(session):
    user = session.exec(select(User)).one()
    rows, _ = build_account_expense_import_rows(session, user, year=2026, month=6)
    transfer = next(row for row in rows if row.external_id == "tx-006")
    assert transfer.import_kind == "transfer"
    assert transfer.to_account == "Nubank"
    assert transfer.payment_account == "Nuconta"
    fatura = next(row for row in rows if row.external_id == "tx-fatura")
    assert fatura.import_kind == "transfer"
    assert fatura.to_account == "Nubank"
    aplicacao = next(row for row in rows if row.external_id == "tx-aplicacao")
    assert aplicacao.import_kind == "investment"
    assert aplicacao.broker == "nubank"
    assert aplicacao.amount == Decimal("-2500.00")


def test_imported_transfer_shows_as_transfer_in_preview(session):
    user = session.exec(select(User)).one()
    session.add(
        FinanceTransferEntry(
            user_id=user.id,
            year=2026,
            month=6,
            from_account="Nuconta",
            to_account="Nubank",
            amount=Decimal("5000.00"),
            description="Pagamento de fatura",
            source=OPEN_FINANCE_SOURCE,
            external_id="tx-fatura",
        )
    )
    session.commit()

    rows, _ = build_account_expense_import_rows(session, user, year=2026, month=6)
    row = next(item for item in rows if item.external_id == "tx-fatura")
    assert row.already_exists
    assert row.import_kind == "transfer"
    assert row.to_account == "Nubank"
    assert row.payment_account == "Nuconta"


def test_account_credits_import_credits(session):
    user = session.exec(select(User)).one()
    rows, _ = build_account_credit_import_rows(session, user, year=2026, month=6)
    assert len(rows) == 2
    salary = next(row for row in rows if row.external_id == "tx-005")
    assert salary.amount == Decimal("15000.00")
    assert salary.import_kind == "income"
    resgate = next(row for row in rows if row.external_id == "tx-resgate")
    assert resgate.amount == Decimal("1200.00")
    assert resgate.import_kind == "investment"
    assert resgate.broker == "nubank"


def test_build_expense_import_rows_from_fixtures(session):
    user = session.exec(select(User)).one()
    cc_rows, _ = build_credit_card_expense_import_rows(session, user, year=2026, month=6)
    bank_rows, _ = build_account_expense_import_rows(session, user, year=2026, month=6)
    rows, warnings = build_expense_import_rows(session, user, year=2026, month=6)
    assert not warnings
    assert len(cc_rows) == 6
    assert len(bank_rows) == 5
    assert len(rows) == 11
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
            vendor="TAXI EXAMPLE",
            payment_account="Nubank",
            amount=Decimal("-30.00"),
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
    assert created == 5

    again, _ = build_account_expense_import_rows(session, user, year=2026, month=6)
    assert all(row.already_exists for row in again)


def test_import_selected_account_debits_as_transfer(session):
    user = session.exec(select(User)).one()
    rows, _ = build_account_expense_import_rows(session, user, year=2026, month=6)
    transfer = next(row for row in rows if row.external_id == "tx-006")

    expense_created, transfer_created, investment_created = import_selected_account_debits(
        session,
        user.id,
        rows,
        {transfer.row_key},
        kind_overrides={transfer.row_key: "transfer"},
    )
    assert expense_created == 0
    assert transfer_created == 1
    assert investment_created == 0

    entry = session.exec(
        select(FinanceTransferEntry).where(FinanceTransferEntry.external_id == "tx-006")
    ).one()
    assert entry.from_account == "Nuconta"
    assert entry.to_account == "Nubank"
    assert entry.amount == Decimal("500")
    assert entry.source == OPEN_FINANCE_SOURCE

    again, _ = build_account_expense_import_rows(session, user, year=2026, month=6)
    matched = next(row for row in again if row.external_id == "tx-006")
    assert matched.already_exists


def test_import_selected_account_debits_mixed(session):
    user = session.exec(select(User)).one()
    rows, _ = build_account_expense_import_rows(session, user, year=2026, month=6)
    expense_row = next(row for row in rows if row.external_id == "tx-003")
    transfer_row = next(row for row in rows if row.external_id == "tx-006")

    expense_created, transfer_created, investment_created = import_selected_account_debits(
        session,
        user.id,
        rows,
        {expense_row.row_key, transfer_row.row_key},
        kind_overrides={transfer_row.row_key: "transfer"},
    )
    assert expense_created == 1
    assert transfer_created == 1
    assert investment_created == 0


def test_import_selected_account_debits_as_investment(session):
    user = session.exec(select(User)).one()
    rows, _ = build_account_expense_import_rows(session, user, year=2026, month=6)
    aplicacao = next(row for row in rows if row.external_id == "tx-aplicacao")
    expense_row = next(row for row in rows if row.external_id == "tx-003")

    expense_created, transfer_created, investment_created = import_selected_account_debits(
        session,
        user.id,
        rows,
        {aplicacao.row_key, expense_row.row_key},
        kind_overrides={aplicacao.row_key: "investment"},
    )
    assert expense_created == 1
    assert transfer_created == 0
    assert investment_created == 1

    entry = session.exec(
        select(FinanceInvestmentEntry)
        .where(FinanceInvestmentEntry.user_id == user.id)
        .where(FinanceInvestmentEntry.year == 2026)
        .where(FinanceInvestmentEntry.month == 6)
        .where(FinanceInvestmentEntry.broker == "nubank")
        .where(FinanceInvestmentEntry.source == OPEN_FINANCE_SOURCE)
    ).one()
    assert entry.amount == Decimal("2500.00")

    import_row = session.exec(
        select(FinanceInvestmentOpenFinanceImport).where(
            FinanceInvestmentOpenFinanceImport.external_id == "tx-aplicacao"
        )
    ).one()
    assert import_row.amount == Decimal("2500.00")

    again, _ = build_account_expense_import_rows(session, user, year=2026, month=6)
    matched = next(row for row in again if row.external_id == "tx-aplicacao")
    assert matched.already_exists
    assert matched.import_kind == "investment"
    assert matched.broker == "nubank"


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
    assert vendor_map[normalize_vendor_key(target.vendor)] == "Assinaturas digitais"


def test_import_prefills_bills_subcategory_from_vendor_rule(session):
    user = session.exec(select(User)).one()
    save_vendor_category(
        session,
        user.id,
        "PIX SENT - RENT",
        BILLS_CATEGORY,
        subcategory=BILLS_SUBCATEGORY_ALUGUEL,
    )
    session.commit()

    rows, _ = build_account_expense_import_rows(session, user, year=2026, month=6)
    target = next(row for row in rows if row.external_id == "tx-003")
    assert target.category == BILLS_CATEGORY
    assert target.subcategory == BILLS_SUBCATEGORY_ALUGUEL


def test_import_prefills_description_from_vendor_rule(session):
    user = session.exec(select(User)).one()
    save_vendor_category(
        session,
        user.id,
        "PIX SENT - RENT",
        BILLS_CATEGORY,
        description="Monthly rent",
    )
    session.commit()

    rows, _ = build_account_expense_import_rows(session, user, year=2026, month=6)
    target = next(row for row in rows if row.external_id == "tx-003")
    assert target.description == "Monthly rent"


def test_import_prefills_description_from_previous_expense(session):
    user = session.exec(select(User)).one()
    session.add(
        FinanceExpenseEntry(
            user_id=user.id,
            year=2026,
            month=5,
            category=BILLS_CATEGORY,
            vendor="PIX SENT - RENT",
            description="Apartment rent",
            payment_account="Nuconta",
            amount=Decimal("-3000.00"),
        )
    )
    session.commit()

    rows, _ = build_account_expense_import_rows(session, user, year=2026, month=6)
    target = next(row for row in rows if row.external_id == "tx-003")
    assert target.description == "Apartment rent"


def test_import_prefills_subcategory_from_previous_expense(session):
    user = session.exec(select(User)).one()
    session.add(
        FinanceExpenseEntry(
            user_id=user.id,
            year=2026,
            month=5,
            category=BILLS_CATEGORY,
            vendor="PIX SENT - RENT",
            subcategory=BILLS_SUBCATEGORY_ALUGUEL,
            payment_account="Nuconta",
            amount=Decimal("-3000.00"),
        )
    )
    session.commit()

    rows, _ = build_account_expense_import_rows(session, user, year=2026, month=6)
    target = next(row for row in rows if row.external_id == "tx-003")
    assert target.subcategory == BILLS_SUBCATEGORY_ALUGUEL


def test_import_prefills_subcategory_from_previous_expense_when_vendor_rule_lacks_it(
    session,
):
    user = session.exec(select(User)).one()
    save_vendor_category(
        session,
        user.id,
        "PIX SENT - RENT",
        BILLS_CATEGORY,
    )
    session.add(
        FinanceExpenseEntry(
            user_id=user.id,
            year=2026,
            month=5,
            category=BILLS_CATEGORY,
            vendor="PIX SENT - RENT",
            subcategory=BILLS_SUBCATEGORY_ALUGUEL,
            payment_account="Nuconta",
            amount=Decimal("-3000.00"),
        )
    )
    session.commit()

    rows, _ = build_account_expense_import_rows(session, user, year=2026, month=6)
    target = next(row for row in rows if row.external_id == "tx-003")
    assert target.subcategory == BILLS_SUBCATEGORY_ALUGUEL


def test_import_selected_expenses_saves_vendor_description(session):
    user = session.exec(select(User)).one()
    rows, _ = build_account_expense_import_rows(session, user, year=2026, month=6)
    target = next(row for row in rows if row.external_id == "tx-003")

    created = import_selected_expenses(
        session,
        user.id,
        rows,
        {target.row_key},
        description_overrides={target.row_key: "Monthly rent"},
    )
    assert created == 1

    vendor_rules = load_vendor_rule_map(session, user.id)
    assert vendor_rules[normalize_vendor_key(target.vendor)][2] == "Monthly rent"


def test_import_selected_expenses_saves_vendor_subcategory(session):
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

    vendor_rules = load_vendor_rule_map(session, user.id)
    assert vendor_rules[normalize_vendor_key(target.vendor)][1] == BILLS_SUBCATEGORY_ALUGUEL


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


def test_import_selected_expenses_persists_description(session):
    user = session.exec(select(User)).one()
    rows, _ = build_account_expense_import_rows(session, user, year=2026, month=6)
    target = next(row for row in rows if row.external_id == "tx-003")

    created = import_selected_expenses(
        session,
        user.id,
        rows,
        {target.row_key},
        description_overrides={target.row_key: "Monthly subscription"},
    )
    assert created == 1

    entry = session.exec(
        select(FinanceExpenseEntry).where(
            FinanceExpenseEntry.external_id == target.external_id
        )
    ).one()
    assert entry.description == "Monthly subscription"


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
    save_vendor_category(session, user.id, "TAXI EXAMPLE", "Transporte")
    session.commit()

    rows, _ = build_credit_card_expense_import_rows(session, user, year=2026, month=6)
    taxi_row = next(row for row in rows if "TAXI" in row.vendor.upper())
    assert taxi_row.category == "Transporte"


def test_vendor_category_matches_installment_suffixes(session):
    user = session.exec(select(User)).one()
    save_vendor_category(session, user.id, "Vendor Installment 1/3", "Compras online")
    session.commit()

    rows, _ = build_credit_card_expense_import_rows(session, user, year=2026, month=6)
    later = next(row for row in rows if row.external_id == "tx-installment-2")
    assert later.vendor == "Vendor Installment 2/3"
    assert later.category == "Compras online"


def test_vendor_category_matches_legacy_installment_key(session):
    user = session.exec(select(User)).one()
    session.add(
        FinanceVendorCategory(
            user_id=user.id,
            vendor_key="vendor installment",
            category="Compras online",
        )
    )
    session.commit()

    rows, _ = build_credit_card_expense_import_rows(session, user, year=2026, month=6)
    later = next(row for row in rows if row.external_id == "tx-installment-2")
    assert later.category == "Compras online"


def test_vendor_category_falls_back_to_expense_history(session):
    user = session.exec(select(User)).one()
    session.add(
        FinanceExpenseEntry(
            user_id=user.id,
            year=2026,
            month=4,
            category="Compras online",
            vendor="Vendor Installment 3/3",
            payment_account="Nubank",
            amount=Decimal("-300.00"),
            source=OPEN_FINANCE_SOURCE,
            external_id="legacy-installment-3",
        )
    )
    session.commit()

    rows, _ = build_credit_card_expense_import_rows(session, user, year=2026, month=6)
    later = next(row for row in rows if row.external_id == "tx-installment-2")
    assert later.category == "Compras online"


def test_import_selected_income(session):
    user = session.exec(select(User)).one()
    rows, _ = build_account_credit_import_rows(session, user, year=2026, month=6)
    salary = next(row for row in rows if row.external_id == "tx-005")
    created = import_selected_income(
        session,
        user.id,
        rows,
        {salary.row_key},
    )
    assert created == 1

    income = session.exec(
        select(FinanceIncomeEntry).where(FinanceIncomeEntry.external_id == "tx-005")
    ).one()
    assert income.source == OPEN_FINANCE_SOURCE
    assert income.amount == Decimal("15000.00")

    again, _ = build_account_credit_import_rows(session, user, year=2026, month=6)
    imported = next(row for row in again if row.external_id == "tx-005")
    assert imported.already_exists


def test_import_selected_account_credits_as_investment(session):
    user = session.exec(select(User)).one()
    session.add(
        FinanceInvestmentEntry(
            user_id=user.id,
            year=2026,
            month=6,
            broker="nubank",
            amount=Decimal("5000.00"),
            source="manual",
        )
    )
    session.commit()

    rows, _ = build_account_credit_import_rows(session, user, year=2026, month=6)
    resgate = next(row for row in rows if row.external_id == "tx-resgate")

    income_created, investment_created = import_selected_account_credits(
        session,
        user.id,
        rows,
        {resgate.row_key},
        kind_overrides={resgate.row_key: "investment"},
    )
    assert income_created == 0
    assert investment_created == 1

    entries = session.exec(
        select(FinanceInvestmentEntry)
        .where(FinanceInvestmentEntry.user_id == user.id)
        .where(FinanceInvestmentEntry.year == 2026)
        .where(FinanceInvestmentEntry.month == 6)
        .where(FinanceInvestmentEntry.broker == "nubank")
        .order_by(FinanceInvestmentEntry.created_at)
    ).all()
    assert len(entries) == 2
    assert sum(entry.amount for entry in entries) == Decimal("3800.00")
    imported = next(entry for entry in entries if entry.source == OPEN_FINANCE_SOURCE)
    assert imported.amount == Decimal("-1200.00")

    import_row = session.exec(
        select(FinanceInvestmentOpenFinanceImport).where(
            FinanceInvestmentOpenFinanceImport.external_id == "tx-resgate"
        )
    ).one()
    assert import_row.amount == Decimal("-1200.00")

    again, _ = build_account_credit_import_rows(session, user, year=2026, month=6)
    matched = next(row for row in again if row.external_id == "tx-resgate")
    assert matched.already_exists
    assert matched.import_kind == "investment"


def test_import_selected_expenses_with_period_override(session):
    user = session.exec(select(User)).one()
    rows, _ = build_credit_card_expense_import_rows(session, user, year=2026, month=6)
    target = next(row for row in rows if row.external_id == "tx-001")
    assert target.month == 6

    created = import_selected_expenses(
        session,
        user.id,
        rows,
        {target.row_key},
        period_overrides={target.row_key: (2026, 5)},
    )
    assert created == 1

    entry = session.exec(
        select(FinanceExpenseEntry).where(
            FinanceExpenseEntry.external_id == target.external_id
        )
    ).one()
    assert entry.year == 2026
    assert entry.month == 5


def test_import_selected_income_with_period_override(session):
    user = session.exec(select(User)).one()
    rows, _ = build_account_credit_import_rows(session, user, year=2026, month=6)
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
