import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from sqlmodel import Session, select

from app.models.dividend import Dividend
from app.models.security import SecurityLot
from app.services.dividends import compute_net_amount
from app.services.prices import (
    compute_price_brl,
    fetch_tickers_info,
    resolve_purchase_usd_brl_rate,
)
from app.web.helpers import get_or_create_symbol_target


@dataclass
class IBTradeLot:
    symbol: str
    trade_date: date
    quantity: Decimal
    price_usd: Decimal


@dataclass
class IBOpenPosition:
    symbol: str
    quantity: Decimal
    cost_price_usd: Decimal
    close_price_usd: Decimal
    cost_basis_usd: Decimal
    value_usd: Decimal


@dataclass
class IBDividend:
    symbol: str
    pay_date: date
    gross_amount_usd: Decimal
    withholding_tax_usd: Decimal
    net_amount_usd: Decimal


@dataclass
class IBStatement:
    period_end: date | None
    positions: list[IBOpenPosition] = field(default_factory=list)
    trades: list[IBTradeLot] = field(default_factory=list)
    dividends: list[IBDividend] = field(default_factory=list)
    names: dict[str, str] = field(default_factory=dict)


@dataclass
class ImportDividendRow:
    dividend_key: str
    symbol: str
    name: str
    pay_date: date
    gross_amount_usd: Decimal
    withholding_tax_usd: Decimal
    net_amount_usd: Decimal
    already_exists: bool
    selected: bool


@dataclass
class ImportLotRow:
    lot_key: str
    symbol: str
    name: str
    trade_date: date
    quantity: Decimal
    price_usd: Decimal
    already_exists: bool
    selected: bool


@dataclass
class StashedImport:
    statement: IBStatement


_import_stash: dict[str, StashedImport] = {}


_DIVIDEND_SYMBOL_RE = re.compile(r"^([A-Z0-9.]+)\(")


def dividend_selection_key(
    symbol: str,
    pay_date: date,
    gross_amount_usd: Decimal,
) -> str:
    gross = gross_amount_usd.quantize(Decimal("0.01"))
    return f"{symbol.upper()}|{pay_date.isoformat()}|{gross}"


def lot_selection_key(
    symbol: str,
    trade_date: date,
    quantity: Decimal,
    price_usd: Decimal,
) -> str:
    qty = quantity.quantize(Decimal("0.0001"))
    price = price_usd.quantize(Decimal("0.00000001"))
    return f"{symbol.upper()}|{trade_date.isoformat()}|{qty}|{price}"


def stash_import(statement: IBStatement) -> str:
    token = str(uuid4())
    _import_stash[token] = StashedImport(statement=statement)
    return token


def pop_stashed_import(token: str) -> IBStatement | None:
    stashed = _import_stash.pop(token, None)
    if not stashed:
        return None
    return stashed.statement


def clear_import_stash() -> None:
    _import_stash.clear()


def _parse_decimal(value: str) -> Decimal | None:
    cleaned = value.strip()
    if not cleaned or cleaned == "--":
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _parse_trade_date(value: str) -> date:
    date_part = value.split(",", 1)[0].strip()
    return date.fromisoformat(date_part)


def _parse_iso_date(value: str) -> date | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        return None


def _symbol_from_dividend_description(description: str) -> str | None:
    match = _DIVIDEND_SYMBOL_RE.match(description.strip())
    if not match:
        return None
    return match.group(1).upper()


def _parse_period_end(period: str) -> date | None:
    if " - " not in period:
        return None
    end_part = period.strip().strip('"').split(" - ", 1)[1].strip()
    try:
        return datetime.strptime(end_part, "%B %d, %Y").date()
    except ValueError:
        return None


