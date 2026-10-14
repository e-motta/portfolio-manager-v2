"""Rate limiting using slowapi/limits.

Applies different limits to different route prefixes:
- /auth/*: Strict (10 requests/minute) - prevents OAuth brute-force
- /api/auth/config: Relaxed (60 requests/minute) - health check endpoint
- /api/*: Moderate (120 requests/minute) - normal API usage
- Static assets: Unlimited

The client IP is extracted from the RIGHTMOST X-Forwarded-For entry,
which is the one Caddy appends (the actual peer IP). We never trust
client-supplied forwarded values as localhost.
"""

import ipaddress
import os
from typing import Callable

from fastapi import FastAPI, Request
from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

DOCKER_NETWORKS = [
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("10.0.0.0/8"),
]

LOCALHOST_ADDRESSES = frozenset({"127.0.0.1", "::1"})

AUTH_LIMIT = parse("10/minute")
API_LIMIT = parse("120/minute")
HEALTH_CHECK_LIMIT = parse("60/minute")

STATIC_PREFIXES = ("/assets/", "/static/", "/favicon.ico")

storage = MemoryStorage()
rate_limiter = FixedWindowRateLimiter(storage)


def _is_docker_network_ip(ip: str) -> bool:
    """Check if IP is from Docker internal network (Caddy container)."""
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in network for network in DOCKER_NETWORKS)
    except ValueError:
        return False


def _is_localhost(ip: str) -> bool:
    """Check if IP is localhost."""
    return ip in LOCALHOST_ADDRESSES


def get_client_ip(request: Request) -> str:
    """Extract client IP, using the RIGHTMOST X-Forwarded-For entry.

    Caddy appends the real peer IP to the END of X-Forwarded-For.
    An attacker can prepend fake IPs, but the rightmost entry is
    what Caddy added from the actual TCP connection.

    We only trust X-Forwarded-For when the direct connection comes
    from Docker internal network (where Caddy runs).

    IMPORTANT: We never treat a forwarded IP as localhost.
    Only the actual socket peer can earn localhost exemption.
    """
    client_host = request.client.host if request.client else "127.0.0.1"

    if _is_docker_network_ip(client_host):
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            entries = [e.strip() for e in forwarded_for.split(",") if e.strip()]
            if entries:
                return entries[-1]

    return client_host


def _is_static_asset(path: str) -> bool:
    """Check if path is a static asset that should be exempt."""
    return path.startswith(STATIC_PREFIXES)


def _get_limit_for_path(path: str):
    """Determine the rate limit based on request path.

    Returns None for exempt paths (static assets).
    """
    if _is_static_asset(path):
        return None

    if path == "/api/auth/config":
        return HEALTH_CHECK_LIMIT

    if path.startswith("/auth/"):
        return AUTH_LIMIT

    if path.startswith("/api/"):
        return API_LIMIT

    return None


def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Custom handler for rate limit exceeded errors."""
    retry_after = getattr(exc, "retry_after", 60)
    if isinstance(retry_after, str):
        try:
            retry_after = int(retry_after)
        except (TypeError, ValueError):
            retry_after = 60

    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Please slow down.",
            "retry_after": retry_after,
        },
        headers={
            "Retry-After": str(retry_after),
            "X-RateLimit-Limit": str(getattr(exc, "limit", "")),
        },
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware that applies rate limits based on path prefix.

    This ensures ALL routes are covered automatically, not just those
    with explicit decorators. New routes get rate limited by default.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if os.getenv("TESTING") == "1":
            return await call_next(request)

        client_host = request.client.host if request.client else ""
        if _is_localhost(client_host):
            return await call_next(request)

        path = request.url.path
        limit = _get_limit_for_path(path)

        if limit is None:
            return await call_next(request)

        client_ip = get_client_ip(request)

        if not rate_limiter.hit(limit, client_ip):
            window_stats = rate_limiter.get_window_stats(limit, client_ip)
            retry_after = max(1, int(window_stats.reset_time - window_stats.elapsed_time))

            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Please slow down.",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                },
            )

        return await call_next(request)


def setup_rate_limiting(app: FastAPI) -> None:
    """Configure rate limiting on the FastAPI app."""
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RateLimitMiddleware)
