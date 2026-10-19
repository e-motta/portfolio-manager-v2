"""Tests for Pluggy integration."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlmodel import select

from app.models.finance import FinanceExpenseEntry
from app.models.investment import Investment
from app.models.open_finance import OpenFinanceConnection
from app.models.user import User
from app.services.pluggy_client import (
    _parse_decimal,
    _parse_date,
    clear_auth_cache,
)
from app.services.pluggy_sync import (
    PLUGGY_PROVIDER,
    add_pluggy_connection,
    build_pluggy_expense_import_rows,
    build_pluggy_income_import_rows,
    build_pluggy_investment_import_rows,
    get_pluggy_connections,
    is_exchange_traded_investment,
    map_asset_type_slug,
    map_category,
    map_payment_account,
    pluggy_investment_current_value,
    remove_pluggy_connection,
    suggest_pluggy_debit_import_kind,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def clear_pluggy_cache():
    """Clear Pluggy auth cache before each test."""
    clear_auth_cache()
    yield
    clear_auth_cache()


@pytest.fixture
def pluggy_item():
    return _load_fixture("pluggy_item.json")


@pytest.fixture
def pluggy_accounts():
    return _load_fixture("pluggy_accounts.json")


@pytest.fixture
def pluggy_transactions():
    return _load_fixture("pluggy_transactions.json")


@pytest.fixture
def pluggy_investments():
    return _load_fixture("pluggy_investments.json")


def test_parse_decimal_handles_none():
    assert _parse_decimal(None) == Decimal("0")


def test_parse_decimal_handles_string():
    assert _parse_decimal("123.45") == Decimal("123.45")


def test_parse_decimal_handles_float():
    assert _parse_decimal(100.50) == Decimal("100.5")


def test_parse_date_handles_iso_string():
    assert _parse_date("2026-06-15") == date(2026, 6, 15)


def test_parse_date_handles_datetime_string():
    assert _parse_date("2026-06-15T10:30:00Z") == date(2026, 6, 15)


def test_parse_date_handles_none():
    assert _parse_date(None) is None


def test_map_payment_account_nubank():
    assert map_payment_account("Nubank", "CHECKING_ACCOUNT") == "Nuconta"


def test_map_payment_account_bb():
    assert map_payment_account("Banco do Brasil", "CHECKING") == "BB Débito"


def test_map_payment_account_unknown_defaults_to_nuconta():
    assert map_payment_account("Unknown Bank", "") == "Nuconta"


def test_map_category_groceries():
    assert map_category("Groceries", "Supermercado Extra") == "Supermercado"


def test_map_category_transport():
    assert map_category("Transport", "Uber Trip") == "Transporte"


def test_map_category_food():
    assert map_category("Food", "Restaurante") == "Alimentação fora"


def test_map_category_unknown_falls_back_to_description():
    assert map_category("Unknown", "supermercado test") == "Supermercado"


def test_map_category_unknown_defaults_to_outros():
    assert map_category("Unknown", "Random purchase") == "Outros"


def test_map_asset_type_slug_cdb():
    inv = {"type": "FIXED_INCOME", "subtype": "CDB", "name": "CDB Nubank"}
    assert map_asset_type_slug(inv) == "bonds"


def test_map_asset_type_slug_savings():
    inv = {"type": "FIXED_INCOME", "subtype": "SAVINGS", "name": "Poupança"}
    assert map_asset_type_slug(inv) == "cash"


def test_map_asset_type_slug_tesouro():
    inv = {"type": "FIXED_INCOME", "subtype": "TREASURY", "name": "Tesouro Selic"}
    assert map_asset_type_slug(inv) == "bonds"


def test_is_exchange_traded_equity():
    assert is_exchange_traded_investment({"type": "EQUITY", "subtype": "STOCK"})


def test_is_exchange_traded_etf():
    assert is_exchange_traded_investment({"type": "ETF", "subtype": "ETF"})


def test_is_not_exchange_traded_fixed_income():
    assert not is_exchange_traded_investment({"type": "FIXED_INCOME", "subtype": "CDB"})


class TestPluggyConnectionManagement:
    """Tests for Pluggy connection management."""

    def test_add_pluggy_connection_success(self, session, pluggy_item):
        user = session.exec(select(User)).one()

        with patch("app.services.pluggy_sync.is_pluggy_available", return_value=True), \
             patch("app.services.pluggy_sync.validate_item") as mock_validate:
            mock_validate.return_value = (True, pluggy_item)

            connection, error = add_pluggy_connection(
                session,
                user.id,
                "550e8400-e29b-41d4-a716-446655440000",
            )

            assert error is None
            assert connection is not None
            assert connection.provider == PLUGGY_PROVIDER
            assert connection.external_id == "550e8400-e29b-41d4-a716-446655440000"
            assert connection.institution_name == "Nubank"
            assert connection.status == "active"

    def test_add_pluggy_connection_already_exists(self, session, pluggy_item):
        user = session.exec(select(User)).one()

        session.add(OpenFinanceConnection(
            user_id=user.id,
            provider=PLUGGY_PROVIDER,
            external_id="550e8400-e29b-41d4-a716-446655440000",
            institution_name="Nubank",
            status="active",
        ))
        session.commit()

        with patch("app.services.pluggy_sync.is_pluggy_available", return_value=True), \
             patch("app.services.pluggy_sync.validate_item") as mock_validate:
            mock_validate.return_value = (True, pluggy_item)

            connection, error = add_pluggy_connection(
                session,
                user.id,
                "550e8400-e29b-41d4-a716-446655440000",
            )

            assert connection is None
            assert error == "This connection already exists."

    def test_add_pluggy_connection_invalid_item(self, session):
        user = session.exec(select(User)).one()

        with patch("app.services.pluggy_sync.is_pluggy_available", return_value=True), \
             patch("app.services.pluggy_sync.validate_item") as mock_validate:
            mock_validate.return_value = (False, "Item not found.")

            connection, error = add_pluggy_connection(
                session,
                user.id,
                "invalid-item-id",
            )

            assert connection is None
            assert error == "Item not found."
    
    def test_add_pluggy_connection_not_configured(self, session):
        user = session.exec(select(User)).one()

        with patch("app.services.pluggy_sync.is_pluggy_available", return_value=False):
            connection, error = add_pluggy_connection(
                session,
                user.id,
                "any-item-id",
            )

            assert connection is None
            assert error == "Pluggy is not configured."

    def test_remove_pluggy_connection(self, session):
        user = session.exec(select(User)).one()

        connection = OpenFinanceConnection(
            user_id=user.id,
            provider=PLUGGY_PROVIDER,
            external_id="test-item-id",
            institution_name="Test Bank",
            status="active",
        )
        session.add(connection)
        session.commit()
        connection_id = connection.id

        removed = remove_pluggy_connection(session, user.id, connection_id)
        assert removed

        remaining = get_pluggy_connections(session, user.id)
        assert len(remaining) == 0

    def test_remove_pluggy_connection_not_found(self, session):
        user = session.exec(select(User)).one()
        removed = remove_pluggy_connection(session, user.id, uuid4())
        assert not removed

    def test_get_pluggy_connections_filters_by_provider(self, session):
        user = session.exec(select(User)).one()

        session.add(OpenFinanceConnection(
            user_id=user.id,
            provider=PLUGGY_PROVIDER,
            external_id="pluggy-item-1",
            institution_name="Nubank",
            status="active",
        ))
        session.add(OpenFinanceConnection(
            user_id=user.id,
            provider="cumbuca",
            external_id="",
            institution_name="Cumbuca",
            status="active",
        ))
        session.commit()

        connections = get_pluggy_connections(session, user.id)
        assert len(connections) == 1
        assert connections[0].provider == PLUGGY_PROVIDER


class TestPluggyExpenseImport:
    """Tests for Pluggy expense import."""

    def test_build_expense_import_rows(self, session, pluggy_accounts, pluggy_transactions):
        user = session.exec(select(User)).one()

        session.add(OpenFinanceConnection(
            user_id=user.id,
            provider=PLUGGY_PROVIDER,
            external_id="550e8400-e29b-41d4-a716-446655440000",
            institution_name="Nubank",
            status="active",
        ))
        session.commit()

        connections = get_pluggy_connections(session, user.id)

        with patch("app.services.pluggy_sync.fetch_accounts") as mock_accounts, \
             patch("app.services.pluggy_sync.fetch_transactions") as mock_tx:
            mock_accounts.return_value = [
                acc for acc in pluggy_accounts["results"]
                if acc["type"] != "CREDIT"
            ]
            mock_tx.return_value = pluggy_transactions["results"]

            rows, warnings = build_pluggy_expense_import_rows(
                session,
                user.id,
                connections,
                year=2026,
                month=6,
            )

        expense_rows = [r for r in rows if r.amount < 0]
        assert len(expense_rows) == 5

        supermarket = next((r for r in expense_rows if "Supermercado" in r.vendor), None)
        assert supermarket is not None
        assert supermarket.category == "Supermercado"
        assert supermarket.amount == Decimal("-350.50")

    def test_expense_import_skips_credits(self, session, pluggy_accounts, pluggy_transactions):
        user = session.exec(select(User)).one()

        session.add(OpenFinanceConnection(
            user_id=user.id,
            provider=PLUGGY_PROVIDER,
            external_id="550e8400-e29b-41d4-a716-446655440000",
            institution_name="Nubank",
            status="active",
        ))
        session.commit()

        connections = get_pluggy_connections(session, user.id)

        with patch("app.services.pluggy_sync.fetch_accounts") as mock_accounts, \
             patch("app.services.pluggy_sync.fetch_transactions") as mock_tx:
            mock_accounts.return_value = [
                acc for acc in pluggy_accounts["results"]
                if acc["type"] != "CREDIT"
            ]
            mock_tx.return_value = pluggy_transactions["results"]

            rows, _ = build_pluggy_expense_import_rows(
                session,
                user.id,
                connections,
                year=2026,
                month=6,
            )

        credit_rows = [r for r in rows if r.amount > 0]
        assert len(credit_rows) == 0


class TestPluggyIncomeImport:
    """Tests for Pluggy income import."""

    def test_build_income_import_rows(self, session, pluggy_accounts, pluggy_transactions):
        user = session.exec(select(User)).one()

        session.add(OpenFinanceConnection(
            user_id=user.id,
            provider=PLUGGY_PROVIDER,
            external_id="550e8400-e29b-41d4-a716-446655440000",
            institution_name="Nubank",
            status="active",
        ))
        session.commit()

        connections = get_pluggy_connections(session, user.id)

        with patch("app.services.pluggy_sync.fetch_accounts") as mock_accounts, \
             patch("app.services.pluggy_sync.fetch_transactions") as mock_tx:
            mock_accounts.return_value = [
                acc for acc in pluggy_accounts["results"]
                if acc["type"] != "CREDIT"
            ]
            mock_tx.return_value = pluggy_transactions["results"]

            rows, warnings = build_pluggy_income_import_rows(
                session,
                user.id,
                connections,
                year=2026,
                month=6,
            )

        assert len(rows) == 1
        salary = rows[0]
        assert salary.amount == Decimal("12000.00")
        assert "Salário" in salary.description


class TestPluggyInvestmentImport:
    """Tests for Pluggy investment import."""

    def test_build_investment_import_rows_filters_equity(self, session, pluggy_investments):
        user = session.exec(select(User)).one()

        session.add(OpenFinanceConnection(
            user_id=user.id,
            provider=PLUGGY_PROVIDER,
            external_id="550e8400-e29b-41d4-a716-446655440000",
            institution_name="Nubank",
            status="active",
        ))
        session.commit()

        connections = get_pluggy_connections(session, user.id)

        with patch("app.services.pluggy_sync.fetch_investments") as mock_inv:
            mock_inv.return_value = pluggy_investments["results"]

            rows, warnings = build_pluggy_investment_import_rows(session, user.id, connections)

        names = {row.name for row in rows}
        assert "CDB Nubank 100% CDI" in names
        assert "Tesouro Selic 2029" in names
        assert "Poupança" in names
        assert "Fundo DI" not in names
        assert "BOVA11" not in names

    def test_investment_import_maps_asset_types(self, session, pluggy_investments):
        user = session.exec(select(User)).one()

        session.add(OpenFinanceConnection(
            user_id=user.id,
            provider=PLUGGY_PROVIDER,
            external_id="550e8400-e29b-41d4-a716-446655440000",
            institution_name="Nubank",
            status="active",
        ))
        session.commit()

        connections = get_pluggy_connections(session, user.id)

        with patch("app.services.pluggy_sync.fetch_investments") as mock_inv:
            mock_inv.return_value = pluggy_investments["results"]

            rows, _ = build_pluggy_investment_import_rows(session, user.id, connections)

        cdb = next((r for r in rows if "CDB" in r.name), None)
        assert cdb is not None
        assert cdb.asset_type_slug == "bonds"

        poupanca = next((r for r in rows if "Poupança" in r.name), None)
        assert poupanca is not None
        assert poupanca.asset_type_slug == "cash"

    def test_current_value_uses_balance_not_unit_price(self, session, pluggy_investments):
        user = session.exec(select(User)).one()
        _add_pluggy_connection(session, user)
        connections = get_pluggy_connections(session, user.id)

        with patch("app.services.pluggy_sync.fetch_investments") as mock_inv:
            mock_inv.return_value = pluggy_investments["results"]
            rows, _ = build_pluggy_investment_import_rows(session, user.id, connections)

        cdb = next(row for row in rows if row.external_id == "pluggy:inv-pluggy-cdb-001")
        tesouro = next(row for row in rows if "Tesouro" in row.name)
        assert cdb.current_value == Decimal("52000.00")
        assert tesouro.current_value == Decimal("85000.00")
        assert cdb.current_value != Decimal("1.04")
        assert cdb.current_value != Decimal("50000.00")

    def test_resync_updates_existing_pluggy_investment_value(self, session, pluggy_investments):
        from app.services.cumbuca_sync import ImportInvestmentRow, import_selected_investments
        from app.services.pluggy_sync import PLUGGY_SOURCE

        user = session.exec(select(User)).one()
        _add_pluggy_connection(session, user)
        connections = get_pluggy_connections(session, user.id)

        with patch("app.services.pluggy_sync.fetch_investments") as mock_inv:
            mock_inv.return_value = pluggy_investments["results"]
            rows, _ = build_pluggy_investment_import_rows(session, user.id, connections)

        converted = [
            ImportInvestmentRow(
                row_key=row.row_key,
                external_id=row.external_id,
                institution=row.institution,
                name=row.name,
                asset_type_slug=row.asset_type_slug,
                current_value=row.current_value,
                already_exists=row.already_exists,
                selected=row.selected,
                is_update=row.is_update,
            )
            for row in rows
        ]
        created, updated = import_selected_investments(
            session, converted, {row.row_key for row in converted},
            source=PLUGGY_SOURCE, user_id=user.id,
        )
        assert created == len(converted)
        assert updated == 0

        stored = session.exec(
            select(Investment).where(Investment.external_id == "pluggy:inv-pluggy-cdb-001")
        ).one()
        stored.current_value = Decimal("1.04")
        session.add(stored)
        session.commit()

        with patch("app.services.pluggy_sync.fetch_investments") as mock_inv:
            mock_inv.return_value = pluggy_investments["results"]
            again, _ = build_pluggy_investment_import_rows(session, user.id, connections)

        cdb = next(row for row in again if row.external_id == "pluggy:inv-pluggy-cdb-001")
        assert cdb.is_update
        assert cdb.already_exists
        assert cdb.selected
        assert cdb.current_value == Decimal("52000.00")

        converted_again = [
            ImportInvestmentRow(
                row_key=row.row_key,
                external_id=row.external_id,
                institution=row.institution,
                name=row.name,
                asset_type_slug=row.asset_type_slug,
                current_value=row.current_value,
                already_exists=row.already_exists,
                selected=row.selected,
                is_update=row.is_update,
            )
            for row in again
        ]
        created, updated = import_selected_investments(
            session, converted_again, {cdb.row_key},
            source=PLUGGY_SOURCE, user_id=user.id,
        )
        assert created == 0
        assert updated == 1
        session.refresh(stored)
        assert stored.current_value == Decimal("52000.00")
        assert stored.source == "pluggy"


def test_pluggy_investment_current_value_ignores_unit_price():
    cdb = {
        "type": "FIXED_INCOME",
        "subtype": "CDB",
        "balance": 52000.00,
        "value": 1.04,
        "amount": 50000.00,
        "quantity": 50000,
    }
    fund = {
        "type": "MUTUAL_FUND",
        "subtype": "ETF",
        "balance": 15000.00,
        "value": 3.25,
        "amount": 14000.00,
        "quantity": 4307.69,
    }
    assert pluggy_investment_current_value(cdb) == Decimal("52000.00")
    assert pluggy_investment_current_value(fund) == Decimal("15000.00")
    assert pluggy_investment_current_value({"value": 1.04, "quantity": 10}) is None
    assert pluggy_investment_current_value({"amount": 4800.00}) == Decimal("4800.00")


class TestPluggyDeduplication:
    """Tests for deduplication between Pluggy and Cumbuca."""

    def test_pluggy_external_id_has_prefix(self, session, pluggy_accounts, pluggy_transactions):
        user = session.exec(select(User)).one()

        session.add(OpenFinanceConnection(
            user_id=user.id,
            provider=PLUGGY_PROVIDER,
            external_id="550e8400-e29b-41d4-a716-446655440000",
            institution_name="Nubank",
            status="active",
        ))
        session.commit()

        connections = get_pluggy_connections(session, user.id)

        with patch("app.services.pluggy_sync.fetch_accounts") as mock_accounts, \
             patch("app.services.pluggy_sync.fetch_transactions") as mock_tx:
            mock_accounts.return_value = [
                acc for acc in pluggy_accounts["results"]
                if acc["type"] != "CREDIT"
            ]
            mock_tx.return_value = pluggy_transactions["results"]

            rows, _ = build_pluggy_expense_import_rows(
                session,
                user.id,
                connections,
                year=2026,
                month=6,
            )

        for row in rows:
            assert row.external_id.startswith("pluggy:")

    def test_existing_pluggy_import_marked_as_existing(self, session, pluggy_accounts, pluggy_transactions):
        user = session.exec(select(User)).one()

        session.add(FinanceExpenseEntry(
            user_id=user.id,
            year=2026,
            month=6,
            category="Supermercado",
            vendor="Supermercado Extra",
            payment_account="Nuconta",
            amount=Decimal("-350.50"),
            source="pluggy",
            external_id="pluggy:tx-pluggy-002",
        ))
        session.commit()

        session.add(OpenFinanceConnection(
            user_id=user.id,
            provider=PLUGGY_PROVIDER,
            external_id="550e8400-e29b-41d4-a716-446655440000",
            institution_name="Nubank",
            status="active",
        ))
        session.commit()

        connections = get_pluggy_connections(session, user.id)

        with patch("app.services.pluggy_sync.fetch_accounts") as mock_accounts, \
             patch("app.services.pluggy_sync.fetch_transactions") as mock_tx:
            mock_accounts.return_value = [
                acc for acc in pluggy_accounts["results"]
                if acc["type"] != "CREDIT"
            ]
            mock_tx.return_value = pluggy_transactions["results"]

            rows, _ = build_pluggy_expense_import_rows(
                session,
                user.id,
                connections,
                year=2026,
                month=6,
            )

        supermarket = next((r for r in rows if "tx-pluggy-002" in r.external_id), None)
        assert supermarket is not None
        assert supermarket.already_exists
        assert not supermarket.selected


def _add_pluggy_connection(session, user, *, status="active", institution="Nubank"):
    connection = OpenFinanceConnection(
        user_id=user.id,
        provider=PLUGGY_PROVIDER,
        external_id="550e8400-e29b-41d4-a716-446655440000",
        institution_name=institution,
        status=status,
    )
    session.add(connection)
    session.commit()
    return connection


class TestPluggyClassification:
    def test_transfer_category_defaults_to_transfer(self, session, pluggy_accounts, pluggy_transactions):
        user = session.exec(select(User)).one()
        _add_pluggy_connection(session, user)
        connections = get_pluggy_connections(session, user.id)

        with patch("app.services.pluggy_sync.fetch_accounts") as mock_accounts, \
             patch("app.services.pluggy_sync.fetch_transactions") as mock_tx:
            mock_accounts.return_value = [
                acc for acc in pluggy_accounts["results"] if acc["type"] != "CREDIT"
            ]
            mock_tx.return_value = pluggy_transactions["results"]
            rows, _ = build_pluggy_expense_import_rows(
                session, user.id, connections, year=2026, month=6
            )

        transfer = next((r for r in rows if "Transferência" in r.vendor), None)
        assert transfer is not None
        assert transfer.import_kind == "transfer"

    def test_pix_purchase_is_not_a_transfer(self):
        tx = {
            "id": "tx-pix-ifood",
            "description": "PIX IFOOD",
            "amount": -42.00,
            "type": "DEBIT",
            "category": "Transfer - PIX",
            "categoryId": "05070000",
        }
        assert suggest_pluggy_debit_import_kind(tx, "PIX IFOOD") == "expense"

    def test_own_account_transfer_matches_exact_category_id(self):
        tx = {
            "id": "tx-own",
            "description": "PIX para conta XP",
            "category": "Same person transfer - PIX",
            "categoryId": "04020000",
        }
        assert suggest_pluggy_debit_import_kind(tx, tx["description"]) == "transfer"

    def test_ted_purchase_category_is_not_a_transfer(self):
        tx = {
            "id": "tx-ted-shop",
            "description": "Magazine Luiza",
            "category": "Transfer - TED",
            "categoryId": "05080000",
        }
        assert suggest_pluggy_debit_import_kind(tx, tx["description"]) == "expense"

    def test_bill_payment_left_unselected(self, session, pluggy_accounts):
        user = session.exec(select(User)).one()
        _add_pluggy_connection(session, user)
        connections = get_pluggy_connections(session, user.id)
        bill_tx = {
            "id": "tx-bill-001",
            "accountId": "acc-pluggy-checking-001",
            "description": "Pagamento de fatura Nubank",
            "amount": -2500.00,
            "date": "2026-06-12",
            "type": "DEBIT",
            "category": "Transfer",
        }

        with patch("app.services.pluggy_sync.fetch_accounts") as mock_accounts, \
             patch("app.services.pluggy_sync.fetch_transactions") as mock_tx:
            mock_accounts.return_value = [
                acc for acc in pluggy_accounts["results"] if acc["type"] != "CREDIT"
            ]
            mock_tx.return_value = [bill_tx]
            rows, _ = build_pluggy_expense_import_rows(
                session, user.id, connections, year=2026, month=6
            )

        assert len(rows) == 1
        assert rows[0].import_kind == "transfer"
        assert rows[0].is_bill_payment
        assert not rows[0].selected

    def test_bill_payment_prefers_pluggy_category(self, session, pluggy_accounts):
        user = session.exec(select(User)).one()
        _add_pluggy_connection(session, user)
        connections = get_pluggy_connections(session, user.id)
        bill_tx = {
            "id": "tx-bill-cat",
            "accountId": "acc-pluggy-checking-001",
            "description": "Nubank Mastercard",
            "amount": -1800.00,
            "date": "2026-06-12",
            "type": "DEBIT",
            "category": "Credit card payment",
            "categoryId": "05090000",
        }

        with patch("app.services.pluggy_sync.fetch_accounts") as mock_accounts, \
             patch("app.services.pluggy_sync.fetch_transactions") as mock_tx:
            mock_accounts.return_value = [
                acc for acc in pluggy_accounts["results"] if acc["type"] != "CREDIT"
            ]
            mock_tx.return_value = [bill_tx]
            rows, _ = build_pluggy_expense_import_rows(
                session, user.id, connections, year=2026, month=6
            )

        assert len(rows) == 1
        assert rows[0].import_kind == "transfer"
        assert rows[0].is_bill_payment
        assert not rows[0].selected


class TestPluggyCreditCards:
    def test_imports_credit_card_purchases_and_skips_bill(self, session, pluggy_accounts):
        user = session.exec(select(User)).one()
        _add_pluggy_connection(session, user)
        connections = get_pluggy_connections(session, user.id)
        credit_txs = _load_fixture("pluggy_credit_transactions.json")["results"]

        def _transactions(account_id, **_kwargs):
            if account_id == "acc-pluggy-credit-001":
                return credit_txs
            return []

        with patch("app.services.pluggy_sync.fetch_accounts") as mock_accounts, \
             patch("app.services.pluggy_sync.fetch_transactions") as mock_tx:
            mock_accounts.return_value = pluggy_accounts["results"]
            mock_tx.side_effect = _transactions
            rows, _ = build_pluggy_expense_import_rows(
                session, user.id, connections, year=2026, month=6
            )

        vendors = {row.vendor for row in rows}
        assert "iFood" in vendors
        assert "Magazine Luiza" in vendors
        assert "Pagamento recebido" not in vendors

        ifood = next(row for row in rows if row.vendor == "iFood")
        assert ifood.amount == Decimal("-89.90")
        assert ifood.payment_account == "Nubank"
        assert ifood.transaction_date == date(2026, 6, 3)
        assert ifood.import_kind == "expense"
        assert ifood.selected

        installment = next(row for row in rows if row.vendor == "Magazine Luiza")
        assert installment.transaction_date == date(2026, 5, 10)
        assert installment.amount == Decimal("-200.00")

        refund = next(row for row in rows if row.vendor == "Estorno iFood")
        assert refund.is_reversal
        assert refund.amount == Decimal("45.00")
        assert refund.import_kind == "expense"
        assert refund.selected


class TestCrossProviderDedupe:
    def test_flags_matching_cumbuca_expense(self, session, pluggy_accounts, pluggy_transactions):
        user = session.exec(select(User)).one()
        session.add(FinanceExpenseEntry(
            user_id=user.id,
            year=2026,
            month=6,
            transaction_date=date(2026, 6, 8),
            category="Supermercado",
            vendor="Supermercado Extra",
            payment_account="Nuconta",
            amount=Decimal("-350.50"),
            source="open_finance",
            external_id="cumbuca-tx-002",
        ))
        session.commit()
        _add_pluggy_connection(session, user)
        connections = get_pluggy_connections(session, user.id)

        with patch("app.services.pluggy_sync.fetch_accounts") as mock_accounts, \
             patch("app.services.pluggy_sync.fetch_transactions") as mock_tx:
            mock_accounts.return_value = [
                acc for acc in pluggy_accounts["results"] if acc["type"] != "CREDIT"
            ]
            mock_tx.return_value = pluggy_transactions["results"]
            rows, _ = build_pluggy_expense_import_rows(
                session, user.id, connections, year=2026, month=6
            )

        supermarket = next(row for row in rows if "Supermercado Extra" in row.vendor)
        assert supermarket.likely_duplicate
        assert not supermarket.selected
        assert not supermarket.already_exists


class TestPluggyItemStatus:
    def test_waiting_user_input_needs_attention(self, session, pluggy_item):
        from app.services.pluggy_sync import map_pluggy_item_status

        assert map_pluggy_item_status("UPDATED") == "active"
        assert map_pluggy_item_status("UPDATING") == "active"
        assert map_pluggy_item_status("WAITING_USER_INPUT") == "needs_attention"
        assert map_pluggy_item_status("LOGIN_ERROR") == "needs_attention"
        assert map_pluggy_item_status("OUTDATED") == "needs_attention"
        assert map_pluggy_item_status("UNKNOWN") == "inactive"

        user = session.exec(select(User)).one()
        item = dict(pluggy_item)
        item["status"] = "WAITING_USER_INPUT"
        with patch("app.services.pluggy_sync.is_pluggy_available", return_value=True), \
             patch("app.services.pluggy_sync.validate_item", return_value=(True, item)):
            connection, error = add_pluggy_connection(
                session, user.id, "550e8400-e29b-41d4-a716-446655440001"
            )
        assert error is None
        assert connection is not None
        assert connection.status == "needs_attention"


class TestPluggyResyncDedupe:
    def test_imported_pluggy_rows_are_not_selected_again(self, session, pluggy_accounts, pluggy_transactions):
        from app.services.cumbuca_sync import ImportExpenseRow, import_selected_account_debits
        from app.services.pluggy_sync import PLUGGY_SOURCE

        user = session.exec(select(User)).one()
        _add_pluggy_connection(session, user)
        connections = get_pluggy_connections(session, user.id)

        with patch("app.services.pluggy_sync.fetch_accounts") as mock_accounts, \
             patch("app.services.pluggy_sync.fetch_transactions") as mock_tx:
            mock_accounts.return_value = [
                acc for acc in pluggy_accounts["results"] if acc["type"] != "CREDIT"
            ]
            mock_tx.return_value = pluggy_transactions["results"]
            rows, _ = build_pluggy_expense_import_rows(
                session, user.id, connections, year=2026, month=6
            )

        converted = [
            ImportExpenseRow(
                row_key=row.row_key,
                external_id=row.external_id,
                year=row.year,
                month=row.month,
                category=row.category,
                vendor=row.vendor,
                payment_account=row.payment_account,
                amount=row.amount,
                transaction_date=row.transaction_date,
                already_exists=row.already_exists,
                selected=row.selected,
                import_kind="expense",
            )
            for row in rows
            if row.import_kind == "expense"
        ]
        created, _, _ = import_selected_account_debits(
            session,
            user.id,
            converted,
            {row.row_key for row in converted},
            source=PLUGGY_SOURCE,
        )
        assert created == len(converted)

        saved = session.exec(select(FinanceExpenseEntry).where(FinanceExpenseEntry.source == "pluggy")).all()
        assert len(saved) == created
        assert all(entry.external_id.startswith("pluggy:") for entry in saved)

        with patch("app.services.pluggy_sync.fetch_accounts") as mock_accounts, \
             patch("app.services.pluggy_sync.fetch_transactions") as mock_tx:
            mock_accounts.return_value = [
                acc for acc in pluggy_accounts["results"] if acc["type"] != "CREDIT"
            ]
            mock_tx.return_value = pluggy_transactions["results"]
            again, _ = build_pluggy_expense_import_rows(
                session, user.id, connections, year=2026, month=6
            )

        expenses_again = [row for row in again if row.import_kind == "expense"]
        assert expenses_again
        assert all(row.already_exists and not row.selected for row in expenses_again)


class TestInvestmentLookupByUser:
    def test_ignores_other_users_investments(self, session, pluggy_investments):
        from app.models.portfolio import Portfolio
        from app.services.auth import ensure_user_portfolio
        from app.tests.conftest import make_investment

        user = session.exec(select(User)).one()
        other = User(email="other@example.com", google_sub="other-sub", name="Other")
        session.add(other)
        session.commit()
        session.refresh(other)
        ensure_user_portfolio(session, other)

        other_types = session.exec(
            select(Portfolio).where(Portfolio.user_id == other.id)
        ).one()
        from app.models.asset_type import AssetType
        other_bonds = session.exec(
            select(AssetType).where(AssetType.portfolio_id == other_types.id)
        ).first()
        assert other_bonds is not None
        make_investment(
            session,
            other_bonds.id,
            "CDB Nubank 100% CDI",
            Decimal("1"),
        )
        # Tag as a Pluggy investment belonging to the other user
        inv = session.exec(select(Investment).where(Investment.name == "CDB Nubank 100% CDI")).one()
        inv.external_id = "pluggy:inv-other"
        session.add(inv)
        session.commit()

        _add_pluggy_connection(session, user)
        connections = get_pluggy_connections(session, user.id)
        with patch("app.services.pluggy_sync.fetch_investments") as mock_inv:
            mock_inv.return_value = pluggy_investments["results"]
            rows, _ = build_pluggy_investment_import_rows(session, user.id, connections)

        cdb = next(row for row in rows if "CDB" in row.name)
        assert not cdb.already_exists
        assert not cdb.is_update


class TestPluggyRoutes:
    def test_add_connection_rejects_non_uuid(self, client):
        with patch("app.web.routes.open_finance.is_pluggy_available", return_value=True):
            response = client.post(
                "/api/open-finance/pluggy/connections",
                data={"item_id": "../items/secret"},
            )
        assert response.status_code == 400
        assert "UUID" in response.json()["detail"]

    def test_confirm_rejects_preview_from_other_user(self, client, session):
        from app.web.routes import open_finance as routes
        from app.services.pluggy_sync import PluggyImportExpenseRow
        from uuid import uuid4

        other_user_id = uuid4()
        token = routes._stash_pluggy_expense_import(
            other_user_id,
            [
                PluggyImportExpenseRow(
                    row_key="pluggy:x",
                    external_id="pluggy:x",
                    year=2026,
                    month=6,
                    category="Outros",
                    vendor="Test",
                    payment_account="Nuconta",
                    amount=Decimal("-10"),
                    transaction_date=date(2026, 6, 1),
                    already_exists=False,
                    selected=True,
                )
            ],
        )
        response = client.post(
            "/api/open-finance/pluggy/sync/expenses/confirm",
            data={"import_token": token, "selected_rows": ["pluggy:x"]},
        )
        assert response.status_code == 400


class TestOpenFinanceMatch:
    def test_overlapping_institutions_detects_same_bank(self, session):
        from app.services.open_finance_match import (
            both_providers_connected,
            overlapping_institutions,
        )

        user = session.exec(select(User)).one()
        session.add(OpenFinanceConnection(
            user_id=user.id,
            provider="cumbuca",
            external_id="",
            institution_name="Nubank",
            status="active",
            refresh_token="refresh",
        ))
        session.add(OpenFinanceConnection(
            user_id=user.id,
            provider=PLUGGY_PROVIDER,
            external_id="550e8400-e29b-41d4-a716-446655440000",
            institution_name="Nu Pagamentos",
            status="active",
        ))
        session.commit()
        connections = list(session.exec(select(OpenFinanceConnection)).all())
        assert overlapping_institutions(connections) == ["nubank"]
        assert both_providers_connected(connections)

    def test_tokenless_active_cumbuca_is_not_live(self, session):
        from app.services.open_finance_match import (
            both_providers_connected,
            overlapping_institutions,
        )

        user = session.exec(select(User)).one()
        session.add(OpenFinanceConnection(
            user_id=user.id,
            provider="cumbuca",
            external_id="",
            institution_name="Nubank",
            status="active",
            refresh_token=None,
            access_token=None,
        ))
        session.add(OpenFinanceConnection(
            user_id=user.id,
            provider=PLUGGY_PROVIDER,
            external_id="550e8400-e29b-41d4-a716-446655440000",
            institution_name="Nu Pagamentos",
            status="active",
        ))
        session.commit()
        connections = list(session.exec(select(OpenFinanceConnection)).all())
        assert both_providers_connected(connections) is False
        assert overlapping_institutions(connections) == []


class TestOpenFinancePageState:
    def test_page_exposes_provider_flags_and_hides_banner_for_tokenless_cumbuca(
        self, client, session
    ):
        user = session.exec(select(User)).one()
        session.add(OpenFinanceConnection(
            user_id=user.id,
            provider="cumbuca",
            external_id="",
            institution_name="Cumbuca Open Finance",
            status="active",
            oauth_client_id="client",
        ))
        session.add(OpenFinanceConnection(
            user_id=user.id,
            provider=PLUGGY_PROVIDER,
            external_id="550e8400-e29b-41d4-a716-446655440000",
            institution_name="Nubank",
            status="active",
        ))
        session.commit()

        with patch("app.web.routes.open_finance.is_pluggy_available", return_value=True):
            response = client.get("/api/open-finance")

        assert response.status_code == 200
        payload = response.json()
        assert payload["cumbuca_connected"] is False
        assert payload["pluggy_connected"] is True
        assert payload["same_institution_warning"] is None
        cumbuca = next(row for row in payload["connections"] if row["provider"] == "cumbuca")
        assert cumbuca["status"] != "active"


def test_unique_external_id_constraint_blocks_duplicate_expenses(session):
    from sqlalchemy.exc import IntegrityError

    user = session.exec(select(User)).one()
    session.add(FinanceExpenseEntry(
        user_id=user.id,
        year=2026,
        month=6,
        category="Outros",
        vendor="A",
        payment_account="Nuconta",
        amount=Decimal("-1"),
        source="pluggy",
        external_id="pluggy:dup",
    ))
    session.commit()
    session.add(FinanceExpenseEntry(
        user_id=user.id,
        year=2026,
        month=6,
        category="Outros",
        vendor="B",
        payment_account="Nuconta",
        amount=Decimal("-2"),
        source="pluggy",
        external_id="pluggy:dup",
    ))
    with pytest.raises(IntegrityError):
        session.commit()
