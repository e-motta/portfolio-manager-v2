def test_snapshots_page_loads(client):
    response = client.get("/history")
    assert response.status_code == 200
    assert "Portfolio history" in response.text
    assert "Capture" in response.text


def test_create_snapshot_captures_portfolio(client, session, exchange_type):
    from datetime import date
    from decimal import Decimal

    from sqlmodel import select

    from app.models.asset_type import AssetType
    from app.models.snapshot import PortfolioSnapshot, SnapshotAssetClass
    from app.tests.conftest import make_investment, make_lot

    cash_type = session.exec(select(AssetType).where(AssetType.slug == "cash")).one()
    make_investment(session, cash_type.id, "Savings", Decimal("1000"))
    make_lot(session, exchange_type.id, "AAA", Decimal("10"), Decimal("100"), target_pct=Decimal("1"))

    response = client.post(
        "/history",
        data={"snapshot_date": "2026-06-08"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    snapshot = session.exec(
        select(PortfolioSnapshot).where(PortfolioSnapshot.snapshot_date == date(2026, 6, 8))
    ).one()
    assert snapshot.total_value > 0

    asset_classes = session.exec(
        select(SnapshotAssetClass).where(SnapshotAssetClass.snapshot_id == snapshot.id)
    ).all()
    assert len(asset_classes) >= 2
    assert any(row.name == "Listed Securities" for row in asset_classes)

    detail = client.get(f"/history/{snapshot.id}")
    assert detail.status_code == 200
    assert "AAA" in detail.text
    assert "Captured" in detail.text
    assert "BRT" in detail.text

    delete_response = client.delete(f"/history/{snapshot.id}")
    assert delete_response.status_code == 200


def test_dashboard_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Portfolio overview" in response.text
    assert "data-layout-value" in response.text
    assert "layout.js" in response.text


def test_investments_page_loads(client, session, exchange_type):
    from decimal import Decimal

    from sqlmodel import select

    from app.models.asset_type import AssetType
    from app.tests.conftest import make_investment

    cash = session.exec(select(AssetType).where(AssetType.slug == "cash")).one()
    make_investment(session, cash.id, "Savings", Decimal("1000"), institution="Nubank")
    make_investment(session, cash.id, "CDB", Decimal("2500"), institution="Nubank")
    make_investment(session, cash.id, "Fund", Decimal("1500"), institution="XP")
    response = client.get("/portfolio/investments")
    assert response.status_code == 200
    assert "Other" in response.text
    assert "positions outside securities" in response.text
    assert "Add investment" in response.text
    assert 'id="add-investment-modal"' in response.text
    assert "/static/js/form-modal.js" in response.text
    assert "By bank / institution" in response.text
    assert "Nubank" in response.text
    assert "XP" in response.text
    assert "Updated" in response.text
    assert "BRT" in response.text


def test_create_investment(client, session, exchange_type):
    from decimal import Decimal

    from sqlmodel import select

    from app.models.asset_type import AssetType
    from app.models.investment import Investment
    bonds = session.exec(
        select(AssetType).where(
            AssetType.is_exchange_traded.is_(False),  # type: ignore[attr-defined]
            AssetType.slug == "bonds",
        )
    ).one()
    response = client.post(
        "/portfolio/investments",
        data={
            "asset_type_id": str(bonds.id),
            "institution": "Nubank",
            "name": "CDB Test",
            "current_value": "10500.00",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    investment = session.exec(
        select(Investment).where(Investment.name == "CDB Test")
    ).one()
    assert investment.institution == "Nubank"
    assert investment.current_value == Decimal("10500.00")

    delete_response = client.delete(f"/portfolio/investments/{investment.id}")
    assert delete_response.status_code == 200


def test_clear_asset_type_target_after_create(client, session, exchange_type):
    from decimal import Decimal

    from app.tests.conftest import make_asset_type

    portfolio_id = exchange_type.portfolio_id
    asset_type = make_asset_type(
        session,
        portfolio_id,
        "Clearable",
        Decimal("0.15"),
        Decimal("0"),
    )
    response = client.post(
        f"/allocation/classes/{asset_type.id}",
        data={"name": "Clearable", "target_pct": ""},
    )
    assert response.status_code == 200
    assert "—" in response.text
    assert "15.0%" not in response.text

    session.refresh(asset_type)
    assert asset_type.target_pct is None


def test_asset_types_page_loads(client):
    response = client.get("/allocation/classes")
    assert response.status_code == 200
    assert "Asset classes" in response.text
    assert "Add class" in response.text
    assert 'id="add-asset-class-modal"' in response.text
    assert "/static/js/form-modal.js" in response.text
    assert "Assets" in response.text
    assert "Actions" in response.text
    listed_idx = response.text.index("Listed Securities")
    cash_idx = response.text.index("Cash")
    assert listed_idx < cash_idx
    main_end = response.text.index("</main>")
    modal_start = response.text.index('id="add-asset-class-modal"')
    assert modal_start > main_end


def test_create_asset_type_redirects(client, session, exchange_type):
    response = client.post(
        "/allocation/classes",
        data={"name": "Commodities", "target_pct": ""},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/allocation/classes"

    from sqlmodel import select

    from app.models.asset_type import AssetType

    asset_type = session.exec(
        select(AssetType).where(AssetType.slug == "commodities")
    ).one()
    assert asset_type.name == "Commodities"
    assert asset_type.target_pct is None


def test_securities_page_loads(client, session, exchange_type):
    from app.tests.conftest import make_lot
    from decimal import Decimal

    make_lot(session, exchange_type.id, "AAA", Decimal("10"), Decimal("100"))
    response = client.get("/portfolio/holdings")
    assert response.status_code == 200
    assert 'id="securities-content"' in response.text
    assert 'hx-get="/portfolio/holdings/partials/content"' in response.text
    assert "Loading securities and market data" in response.text
    assert "Add trade" in response.text
    assert 'id="add-trade-modal"' in response.text
    assert 'id="add-dividend-modal"' in response.text
    assert "/static/js/form-modal.js" in response.text
    assert "Record trade" not in response.text
    assert 'class="panel panel--import"' not in response.text

    partial = client.get("/portfolio/holdings/partials/content")
    assert partial.status_code == 200
    assert "Positions by ticker" in partial.text
    assert "Performance by ticker" in partial.text
    assert "Total return (USD)" in partial.text
    assert "Dividends net (USD)" in partial.text
    assert "Prices " in partial.text
    assert "BRT" in partial.text
    assert 'id="securities-subtitle"' in partial.text
    assert 'hx-swap-oob="true"' in partial.text


def test_suggestions_page_loads(client):
    response = client.get("/allocation/rebalance")
    assert response.status_code == 200
    assert "Rebalancing" in response.text


def test_type_suggestions_partial(client):
    response = client.get("/allocation/rebalance/types?mode=buy_only&new_cash=0")
    assert response.status_code == 200
    assert "Asset class" in response.text


def test_update_symbol_target_returns_row_only(client, session, exchange_type):
    from decimal import Decimal

    from app.tests.conftest import make_lot, make_symbol_target

    make_symbol_target(session, exchange_type.id, "AAA", Decimal("0.1"))
    make_lot(session, exchange_type.id, "AAA", Decimal("10"), Decimal("100"))
    response = client.post("/portfolio/holdings/symbols/AAA", data={"target_pct": "10.0"})
    assert response.status_code == 200
    assert response.text.strip().startswith("<tr")
    assert "hx-swap-oob" not in response.text
    assert "target-weight-status" not in response.text
    assert "btn-edit" in response.text
    assert "view-mode" in response.text
    assert "hx-trigger-after-settle" in {
        k.lower(): v for k, v in response.headers.items()
    }
    assert "targetTotalRefresh" in response.headers.get("HX-Trigger-After-Settle", "")


def test_update_symbol_target_allows_total_over_100(client, session, exchange_type):
    from decimal import Decimal

    from app.tests.conftest import make_lot, make_symbol_target

    make_symbol_target(session, exchange_type.id, "AAA", Decimal("0.6"))
    make_symbol_target(session, exchange_type.id, "BBB", Decimal("0.5"))
    make_lot(session, exchange_type.id, "AAA", Decimal("10"), Decimal("100"))
    make_lot(session, exchange_type.id, "BBB", Decimal("10"), Decimal("100"))
    response = client.post("/portfolio/holdings/symbols/AAA", data={"target_pct": "50.0"})
    assert response.status_code == 200


def test_update_symbol_target_rejects_over_100_for_single_holding(client, session, exchange_type):
    from decimal import Decimal

    from app.tests.conftest import make_lot, make_symbol_target

    make_symbol_target(session, exchange_type.id, "AAA", Decimal("0.1"))
    make_lot(session, exchange_type.id, "AAA", Decimal("10"), Decimal("100"))
    response = client.post("/portfolio/holdings/symbols/AAA", data={"target_pct": "100.1"})
    assert response.status_code == 422
    assert "between 0% and 100%" in response.json()["detail"]


def test_target_weight_total_partial(client):
    response = client.get("/portfolio/holdings/partials/target-weight-total")
    assert response.status_code == 200
    assert "No target weights set" in response.text
    assert 'id="target-weight-status"' in response.text
    assert "status-pill warn" in response.text


def test_target_weight_total_shows_over_100(client, session, exchange_type):
    from decimal import Decimal

    from app.tests.conftest import make_symbol_target

    make_symbol_target(session, exchange_type.id, "AAA", Decimal("0.6"))
    make_symbol_target(session, exchange_type.id, "BBB", Decimal("0.5"))
    response = client.get("/portfolio/holdings/partials/target-weight-total")
    assert response.status_code == 200
    assert "Targets = 110.0%" in response.text
    assert "status-pill warn" in response.text
    assert "status-pill ok" not in response.text


def test_holdings_page_import_modal_is_outside_main_content(client):
    response = client.get("/portfolio/holdings")
    assert response.status_code == 200
    assert 'id="import-modal"' in response.text
    assert 'id="import-modal-body"' in response.text
    assert 'id="add-trade-modal"' in response.text
    assert 'id="add-dividend-modal"' in response.text
    assert "/static/js/import.js" in response.text
    assert "/static/js/form-modal.js" in response.text
    main_end = response.text.index("</main>")
    modal_start = response.text.index('id="import-modal"')
    assert modal_start > main_end
    trade_modal_start = response.text.index('id="add-trade-modal"')
    assert trade_modal_start > main_end


def test_statement_import_preview(client, session, exchange_type):
    from datetime import date
    from decimal import Decimal
    from pathlib import Path

    from app.tests.conftest import make_lot

    csv_path = (
        Path(__file__).resolve().parent / "fixtures" / "U00000001_2024_2024.csv"
    )
    make_lot(
        session,
        exchange_type.id,
        "VTI",
        Decimal("24"),
        Decimal("295.61"),
        purchase_date=date(2024, 11, 14),
    )

    with csv_path.open("rb") as handle:
        response = client.post(
            "/portfolio/holdings/import/preview",
            files={"statement": ("statement.csv", handle, "text/csv")},
        )

    assert response.status_code == 200
    assert "VTI" in response.text
    assert "Trade date" in response.text
    assert "In portfolio" in response.text
    assert "New" in response.text
    assert "already imported" in response.text
    assert 'name="lots"' in response.text
    assert "14/11/2024" in response.text
    assert "checked" in response.text
    assert "disabled" in response.text
    assert "data-import-select-all" in response.text
    assert "Add selected tax lots" in response.text


def test_statement_import_preview_positions_only_has_no_lots(client):
    from pathlib import Path

    csv_path = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "U00000001_20260101_20260609.csv"
    )

    with csv_path.open("rb") as handle:
        response = client.post(
            "/portfolio/holdings/import/preview",
            files={"statement": ("statement.csv", handle, "text/csv")},
        )

    assert response.status_code == 200
    assert "No trades found in this statement" in response.text
    assert 'name="lots"' not in response.text


def test_statement_import_confirm_adds_positions(client, session, exchange_type):
    from pathlib import Path

    from sqlmodel import select

    from app.models.security import SecurityLot
    from app.services.ib_statement import (
        build_import_lot_rows,
        clear_import_stash,
        parse_ib_statement,
        stash_import,
    )

    clear_import_stash()
    csv_path = (
        Path(__file__).resolve().parent / "fixtures" / "U00000001_2024_2024.csv"
    )
    statement = parse_ib_statement(csv_path.read_text(encoding="utf-8"))
    token = stash_import(statement)
    ijs_keys = [row.lot_key for row in build_import_lot_rows(statement, set()) if row.symbol == "IJS"]

    response = client.post(
        "/portfolio/holdings/import/confirm",
        data={"import_token": token, "lots": ijs_keys},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/portfolio/holdings"

    lots = session.exec(
        select(SecurityLot).where(
            SecurityLot.asset_type_id == exchange_type.id,
            SecurityLot.symbol == "IJS",
        )
    ).all()
    assert len(lots) == 2
    assert all(lot.source == "statement" for lot in lots)


def test_dividend_import_preview(client, session, exchange_type):
    from datetime import date
    from decimal import Decimal
    from pathlib import Path

    from app.models.dividend import Dividend
    from app.services.ib_statement import dividend_selection_key

    csv_path = (
        Path(__file__).resolve().parent / "fixtures" / "U00000001_2024_2024.csv"
    )
    session.add(
        Dividend(
            asset_type_id=exchange_type.id,
            symbol="VTI",
            pay_date=date(2024, 12, 26),
            gross_amount_usd=Decimal("23.76"),
            withholding_tax_usd=Decimal("7.13"),
            net_amount_usd=Decimal("16.63"),
            source="ib_statement",
            import_key=dividend_selection_key(
                "VTI",
                date(2024, 12, 26),
                Decimal("23.76"),
            ),
        )
    )
    session.commit()

    with csv_path.open("rb") as handle:
        response = client.post(
            "/portfolio/holdings/dividends/import/preview",
            files={"statement": ("statement.csv", handle, "text/csv")},
        )

    assert response.status_code == 200
    assert "VTI" in response.text
    assert "already imported" in response.text
    assert 'name="dividends"' in response.text
    assert "Add selected dividends" in response.text


def test_create_manual_dividend(client, session, exchange_type):
    from decimal import Decimal

    from sqlmodel import select

    from app.models.dividend import Dividend

    response = client.post(
        "/portfolio/holdings/dividends",
        data={
            "symbol": "VTI",
            "pay_date": "2024-12-26",
            "gross_amount_usd": "23.76",
            "withholding_tax_usd": "7.13",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    dividend = session.exec(
        select(Dividend).where(
            Dividend.asset_type_id == exchange_type.id,
            Dividend.symbol == "VTI",
        )
    ).one()
    assert dividend.source == "manual"
    assert dividend.net_amount_usd == Decimal("16.63")


def test_holdings_page_shows_dividends_section(client):
    response = client.get("/portfolio/holdings")
    assert response.status_code == 200
    assert "Preview dividends" in response.text

    partial = client.get("/portfolio/holdings/partials/content")
    assert partial.status_code == 200
    assert "Dividends" in partial.text


def test_create_lot_with_provisional_fx(client, session, exchange_type):
    response = client.post(
        "/portfolio/holdings/lots",
        data={
            "symbol": "TEST",
            "purchase_date": "2024-01-15",
            "position": "5",
            "purchase_price_usd": "100.00",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    from sqlmodel import select
    from app.models.security import SecurityLot

    lot = session.exec(select(SecurityLot).where(SecurityLot.symbol == "TEST")).one()
    assert lot.provisional_fx is True
    assert lot.source == "manual"
    assert lot.purchase_price_usd == 100

    delete_response = client.delete(f"/portfolio/holdings/lots/{lot.id}")
    assert delete_response.status_code == 200


def test_refresh_ptax_rates_updates_provisional_lots(client, session, exchange_type):
    from datetime import date
    from decimal import Decimal
    from unittest.mock import patch

    from app.services import prices
    from app.tests.conftest import make_lot

    lot = make_lot(
        session,
        exchange_type.id,
        "VTI",
        Decimal("10"),
        Decimal("100"),
        purchase_date=date(2024, 12, 16),
        usd_brl_rate=Decimal("5.5"),
        provisional_fx=True,
    )

    with patch.object(prices, "fetch_ptax_usd_brl_rate", return_value=Decimal("6.05")):
        response = client.post("/portfolio/holdings/ptax/refresh", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/portfolio/holdings"
    session.refresh(lot)
    assert lot.usd_brl_rate == Decimal("6.05")
    assert lot.provisional_fx is False


def test_holdings_page_shows_update_ptax_button_when_provisional_fx(client, session, exchange_type):
    from decimal import Decimal

    from app.tests.conftest import make_lot

    make_lot(
        session,
        exchange_type.id,
        "VTI",
        Decimal("10"),
        Decimal("100"),
        provisional_fx=True,
    )
    response = client.get("/portfolio/holdings")
    assert response.status_code == 200

    partial = client.get("/portfolio/holdings/partials/content")
    assert partial.status_code == 200
    assert "Update PTAX rates" in partial.text
    assert "/portfolio/holdings/ptax/refresh" in partial.text


def test_holdings_page_hides_update_ptax_button_without_provisional_fx(client, session, exchange_type):
    from decimal import Decimal

    from app.tests.conftest import make_lot

    make_lot(session, exchange_type.id, "VTI", Decimal("10"), Decimal("100"))
    response = client.get("/portfolio/holdings")
    assert response.status_code == 200

    partial = client.get("/portfolio/holdings/partials/content")
    assert partial.status_code == 200
    assert "Update PTAX rates" not in partial.text
