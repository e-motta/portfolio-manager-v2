from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, UploadFile, status
from fastapi.responses import RedirectResponse

from sqlmodel import select

from app.core.db import SessionDep
from app.models.dividend import Dividend
from app.models.security import SecurityLot
from app.models.symbol_target import SymbolTarget
from app.services.dividends import compute_net_amount
from app.services.prices import (
    compute_price_brl,
    count_provisional_fx_lots,
    fetch_tickers_info,
    get_last_prices_updated_at,
    refresh_provisional_ptax_rates,
    resolve_purchase_usd_brl_rate,
)
from app.services.ib_statement import (
    build_import_dividend_rows,
    build_import_lot_rows,
    existing_dividend_keys,
    existing_lot_keys,
    import_selected_dividends,
    import_selected_lots,
    parse_ib_statement,
    pop_stashed_import,
    stash_import,
)
from app.web.helpers import (
    get_consolidated_securities,
    get_exchange_traded_type,
    get_or_create_symbol_target,
    get_securities_performance,
    get_security_lots,
    get_symbol_targets,
)
from app.web.jsonutil import json_ok

router = APIRouter(prefix="/portfolio/holdings", tags=["securities"])


def _parse_target_pct(value: str) -> Decimal:
    normalized = value.strip().replace(",", ".")
    try:
        pct = Decimal(normalized)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid target weight.",
        ) from exc
    if pct < 0 or pct > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Target weight must be between 0% and 100%.",
        )
    return pct / Decimal("100")


def _parse_purchase_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid trade date. Use YYYY-MM-DD.",
        ) from exc


def _target_weight_context(session) -> dict:
    total = sum((t.target_pct for t in get_symbol_targets(session)), start=Decimal("0"))
    display_pct = (total * Decimal("100")).quantize(Decimal("0.1"))
    return {
        "target_total": total,
        "target_total_display": display_pct,
        "target_total_balanced": display_pct == Decimal("100.0"),
    }


def _securities_context(session, exchange_type):
    lots = get_security_lots(session)
    performance = get_securities_performance(session)
    consolidated = performance["consolidated"]
    dividends = performance["dividends"]
    return_totals = performance["return_totals"]
    target_context = _target_weight_context(session)
    return {
        "consolidated": consolidated,
        "security_returns": performance["security_returns"],
        "return_totals": return_totals,
        "lots": lots,
        "exchange_type": exchange_type,
        "today": date.today().isoformat(),
        "total_brl": return_totals.current_value_brl,
        "total_cost_usd": return_totals.cost_basis_usd,
        "total_cost_brl": return_totals.cost_basis_brl,
        "total_current_usd": return_totals.current_value_usd,
        "total_pl_usd": return_totals.total_return_usd,
        "total_pl_brl": return_totals.total_return_brl,
        "total_pl_pct_usd": return_totals.total_return_pct_usd,
        "total_pl_pct_brl": return_totals.total_return_pct_brl,
        "unrealized_pl_usd": return_totals.unrealized_pl_usd,
        "unrealized_pl_brl": return_totals.unrealized_pl_brl,
        "lot_count": len(lots),
        "symbol_count": len(consolidated),
        "dividends": dividends,
        "dividend_count": len(dividends),
        "dividend_gross_usd": return_totals.dividend_gross_usd,
        "dividend_withholding_usd": return_totals.dividend_withholding_usd,
        "dividend_net_usd": return_totals.dividend_net_usd,
        "last_prices_at": get_last_prices_updated_at(session),
        "provisional_fx_count": count_provisional_fx_lots(session),
        **target_context,
    }


@router.get("")
def list_securities(session: SessionDep):
    exchange_type = get_exchange_traded_type(session)
    return json_ok(_securities_context(session, exchange_type))


@router.get("/partials/content")
def securities_content_partial(session: SessionDep):
    exchange_type = get_exchange_traded_type(session)
    return json_ok(_securities_context(session, exchange_type))


