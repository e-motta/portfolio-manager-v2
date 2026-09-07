from decimal import Decimal

from fastapi import APIRouter

from app.core.auth import CurrentUserDep
from app.core.config import settings
from app.core.db import SessionDep
from app.services.allocation import allocation_sleeve_value, allocation_target_total
from app.web.helpers import build_dashboard_rows, get_asset_types, sort_asset_types_for_display
from app.web.jsonutil import json_ok

router = APIRouter(tags=["dashboard"])


@router.get("/me")
def current_user_profile(current_user: CurrentUserDep):
    return json_ok(
        {
            "id": current_user.id,
            "email": current_user.email,
            "name": current_user.name,
            "picture_url": current_user.picture_url,
            "google_configured": bool(settings.GOOGLE_CLIENT_ID),
            "drive_connected": bool(current_user.google_refresh_token),
            "cumbuca_connected": bool(current_user.cumbuca_refresh_token),
            "display_timezone": settings.DISPLAY_TIMEZONE,
            "display_timezone_label": settings.DISPLAY_TIMEZONE_LABEL,
        }
    )


@router.get("/dashboard")
def dashboard(session: SessionDep, current_user: CurrentUserDep):
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
    return json_ok(
        {
            "rows": [
                {
                    **row,
                    "asset_type": row["asset_type"],
                }
                for row in rows
            ],
            "total_value": total_value,
            "allocation_sleeve_value": allocation_sleeve,
            "allocation_target_sum": allocation_target_sum,
            "overweight": overweight,
            "underweight": underweight,
            "user": {
                "id": current_user.id,
                "email": current_user.email,
                "name": current_user.name,
                "picture_url": current_user.picture_url,
            },
            "display_timezone": settings.DISPLAY_TIMEZONE,
            "display_timezone_label": settings.DISPLAY_TIMEZONE_LABEL,
        }
    )
