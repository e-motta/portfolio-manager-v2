from decimal import Decimal
from typing import NamedTuple

from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from app.models.asset_type import AssetType
from app.models.dividend import Dividend
from app.models.investment import Investment
from app.models.portfolio import Portfolio
from app.models.security import SecurityLot
from app.models.symbol_target import SymbolTarget
from app.services.allocation import (
    allocation_sleeve_value,
    allocation_target_total,
    get_effective_type_value,
    has_type_target,
    normalize_allocation_target,
    weight_of_allocation_sleeve,
    weight_of_total,
)
from app.services import prices
from app.services.securities import (
    build_portfolio_return_totals,
    build_security_returns,
    consolidate_securities,
)


def get_portfolio(session: Session) -> Portfolio:
    portfolio = session.exec(select(Portfolio)).first()
    if not portfolio:
        raise RuntimeError("Portfolio not seeded. Run migrations and init_db.")
    return portfolio


def get_exchange_traded_type(session: Session) -> AssetType | None:
    portfolio = get_portfolio(session)
    return session.exec(
        select(AssetType).where(
            AssetType.portfolio_id == portfolio.id,
            AssetType.is_exchange_traded.is_(True),  # type: ignore[attr-defined]
        )
    ).first()


def get_dividends(session: Session) -> list[Dividend]:
    exchange_type = get_exchange_traded_type(session)
    if not exchange_type:
        return []
    return list(
        session.exec(
            select(Dividend)
            .where(Dividend.asset_type_id == exchange_type.id)
            .order_by(Dividend.pay_date.desc(), Dividend.symbol)
        ).all()
    )


def get_security_lots(session: Session) -> list[SecurityLot]:
    exchange_type = get_exchange_traded_type(session)
    if not exchange_type:
        return []
    return list(
        session.exec(
            select(SecurityLot)
            .where(SecurityLot.asset_type_id == exchange_type.id)
            .order_by(SecurityLot.symbol, SecurityLot.purchase_date)
        ).all()
    )


def get_symbol_targets(session: Session) -> list[SymbolTarget]:
    exchange_type = get_exchange_traded_type(session)
    if not exchange_type:
        return []
    return list(
        session.exec(
            select(SymbolTarget)
            .where(SymbolTarget.asset_type_id == exchange_type.id)
            .order_by(SymbolTarget.symbol)
        ).all()
    )


def get_consolidated_securities(session: Session):
    lots = get_security_lots(session)
    targets = get_symbol_targets(session)
    return consolidate_securities(lots, targets)


def get_securities_performance(session: Session) -> dict:
    consolidated = get_consolidated_securities(session)
    dividends = get_dividends(session)
    usd_brl_rate = prices.fetch_usd_brl_rate()
    security_returns = build_security_returns(consolidated, dividends, usd_brl_rate)
    return_totals = build_portfolio_return_totals(security_returns)
    return {
        "consolidated": consolidated,
        "dividends": dividends,
        "security_returns": security_returns,
        "return_totals": return_totals,
        "usd_brl_rate": usd_brl_rate,
    }


def get_or_create_symbol_target(
    session: Session, asset_type_id, symbol: str, name: str = ""
) -> SymbolTarget:
    target = session.exec(
        select(SymbolTarget).where(
            SymbolTarget.asset_type_id == asset_type_id,
            SymbolTarget.symbol == symbol,
        )
    ).first()
    if target:
        if name and not target.name:
            target.name = name
            session.add(target)
            session.commit()
            session.refresh(target)
        return target

    target = SymbolTarget(
        asset_type_id=asset_type_id,
        symbol=symbol,
        name=name or symbol,
        target_pct=Decimal("0"),
    )
    session.add(target)
    session.commit()
    session.refresh(target)
    return target


def get_investments(session: Session) -> list[Investment]:
    return list(
        session.exec(
            select(Investment)
            .join(AssetType)
            .where(AssetType.is_exchange_traded.is_(False))  # type: ignore[attr-defined]
            .options(selectinload(Investment.asset_type))  # type: ignore[arg-type]
            .order_by(Investment.institution, Investment.name, AssetType.name)
        ).all()
    )


class InstitutionSummary(NamedTuple):
    institution: str
    position_count: int
    total_value: Decimal
    weight: Decimal


