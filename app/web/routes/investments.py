from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, status
from fastapi.responses import RedirectResponse

from app.core.db import SessionDep
from app.models.asset_type import AssetType
from app.models.investment import Investment
from app.web.helpers import (
    build_institution_summaries,
    get_investable_asset_types,
    get_investments,
)
from app.web.jsonutil import json_ok

router = APIRouter(prefix="/portfolio/investments", tags=["investments"])


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


def _get_investable_type(session, asset_type_id: UUID) -> AssetType:
    asset_type = session.get(AssetType, asset_type_id)
    if not asset_type or asset_type.is_exchange_traded:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Investments must be linked to a non-listed asset class.",
        )
    return asset_type


def _investments_context(session) -> dict:
    investments = get_investments(session)
    total_current = sum((item.current_value for item in investments), start=Decimal("0"))
    return {
        "investments": investments,
        "institution_summaries": [
            {
                "institution": row.institution,
                "position_count": row.position_count,
                "total_value": row.total_value,
                "weight": row.weight,
            }
            for row in build_institution_summaries(investments, total_current)
        ],
        "asset_types": get_investable_asset_types(session),
        "total_current": total_current,
        "investment_count": len(investments),
    }


@router.get("")
def list_investments(session: SessionDep):
    return json_ok(_investments_context(session))


@router.post("")
def create_investment(
    session: SessionDep,
    asset_type_id: Annotated[str, Form()],
    institution: Annotated[str, Form()],
    name: Annotated[str, Form()],
    current_value: Annotated[str, Form()],
) -> RedirectResponse:
    _get_investable_type(session, UUID(asset_type_id))

    investment = Investment(
        asset_type_id=UUID(asset_type_id),
        institution=institution.strip(),
        name=name.strip(),
        current_value=_parse_amount(current_value, "current value"),
    )
    session.add(investment)
    session.commit()
    return RedirectResponse(url="/portfolio/investments", status_code=303)


@router.post("/{investment_id}")
def update_investment(
    session: SessionDep,
    investment_id: UUID,
    institution: str = Form(default=""),
    name: str = Form(default=""),
    asset_type_id: str = Form(default=""),
    current_value: str = Form(default=""),
):
    investment = session.get(Investment, investment_id)
    if not investment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if institution:
        investment.institution = institution.strip()
    if name:
        investment.name = name.strip()
    if asset_type_id:
        _get_investable_type(session, UUID(asset_type_id))
        investment.asset_type_id = UUID(asset_type_id)
    if current_value:
        investment.current_value = _parse_amount(current_value, "current value")

    investment.updated_at = datetime.utcnow()
    session.add(investment)
    session.commit()
    session.refresh(investment)
    investment.asset_type = _get_investable_type(session, investment.asset_type_id)

    return json_ok(
        {
            "investment": investment,
            "asset_types": get_investable_asset_types(session),
        }
    )


@router.delete("/{investment_id}")
def delete_investment(
    session: SessionDep,
    investment_id: UUID,
):
    investment = session.get(Investment, investment_id)
    if not investment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    session.delete(investment)
    session.commit()
    return json_ok({})
