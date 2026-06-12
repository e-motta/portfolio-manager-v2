import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlmodel import Session, select

from app.models.asset_type import AssetType
from app.models.dividend import Dividend
from app.models.investment import Investment
from app.models.security import SecurityLot
from app.models.snapshot import (
    PortfolioSnapshot,
    SnapshotAssetClass,
    SnapshotHolding,
    SnapshotInvestment,
)
from app.models.symbol_target import SymbolTarget
from app.web.helpers import get_portfolio

BACKUP_VERSION = 1


def _serialize_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _serialize_date(value: date) -> str:
    return value.isoformat()


def _serialize_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _parse_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(value)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def export_portfolio_data(session: Session) -> dict[str, Any]:
    portfolio = get_portfolio(session)
    asset_types = list(
        session.exec(
            select(AssetType)
            .where(AssetType.portfolio_id == portfolio.id)
            .order_by(AssetType.name)
        ).all()
    )
    slug_by_id = {asset_type.id: asset_type.slug for asset_type in asset_types}

    asset_type_rows = [
        {
            "slug": asset_type.slug,
            "name": asset_type.name,
            "target_pct": _serialize_decimal(asset_type.target_pct),
            "current_value": _serialize_decimal(asset_type.current_value),
            "is_exchange_traded": asset_type.is_exchange_traded,
        }
        for asset_type in asset_types
    ]

    securities = []
    investments = []
    dividends = []
    symbol_targets = []

    for asset_type in asset_types:
        if asset_type.is_exchange_traded:
            lots = session.exec(
                select(SecurityLot)
                .where(SecurityLot.asset_type_id == asset_type.id)
                .order_by(SecurityLot.symbol, SecurityLot.purchase_date)
            ).all()
            for lot in lots:
                securities.append(
                    {
                        "asset_type_slug": slug_by_id[lot.asset_type_id],
                        "symbol": lot.symbol,
                        "name": lot.name,
                        "position": _serialize_decimal(lot.position),
                        "purchase_date": _serialize_date(lot.purchase_date),
                        "purchase_price_usd": _serialize_decimal(lot.purchase_price_usd),
                        "purchase_price_brl": _serialize_decimal(lot.purchase_price_brl),
                        "usd_brl_rate": _serialize_decimal(lot.usd_brl_rate),
                        "provisional_fx": lot.provisional_fx,
                        "source": lot.source,
                        "current_price_usd": _serialize_decimal(lot.current_price_usd),
                        "current_price_brl": _serialize_decimal(lot.current_price_brl),
                    }
                )

            type_dividends = session.exec(
                select(Dividend)
                .where(Dividend.asset_type_id == asset_type.id)
                .order_by(Dividend.pay_date, Dividend.symbol)
            ).all()
            for dividend in type_dividends:
                dividends.append(
                    {
                        "asset_type_slug": slug_by_id[dividend.asset_type_id],
                        "symbol": dividend.symbol,
                        "pay_date": _serialize_date(dividend.pay_date),
                        "gross_amount_usd": _serialize_decimal(dividend.gross_amount_usd),
                        "withholding_tax_usd": _serialize_decimal(
                            dividend.withholding_tax_usd
                        ),
                        "net_amount_usd": _serialize_decimal(dividend.net_amount_usd),
                        "source": dividend.source,
                        "import_key": dividend.import_key,
                    }
                )

            targets = session.exec(
                select(SymbolTarget)
                .where(SymbolTarget.asset_type_id == asset_type.id)
                .order_by(SymbolTarget.symbol)
            ).all()
            for target in targets:
                symbol_targets.append(
                    {
                        "asset_type_slug": slug_by_id[target.asset_type_id],
                        "symbol": target.symbol,
                        "name": target.name,
                        "target_pct": _serialize_decimal(target.target_pct),
                    }
                )
        else:
            type_investments = session.exec(
                select(Investment)
                .where(Investment.asset_type_id == asset_type.id)
                .order_by(Investment.institution, Investment.name)
            ).all()
            for investment in type_investments:
                investments.append(
                    {
                        "asset_type_slug": slug_by_id[investment.asset_type_id],
                        "institution": investment.institution,
                        "name": investment.name,
                        "current_value": _serialize_decimal(investment.current_value),
                    }
                )

    snapshots = session.exec(
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.portfolio_id == portfolio.id)
        .order_by(PortfolioSnapshot.snapshot_date)
    ).all()
    snapshot_rows = []
    for snapshot in snapshots:
        snapshot_rows.append(
            {
                "snapshot_date": _serialize_date(snapshot.snapshot_date),
                "total_value": _serialize_decimal(snapshot.total_value),
                "created_at": _serialize_datetime(snapshot.created_at),
                "asset_classes": [
                    {
                        "name": row.name,
                        "current_value": _serialize_decimal(row.current_value),
                        "current_weight": _serialize_decimal(row.current_weight),
                        "target_weight": _serialize_decimal(row.target_weight),
                    }
                    for row in session.exec(
                        select(SnapshotAssetClass).where(
                            SnapshotAssetClass.snapshot_id == snapshot.id
                        )
                    ).all()
                ],
                "investments": [
                    {
                        "institution": row.institution,
                        "name": row.name,
                        "asset_type_name": row.asset_type_name,
                        "current_value": _serialize_decimal(row.current_value),
                    }
                    for row in session.exec(
                        select(SnapshotInvestment).where(
                            SnapshotInvestment.snapshot_id == snapshot.id
                        )
                    ).all()
                ],
                "holdings": [
                    {
                        "symbol": row.symbol,
                        "name": row.name,
                        "total_position": _serialize_decimal(row.total_position),
                        "current_value_brl": _serialize_decimal(row.current_value_brl),
                    }
                    for row in session.exec(
                        select(SnapshotHolding).where(
                            SnapshotHolding.snapshot_id == snapshot.id
                        )
                    ).all()
                ],
            }
        )

    exported_at = datetime.now(timezone.utc)
    return {
        "version": BACKUP_VERSION,
        "exported_at": _serialize_datetime(exported_at),
        "portfolio": {"name": portfolio.name},
        "asset_types": asset_type_rows,
        "securities": securities,
        "investments": investments,
        "dividends": dividends,
        "symbol_targets": symbol_targets,
        "snapshots": snapshot_rows,
    }


