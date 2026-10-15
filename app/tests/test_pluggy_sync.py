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
    remove_pluggy_connection,
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

            rows, warnings = build_pluggy_investment_import_rows(session, connections)

        names = {row.name for row in rows}
        assert "CDB Nubank 100% CDI" in names
        assert "Tesouro Selic 2029" in names
        assert "Poupança" in names
        assert "PETR4" not in names

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

            rows, _ = build_pluggy_investment_import_rows(session, connections)

        cdb = next((r for r in rows if "CDB" in r.name), None)
        assert cdb is not None
        assert cdb.asset_type_slug == "bonds"

        poupanca = next((r for r in rows if "Poupança" in r.name), None)
        assert poupanca is not None
        assert poupanca.asset_type_slug == "cash"


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
