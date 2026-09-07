from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.db import SessionDep
from app.schemas.allocation import SuggestionMode
from app.services.allocation import (
    calculate_security_suggestions,
    calculate_type_suggestions,
)
from app.services.prices import fetch_usd_brl_rate
from app.web.helpers import get_asset_types, get_consolidated_securities
from app.web.jsonutil import json_ok

router = APIRouter(prefix="/allocation/rebalance", tags=["suggestions"])


@router.get("")
def suggestions_meta():
    return json_ok({"usd_brl_rate": fetch_usd_brl_rate()})


@router.get("/types")
def type_suggestions(
    session: SessionDep,
    mode: Annotated[SuggestionMode, Query()] = SuggestionMode.BUY_ONLY,
    new_cash: Annotated[str, Query()] = "0",
):
    asset_types = get_asset_types(session)
    suggestions = calculate_type_suggestions(
        asset_types,
        mode=mode,
        new_cash=Decimal(new_cash or "0"),
    )
    return json_ok(
        {
            "suggestions": suggestions,
            "mode": mode,
            "new_cash": new_cash,
            "level": "types",
            "currency": "BRL",
        }
    )


@router.get("/securities")
def security_suggestions(
    session: SessionDep,
    mode: Annotated[SuggestionMode, Query()] = SuggestionMode.BUY_ONLY,
    new_cash: Annotated[str, Query()] = "0",
):
    consolidated = get_consolidated_securities(session)
    suggestions = calculate_security_suggestions(
        consolidated,
        mode=mode,
        new_cash=Decimal(new_cash or "0"),
    )
    return json_ok(
        {
            "suggestions": suggestions,
            "mode": mode,
            "new_cash": new_cash,
            "level": "securities",
            "currency": "USD",
        }
    )
