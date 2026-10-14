import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.db import init_db, run_migrations
from app.core.ratelimit import setup_rate_limiting
from app.web.middleware import RequireAuthMiddleware
from app.web.router import router as web_router


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self' https://query1.finance.yahoo.com https://query2.finance.yahoo.com; "
            "frame-ancestors 'none'"
        )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("TESTING") != "1":
        run_migrations()
        from app.core.db import engine
        from sqlmodel import Session

        with Session(engine) as session:
            init_db(session)
    yield


app = FastAPI(title="Portfolio Manager", lifespan=lifespan)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequireAuthMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    same_site="lax",
    https_only=settings.is_production,
)

setup_rate_limiting(app)

app.include_router(web_router)

frontend_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"
app.frontend(
    "/",
    directory=str(frontend_dir),
    fallback="index.html",
    check_dir=False,
)
