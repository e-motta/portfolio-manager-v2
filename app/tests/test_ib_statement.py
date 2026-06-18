from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlmodel import select

from app.models.dividend import Dividend
from app.models.security import SecurityLot
from app.services.ib_statement import (
    build_import_dividend_rows,
    build_import_lot_rows,
    clear_import_stash,
    dividend_selection_key,
    import_selected_dividends,
    import_selected_lots,
    lot_selection_key,
    parse_ib_statement,
    pop_stashed_import,
    stash_import,
)
from app.tests.conftest import make_lot


FIXTURES = Path(__file__).resolve().parent / "fixtures"
EXAMPLE_CSV = FIXTURES / "ib_example_2024_2024.csv"
POSITIONS_ONLY_CSV = FIXTURES / "ib_example_20260101_20260609.csv"


@pytest.fixture(autouse=True)
def clear_stash():
    clear_import_stash()
    yield
    clear_import_stash()


def test_parse_example_statement():
    content = EXAMPLE_CSV.read_text(encoding="utf-8")
    statement = parse_ib_statement(content)

    assert statement.period_end == date(2024, 12, 31)
    assert len(statement.positions) == 6
    symbols = {position.symbol for position in statement.positions}
    assert symbols == {"IJS", "SCHH", "VBR", "VOOV", "VTI", "XLRE"}
    assert statement.names["VTI"] == "VANGUARD TOTAL STOCK MKT ETF"
    assert len(statement.trades) == 12

    vti = next(position for position in statement.positions if position.symbol == "VTI")
    assert vti.quantity == Decimal("10.0000")
    assert vti.close_price_usd == Decimal("100.00")


def test_build_import_lot_rows_marks_matching_lots(session, exchange_type):
    content = EXAMPLE_CSV.read_text(encoding="utf-8")
    statement = parse_ib_statement(content)
    make_lot(
        session,
        exchange_type.id,
        "VTI",
        Decimal("8"),
        Decimal("100.00"),
        purchase_date=date(2024, 11, 14),
    )

    rows = build_import_lot_rows(
        statement,
        {
            lot_selection_key(
                "VTI",
                date(2024, 11, 14),
                Decimal("8"),
                Decimal("100.00"),
            )
        },
    )

    vti_rows = [row for row in rows if row.symbol == "VTI"]
    assert len(vti_rows) == 2
    imported = next(
        row
        for row in vti_rows
        if row.trade_date == date(2024, 11, 14) and row.quantity == Decimal("8")
    )
    new_lot = next(
        row
        for row in vti_rows
        if row.trade_date == date(2024, 12, 16)
    )
    assert imported.already_exists is True
    assert imported.selected is False
    assert new_lot.already_exists is False
    assert new_lot.selected is True


def test_import_selected_lots_can_add_second_lot_for_existing_symbol(session, exchange_type):
    content = EXAMPLE_CSV.read_text(encoding="utf-8")
    statement = parse_ib_statement(content)
    make_lot(
        session,
        exchange_type.id,
        "VTI",
        Decimal("8"),
        Decimal("100.00"),
        purchase_date=date(2024, 11, 14),
    )

    second_vti_key = lot_selection_key(
        "VTI",
        date(2024, 12, 16),
        Decimal("2"),
        Decimal("105.00"),
    )
    created = import_selected_lots(
        session,
        exchange_type.id,
        statement,
        {second_vti_key},
    )

    assert created == 1
    vti_lots = session.exec(
        select(SecurityLot).where(
            SecurityLot.asset_type_id == exchange_type.id,
            SecurityLot.symbol == "VTI",
        )
    ).all()
    assert len(vti_lots) == 2


def test_import_selected_lots_creates_only_selected(session, exchange_type):
    content = EXAMPLE_CSV.read_text(encoding="utf-8")
    statement = parse_ib_statement(content)
    rows = build_import_lot_rows(statement, set())
    ijs_keys = {row.lot_key for row in rows if row.symbol == "IJS"}

    created = import_selected_lots(
        session,
        exchange_type.id,
        statement,
        ijs_keys,
    )

    assert created == 2
    lots = session.exec(
        select(SecurityLot).where(SecurityLot.asset_type_id == exchange_type.id)
    ).all()
    assert {lot.symbol for lot in lots} == {"IJS"}
    assert all(lot.source == "statement" for lot in lots)


def test_positions_only_statement_has_no_importable_lots():
    content = POSITIONS_ONLY_CSV.read_text(encoding="utf-8")
    statement = parse_ib_statement(content)

    assert statement.period_end == date(2026, 6, 9)
    assert len(statement.positions) == 6
    assert statement.trades == []

    rows = build_import_lot_rows(statement, set())
    assert rows == []


def test_parse_example_statement_dividends():
    content = EXAMPLE_CSV.read_text(encoding="utf-8")
    statement = parse_ib_statement(content)

    assert len(statement.dividends) == 6
    vti = next(dividend for dividend in statement.dividends if dividend.symbol == "VTI")
    assert vti.pay_date == date(2024, 12, 26)
    assert vti.gross_amount_usd == Decimal("20.00")
    assert vti.withholding_tax_usd == Decimal("6.00")
    assert vti.net_amount_usd == Decimal("14.00")


def test_positions_only_statement_has_dividends():
    content = POSITIONS_ONLY_CSV.read_text(encoding="utf-8")
    statement = parse_ib_statement(content)

    assert len(statement.dividends) == 6
    symbols = {dividend.symbol for dividend in statement.dividends}
    assert symbols == {"IJS", "SCHH", "VBR", "VOOV", "VTI", "XLRE"}


def test_build_import_dividend_rows_marks_existing(session, exchange_type):
    content = EXAMPLE_CSV.read_text(encoding="utf-8")
    statement = parse_ib_statement(content)
    existing_key = dividend_selection_key("VTI", date(2024, 12, 26), Decimal("20.00"))

    rows = build_import_dividend_rows(statement, {existing_key})
    vti = next(row for row in rows if row.symbol == "VTI")
    assert vti.already_exists is True
    assert vti.selected is False


def test_import_selected_dividends_creates_records(session, exchange_type):
    content = EXAMPLE_CSV.read_text(encoding="utf-8")
    statement = parse_ib_statement(content)
    rows = build_import_dividend_rows(statement, set())
    vti_key = next(row.dividend_key for row in rows if row.symbol == "VTI")

    created = import_selected_dividends(
        session,
        exchange_type.id,
        statement,
        {vti_key},
    )

    assert created == 1
    dividends = session.exec(
        select(Dividend).where(
            Dividend.asset_type_id == exchange_type.id,
            Dividend.symbol == "VTI",
        )
    ).all()
    assert len(dividends) == 1
    assert dividends[0].gross_amount_usd == Decimal("20.00")
    assert dividends[0].source == "ib_statement"


def test_stash_and_pop_import():
    content = EXAMPLE_CSV.read_text(encoding="utf-8")
    statement = parse_ib_statement(content)
    token = stash_import(statement)

    restored = pop_stashed_import(token)
    assert restored is not None
    assert len(restored.positions) == 6
    assert pop_stashed_import(token) is None
