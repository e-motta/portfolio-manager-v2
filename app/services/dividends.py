from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlmodel import Session, select

from app.models.dividend import Dividend


@dataclass
class DividendTotals:
    gross_usd: Decimal
    withholding_usd: Decimal
    net_usd: Decimal


@dataclass(frozen=True)
class DividendSymbolSummary:
    symbol: str
    payment_count: int
    gross_usd: Decimal
    withholding_usd: Decimal
    net_usd: Decimal


def get_dividends(session: Session, asset_type_id: UUID) -> list[Dividend]:
    return list(
        session.exec(
            select(Dividend)
            .where(Dividend.asset_type_id == asset_type_id)
            .order_by(Dividend.pay_date.desc(), Dividend.symbol)
        ).all()
    )


def summarize_dividends_by_symbol(dividends: list[Dividend]) -> dict[str, DividendSymbolSummary]:
    grouped: dict[str, list[Dividend]] = {}
    for dividend in dividends:
        grouped.setdefault(dividend.symbol, []).append(dividend)

    summaries: dict[str, DividendSymbolSummary] = {}
    for symbol in sorted(grouped):
        payments = grouped[symbol]
        summaries[symbol] = DividendSymbolSummary(
            symbol=symbol,
            payment_count=len(payments),
            gross_usd=sum(
                (payment.gross_amount_usd for payment in payments),
                start=Decimal("0"),
            ),
            withholding_usd=sum(
                (payment.withholding_tax_usd for payment in payments),
                start=Decimal("0"),
            ),
            net_usd=sum(
                (payment.net_amount_usd for payment in payments),
                start=Decimal("0"),
            ),
        )
    return summaries


def dividend_totals(dividends: list[Dividend]) -> DividendTotals:
    gross = sum((item.gross_amount_usd for item in dividends), start=Decimal("0"))
    withholding = sum((item.withholding_tax_usd for item in dividends), start=Decimal("0"))
    net = sum((item.net_amount_usd for item in dividends), start=Decimal("0"))
    return DividendTotals(gross_usd=gross, withholding_usd=withholding, net_usd=net)


def compute_net_amount(gross: Decimal, withholding: Decimal) -> Decimal:
    return gross - withholding
