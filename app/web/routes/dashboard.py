from decimal import Decimal

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.core.db import SessionDep
from app.web.dependencies import TemplatesDep
from app.services.allocation import allocation_sleeve_value, allocation_target_total
from app.web.helpers import build_dashboard_rows, get_asset_types, sort_asset_types_for_display

router = APIRouter(tags=["dashboard"])


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    session: SessionDep,
    templates: TemplatesDep,
) -> HTMLResponse:
    asset_types = sort_asset_types_for_display(get_asset_types(session))
    rows = build_dashboard_rows(session)
    total_value = sum(
        (row["current_value"] for row in rows),
        start=Decimal("0"),
    )
    allocation_sleeve = allocation_sleeve_value(asset_types)
    allocation_target_sum = allocation_target_total(asset_types)
    overweight = sum(
        1
        for row in rows
        if row["drift"] is not None and row["drift"] > Decimal("0.005")
    )
    underweight = sum(
        1
        for row in rows
        if row["drift"] is not None and row["drift"] < Decimal("-0.005")
    )
    return templates.TemplateResponse(
        request=request,
        name="pages/dashboard.html",
        context={
            "rows": rows,
            "total_value": total_value,
            "allocation_sleeve_value": allocation_sleeve,
            "allocation_target_sum": allocation_target_sum,
            "overweight": overweight,
            "underweight": underweight,
            "portfolio_tab": "dashboard",
        },
    )