@router.get("/partials/target-weight-total")
def target_weight_total_partial(session: SessionDep):
    return json_ok(_target_weight_context(session))


@router.post("/ptax/refresh")
def refresh_ptax_rates(session: SessionDep) -> RedirectResponse:
    refresh_provisional_ptax_rates(session)
    return RedirectResponse(url="/portfolio/holdings", status_code=303)


@router.post("/import/preview")
def preview_statement_import(
    session: SessionDep,
    statement: UploadFile,
):
    exchange_type = get_exchange_traded_type(session)
    if not exchange_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Listed securities asset class not configured.",
        )

    raw = statement.file.read()
    if not raw:
        return json_ok({"error": "The uploaded file is empty."})

    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Statement file must be UTF-8 text.",
        ) from exc

    try:
        parsed = parse_ib_statement(content)
    except (ValueError, IndexError) as exc:
        return json_ok({"error": f"Could not parse statement: {exc}"})

    existing = existing_lot_keys(session, exchange_type.id)
    rows = build_import_lot_rows(parsed, existing)
    import_token = stash_import(parsed)
    new_count = sum(1 for row in rows if not row.already_exists)
    existing_count = sum(1 for row in rows if row.already_exists)

    return json_ok(
        {
            "rows": rows,
            "import_token": import_token,
            "period_end": parsed.period_end,
            "has_trades": bool(parsed.trades),
            "has_positions": bool(parsed.positions),
            "new_count": new_count,
            "existing_count": existing_count,
        }
    )


@router.post("/import/confirm")
def confirm_statement_import(
    session: SessionDep,
    import_token: Annotated[str, Form()],
    lots: Annotated[list[str] | None, Form()] = None,
) -> RedirectResponse:
    exchange_type = get_exchange_traded_type(session)
    if not exchange_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Listed securities asset class not configured.",
        )

    parsed = pop_stashed_import(import_token)
    if not parsed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Import session expired. Upload the statement again.",
        )

    selected = {lot_key.strip() for lot_key in (lots or []) if lot_key.strip()}
    if not selected:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Select at least one tax lot to add.",
        )

    existing = existing_lot_keys(session, exchange_type.id)
    new_lots = selected - existing
    if not new_lots:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Selected tax lots are already in your portfolio.",
        )

    try:
        created = import_selected_lots(session, exchange_type.id, parsed, new_lots)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    if created == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No matching tax lots found in the statement.",
        )

    return RedirectResponse(url="/portfolio/holdings", status_code=303)


@router.post("/dividends/import/preview")
def preview_dividend_import(
    session: SessionDep,
    statement: UploadFile,
):
    exchange_type = get_exchange_traded_type(session)
    if not exchange_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Listed securities asset class not configured.",
        )

    raw = statement.file.read()
    if not raw:
        return json_ok({"error": "The uploaded file is empty."})

    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Statement file must be UTF-8 text.",
        ) from exc

    try:
        parsed = parse_ib_statement(content)
    except (ValueError, IndexError) as exc:
        return json_ok({"error": f"Could not parse statement: {exc}"})

    existing = existing_dividend_keys(session, exchange_type.id)
    rows = build_import_dividend_rows(parsed, existing)
    import_token = stash_import(parsed)
    new_count = sum(1 for row in rows if not row.already_exists)
    existing_count = sum(1 for row in rows if row.already_exists)

    return json_ok(
        {
            "rows": rows,
            "import_token": import_token,
            "period_end": parsed.period_end,
            "has_dividends": bool(parsed.dividends),
            "new_count": new_count,
            "existing_count": existing_count,
        }
    )


