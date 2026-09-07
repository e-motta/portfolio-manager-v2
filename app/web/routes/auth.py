from urllib.parse import quote

from authlib.integrations.base_client.errors import MismatchingStateError
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.core.db import SessionDep
from app.services.auth import ensure_user_portfolio, find_or_create_user
from app.services.google_drive_auth import (
    OAUTH_PURPOSE_DRIVE,
    complete_drive_connection,
    get_logged_in_user,
)
from app.services.cumbuca_oauth import (
    OAUTH_PURPOSE_CUMBUCA,
    build_authorization_request,
    complete_authorization,
)
from app.services.google_oauth import oauth
from app.web.jsonutil import json_ok

router = APIRouter(prefix="/auth", tags=["auth"])
config_router = APIRouter(prefix="/api/auth", tags=["auth"])


@config_router.get("/config")
def auth_config(request: Request):
    return json_ok(
        {
            "google_configured": bool(settings.GOOGLE_CLIENT_ID),
            "authenticated": bool(request.session.get("user_id")),
            "error": request.query_params.get("error"),
        }
    )


@router.get("/google")
async def google_login(request: Request) -> RedirectResponse:
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google login is not configured")
    request.session.pop("oauth_purpose", None)
    return await oauth.google.authorize_redirect(request, settings.GOOGLE_REDIRECT_URI)


@router.get("/callback")
async def google_callback(request: Request, session: SessionDep) -> RedirectResponse:
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google login is not configured")

    try:
        token = await oauth.google.authorize_access_token(request)
    except MismatchingStateError:
        return RedirectResponse(
            url="/auth/login?error=Login%20session%20expired.%20Please%20try%20again.",
            status_code=303,
        )
    except Exception as exc:
        return RedirectResponse(
            url=f"/auth/login?error={quote(str(exc))}",
            status_code=303,
        )

    oauth_purpose = request.session.pop("oauth_purpose", None)

    if oauth_purpose == OAUTH_PURPOSE_DRIVE:
        user = get_logged_in_user(session, request.session.get("user_id"))
        try:
            complete_drive_connection(session, user, token)
        except HTTPException as exc:
            return RedirectResponse(
                url=f"/backups?error={quote(exc.detail)}",
                status_code=303,
            )
        return RedirectResponse(url="/backups?connected=1", status_code=303)

    userinfo = token.get("userinfo")
    if not userinfo:
        raise HTTPException(status_code=400, detail="Google did not return user info")

    email = userinfo.get("email")
    google_sub = userinfo.get("sub")
    if not email or not google_sub:
        raise HTTPException(status_code=400, detail="Google account missing email")

    user = find_or_create_user(
        session,
        email=email,
        google_sub=google_sub,
        name=userinfo.get("name", ""),
        picture_url=userinfo.get("picture", ""),
    )
    ensure_user_portfolio(session, user)

    request.session["user_id"] = str(user.id)
    return RedirectResponse(url="/", status_code=303)


@router.post("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/auth/login", status_code=303)


@router.get("/cumbuca")
def cumbuca_login(request: Request, session: SessionDep) -> RedirectResponse:
    user = get_logged_in_user(session, request.session.get("user_id"))
    try:
        authorization_url, state, verifier = build_authorization_request(session, user)
    except HTTPException as exc:
        return RedirectResponse(
            url=f"/open-finance?error={quote(exc.detail)}",
            status_code=303,
        )
    request.session["oauth_purpose"] = OAUTH_PURPOSE_CUMBUCA
    request.session["cumbuca_oauth_state"] = state
    request.session["cumbuca_code_verifier"] = verifier
    return RedirectResponse(url=authorization_url, status_code=303)


@router.get("/cumbuca/callback")
def cumbuca_callback(request: Request, session: SessionDep) -> RedirectResponse:
    user = get_logged_in_user(session, request.session.get("user_id"))
    request.session.pop("oauth_purpose", None)

    error = request.query_params.get("error")
    if error:
        description = request.query_params.get("error_description") or error
        return RedirectResponse(
            url=f"/open-finance?error={quote(description)}",
            status_code=303,
        )

    state = request.query_params.get("state")
    code = request.query_params.get("code")
    expected_state = request.session.pop("cumbuca_oauth_state", None)
    code_verifier = request.session.pop("cumbuca_code_verifier", None)

    if not code or not code_verifier or state != expected_state:
        return RedirectResponse(
            url="/open-finance?error=Invalid%20Open%20Finance%20callback",
            status_code=303,
        )

    try:
        complete_authorization(
            session,
            user,
            code=code,
            code_verifier=code_verifier,
        )
    except HTTPException as exc:
        return RedirectResponse(
            url=f"/open-finance?error={quote(exc.detail)}",
            status_code=303,
        )

    return RedirectResponse(url="/open-finance?connected=1", status_code=303)
