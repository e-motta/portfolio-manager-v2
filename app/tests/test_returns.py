from datetime import date
from decimal import Decimal

from app.services.dividends import summarize_dividends_by_symbol
from app.services.securities import (
    build_portfolio_return_totals,
    build_security_returns,
    consolidate_securities,
)
from app.tests.conftest import make_dividend, make_lot, make_symbol_target


def test_summarize_dividends_by_symbol(session, exchange_type):
    make_dividend(
        session,
        exchange_type.id,
        "VTI",
        date(2024, 12, 26),
        Decimal("23.76"),
        withholding_tax_usd=Decimal("7.13"),
    )
    make_dividend(
        session,
        exchange_type.id,
        "VTI",
        date(2025, 3, 31),
        Decimal("37.44"),
        withholding_tax_usd=Decimal("11.23"),
    )
    make_dividend(
        session,
        exchange_type.id,
        "IJS",
        date(2024, 12, 20),
        Decimal("3.53"),
        withholding_tax_usd=Decimal("1.06"),
    )

    from app.web.helpers import get_dividends

    summaries = summarize_dividends_by_symbol(get_dividends(session))

    assert set(summaries) == {"VTI", "IJS"}
    assert summaries["VTI"].payment_count == 2
    assert summaries["VTI"].gross_usd == Decimal("61.20")
    assert summaries["VTI"].net_usd == Decimal("42.84")


def test_build_security_returns_includes_dividends(session, exchange_type):
    lot = make_lot(session, exchange_type.id, "VTI", Decimal("10"), Decimal("100"))
    lot.current_price_usd = Decimal("110")
    lot.current_price_brl = Decimal("550")
    session.add(lot)
    session.commit()

    make_symbol_target(session, exchange_type.id, "VTI", Decimal("1"))
    make_dividend(
        session,
        exchange_type.id,
        "VTI",
        date(2024, 12, 26),
        Decimal("20"),
        withholding_tax_usd=Decimal("5"),
    )

    from app.web.helpers import get_dividends, get_security_lots, get_symbol_targets

    consolidated = consolidate_securities(
        get_security_lots(session),
        get_symbol_targets(session),
    )
    returns = build_security_returns(
        consolidated,
        get_dividends(session),
        Decimal("5"),
    )

    assert len(returns) == 1
    item = returns[0]
    assert item.unrealized_pl_usd == Decimal("100")
    assert item.dividend_net_usd == Decimal("15")
    assert item.total_return_usd == Decimal("115")
    assert item.total_return_brl == Decimal("575")
    assert item.dividend_payment_count == 1


def test_build_security_returns_includes_dividend_only_symbol(session, exchange_type):
    make_dividend(
        session,
        exchange_type.id,
        "IJS",
        date(2024, 12, 20),
        Decimal("3.53"),
        withholding_tax_usd=Decimal("1.06"),
    )

    from app.web.helpers import get_dividends

    returns = build_security_returns([], get_dividends(session), Decimal("5"))

    assert len(returns) == 1
    item = returns[0]
    assert item.symbol == "IJS"
    assert item.unrealized_pl_usd == Decimal("0")
    assert item.dividend_net_usd == Decimal("2.47")
    assert item.total_return_usd == Decimal("2.47")


def test_build_portfolio_return_totals(session, exchange_type):
    lot = make_lot(session, exchange_type.id, "VTI", Decimal("10"), Decimal("100"))
    lot.current_price_usd = Decimal("110")
    lot.current_price_brl = Decimal("550")
    session.add(lot)
    session.commit()

    make_dividend(
        session,
        exchange_type.id,
        "VTI",
        date(2024, 12, 26),
        Decimal("20"),
        withholding_tax_usd=Decimal("0"),
    )

    from app.web.helpers import get_dividends, get_security_lots, get_symbol_targets

    consolidated = consolidate_securities(
        get_security_lots(session),
        get_symbol_targets(session),
    )
    returns = build_security_returns(
        consolidated,
        get_dividends(session),
        Decimal("5"),
    )
    totals = build_portfolio_return_totals(returns)

    assert totals.unrealized_pl_usd == Decimal("100")
    assert totals.dividend_net_usd == Decimal("20")
    assert totals.total_return_usd == Decimal("120")
    assert totals.total_return_pct_usd == Decimal("12")
