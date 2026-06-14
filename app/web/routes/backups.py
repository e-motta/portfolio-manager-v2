from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.auth import CurrentUserDep
from app.core.config import settings
from app.core.db import SessionDep
from app.services.backup import export_portfolio_json, restore_portfolio_json
from app.services.google_drive import (
    backup_filename,
    delete_backup,
    download_backup,
    drive_call,
    ensure_backup_folder,
    list_backups,
    upload_backup,
)
from app.services.google_oauth import DRIVE_SCOPES, oauth, refresh_access_token
from app.services.google_drive_auth import OAUTH_PURPOSE_DRIVE
from app.web.dependencies import TemplatesDep

router = APIRouter(prefix="/backups", tags=["backups"])


def _drive_configured() -> bool:
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)


def _user_has_drive(user) -> bool:
    return bool(user.google_refresh_token)


def _get_access_token(user) -> str:
    if not user.google_refresh_token:
        raise HTTPException(status_code=400, detail="Google Drive is not connected.")
    return refresh_access_token(user.google_refresh_token)


def _load_drive_backups(user):
    access_token = _get_access_token(user)
    folder_id = drive_call(
        ensure_backup_folder, access_token, user.google_drive_folder_id
    )
    return access_token, folder_id, drive_call(list_backups, access_token, folder_id)


@router.get("", response_class=HTMLResponse)
def backups_page(
    request: Request,
    session: SessionDep,
    templates: TemplatesDep,
    user: CurrentUserDep,
) -> HTMLResponse:
    drive_connected = _user_has_drive(user)
    backups = []
    drive_error = None

    if drive_connected:
        try:
            _, _, backups = _load_drive_backups(user)
        except HTTPException as exc:
            drive_error = exc.detail

    return templates.TemplateResponse(
        request=request,
        name="pages/backups.html",
        context={
            "google_configured": _drive_configured(),
            "drive_connected": drive_connected,
            "backups": backups,
            "drive_error": drive_error,
            "saved": request.query_params.get("saved") == "1",
            "restored": request.query_params.get("restored") == "1",
            "deleted": request.query_params.get("deleted") == "1",
            "connected": request.query_params.get("connected") == "1",
            "error_message": request.query_params.get("error"),
            "sync_tab": "backups",
        },
    )


@router.get("/google/connect")
async def connect_google_drive(request: Request) -> RedirectResponse:
    if not _drive_configured():
        raise HTTPException(status_code=503, detail="Google Drive is not configured.")
    request.session["oauth_purpose"] = OAUTH_PURPOSE_DRIVE
    return await oauth.google.authorize_redirect(
        request,
        settings.GOOGLE_REDIRECT_URI,
        scope=DRIVE_SCOPES,
        access_type="offline",
        prompt="consent",
    )


@router.post("/create")
def create_backup(
    session: SessionDep,
    user: CurrentUserDep,
) -> RedirectResponse:
    if not _user_has_drive(user):
        raise HTTPException(status_code=400, detail="Connect Google Drive first.")

    content = export_portfolio_json(session)
    access_token = _get_access_token(user)
    folder_id = drive_call(
        ensure_backup_folder, access_token, user.google_drive_folder_id
    )
    if folder_id != user.google_drive_folder_id:
        user.google_drive_folder_id = folder_id
        session.add(user)
        session.commit()

    drive_call(
        upload_backup,
        access_token,
        folder_id,
        backup_filename(),
        content,
    )
    return RedirectResponse(url="/backups?saved=1", status_code=303)


@router.post("/{file_id}/restore")
def restore_backup(
    file_id: str,
    session: SessionDep,
    user: CurrentUserDep,
) -> RedirectResponse:
    if not _user_has_drive(user):
        raise HTTPException(status_code=400, detail="Connect Google Drive first.")

    access_token = _get_access_token(user)
    raw = drive_call(download_backup, access_token, file_id)
    try:
        restore_portfolio_json(session, raw)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RedirectResponse(url="/backups?restored=1", status_code=303)


@router.post("/{file_id}/delete")
def delete_backup_route(
    file_id: str,
    session: SessionDep,
    user: CurrentUserDep,
) -> RedirectResponse:
    if not _user_has_drive(user):
        raise HTTPException(status_code=400, detail="Connect Google Drive first.")

    access_token = _get_access_token(user)
    folder_id = drive_call(
        ensure_backup_folder, access_token, user.google_drive_folder_id
    )
    if folder_id != user.google_drive_folder_id:
        user.google_drive_folder_id = folder_id
        session.add(user)
        session.commit()

    drive_call(delete_backup, access_token, folder_id, file_id)
    return RedirectResponse(url="/backups?deleted=1", status_code=303)
