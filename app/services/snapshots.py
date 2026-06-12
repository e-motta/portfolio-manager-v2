from datetime import date
from decimal import Decimal

from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from app.models.snapshot import (
    PortfolioSnapshot,
    SnapshotAssetClass,
    SnapshotHolding,
    SnapshotInvestment,
)
from app.web.helpers import (
    build_dashboard_rows,
    get_consolidated_securities,
    get_investments,
)


def capture_portfolio_snapshot(session: Session, snapshot_date: date) -> PortfolioSnapshot:
    existing = session.exec(
        select(PortfolioSnapshot).where(PortfolioSnapshot.snapshot_date == snapshot_date)
    ).first()
    if existing:
        session.delete(existing)
        session.commit()

    dashboard_rows = build_dashboard_rows(session)
    investments = get_investments(session)
    holdings = get_consolidated_securities(session)
    total_value = sum(
        (row["current_value"] for row in dashboard_rows),
        start=Decimal("0"),
    )

    snapshot = PortfolioSnapshot(snapshot_date=snapshot_date, total_value=total_value)
    session.add(snapshot)
    session.flush()

    for row in dashboard_rows:
        asset_type = row["asset_type"]
        session.add(
            SnapshotAssetClass(
                snapshot_id=snapshot.id,
                asset_type_id=asset_type.id,
                name=asset_type.name,
                current_value=row["current_value"],
                current_weight=row["current_weight"],
                target_weight=row["target_weight"],
            )
        )

    for investment in investments:
        session.add(
            SnapshotInvestment(
                snapshot_id=snapshot.id,
                institution=investment.institution,
                name=investment.name,
                asset_type_name=investment.asset_type.name,
                current_value=investment.current_value,
            )
        )

    for holding in holdings:
        session.add(
            SnapshotHolding(
                snapshot_id=snapshot.id,
                symbol=holding.symbol,
                name=holding.name,
                total_position=holding.total_position,
                current_value_brl=holding.current_value_brl,
            )
        )

    session.commit()
    session.refresh(snapshot)
    return snapshot


def get_snapshots(session: Session) -> list[PortfolioSnapshot]:
    return list(
        session.exec(
            select(PortfolioSnapshot)
            .options(selectinload(PortfolioSnapshot.asset_classes))  # type: ignore[arg-type]
            .order_by(PortfolioSnapshot.snapshot_date.desc())
        ).all()
    )


def get_snapshot(session: Session, snapshot_id) -> PortfolioSnapshot | None:
    return session.exec(
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.id == snapshot_id)
        .options(
            selectinload(PortfolioSnapshot.asset_classes),  # type: ignore[arg-type]
            selectinload(PortfolioSnapshot.investments),  # type: ignore[arg-type]
            selectinload(PortfolioSnapshot.holdings),  # type: ignore[arg-type]
        )
    ).first()


def build_snapshot_dashboard(session: Session) -> dict:
    snapshots = get_snapshots(session)
    if not snapshots:
        return {
            "snapshots": [],
            "asset_class_names": [],
            "history_rows": [],
        }

    name_order: dict[str, int] = {}
    for snapshot in snapshots:
        for row in snapshot.asset_classes:
            if row.name not in name_order:
                name_order[row.name] = 0 if row.name == "Listed Securities" else len(name_order) + 1

    asset_class_names = sorted(name_order, key=lambda name: (name_order[name], name.lower()))

    history_rows = []
    for snapshot in snapshots:
        values_by_name = {row.name: row.current_value for row in snapshot.asset_classes}
        weights_by_name = {row.name: row.current_weight for row in snapshot.asset_classes}
        history_rows.append(
            {
                "snapshot": snapshot,
                "values_by_name": values_by_name,
                "weights_by_name": weights_by_name,
            }
        )

    return {
        "snapshots": snapshots,
        "asset_class_names": asset_class_names,
        "history_rows": history_rows,
    }


def sort_snapshot_asset_classes(rows: list[SnapshotAssetClass]) -> list[SnapshotAssetClass]:
    exchange = [row for row in rows if row.name == "Listed Securities"]
    others = sorted(
        (row for row in rows if row.name != "Listed Securities"),
        key=lambda row: row.name.lower(),
    )
    return exchange + others
