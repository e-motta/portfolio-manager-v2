from datetime import date
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.db import SessionDep
from app.services.snapshots import (
    build_snapshot_dashboard,
    capture_portfolio_snapshot,
    get_snapshot,
    sort_snapshot_asset_classes,
)
from app.web.dependencies import TemplatesDep

router = APIRouter(prefix="/history", tags=["snapshots"])


def _parse_snapshot_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid snapshot date. Use YYYY-MM-DD.",
        ) from exc


@router.get("", response_class=HTMLResponse)
def snapshots_dashboard(
    request: Request,
    session: SessionDep,
    templates: TemplatesDep,
) -> HTMLResponse:
    dashboard = build_snapshot_dashboard(session)
    return templates.TemplateResponse(
        request=request,
        name="pages/snapshots.html",
        context={
            "today": date.today().isoformat(),
            **dashboard,
        },
    )


@router.post("", response_class=HTMLResponse)
def create_snapshot(
    session: SessionDep,
    snapshot_date: str = Form(default=""),
) -> RedirectResponse:
    parsed_date = _parse_snapshot_date(snapshot_date or date.today().isoformat())
    capture_portfolio_snapshot(session, parsed_date)
    return RedirectResponse(url="/history", status_code=303)


@router.get("/{snapshot_id}", response_class=HTMLResponse)
def snapshot_detail(
    request: Request,
    session: SessionDep,
    templates: TemplatesDep,
    snapshot_id: UUID,
) -> HTMLResponse:
    snapshot = get_snapshot(session, snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return templates.TemplateResponse(
        request=request,
        name="pages/snapshot_detail.html",
        context={
            "snapshot": snapshot,
            "asset_classes": sort_snapshot_asset_classes(snapshot.asset_classes),
            "investments": sorted(
                snapshot.investments,
                key=lambda row: (row.institution.lower(), row.name.lower()),
            ),
            "holdings": sorted(snapshot.holdings, key=lambda row: row.symbol),
        },
    )


@router.delete("/{snapshot_id}", response_class=HTMLResponse)
def delete_snapshot(
    session: SessionDep,
    snapshot_id: UUID,
) -> HTMLResponse:
    snapshot = get_snapshot(session, snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    session.delete(snapshot)
    session.commit()
    return HTMLResponse("")