@router.post("/dividends/import/confirm")
def confirm_dividend_import(
    session: SessionDep,
    import_token: Annotated[str, Form()],
    dividends: Annotated[list[str] | None, Form()] = None,
) -> RedirectResponse:
    exchange_type = get_exchange_traded_type(session)
    if not exchange_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Listed securities asset class not configured.",
        )

    parsed = pop_stashed_import(import_token)
    if not parsed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Import session expired. Upload the statement again.",
        )

    selected = {dividend_key.strip() for dividend_key in (dividends or []) if dividend_key.strip()}
    if not selected:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Select at least one dividend to add.",
        )

    existing = existing_dividend_keys(session, exchange_type.id)
    new_dividends = selected - existing
    if not new_dividends:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Selected dividends are already in your portfolio.",
        )

    created = import_selected_dividends(session, exchange_type.id, parsed, new_dividends)
    if created == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No matching dividends found in the statement.",
        )

    return RedirectResponse(url="/portfolio/holdings", status_code=303)


def _parse_amount(value: str, field_name: str) -> Decimal:
    normalized = value.strip().replace(",", ".")
    try:
        amount = Decimal(normalized)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid {field_name}.",
        ) from exc
    if amount < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} cannot be negative.",
        )
    return amount


@router.post("/dividends")
def create_dividend(
    session: SessionDep,
    symbol: Annotated[str, Form()],
    pay_date: Annotated[str, Form()],
    gross_amount_usd: Annotated[str, Form()],
    withholding_tax_usd: Annotated[str, Form()] = "0",
) -> RedirectResponse:
    exchange_type = get_exchange_traded_type(session)
    if not exchange_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Listed securities asset class not configured.",
        )

    symbol = symbol.strip().upper()
    gross = _parse_amount(gross_amount_usd, "gross amount")
    withholding = _parse_amount(withholding_tax_usd, "withholding tax")
    if gross <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Gross amount must be greater than zero.",
        )
    if withholding > gross:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Withholding tax cannot exceed gross amount.",
        )

    tickers = fetch_tickers_info([symbol])
    info = tickers.get(symbol)
    name = info.name if info else symbol
    get_or_create_symbol_target(session, exchange_type.id, symbol, name)

    dividend = Dividend(
        asset_type_id=exchange_type.id,
        symbol=symbol,
        pay_date=_parse_purchase_date(pay_date),
        gross_amount_usd=gross,
        withholding_tax_usd=withholding,
        net_amount_usd=compute_net_amount(gross, withholding),
        source="manual",
    )
    session.add(dividend)
    session.commit()
    return RedirectResponse(url="/portfolio/holdings", status_code=303)


@router.post("/dividends/{dividend_id}")
def update_dividend(
    session: SessionDep,
    dividend_id: UUID,
    pay_date: str = Form(default=""),
    gross_amount_usd: str = Form(default=""),
    withholding_tax_usd: str = Form(default=""),
):
    dividend = session.get(Dividend, dividend_id)
    if not dividend:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if pay_date:
        dividend.pay_date = _parse_purchase_date(pay_date)
    if gross_amount_usd:
        dividend.gross_amount_usd = _parse_amount(gross_amount_usd, "gross amount")
    if withholding_tax_usd:
        dividend.withholding_tax_usd = _parse_amount(withholding_tax_usd, "withholding tax")

    if dividend.withholding_tax_usd > dividend.gross_amount_usd:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Withholding tax cannot exceed gross amount.",
        )

    dividend.net_amount_usd = compute_net_amount(
        dividend.gross_amount_usd,
        dividend.withholding_tax_usd,
    )
    dividend.updated_at = datetime.utcnow()
    session.add(dividend)
    session.commit()
    session.refresh(dividend)

    return json_ok({"dividend": dividend})


@router.delete("/dividends/{dividend_id}")
def delete_dividend(
    session: SessionDep,
    dividend_id: UUID,
):
    dividend = session.get(Dividend, dividend_id)
    if not dividend:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    session.delete(dividend)
    session.commit()
    return json_ok({})


