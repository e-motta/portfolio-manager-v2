from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import select

from app.models.asset_type import AssetType
from app.models.investment import Investment
from app.models.security import SecurityLot
from app.services.backup import (
    BACKUP_VERSION,
    export_portfolio_data,
    export_portfolio_json,
    restore_portfolio_json,
)
from app.services.snapshots import capture_portfolio_snapshot
from app.tests.conftest import make_dividend, make_investment, make_lot


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


def test_restore_rejects_unsupported_version(session):
    with pytest.raises(ValueError, match="Unsupported backup version"):
        restore_portfolio_json(session, b'{"version": 99, "asset_types": []}')
