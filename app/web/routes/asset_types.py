import re
from decimal import Decimal, InvalidOperation
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, status
from fastapi.responses import RedirectResponse

from app.core.db import SessionDep
from app.models.asset_type import AssetType
from app.services.allocation import has_type_target, validate_type_targets
from app.web.helpers import (
    enrich_asset_type,
    get_asset_type_asset_count,
    get_asset_types,
    get_portfolio,
    sort_asset_types_for_display,
)
from app.web.jsonutil import json_ok

router = APIRouter(prefix="/allocation/classes", tags=["asset-types"])


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "type"


def _parse_optional_target_pct(value: str) -> Decimal | None:
    normalized = value.strip().replace(",", ".")
    if not normalized:
        return None
    try:
        pct = Decimal(normalized)
    except InvalidOperation as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Target weight must be a number between 0% and 100%.",
        ) from exc
    if pct < 0 or pct > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Target weight must be between 0% and 100%.",
        )
    return pct / Decimal("100")


def _target_total(asset_types: list[AssetType]) -> Decimal:
    return sum(
        (asset_type.target_pct for asset_type in asset_types if has_type_target(asset_type)),
        start=Decimal("0"),
    )


def _asset_type_payload(session, asset_type: AssetType) -> dict:
    enrich_asset_type(session, asset_type)
    return {
        "asset_type": asset_type,
        "asset_count": get_asset_type_asset_count(asset_type),
        "has_target": has_type_target(asset_type),
    }


@router.get("")
def list_asset_types(session: SessionDep):
    asset_types = sort_asset_types_for_display(get_asset_types(session))
    target_total = _target_total(asset_types)
    weighted_count = sum(1 for asset_type in asset_types if has_type_target(asset_type))
    return json_ok(
        {
            "asset_types": [
                {
                    "asset_type": asset_type,
                    "asset_count": get_asset_type_asset_count(asset_type),
                    "has_target": has_type_target(asset_type),
                }
                for asset_type in asset_types
            ],
            "target_total": target_total,
            "weighted_count": weighted_count,
        }
    )


@router.post("")
def create_asset_type(
    session: SessionDep,
    name: Annotated[str, Form()],
    target_pct: Annotated[str, Form()] = "",
) -> RedirectResponse:
    portfolio = get_portfolio(session)
    target = _parse_optional_target_pct(target_pct)

    asset_types = get_asset_types(session)
    if target is not None:
        try:
            validate_type_targets(asset_types, new_target=target)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            )

    asset_type = AssetType(
        portfolio_id=portfolio.id,
        name=name.strip(),
        slug=_slugify(name),
        target_pct=target,
        current_value=Decimal("0"),
        is_exchange_traded=False,
    )
    session.add(asset_type)
    session.commit()
    return RedirectResponse(url="/allocation/classes", status_code=303)


@router.post("/{asset_type_id}")
def update_asset_type(
    session: SessionDep,
    asset_type_id: UUID,
    name: str = Form(default=""),
    target_pct: str = Form(default=""),
):
    asset_type = session.get(AssetType, asset_type_id)
    if not asset_type:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if name:
        asset_type.name = name.strip()
        asset_type.slug = _slugify(name)

    target = _parse_optional_target_pct(target_pct)
    if target is not None:
        asset_types = get_asset_types(session)
        try:
            validate_type_targets(
                asset_types,
                exclude_id=asset_type.id,
                new_target=target,
            )
        except ValueError as ext:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(ext)
            )
    asset_type.target_pct = target

    session.add(asset_type)
    session.commit()
    session.refresh(asset_type)

    return json_ok(_asset_type_payload(session, asset_type))


@router.delete("/{asset_type_id}")
def delete_asset_type(
    session: SessionDep,
    asset_type_id: UUID,
):
    asset_type = session.get(AssetType, asset_type_id)
    if not asset_type:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if asset_type.is_exchange_traded:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot delete the listed securities asset class.",
        )
    session.delete(asset_type)
    session.commit()
    return json_ok({})
