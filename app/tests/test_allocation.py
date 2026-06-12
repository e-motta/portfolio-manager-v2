from decimal import Decimal

import pytest
from sqlmodel import select

from app.models.asset_type import AssetType
from app.models.investment import Investment
from app.models.security import SecurityLot
from app.models.symbol_target import SymbolTarget
from app.schemas.allocation import SuggestionMode
from app.services.allocation import (
    calculate_security_suggestions,
    calculate_type_suggestions,
    has_type_target,
    validate_symbol_targets,
    validate_type_targets,
)
from app.web.helpers import build_dashboard_rows
from app.services.allocation import get_effective_type_value
from app.services.securities import consolidate_securities, pl_pct
from app.tests.conftest import make_asset_type, make_investment, make_lot, make_symbol_target


def test_buy_only_never_negative(session, exchange_type):
    from app.web.helpers import get_asset_types

    cash = session.exec(select(AssetType).where(AssetType.slug == "cash")).one()
    make_investment(session, cash.id, "Cash balance", Decimal("500"))

    make_lot(session, exchange_type.id, "VTI", Decimal("10"), Decimal("100"), target_pct=Decimal("0.6"))

    asset_types = get_asset_types(session)
    suggestions = calculate_type_suggestions(
        list(asset_types),
        mode=SuggestionMode.BUY_ONLY,
        new_cash=Decimal("1000"),
    )
    assert all(item.delta >= 0 for item in suggestions)


def test_buy_and_sell_returns_sells(session, exchange_type):
    portfolio_id = exchange_type.portfolio_id
    bonds = make_asset_type(
        session,
        portfolio_id,
        "Bonds Test",
        Decimal("0.5"),
        Decimal("0"),
    )
    stocks = make_asset_type(
        session,
        portfolio_id,
        "Stocks Test",
        Decimal("0.5"),
        Decimal("0"),
    )
    make_investment(session, bonds.id, "Bonds", Decimal("8000"))
    make_investment(session, stocks.id, "Stocks", Decimal("2000"))
    bonds.investments = list(
        session.exec(select(Investment).where(Investment.asset_type_id == bonds.id)).all()
    )
    stocks.investments = list(
        session.exec(select(Investment).where(Investment.asset_type_id == stocks.id)).all()
    )

    suggestions = calculate_type_suggestions(
        [bonds, stocks],
        mode=SuggestionMode.BUY_AND_SELL,
    )
    actions = {item.label: item.action for item in suggestions}
    assert actions["Bonds Test"] == "sell"
    assert actions["Stocks Test"] == "buy"


def test_effective_type_value_uses_investments(session, exchange_type):
    from app.web.helpers import get_asset_types

    portfolio_id = exchange_type.portfolio_id
    bonds = make_asset_type(
        session,
        portfolio_id,
        "Bonds Test",
        Decimal("0.2"),
        Decimal("0"),
    )
    make_investment(session, bonds.id, "CDB", Decimal("11000"))
    bonds = next(item for item in get_asset_types(session) if item.id == bonds.id)
    assert get_effective_type_value(bonds) == Decimal("11000")


def test_consolidated_security_pl(session, exchange_type):
    lot = make_lot(session, exchange_type.id, "AAA", Decimal("10"), Decimal("100"))
    lot.current_price_usd = Decimal("110")
    lot.current_price_brl = Decimal("550")
    session.add(lot)
    session.commit()

    targets = session.exec(select(SymbolTarget).where(SymbolTarget.asset_type_id == exchange_type.id)).all()
    consolidated = consolidate_securities([lot], list(targets))

    assert len(consolidated) == 1
    item = consolidated[0]
    assert item.cost_basis_usd == Decimal("1000")
    assert item.current_value_usd == Decimal("1100")
    assert item.pl_usd == Decimal("100")
    assert item.cost_basis_brl == Decimal("5000")
    assert item.current_value_brl == Decimal("5500")
    assert item.pl_brl == Decimal("500")
    assert item.pl_pct_usd == Decimal("10")
    assert item.pl_pct_brl == Decimal("10")


def test_pl_pct_handles_zero_cost_basis():
    assert pl_pct(Decimal("100"), Decimal("0")) is None
    assert pl_pct(Decimal("100"), Decimal("1000")) == Decimal("10")