@router.post("/lots")
def create_lot(
    session: SessionDep,
    symbol: Annotated[str, Form()],
    purchase_date: Annotated[str, Form()],
    position: Annotated[str, Form()],
    purchase_price_usd: Annotated[str, Form()],
    usd_brl_rate: Annotated[str, Form()] = "",
) -> RedirectResponse:
    exchange_type = get_exchange_traded_type(session)
    if not exchange_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Listed securities asset class not configured.",
        )

    symbol = symbol.strip().upper()
    pos = Decimal(position)
    price_usd = Decimal(purchase_price_usd)
    if pos <= 0 or price_usd <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Quantity and execution price must be greater than zero.",
        )

    tickers = fetch_tickers_info([symbol])
    info = tickers.get(symbol)
    name = info.name if info else symbol

    provisional_fx = False
    if usd_brl_rate:
        rate = Decimal(usd_brl_rate)
    else:
        rate, provisional_fx = resolve_purchase_usd_brl_rate(
            _parse_purchase_date(purchase_date)
        )

    if rate <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not determine USD/BRL rate.",
        )

    purchase_brl = compute_price_brl(price_usd, rate)
    market_usd = info.latest_price if info and info.latest_price > 0 else price_usd
    current_brl = compute_price_brl(market_usd, rate)

    get_or_create_symbol_target(session, exchange_type.id, symbol, name)

    lot = SecurityLot(
        asset_type_id=exchange_type.id,
        symbol=symbol,
        name=name,
        position=pos,
        purchase_date=_parse_purchase_date(purchase_date),
        purchase_price_usd=price_usd,
        purchase_price_brl=purchase_brl,
        usd_brl_rate=rate,
        provisional_fx=provisional_fx,
        source="manual",
        current_price_usd=market_usd,
        current_price_brl=current_brl,
    )
    session.add(lot)
    session.commit()
    session.refresh(lot)

    return RedirectResponse(url="/portfolio/holdings", status_code=303)


@router.post("/lots/{lot_id}")
def update_lot(
    session: SessionDep,
    lot_id: UUID,
    purchase_date: str = Form(default=""),
    position: str = Form(default=""),
    purchase_price_usd: str = Form(default=""),
    usd_brl_rate: str = Form(default=""),
):
    lot = session.get(SecurityLot, lot_id)
    if not lot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if purchase_date:
        lot.purchase_date = _parse_purchase_date(purchase_date)
    if position:
        lot.position = Decimal(position)
    if purchase_price_usd:
        lot.purchase_price_usd = Decimal(purchase_price_usd)
    if usd_brl_rate:
        lot.usd_brl_rate = Decimal(usd_brl_rate)
        lot.provisional_fx = False

    lot.purchase_price_brl = compute_price_brl(lot.purchase_price_usd, lot.usd_brl_rate)
    session.add(lot)
    session.commit()
    session.refresh(lot)

    return json_ok({"lot": lot})


@router.delete("/lots/{lot_id}")
def delete_lot(
    session: SessionDep,
    lot_id: UUID,
):
    lot = session.get(SecurityLot, lot_id)
    if not lot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    session.delete(lot)
    session.commit()
    return json_ok({})


@router.post("/symbols/{symbol}")
def update_symbol_target(
    session: SessionDep,
    symbol: str,
    target_pct: Annotated[str, Form()],
):
    exchange_type = get_exchange_traded_type(session)
    if not exchange_type:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    symbol = symbol.strip().upper()
    target = session.exec(
        select(SymbolTarget).where(
            SymbolTarget.asset_type_id == exchange_type.id,
            SymbolTarget.symbol == symbol,
        )
    ).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    target.target_pct = _parse_target_pct(target_pct)
    session.add(target)
    session.commit()
    session.refresh(target)

    consolidated = next(
        (item for item in get_consolidated_securities(session) if item.symbol == symbol),
        None,
    )
    if not consolidated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    target_context = _target_weight_context(session)
    return json_ok({"item": consolidated, **target_context})
