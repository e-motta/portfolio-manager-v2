from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from app.core.db import SessionDep
from app.schemas.allocation import SuggestionMode
from app.services import prices
from app.services.allocation import (
    calculate_security_suggestions,
    calculate_type_suggestions,
    round_decimal,
)
from app.web.dependencies import TemplatesDep
from app.web.helpers import get_asset_types, get_consolidated_securities

router = APIRouter(prefix="/allocation/rebalance", tags=["suggestions"])


@router.get("", response_class=HTMLResponse)
def suggestions_page(
    request: Request,
    templates: TemplatesDep,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="pages/suggestions.html",
        context={"allocation_tab": "rebalance"},
    )


@router.get("/types", response_class=HTMLResponse)
def type_suggestions(
    request: Request,
    session: SessionDep,
    templates: TemplatesDep,
    mode: Annotated[SuggestionMode, Query()] = SuggestionMode.BUY_ONLY,
    new_cash: Annotated[str, Query()] = "0",
) -> HTMLResponse:
    asset_types = get_asset_types(session)
    suggestions = calculate_type_suggestions(
        asset_types,
        mode=mode,
        new_cash=Decimal(new_cash or "0"),
    )
    return templates.TemplateResponse(
        request=request,
        name="partials/type_suggestions.html",
        context={
            "suggestions": suggestions,
            "mode": mode,
            "new_cash": new_cash,
            "level": "types",
        },
    )


@router.get("/securities", response_class=HTMLResponse)
def security_suggestions(
    request: Request,
    session: SessionDep,
    templates: TemplatesDep,
    mode: Annotated[SuggestionMode, Query()] = SuggestionMode.BUY_ONLY,
    new_cash: Annotated[str, Query()] = "0",
) -> HTMLResponse:
    consolidated = get_consolidated_securities(session)
    cash_brl = Decimal(new_cash or "0")
    usd_brl_rate = prices.fetch_usd_brl_rate()
    cash_usd = (
        round_decimal(cash_brl / usd_brl_rate, 2)
        if usd_brl_rate > 0
        else Decimal("0")
    )
    suggestions = calculate_security_suggestions(
        consolidated,
        mode=mode,
        new_cash=cash_usd,
    )
    return templates.TemplateResponse(
        request=request,
        name="partials/security_suggestions.html",
        context={
            "suggestions": suggestions,
            "mode": mode,
            "new_cash": new_cash,
            "level": "securities",
        },
    )
