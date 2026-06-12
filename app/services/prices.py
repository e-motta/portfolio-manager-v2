import json
import urllib.error
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import yfinance as yf
from sqlmodel import Session, select

from app.models.asset_type import AssetType
from app.models.security import SecurityLot


@dataclass
class TickerInfo:
    symbol: str
    name: str
    latest_price: Decimal


def _get_price_from_ticker(ticker_info: dict) -> Decimal:
    for key in ("regularMarketPrice", "bid", "previousClose"):
        value = ticker_info.get(key)
        if value is not None and Decimal(str(value)) > 0:
            return Decimal(str(value))
    return Decimal("0")


def fetch_usd_brl_rate() -> Decimal:
    info = yf.Ticker("USDBRL=X").info
    rate = _get_price_from_ticker(info)
    if rate <= 0:
        history = yf.Ticker("USDBRL=X").history(period="1d")
        if not history.empty:
            rate = Decimal(str(history["Close"].iloc[-1]))
    return rate


def _ptax_url(purchase_date: date) -> str:
    date_str = purchase_date.strftime("%m-%d-%Y")
    return (
        "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
        "CotacaoMoedaPeriodoFechamento(codigoMoeda=@codigoMoeda,"
        "dataInicialCotacao=@dataInicialCotacao,dataFinalCotacao=@dataFinalCotacao)"
        f"?@codigoMoeda='USD'"
        f"&@dataInicialCotacao='{date_str}'"
        f"&@dataFinalCotacao='{date_str}'"
        "&$format=json"
        "&$select=cotacaoVenda"
    )


def fetch_ptax_usd_brl_rate(purchase_date: date) -> Decimal | None:
    try:
        with urllib.request.urlopen(_ptax_url(purchase_date), timeout=10) as response:
            data = json.loads(response.read())
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError):
        return None

    values = data.get("value")
    if not values:
        return None

    rate = values[0].get("cotacaoVenda")
    if rate is None:
        return None

    try:
        parsed = Decimal(str(rate))
    except InvalidOperation:
        return None
    return parsed if parsed > 0 else None


def resolve_purchase_usd_brl_rate(purchase_date: date) -> tuple[Decimal, bool]:
    """Return (rate, provisional_fx). PTAX is final; yfinance fallback is estimated."""
    rate = fetch_ptax_usd_brl_rate(purchase_date)
    if rate is not None:
        return rate, False
    return fetch_usd_brl_rate(), True


def fetch_tickers_info(symbols: Iterable[str]) -> dict[str, TickerInfo]:
    symbol_list = list(symbols)
    if not symbol_list:
        return {}

    if len(symbol_list) == 1:
        symbol = symbol_list[0]
        info = yf.Ticker(symbol).info
        return {
            symbol: TickerInfo(
                symbol=symbol,
                name=info.get("longName", "") or info.get("shortName", "") or symbol,
                latest_price=_get_price_from_ticker(info),
            )
        }

    tickers = yf.Tickers(" ".join(symbol_list))
    out: dict[str, TickerInfo] = {}
    for symbol in symbol_list:
        ticker = tickers.tickers.get(symbol)
        if not ticker:
            continue
        info = ticker.info
        out[symbol] = TickerInfo(
            symbol=symbol,
            name=info.get("longName", "") or info.get("shortName", "") or symbol,
            latest_price=_get_price_from_ticker(info),
        )
    return out


def compute_price_brl(price_usd: Decimal, usd_brl_rate: Decimal) -> Decimal:
    return (price_usd * usd_brl_rate).quantize(Decimal("0.00000001"))


def refresh_security_prices(session: Session, lots: list[SecurityLot]) -> None:
    if not lots:
        return

    symbols = sorted({lot.symbol for lot in lots})
    market_fx = fetch_usd_brl_rate()
    tickers_info = fetch_tickers_info(symbols)

    for lot in lots:
        info = tickers_info.get(lot.symbol)
        if info:
            lot.current_price_usd = info.latest_price
            if info.name:
                lot.name = info.name
        elif lot.current_price_usd <= 0:
            lot.current_price_usd = lot.purchase_price_usd

        if market_fx > 0:
            lot.current_price_brl = compute_price_brl(lot.current_price_usd, market_fx)
        lot.updated_at = datetime.utcnow()
        session.add(lot)
    session.commit()


def get_last_prices_updated_at(session: Session) -> datetime | None:
    exchange_type = session.exec(
        select(AssetType).where(AssetType.is_exchange_traded.is_(True))  # type: ignore[attr-defined]
    ).first()
    if not exchange_type:
        return None

    lots = session.exec(
        select(SecurityLot).where(SecurityLot.asset_type_id == exchange_type.id)
    ).all()
    if not lots:
        return None

    return max(lot.updated_at for lot in lots)


def refresh_all_exchange_traded_prices(session: Session) -> int:
    exchange_type = session.exec(
        select(AssetType).where(AssetType.is_exchange_traded.is_(True))  # type: ignore[attr-defined]
    ).first()
    if not exchange_type:
        return 0

    lots = session.exec(
        select(SecurityLot).where(SecurityLot.asset_type_id == exchange_type.id)
    ).all()
    refresh_security_prices(session, list(lots))
    return len(lots)


def refresh_provisional_ptax_rates(session: Session) -> int:
    exchange_type = session.exec(
        select(AssetType).where(AssetType.is_exchange_traded.is_(True))  # type: ignore[attr-defined]
    ).first()
    if not exchange_type:
        return 0

    lots = session.exec(
        select(SecurityLot).where(
            SecurityLot.asset_type_id == exchange_type.id,
            SecurityLot.provisional_fx.is_(True),  # type: ignore[attr-defined]
        )
    ).all()
    if not lots:
        return 0

    ptax_cache: dict[date, Decimal | None] = {}
    updated = 0
    for lot in lots:
        if lot.purchase_date not in ptax_cache:
            ptax_cache[lot.purchase_date] = fetch_ptax_usd_brl_rate(lot.purchase_date)
        rate = ptax_cache[lot.purchase_date]
        if rate is None:
            continue
        lot.usd_brl_rate = rate
        lot.purchase_price_brl = compute_price_brl(lot.purchase_price_usd, rate)
        lot.provisional_fx = False
        lot.updated_at = datetime.utcnow()
        session.add(lot)
        updated += 1

    if updated:
        session.commit()
    return updated


def count_provisional_fx_lots(session: Session) -> int:
    exchange_type = session.exec(
        select(AssetType).where(AssetType.is_exchange_traded.is_(True))  # type: ignore[attr-defined]
    ).first()
    if not exchange_type:
        return 0

    lots = session.exec(
        select(SecurityLot).where(
            SecurityLot.asset_type_id == exchange_type.id,
            SecurityLot.provisional_fx.is_(True),  # type: ignore[attr-defined]
        )
    ).all()
    return len(lots)
