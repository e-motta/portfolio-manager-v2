import os

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response


class RequireAuthMiddleware(BaseHTTPMiddleware):
    PUBLIC_PREFIXES = ("/auth/", "/assets/", "/static/")
    PUBLIC_PATHS = {
        "/favicon.ico",
        "/favicon.svg",
        "/api/auth/config",
    }

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if os.getenv("TESTING") == "1":
            return await call_next(request)

        path = request.url.path
        if path in self.PUBLIC_PATHS or any(
            path.startswith(prefix) for prefix in self.PUBLIC_PREFIXES
        ):
            return await call_next(request)

        if not request.session.get("user_id"):
            if path.startswith("/api/"):
                return JSONResponse({"detail": "Not authenticated"}, status_code=401)
            return RedirectResponse(url="/auth/login", status_code=303)

        return await call_next(request)