def export_portfolio_json(session: Session) -> bytes:
    payload = export_portfolio_data(session)
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")


def _clear_portfolio_data(session: Session) -> None:
    portfolio = get_portfolio(session)

    snapshots = session.exec(
        select(PortfolioSnapshot).where(PortfolioSnapshot.portfolio_id == portfolio.id)
    ).all()
    for snapshot in snapshots:
        session.delete(snapshot)

    asset_types = session.exec(
        select(AssetType).where(AssetType.portfolio_id == portfolio.id)
    ).all()
    for asset_type in asset_types:
        for lot in session.exec(
            select(SecurityLot).where(SecurityLot.asset_type_id == asset_type.id)
        ).all():
            session.delete(lot)
        for investment in session.exec(
            select(Investment).where(Investment.asset_type_id == asset_type.id)
        ).all():
            session.delete(investment)
        for dividend in session.exec(
            select(Dividend).where(Dividend.asset_type_id == asset_type.id)
        ).all():
            session.delete(dividend)
        for target in session.exec(
            select(SymbolTarget).where(SymbolTarget.asset_type_id == asset_type.id)
        ).all():
            session.delete(target)
        session.delete(asset_type)

    session.commit()


def restore_portfolio_data(session: Session, payload: dict[str, Any]) -> None:
    version = payload.get("version")
    if version != BACKUP_VERSION:
        raise ValueError(f"Unsupported backup version: {version}")

    portfolio = get_portfolio(session)
    _clear_portfolio_data(session)

    portfolio_data = payload.get("portfolio") or {}
    portfolio.name = portfolio_data.get("name") or portfolio.name
    session.add(portfolio)
    session.flush()

    slug_to_id: dict[str, Any] = {}
    name_to_id: dict[str, Any] = {}
    for row in payload.get("asset_types", []):
        asset_type = AssetType(
            portfolio_id=portfolio.id,
            name=row["name"],
            slug=row["slug"],
            target_pct=_parse_decimal(row.get("target_pct")),
            current_value=_parse_decimal(row.get("current_value")) or Decimal("0"),
            is_exchange_traded=bool(row.get("is_exchange_traded")),
        )
        session.add(asset_type)
        session.flush()
        slug_to_id[row["slug"]] = asset_type.id
        name_to_id[row["name"]] = asset_type.id

    for row in payload.get("securities", []):
        session.add(
            SecurityLot(
                asset_type_id=slug_to_id[row["asset_type_slug"]],
                symbol=row["symbol"],
                name=row.get("name", ""),
                position=_parse_decimal(row["position"]) or Decimal("0"),
                purchase_date=_parse_date(row["purchase_date"]),
                purchase_price_usd=_parse_decimal(row["purchase_price_usd"])
                or Decimal("0"),
                purchase_price_brl=_parse_decimal(row["purchase_price_brl"])
                or Decimal("0"),
                usd_brl_rate=_parse_decimal(row["usd_brl_rate"]) or Decimal("0"),
                provisional_fx=bool(row.get("provisional_fx")),
                source=row.get("source", "manual"),
                current_price_usd=_parse_decimal(row.get("current_price_usd"))
                or Decimal("0"),
                current_price_brl=_parse_decimal(row.get("current_price_brl"))
                or Decimal("0"),
            )
        )

    for row in payload.get("investments", []):
        session.add(
            Investment(
                asset_type_id=slug_to_id[row["asset_type_slug"]],
                institution=row.get("institution", ""),
                name=row["name"],
                current_value=_parse_decimal(row.get("current_value")) or Decimal("0"),
            )
        )

    for row in payload.get("dividends", []):
        session.add(
            Dividend(
                asset_type_id=slug_to_id[row["asset_type_slug"]],
                symbol=row["symbol"],
                pay_date=_parse_date(row["pay_date"]),
                gross_amount_usd=_parse_decimal(row["gross_amount_usd"]) or Decimal("0"),
                withholding_tax_usd=_parse_decimal(row.get("withholding_tax_usd"))
                or Decimal("0"),
                net_amount_usd=_parse_decimal(row["net_amount_usd"]) or Decimal("0"),
                source=row.get("source", "manual"),
                import_key=row.get("import_key"),
            )
        )

    for row in payload.get("symbol_targets", []):
        session.add(
            SymbolTarget(
                asset_type_id=slug_to_id[row["asset_type_slug"]],
                symbol=row["symbol"],
                name=row.get("name", ""),
                target_pct=_parse_decimal(row.get("target_pct")) or Decimal("0"),
            )
        )

    for row in payload.get("snapshots", []):
        snapshot = PortfolioSnapshot(
            portfolio_id=portfolio.id,
            snapshot_date=_parse_date(row["snapshot_date"]),
            total_value=_parse_decimal(row.get("total_value")) or Decimal("0"),
        )
        if row.get("created_at"):
            snapshot.created_at = datetime.fromisoformat(row["created_at"])
        session.add(snapshot)
        session.flush()

        for asset_class_row in row.get("asset_classes", []):
            session.add(
                SnapshotAssetClass(
                    snapshot_id=snapshot.id,
                    asset_type_id=name_to_id.get(asset_class_row["name"]),
                    name=asset_class_row["name"],
                    current_value=_parse_decimal(asset_class_row.get("current_value"))
                    or Decimal("0"),
                    current_weight=_parse_decimal(asset_class_row.get("current_weight"))
                    or Decimal("0"),
                    target_weight=_parse_decimal(asset_class_row.get("target_weight")),
                )
            )

        for investment_row in row.get("investments", []):
            session.add(
                SnapshotInvestment(
                    snapshot_id=snapshot.id,
                    institution=investment_row.get("institution", ""),
                    name=investment_row["name"],
                    asset_type_name=investment_row["asset_type_name"],
                    current_value=_parse_decimal(investment_row.get("current_value"))
                    or Decimal("0"),
                )
            )

        for holding_row in row.get("holdings", []):
            session.add(
                SnapshotHolding(
                    snapshot_id=snapshot.id,
                    symbol=holding_row["symbol"],
                    name=holding_row.get("name", ""),
                    total_position=_parse_decimal(holding_row.get("total_position"))
                    or Decimal("0"),
                    current_value_brl=_parse_decimal(holding_row.get("current_value_brl"))
                    or Decimal("0"),
                )
            )

    session.commit()


def restore_portfolio_json(session: Session, raw: bytes) -> None:
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Backup file must contain a JSON object.")
    restore_portfolio_data(session, payload)
