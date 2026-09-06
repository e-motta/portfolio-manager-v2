from datetime import date
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, status
from fastapi.responses import RedirectResponse

from app.core.db import SessionDep
from app.services.snapshots import (
    build_snapshot_dashboard,
    capture_portfolio_snapshot,
    get_snapshot,
    sort_snapshot_asset_classes,
)
from app.web.jsonutil import json_ok

router = APIRouter(prefix="/history", tags=["snapshots"])


def _parse_snapshot_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid snapshot date. Use YYYY-MM-DD.",
        ) from exc


@router.get("")
def snapshots_dashboard(session: SessionDep):
    dashboard = build_snapshot_dashboard(session)
    return json_ok({"today": date.today().isoformat(), **dashboard})


@router.post("")
def create_snapshot(
    session: SessionDep,
    snapshot_date: str = Form(default=""),
) -> RedirectResponse:
    parsed_date = _parse_snapshot_date(snapshot_date or date.today().isoformat())
    capture_portfolio_snapshot(session, parsed_date)
    return RedirectResponse(url="/history", status_code=303)


@router.get("/{snapshot_id}")
def snapshot_detail(
    session: SessionDep,
    snapshot_id: UUID,
):
    snapshot = get_snapshot(session, snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return json_ok(
        {
            "snapshot": snapshot,
            "asset_classes": sort_snapshot_asset_classes(snapshot.asset_classes),
            "investments": sorted(
                snapshot.investments,
                key=lambda row: (row.institution.lower(), row.name.lower()),
            ),
            "holdings": sorted(snapshot.holdings, key=lambda row: row.symbol),
        }
    )


@router.delete("/{snapshot_id}")
def delete_snapshot(
    session: SessionDep,
    snapshot_id: UUID,
):
    snapshot = get_snapshot(session, snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    session.delete(snapshot)
    session.commit()
    return json_ok({})
