from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.models.dividend import Dividend
from app.models.security import SecurityLot
from app.models.symbol_target import SymbolTarget
from app.services.dividends import summarize_dividends_by_symbol
from app.services.prices import compute_price_brl


@dataclass
class ConsolidatedSecurity:
    symbol_target_id: UUID
    symbol: str
    name: str
    total_position: Decimal
    avg_purchase_price_usd: Decimal
    avg_purchase_price_brl: Decimal
    current_price_usd: Decimal
    current_price_brl: Decimal
    cost_basis_usd: Decimal
    cost_basis_brl: Decimal
    current_value_usd: Decimal
    current_value_brl: Decimal
    pl_usd: Decimal
    pl_brl: Decimal
    current_weight: Decimal
    target_pct: Decimal
    has_provisional_fx: bool
    lots: list[SecurityLot]

    @property
    def pl_pct_usd(self) -> Decimal | None:
        if self.cost_basis_usd <= 0:
            return None
        return (self.pl_usd / self.cost_basis_usd) * Decimal("100")

    @property
    def pl_pct_brl(self) -> Decimal | None:
        if self.cost_basis_brl <= 0:
            return None
        return (self.pl_brl / self.cost_basis_brl) * Decimal("100")


def consolidate_securities(
    lots: list[SecurityLot],
    symbol_targets: list[SymbolTarget],
) -> list[ConsolidatedSecurity]:
    targets_by_symbol = {target.symbol: target for target in symbol_targets}
    grouped: dict[str, list[SecurityLot]] = {}
    for lot in lots:
        grouped.setdefault(lot.symbol, []).append(lot)

    bucket_value = sum(
        (
            lot.position * lot.current_price_brl
            for lot in lots
            if lot.current_price_brl > 0
        ),
        start=Decimal("0"),
    )

    consolidated: list[ConsolidatedSecurity] = []
    for symbol in sorted(grouped):
        symbol_lots = grouped[symbol]
        total_position = sum((lot.position for lot in symbol_lots), start=Decimal("0"))
        if total_position <= 0:
            continue

        cost_usd = sum(
            (lot.position * lot.purchase_price_usd for lot in symbol_lots),
            start=Decimal("0"),
        )
        cost_brl = sum(
            (lot.position * lot.purchase_price_brl for lot in symbol_lots),
            start=Decimal("0"),
        )
        current_price_usd = symbol_lots[0].current_price_usd
        current_price_brl = symbol_lots[0].current_price_brl
        current_value_usd = total_position * current_price_usd
        current_value_brl = total_position * current_price_brl
        target = targets_by_symbol.get(symbol)
        consolidated.append(
            ConsolidatedSecurity(
                symbol_target_id=target.id if target else symbol_lots[0].id,
                symbol=symbol,
                name=target.name if target and target.name else symbol_lots[0].name,
                total_position=total_position,
                avg_purchase_price_usd=cost_usd / total_position,
                avg_purchase_price_brl=cost_brl / total_position,
                current_price_usd=current_price_usd,
                current_price_brl=current_price_brl,
                cost_basis_usd=cost_usd,
                cost_basis_brl=cost_brl,
                current_value_usd=current_value_usd,
                current_value_brl=current_value_brl,
                pl_usd=current_value_usd - cost_usd,
                pl_brl=current_value_brl - cost_brl,
                current_weight=(
                    current_value_brl / bucket_value if bucket_value > 0 else Decimal("0")
                ),
                target_pct=target.target_pct if target else Decimal("0"),
                has_provisional_fx=any(lot.provisional_fx for lot in symbol_lots),
                lots=symbol_lots,
            )
        )
    return consolidated


def bucket_value_from_lots(lots: list[SecurityLot]) -> Decimal:
    return sum((lot.current_value for lot in lots), start=Decimal("0"))


def pl_pct(pl: Decimal, cost_basis: Decimal) -> Decimal | None:
    if cost_basis <= 0:
        return None
    return (pl / cost_basis) * Decimal("100")


@dataclass
class SecurityReturnSummary:
    symbol: str
    name: str
    cost_basis_usd: Decimal
    cost_basis_brl: Decimal
    current_value_usd: Decimal
    current_value_brl: Decimal
    unrealized_pl_usd: Decimal
    unrealized_pl_brl: Decimal
    dividend_gross_usd: Decimal
    dividend_withholding_usd: Decimal
    dividend_net_usd: Decimal
    dividend_payment_count: int
    dividend_net_brl: Decimal
    total_return_usd: Decimal
    total_return_brl: Decimal

    @property
    def unrealized_pl_pct_usd(self) -> Decimal | None:
        return pl_pct(self.unrealized_pl_usd, self.cost_basis_usd)

    @property
    def unrealized_pl_pct_brl(self) -> Decimal | None:
        return pl_pct(self.unrealized_pl_brl, self.cost_basis_brl)

    @property
    def total_return_pct_usd(self) -> Decimal | None:
        return pl_pct(self.total_return_usd, self.cost_basis_usd)

    @property
    def total_return_pct_brl(self) -> Decimal | None:
        return pl_pct(self.total_return_brl, self.cost_basis_brl)