def parse_ib_statement(content: str) -> IBStatement:
    reader = csv.reader(io.StringIO(content))
    statement = IBStatement(period_end=None)

    for row in reader:
        if not row:
            continue

        section = row[0]

        if section == "Statement" and len(row) >= 4 and row[1] == "Data" and row[2] == "Period":
            statement.period_end = _parse_period_end(row[3])

        elif section == "Open Positions" and len(row) >= 12 and row[1] == "Data":
            if row[2] != "Summary" or row[3] != "Stocks":
                continue
            symbol = row[5].strip()
            if not symbol:
                continue
            quantity = _parse_decimal(row[6])
            cost_price = _parse_decimal(row[8])
            cost_basis = _parse_decimal(row[9])
            close_price = _parse_decimal(row[10])
            value = _parse_decimal(row[11])
            if quantity is None or quantity <= 0:
                continue
            if cost_price is None and cost_basis is not None and quantity > 0:
                cost_price = cost_basis / quantity
            if cost_price is None or close_price is None:
                continue
            statement.positions.append(
                IBOpenPosition(
                    symbol=symbol.upper(),
                    quantity=quantity,
                    cost_price_usd=cost_price,
                    close_price_usd=close_price,
                    cost_basis_usd=cost_basis or cost_price * quantity,
                    value_usd=value or close_price * quantity,
                )
            )

        elif section == "Trades" and len(row) >= 9 and row[1] == "Data" and row[2] == "Order":
            if row[3] != "Stocks":
                continue
            symbol = row[5].strip().upper()
            if not symbol:
                continue
            quantity = _parse_decimal(row[7])
            price = _parse_decimal(row[8])
            if quantity is None or price is None or quantity <= 0:
                continue
            statement.trades.append(
                IBTradeLot(
                    symbol=symbol,
                    trade_date=_parse_trade_date(row[6]),
                    quantity=quantity,
                    price_usd=price,
                )
            )

        elif section == "Change in Dividend Accruals" and len(row) >= 15 and row[1] == "Data":
            if row[2] != "Stocks":
                continue
            code = row[14].strip()
            if code != "Po":
                continue
            symbol = row[4].strip().upper()
            pay_date = _parse_iso_date(row[7])
            gross = _parse_decimal(row[12])
            tax = _parse_decimal(row[9])
            net = _parse_decimal(row[13])
            if not symbol or pay_date is None or gross is None or gross <= 0:
                continue
            withholding = abs(tax) if tax is not None else Decimal("0")
            if net is None:
                net = compute_net_amount(gross, withholding)
            statement.dividends.append(
                IBDividend(
                    symbol=symbol,
                    pay_date=pay_date,
                    gross_amount_usd=gross,
                    withholding_tax_usd=withholding,
                    net_amount_usd=net,
                )
            )

        elif section == "Financial Instrument Information" and len(row) >= 5 and row[1] == "Data":
            if row[2] != "Stocks":
                continue
            symbol = row[3].strip().upper()
            name = row[4].strip()
            if symbol and name:
                statement.names[symbol] = name

    if not statement.dividends:
        statement.dividends = _parse_dividends_from_cash_sections(content)

    return statement


def _parse_dividends_from_cash_sections(content: str) -> list[IBDividend]:
    reader = csv.reader(io.StringIO(content))
    gross_rows: list[tuple[str, date, Decimal]] = []
    tax_by_key: dict[tuple[str, date], Decimal] = {}

    for row in reader:
        if not row:
            continue
        section = row[0]

        if section == "Dividends" and len(row) >= 5 and row[1] == "Data":
            if row[2] == "Total":
                continue
            pay_date = _parse_iso_date(row[3])
            description = row[4]
            amount = _parse_decimal(row[5] if len(row) > 5 else "")
            symbol = _symbol_from_dividend_description(description)
            if not symbol or pay_date is None or amount is None or amount <= 0:
                continue
            gross_rows.append((symbol, pay_date, amount))

        elif section == "Withholding Tax" and len(row) >= 5 and row[1] == "Data":
            if row[2] == "Total":
                continue
            pay_date = _parse_iso_date(row[3])
            description = row[4]
            amount = _parse_decimal(row[5] if len(row) > 5 else "")
            symbol = _symbol_from_dividend_description(description)
            if not symbol or pay_date is None or amount is None or amount >= 0:
                continue
            key = (symbol, pay_date)
            tax_by_key[key] = tax_by_key.get(key, Decimal("0")) + abs(amount)

    dividends: list[IBDividend] = []
    for symbol, pay_date, gross in gross_rows:
        withholding = tax_by_key.get((symbol, pay_date), Decimal("0"))
        dividends.append(
            IBDividend(
                symbol=symbol,
                pay_date=pay_date,
                gross_amount_usd=gross,
                withholding_tax_usd=withholding,
                net_amount_usd=compute_net_amount(gross, withholding),
            )
        )
    return dividends


def iter_statement_lots(statement: IBStatement) -> list[IBTradeLot]:
    return sorted(
        statement.trades,
        key=lambda item: (item.symbol, item.trade_date, item.price_usd, item.quantity),
    )


def existing_lot_keys(session: Session, exchange_type_id: UUID) -> set[str]:
    lots = session.exec(
        select(SecurityLot).where(SecurityLot.asset_type_id == exchange_type_id)
    ).all()
    return {
        lot_selection_key(lot.symbol, lot.purchase_date, lot.position, lot.purchase_price_usd)
        for lot in lots
    }


def build_import_lot_rows(
    statement: IBStatement,
    existing_keys: set[str],
) -> list[ImportLotRow]:
    rows: list[ImportLotRow] = []
    for lot in iter_statement_lots(statement):
        lot_key = lot_selection_key(lot.symbol, lot.trade_date, lot.quantity, lot.price_usd)
        already_exists = lot_key in existing_keys
        rows.append(
            ImportLotRow(
                lot_key=lot_key,
                symbol=lot.symbol,
                name=statement.names.get(lot.symbol, lot.symbol),
                trade_date=lot.trade_date,
                quantity=lot.quantity,
                price_usd=lot.price_usd,
                already_exists=already_exists,
                selected=not already_exists,
            )
        )
    return rows


def _resolve_name(symbol: str, statement: IBStatement, ticker_names: dict[str, str]) -> str:
    if symbol in statement.names:
        return statement.names[symbol]
    if symbol in ticker_names:
        return ticker_names[symbol]
    return symbol


def _close_price_by_symbol(statement: IBStatement) -> dict[str, Decimal]:
    return {position.symbol: position.close_price_usd for position in statement.positions}