def test_security_suggestions_use_consolidated_symbols(session, exchange_type):
    make_lot(session, exchange_type.id, "AAA", Decimal("10"), Decimal("100"), target_pct=Decimal("0.6"))
    make_lot(session, exchange_type.id, "AAA", Decimal("5"), Decimal("100"), target_pct=Decimal("0.6"))
    make_lot(session, exchange_type.id, "BBB", Decimal("5"), Decimal("100"), target_pct=Decimal("0.4"))

    lots = session.exec(select(SecurityLot).where(SecurityLot.asset_type_id == exchange_type.id)).all()
    targets = session.exec(select(SymbolTarget).where(SymbolTarget.asset_type_id == exchange_type.id)).all()
    consolidated = consolidate_securities(list(lots), list(targets))

    suggestions = calculate_security_suggestions(
        consolidated,
        mode=SuggestionMode.BUY_AND_SELL,
    )
    assert len(suggestions) == 2
    assert {item.label for item in suggestions} == {"AAA", "BBB"}


def test_buy_only_zero_cash_zeros_adjustments(session, exchange_type):
    portfolio_id = exchange_type.portfolio_id
    underweight = make_asset_type(
        session,
        portfolio_id,
        "Underweight",
        Decimal("0.5"),
        Decimal("0"),
    )
    overweight = make_asset_type(
        session,
        portfolio_id,
        "Overweight",
        Decimal("0.5"),
        Decimal("10000"),
    )

    type_suggestions = calculate_type_suggestions(
        [underweight, overweight],
        mode=SuggestionMode.BUY_ONLY,
        new_cash=Decimal("0"),
    )
    assert all(item.delta == Decimal("0") for item in type_suggestions)
    assert all(item.action == "hold" for item in type_suggestions)

    make_lot(session, exchange_type.id, "AAA", Decimal("10"), Decimal("100"), target_pct=Decimal("0.6"))
    lots = session.exec(select(SecurityLot).where(SecurityLot.asset_type_id == exchange_type.id)).all()
    targets = session.exec(select(SymbolTarget).where(SymbolTarget.asset_type_id == exchange_type.id)).all()
    consolidated = consolidate_securities(list(lots), list(targets))

    security_suggestions = calculate_security_suggestions(
        consolidated,
        mode=SuggestionMode.BUY_ONLY,
        new_cash=Decimal("0"),
    )
    assert all(item.delta == Decimal("0") for item in security_suggestions)
    assert all(item.action == "hold" for item in security_suggestions)


def test_buy_only_scales_when_exceeds_new_cash(session, exchange_type):
    portfolio_id = exchange_type.portfolio_id
    underweight = make_asset_type(
        session,
        portfolio_id,
        "Underweight",
        Decimal("0.5"),
        Decimal("0"),
    )
    overweight = make_asset_type(
        session,
        portfolio_id,
        "Overweight",
        Decimal("0.5"),
        Decimal("10000"),
    )

    suggestions = calculate_type_suggestions(
        [underweight, overweight],
        mode=SuggestionMode.BUY_ONLY,
        new_cash=Decimal("1000"),
    )
    total_buys = sum(item.delta for item in suggestions)
    assert total_buys == Decimal("1000.00")


def test_validate_type_targets_rejects_over_100(session, exchange_type):
    portfolio_id = exchange_type.portfolio_id
    first = make_asset_type(
        session,
        portfolio_id,
        "First",
        Decimal("0.9"),
        Decimal("0"),
    )
    with pytest.raises(ValueError):
        validate_type_targets([first], new_target=Decimal("0.2"))


def test_validate_symbol_targets_rejects_over_100(session, exchange_type):
    first = make_symbol_target(session, exchange_type.id, "ONE", Decimal("0.9"))
    with pytest.raises(ValueError):
        validate_symbol_targets([first], new_target=Decimal("0.2"))


