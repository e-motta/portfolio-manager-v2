from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.config import Config

from app.core.config import settings
from app.core.db import SessionDep
from app.services.auth import ensure_user_portfolio, find_or_create_user
from app.web.dependencies import TemplatesDep

router = APIRouter(prefix="/auth", tags=["auth"])

config = Config(environ={
    "GOOGLE_CLIENT_ID": settings.GOOGLE_CLIENT_ID,
    "GOOGLE_CLIENT_SECRET": settings.GOOGLE_CLIENT_SECRET,
})
oauth = OAuth(config)
oauth.register(
    name="google",
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


@router.get("/login")
def login_page(request: Request, templates: TemplatesDep):
    if request.session.get("user_id"):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="pages/login.html",
        context={"google_configured": bool(settings.GOOGLE_CLIENT_ID)},
    )


@router.get("/google")
async def google_login(request: Request) -> RedirectResponse:
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google login is not configured")
    redirect_uri = settings.GOOGLE_REDIRECT_URI
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback")
async def google_callback(request: Request, session: SessionDep) -> RedirectResponse:
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google login is not configured")

    token = await oauth.google.authorize_access_token(request)
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
