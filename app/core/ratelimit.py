"""Rate limiting using slowapi.

Applies different limits to different route prefixes:
- /auth/*: Strict (10 requests/minute) - prevents OAuth brute-force
- /api/*: Moderate (120 requests/minute) - normal API usage
- Static assets: Unlimited

The client IP is extracted from X-Forwarded-For, but only trusted when the
request comes from Caddy (Docker internal network: 172.x, 192.168.x, 10.x).
Requests from localhost are exempted to allow health checks.

Usage:
- Auth routes: Apply @auth_rate_limit decorator to each endpoint
- API routes: Apply @api_rate_limit decorator to each endpoint
- Or use the shared limits for groups of endpoints
"""

import ipaddress
import os

from fastapi import FastAPI, Request
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.responses import JSONResponse

DOCKER_NETWORKS = [
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("10.0.0.0/8"),
]

LOCALHOST_ADDRESSES = {"127.0.0.1", "::1", "localhost"}

AUTH_RATE_LIMIT = "10/minute"
API_RATE_LIMIT = "120/minute"

EXEMPT_PATHS = frozenset({
    "/api/auth/config",
})


def _is_docker_network_ip(ip: str) -> bool:
    """Check if IP is from Docker internal network (Caddy container)."""
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in network for network in DOCKER_NETWORKS)
    except ValueError:
        return False


def _is_localhost(ip: str) -> bool:
    """Check if IP is localhost (for health checks)."""
    return ip in LOCALHOST_ADDRESSES


def get_client_ip(request: Request) -> str:
    """Extract client IP, trusting X-Forwarded-For only from Caddy.

    The proxy chain in production is:
    Client -> Caddy (172.x) -> App (172.x)

    We trust X-Forwarded-For only when the direct connection comes from
    Docker internal network (Caddy container).
    """
    client_host = request.client.host if request.client else "127.0.0.1"

    if _is_localhost(client_host):
        return "127.0.0.1"

    if _is_docker_network_ip(client_host):
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            real_ip = forwarded_for.split(",")[0].strip()
            if real_ip:
                return real_ip

    return client_host


def _get_route_key(request: Request) -> str:
    """Generate rate limit key based on client IP."""
    return get_client_ip(request)


def _should_exempt(request: Request) -> bool:
    """Check if request should be exempt from rate limiting."""
    if os.getenv("TESTING") == "1":
        return True

    path = request.url.path
    client_ip = get_client_ip(request)

    if _is_localhost(client_ip):
        return True

    if path in EXEMPT_PATHS:
        direct_host = request.client.host if request.client else ""
        if _is_docker_network_ip(direct_host) or _is_localhost(direct_host):
            return True

    if path.startswith("/assets/") or path.startswith("/static/"):
        return True

    return False


limiter = Limiter(
    key_func=_get_route_key,
    default_limits=[],
    headers_enabled=True,
    retry_after="http-date",
)


def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Custom handler for rate limit exceeded errors."""
    retry_after = getattr(exc, "retry_after", 60)
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Please slow down.",
            "retry_after": retry_after,
        },
        headers={
            "Retry-After": str(retry_after),
            "X-RateLimit-Limit": str(exc.limit) if hasattr(exc, "limit") else "",
        },
    )


auth_rate_limit = limiter.limit(AUTH_RATE_LIMIT, exempt_when=_should_exempt)
api_rate_limit = limiter.limit(API_RATE_LIMIT, exempt_when=_should_exempt)


def setup_rate_limiting(app: FastAPI) -> None:
    """Configure rate limiting on the FastAPI app."""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