def test_unweighted_asset_class_excluded_from_suggestions(session, exchange_type):
    portfolio_id = exchange_type.portfolio_id
    tracked = make_asset_type(
        session,
        portfolio_id,
        "Tracked",
        Decimal("1"),
        Decimal("0"),
    )
    untracked = make_asset_type(
        session,
        portfolio_id,
        "Untracked",
        None,
        Decimal("5000"),
    )
    make_investment(session, tracked.id, "Tracked fund", Decimal("10000"))
    make_investment(session, untracked.id, "Side asset", Decimal("5000"))
    tracked.investments = list(
        session.exec(select(Investment).where(Investment.asset_type_id == tracked.id)).all()
    )

    suggestions = calculate_type_suggestions(
        [tracked, untracked],
        mode=SuggestionMode.BUY_AND_SELL,
    )
    assert len(suggestions) == 1
    assert suggestions[0].label == "Tracked"
    assert not has_type_target(untracked)


def test_dashboard_skips_drift_for_unweighted_classes(session, exchange_type):
    portfolio_id = exchange_type.portfolio_id
    untracked = make_asset_type(
        session,
        portfolio_id,
        "Untracked",
        None,
        Decimal("0"),
    )
    make_investment(session, untracked.id, "Side asset", Decimal("2500"))

    rows = build_dashboard_rows(session)
    row = next(item for item in rows if item["asset_type"].id == untracked.id)
    assert row["has_target"] is False
    assert row["target_weight"] is None
    assert row["drift"] is None


def test_dashboard_dual_weights(session, exchange_type):
    portfolio_id = exchange_type.portfolio_id
    for asset_type in session.exec(select(AssetType)).all():
        asset_type.target_pct = None
        session.add(asset_type)
    session.commit()

    tracked_a = make_asset_type(
        session,
        portfolio_id,
        "Tracked A",
        Decimal("0.6"),
        Decimal("0"),
    )
    tracked_b = make_asset_type(
        session,
        portfolio_id,
        "Tracked B",
        Decimal("0.2"),
        Decimal("0"),
    )
    untracked = make_asset_type(
        session,
        portfolio_id,
        "Untracked",
        None,
        Decimal("0"),
    )
    make_investment(session, tracked_a.id, "Fund A", Decimal("60000"))
    make_investment(session, tracked_b.id, "Fund B", Decimal("20000"))
    make_investment(session, untracked.id, "Side asset", Decimal("20000"))

    rows = build_dashboard_rows(session)
    row_a = next(row for row in rows if row["asset_type"].name == "Tracked A")
    row_untracked = next(row for row in rows if row["asset_type"].name == "Untracked")

    assert row_a["current_weight"] == Decimal("0.6")
    assert row_a["current_weight_allocation"] == Decimal("0.75")
    assert row_a["target_weight_allocation"] == Decimal("0.75")
    assert row_untracked["current_weight"] == Decimal("0.2")
    assert row_untracked["current_weight_allocation"] is None
    assert row_untracked["has_target"] is False


def test_suggestions_include_allocation_weights(session, exchange_type):
    portfolio_id = exchange_type.portfolio_id
    first = make_asset_type(
        session,
        portfolio_id,
        "First",
        Decimal("0.75"),
        Decimal("0"),
    )
    second = make_asset_type(
        session,
        portfolio_id,
        "Second",
        Decimal("0.25"),
        Decimal("0"),
    )
    make_investment(session, first.id, "A", Decimal("7500"))
    make_investment(session, second.id, "B", Decimal("2500"))
    first.investments = list(
        session.exec(select(Investment).where(Investment.asset_type_id == first.id)).all()
    )
    second.investments = list(
        session.exec(select(Investment).where(Investment.asset_type_id == second.id)).all()
    )

    suggestions = calculate_type_suggestions([first, second], mode=SuggestionMode.BUY_AND_SELL)
    by_label = {item.label: item for item in suggestions}
    assert by_label["First"].current_weight_allocation == Decimal("0.75")
    assert by_label["First"].target_weight_allocation == Decimal("0.75")


def test_validate_type_targets_ignores_unweighted_classes(session, exchange_type):
    portfolio_id = exchange_type.portfolio_id
    weighted = make_asset_type(
        session,
        portfolio_id,
        "Weighted",
        Decimal("0.8"),
        Decimal("0"),
    )
    unweighted = make_asset_type(
        session,
        portfolio_id,
        "Unweighted",
        None,
        Decimal("0"),
    )
    validate_type_targets([weighted, unweighted], new_target=Decimal("0.1"))