def build_institution_summaries(
    investments: list[Investment],
    total_current: Decimal,
) -> list[InstitutionSummary]:
    totals: dict[str, Decimal] = {}
    counts: dict[str, int] = {}
    for item in investments:
        label = item.institution.strip() or "—"
        totals[label] = totals.get(label, Decimal("0")) + item.current_value
        counts[label] = counts.get(label, 0) + 1

    return [
        InstitutionSummary(
            institution=institution,
            position_count=counts[institution],
            total_value=value,
            weight=value / total_current if total_current > 0 else Decimal("0"),
        )
        for institution, value in sorted(
            totals.items(),
            key=lambda row: (-row[1], row[0].lower()),
        )
    ]


def get_investable_asset_types(session: Session) -> list[AssetType]:
    portfolio = get_portfolio(session)
    return list(
        session.exec(
            select(AssetType)
            .where(
                AssetType.portfolio_id == portfolio.id,
                AssetType.is_exchange_traded.is_(False),  # type: ignore[attr-defined]
            )
            .order_by(AssetType.name)
        ).all()
    )


def get_asset_type_asset_count(asset_type: AssetType) -> int:
    if asset_type.is_exchange_traded:
        return len({lot.symbol for lot in (getattr(asset_type, "securities", None) or [])})
    return len(getattr(asset_type, "investments", None) or [])


def enrich_asset_type(session: Session, asset_type: AssetType) -> AssetType:
    if asset_type.is_exchange_traded:
        asset_type.securities = get_security_lots(session)
    else:
        asset_type.investments = [
            investment
            for investment in get_investments(session)
            if investment.asset_type_id == asset_type.id
        ]
    return asset_type


def sort_asset_types_for_display(asset_types: list[AssetType]) -> list[AssetType]:
    exchange_traded = [asset_type for asset_type in asset_types if asset_type.is_exchange_traded]
    others = sorted(
        (asset_type for asset_type in asset_types if not asset_type.is_exchange_traded),
        key=lambda asset_type: asset_type.name.lower(),
    )
    return exchange_traded + others


def get_asset_types(session: Session) -> list[AssetType]:
    portfolio = get_portfolio(session)
    asset_types = list(
        session.exec(
            select(AssetType)
            .where(AssetType.portfolio_id == portfolio.id)
            .order_by(AssetType.name)
        ).all()
    )
    investments_by_type: dict = {}
    for investment in get_investments(session):
        investments_by_type.setdefault(investment.asset_type_id, []).append(investment)

    exchange_type = next(
        (asset_type for asset_type in asset_types if asset_type.is_exchange_traded),
        None,
    )
    if exchange_type:
        exchange_type.securities = get_security_lots(session)

    for asset_type in asset_types:
        if not asset_type.is_exchange_traded:
            asset_type.investments = investments_by_type.get(asset_type.id, [])

    return asset_types


def build_dashboard_rows(session: Session) -> list[dict]:
    asset_types = sort_asset_types_for_display(get_asset_types(session))
    values = {
        asset_type.id: get_effective_type_value(asset_type)
        for asset_type in asset_types
    }
    total_value = sum(values.values(), start=Decimal("0"))
    sleeve_value = allocation_sleeve_value(asset_types, values)
    target_total = allocation_target_total(asset_types)

    rows = []
    for asset_type in asset_types:
        current_value = values[asset_type.id]
        current_weight = weight_of_total(current_value, total_value)
        if has_type_target(asset_type):
            target_weight = asset_type.target_pct
            assert target_weight is not None
            drift = current_weight - target_weight
            current_weight_allocation = weight_of_allocation_sleeve(
                current_value, sleeve_value
            )
            target_weight_allocation = normalize_allocation_target(
                target_weight, target_total
            )
        else:
            target_weight = None
            drift = None
            current_weight_allocation = None
            target_weight_allocation = None
        rows.append(
            {
                "asset_type": asset_type,
                "current_value": current_value,
                "current_weight": current_weight,
                "current_weight_allocation": current_weight_allocation,
                "target_weight": target_weight,
                "target_weight_allocation": target_weight_allocation,
                "drift": drift,
                "has_target": has_type_target(asset_type),
            }
        )
    return rows