def existing_dividend_keys(session: Session, asset_type_id: UUID) -> set[str]:
    dividends = session.exec(
        select(Dividend).where(Dividend.asset_type_id == asset_type_id)
    ).all()
    return {
        dividend.import_key
        for dividend in dividends
        if dividend.import_key
    }


def iter_statement_dividends(statement: IBStatement) -> list[IBDividend]:
    return sorted(
        statement.dividends,
        key=lambda item: (item.pay_date, item.symbol, item.gross_amount_usd),
    )


def build_import_dividend_rows(
    statement: IBStatement,
    existing_keys: set[str],
) -> list[ImportDividendRow]:
    rows: list[ImportDividendRow] = []
    for dividend in iter_statement_dividends(statement):
        dividend_key = dividend_selection_key(
            dividend.symbol,
            dividend.pay_date,
            dividend.gross_amount_usd,
        )
        already_exists = dividend_key in existing_keys
        rows.append(
            ImportDividendRow(
                dividend_key=dividend_key,
                symbol=dividend.symbol,
                name=statement.names.get(dividend.symbol, dividend.symbol),
                pay_date=dividend.pay_date,
                gross_amount_usd=dividend.gross_amount_usd,
                withholding_tax_usd=dividend.withholding_tax_usd,
                net_amount_usd=dividend.net_amount_usd,
                already_exists=already_exists,
                selected=not already_exists,
            )
        )
    return rows


def import_selected_dividends(
    session: Session,
    exchange_type_id: UUID,
    statement: IBStatement,
    dividend_keys: set[str],
) -> int:
    if not dividend_keys:
        return 0

    existing_keys = existing_dividend_keys(session, exchange_type_id)
    to_import = dividend_keys - existing_keys
    if not to_import:
        return 0

    dividends_by_key = {
        dividend_selection_key(
            dividend.symbol,
            dividend.pay_date,
            dividend.gross_amount_usd,
        ): dividend
        for dividend in iter_statement_dividends(statement)
    }

    symbols = sorted(
        {dividends_by_key[key].symbol for key in to_import if key in dividends_by_key}
    )
    if not symbols:
        return 0

    ticker_info = fetch_tickers_info(symbols)
    created = 0
    for key in sorted(to_import):
        dividend = dividends_by_key.get(key)
        if not dividend:
            continue

        name = _resolve_name(
            dividend.symbol,
            statement,
            {sym: info.name for sym, info in ticker_info.items() if info.name},
        )
        get_or_create_symbol_target(session, exchange_type_id, dividend.symbol, name)
        session.add(
            Dividend(
                asset_type_id=exchange_type_id,
                symbol=dividend.symbol,
                pay_date=dividend.pay_date,
                gross_amount_usd=dividend.gross_amount_usd,
                withholding_tax_usd=dividend.withholding_tax_usd,
                net_amount_usd=dividend.net_amount_usd,
                source="ib_statement",
                import_key=key,
            )
        )
        created += 1

    if created:
        session.commit()
    return created


def import_selected_lots(
    session: Session,
    exchange_type_id: UUID,
    statement: IBStatement,
    lot_keys: set[str],
) -> int:
    if not lot_keys:
        return 0

    existing_keys = existing_lot_keys(session, exchange_type_id)
    to_import = lot_keys - existing_keys
    if not to_import:
        return 0

    lots_by_key = {
        lot_selection_key(lot.symbol, lot.trade_date, lot.quantity, lot.price_usd): lot
        for lot in iter_statement_lots(statement)
    }

    symbols = sorted({lots_by_key[key].symbol for key in to_import if key in lots_by_key})
    if not symbols:
        return 0

    ticker_info = fetch_tickers_info(symbols)
    close_prices = _close_price_by_symbol(statement)

    created = 0
    for key in sorted(to_import):
        lot = lots_by_key.get(key)
        if not lot:
            continue

        rate, provisional_fx = resolve_purchase_usd_brl_rate(lot.trade_date)
        if rate <= 0:
            raise ValueError("Could not determine USD/BRL rate.")

        name = _resolve_name(
            lot.symbol,
            statement,
            {sym: info.name for sym, info in ticker_info.items() if info.name},
        )
        get_or_create_symbol_target(session, exchange_type_id, lot.symbol, name)

        market_usd = close_prices.get(lot.symbol, lot.price_usd)
        info = ticker_info.get(lot.symbol)
        if info and info.latest_price > 0:
            market_usd = info.latest_price

        purchase_brl = compute_price_brl(lot.price_usd, rate)
        current_brl = compute_price_brl(market_usd, rate)
        session.add(
            SecurityLot(
                asset_type_id=exchange_type_id,
                symbol=lot.symbol,
                name=name,
                position=lot.quantity,
                purchase_date=lot.trade_date,
                purchase_price_usd=lot.price_usd,
                purchase_price_brl=purchase_brl,
                usd_brl_rate=rate,
                provisional_fx=provisional_fx,
                source="statement",
                current_price_usd=market_usd,
                current_price_brl=current_brl,
            )
        )
        created += 1

    if created:
        session.commit()
    return created