@dataclass
class PortfolioReturnTotals:
    cost_basis_usd: Decimal
    cost_basis_brl: Decimal
    current_value_usd: Decimal
    current_value_brl: Decimal
    unrealized_pl_usd: Decimal
    unrealized_pl_brl: Decimal
    dividend_gross_usd: Decimal
    dividend_withholding_usd: Decimal
    dividend_net_usd: Decimal
    dividend_net_brl: Decimal
    total_return_usd: Decimal
    total_return_brl: Decimal

    @property
    def unrealized_pl_pct_usd(self) -> Decimal | None:
        return pl_pct(self.unrealized_pl_usd, self.cost_basis_usd)

    @property
    def unrealized_pl_pct_brl(self) -> Decimal | None:
        return pl_pct(self.unrealized_pl_brl, self.cost_basis_brl)

    @property
    def total_return_pct_usd(self) -> Decimal | None:
        return pl_pct(self.total_return_usd, self.cost_basis_usd)

    @property
    def total_return_pct_brl(self) -> Decimal | None:
        return pl_pct(self.total_return_brl, self.cost_basis_brl)


def build_security_returns(
    consolidated: list[ConsolidatedSecurity],
    dividends: list[Dividend],
    usd_brl_rate: Decimal,
) -> list[SecurityReturnSummary]:
    by_symbol = summarize_dividends_by_symbol(dividends)
    consolidated_by_symbol = {item.symbol: item for item in consolidated}
    symbols = sorted(set(consolidated_by_symbol) | set(by_symbol))

    returns: list[SecurityReturnSummary] = []
    for symbol in symbols:
        security = consolidated_by_symbol.get(symbol)
        dividend = by_symbol.get(symbol)
        dividend_net_usd = dividend.net_usd if dividend else Decimal("0")
        dividend_net_brl = compute_price_brl(dividend_net_usd, usd_brl_rate)

        if security:
            unrealized_pl_usd = security.pl_usd
            unrealized_pl_brl = security.pl_brl
            name = security.name
            cost_basis_usd = security.cost_basis_usd
            cost_basis_brl = security.cost_basis_brl
            current_value_usd = security.current_value_usd
            current_value_brl = security.current_value_brl
        else:
            unrealized_pl_usd = Decimal("0")
            unrealized_pl_brl = Decimal("0")
            name = symbol
            cost_basis_usd = Decimal("0")
            cost_basis_brl = Decimal("0")
            current_value_usd = Decimal("0")
            current_value_brl = Decimal("0")

        returns.append(
            SecurityReturnSummary(
                symbol=symbol,
                name=name,
                cost_basis_usd=cost_basis_usd,
                cost_basis_brl=cost_basis_brl,
                current_value_usd=current_value_usd,
                current_value_brl=current_value_brl,
                unrealized_pl_usd=unrealized_pl_usd,
                unrealized_pl_brl=unrealized_pl_brl,
                dividend_gross_usd=dividend.gross_usd if dividend else Decimal("0"),
                dividend_withholding_usd=(
                    dividend.withholding_usd if dividend else Decimal("0")
                ),
                dividend_net_usd=dividend_net_usd,
                dividend_payment_count=dividend.payment_count if dividend else 0,
                dividend_net_brl=dividend_net_brl,
                total_return_usd=unrealized_pl_usd + dividend_net_usd,
                total_return_brl=unrealized_pl_brl + dividend_net_brl,
            )
        )
    return returns


def build_portfolio_return_totals(
    returns: list[SecurityReturnSummary],
) -> PortfolioReturnTotals:
    return PortfolioReturnTotals(
        cost_basis_usd=sum((item.cost_basis_usd for item in returns), start=Decimal("0")),
        cost_basis_brl=sum((item.cost_basis_brl for item in returns), start=Decimal("0")),
        current_value_usd=sum(
            (item.current_value_usd for item in returns),
            start=Decimal("0"),
        ),
        current_value_brl=sum(
            (item.current_value_brl for item in returns),
            start=Decimal("0"),
        ),
        unrealized_pl_usd=sum(
            (item.unrealized_pl_usd for item in returns),
            start=Decimal("0"),
        ),
        unrealized_pl_brl=sum(
            (item.unrealized_pl_brl for item in returns),
            start=Decimal("0"),
        ),
        dividend_gross_usd=sum(
            (item.dividend_gross_usd for item in returns),
            start=Decimal("0"),
        ),
        dividend_withholding_usd=sum(
            (item.dividend_withholding_usd for item in returns),
            start=Decimal("0"),
        ),
        dividend_net_usd=sum(
            (item.dividend_net_usd for item in returns),
            start=Decimal("0"),
        ),
        dividend_net_brl=sum(
            (item.dividend_net_brl for item in returns),
            start=Decimal("0"),
        ),
        total_return_usd=sum(
            (item.total_return_usd for item in returns),
            start=Decimal("0"),
        ),
        total_return_brl=sum(
            (item.total_return_brl for item in returns),
            start=Decimal("0"),
        ),
    )
