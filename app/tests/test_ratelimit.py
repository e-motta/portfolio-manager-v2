"""Tests for rate limiting functionality."""

import os
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create a test client without the TESTING exemption."""
    with patch.dict(os.environ, {"TESTING": "0"}, clear=False):
        with TestClient(app) as c:
            yield c


@pytest.fixture
def testing_client():
    """Create a test client with the TESTING exemption enabled."""
    with patch.dict(os.environ, {"TESTING": "1"}, clear=False):
        with TestClient(app) as c:
            yield c


class TestRateLimitingExemptions:
    """Test rate limit exemption logic."""

    def test_localhost_requests_are_exempt(self, client):
        """Requests from localhost should be exempt from rate limiting."""
        for _ in range(15):
            response = client.get("/api/auth/config")
            assert response.status_code == 200

    def test_testing_environment_is_exempt(self, testing_client):
        """Requests in TESTING=1 environment should be exempt."""
        for _ in range(15):
            response = testing_client.get("/api/auth/config")
            assert response.status_code == 200


class TestRateLimitHeaders:
    """Test rate limit response headers."""

    def test_rate_limited_response_includes_retry_after(self):
        """A 429 response should include Retry-After header."""
        from app.core.ratelimit import _rate_limit_exceeded_handler
        from unittest.mock import MagicMock

        exc = MagicMock()
        exc.retry_after = 30
        exc.limit = "10/minute"

        request = MagicMock()
        response = _rate_limit_exceeded_handler(request, exc)

        assert response.status_code == 429
        assert "Retry-After" in response.headers
        assert response.headers["Retry-After"] == "30"


class TestIPExtraction:
    """Test client IP extraction logic."""

    def test_get_client_ip_from_localhost(self):
        """Localhost should return the socket peer IP."""
        from app.core.ratelimit import get_client_ip

        request = MagicMock()
        request.client.host = "127.0.0.1"
        request.headers = {}

        assert get_client_ip(request) == "127.0.0.1"

    def test_get_client_ip_uses_rightmost_xff_from_docker_network(self):
        """RIGHTMOST X-Forwarded-For entry should be used (Caddy's addition)."""
        from app.core.ratelimit import get_client_ip

        request = MagicMock()
        request.client.host = "172.18.0.2"
        request.headers = {"x-forwarded-for": "spoofed-ip, 203.0.113.50"}

        assert get_client_ip(request) == "203.0.113.50"

    def test_get_client_ip_ignores_xff_from_external_ip(self):
        """X-Forwarded-For should NOT be trusted from external IPs."""
        from app.core.ratelimit import get_client_ip

        request = MagicMock()
        request.client.host = "203.0.113.100"
        request.headers = {"x-forwarded-for": "10.0.0.1"}

        assert get_client_ip(request) == "203.0.113.100"

    def test_get_client_ip_takes_rightmost_entry_not_first(self):
        """Rightmost IP in X-Forwarded-For chain should be used, not first."""
        from app.core.ratelimit import get_client_ip

        request = MagicMock()
        request.client.host = "172.18.0.2"
        request.headers = {"x-forwarded-for": "fake1, fake2, 203.0.113.99"}

        assert get_client_ip(request) == "203.0.113.99"


class TestSpoofedHeaderProtection:
    """Test protection against spoofed X-Forwarded-For headers."""

    def test_spoofed_localhost_not_treated_as_localhost(self):
        """Attacker sending X-Forwarded-For: 127.0.0.1 should NOT be treated as localhost."""
        from app.core.ratelimit import get_client_ip, _is_localhost

        request = MagicMock()
        request.client.host = "172.18.0.2"
        request.headers = {"x-forwarded-for": "127.0.0.1, 203.0.113.50"}

        client_ip = get_client_ip(request)
        assert client_ip == "203.0.113.50"
        assert not _is_localhost(client_ip)

    def test_spoofed_localhost_as_only_xff_entry(self):
        """Attacker sending only X-Forwarded-For: 127.0.0.1 should be caught."""
        from app.core.ratelimit import get_client_ip

        request = MagicMock()
        request.client.host = "172.18.0.2"
        request.headers = {"x-forwarded-for": "127.0.0.1"}

        client_ip = get_client_ip(request)
        assert client_ip == "127.0.0.1"

    def test_only_socket_peer_can_be_localhost_exempt(self):
        """Only the actual socket peer (not forwarded IP) earns localhost exemption."""
        from app.core.ratelimit import _is_localhost

        assert _is_localhost("127.0.0.1") is True
        assert _is_localhost("::1") is True

    def test_attacker_cannot_rotate_fake_ips(self):
        """Attacker prepending multiple fake IPs should always get their real IP."""
        from app.core.ratelimit import get_client_ip

        request = MagicMock()
        request.client.host = "172.18.0.2"

        request.headers = {"x-forwarded-for": "10.0.0.1, 192.168.1.1, 172.16.0.1, 203.0.113.77"}
        assert get_client_ip(request) == "203.0.113.77"

        request.headers = {"x-forwarded-for": "fake, 8.8.8.8, 203.0.113.77"}
        assert get_client_ip(request) == "203.0.113.77"


class TestPathBasedLimits:
    """Test path-based rate limit determination."""

    def test_auth_routes_get_strict_limit(self):
        """Routes under /auth/* should get the strict limit."""
        from app.core.ratelimit import _get_limit_for_path, AUTH_LIMIT

        assert _get_limit_for_path("/auth/google") == AUTH_LIMIT
        assert _get_limit_for_path("/auth/callback") == AUTH_LIMIT
        assert _get_limit_for_path("/auth/cumbuca") == AUTH_LIMIT
        assert _get_limit_for_path("/auth/cumbuca/callback") == AUTH_LIMIT
        assert _get_limit_for_path("/auth/logout") == AUTH_LIMIT
        assert _get_limit_for_path("/auth/login") == AUTH_LIMIT

    def test_api_routes_get_moderate_limit(self):
        """Routes under /api/* should get the moderate limit."""
        from app.core.ratelimit import _get_limit_for_path, API_LIMIT

        assert _get_limit_for_path("/api/portfolio/holdings") == API_LIMIT
        assert _get_limit_for_path("/api/finance/expenses") == API_LIMIT
        assert _get_limit_for_path("/api/allocation/classes") == API_LIMIT

    def test_health_check_gets_relaxed_limit(self):
        """Health check endpoint should get the relaxed limit."""
        from app.core.ratelimit import _get_limit_for_path, HEALTH_CHECK_LIMIT

        assert _get_limit_for_path("/api/auth/config") == HEALTH_CHECK_LIMIT

    def test_static_assets_are_exempt(self):
        """Static assets should be exempt (return None)."""
        from app.core.ratelimit import _get_limit_for_path

        assert _get_limit_for_path("/assets/index.css") is None
        assert _get_limit_for_path("/static/image.png") is None
        assert _get_limit_for_path("/favicon.ico") is None

    def test_unknown_paths_are_not_limited(self):
        """Paths not matching any pattern should not be limited."""
        from app.core.ratelimit import _get_limit_for_path

        assert _get_limit_for_path("/") is None
        assert _get_limit_for_path("/portfolio/holdings") is None


class TestDockerNetworkDetection:
    """Test Docker network IP detection."""

    def test_is_docker_network_ip_172_range(self):
        """172.16-31.x.x should be detected as Docker network."""
        from app.core.ratelimit import _is_docker_network_ip

        assert _is_docker_network_ip("172.18.0.2") is True
        assert _is_docker_network_ip("172.16.0.1") is True
        assert _is_docker_network_ip("172.31.255.255") is True

    def test_is_docker_network_ip_192_168_range(self):
        """192.168.x.x should be detected as Docker network."""
        from app.core.ratelimit import _is_docker_network_ip

        assert _is_docker_network_ip("192.168.1.1") is True
        assert _is_docker_network_ip("192.168.0.100") is True

    def test_is_docker_network_ip_10_range(self):
        """10.x.x.x should be detected as Docker network."""
        from app.core.ratelimit import _is_docker_network_ip

        assert _is_docker_network_ip("10.0.0.1") is True
        assert _is_docker_network_ip("10.255.255.255") is True

    def test_is_docker_network_ip_external(self):
        """Public IPs should not be detected as Docker network."""
        from app.core.ratelimit import _is_docker_network_ip

        assert _is_docker_network_ip("203.0.113.50") is False
        assert _is_docker_network_ip("8.8.8.8") is False
        assert _is_docker_network_ip("1.1.1.1") is False

    def test_is_docker_network_ip_invalid(self):
        """Invalid IPs should return False."""
        from app.core.ratelimit import _is_docker_network_ip

        assert _is_docker_network_ip("not-an-ip") is False
        assert _is_docker_network_ip("") is False


class TestHealthCheckLimit:
    """Test the health check endpoint has proper limiting."""

    def test_health_check_has_60_per_minute_limit(self):
        """Health check should be limited to 60/min, not exempt."""
        from app.core.ratelimit import _get_limit_for_path, HEALTH_CHECK_LIMIT

        limit = _get_limit_for_path("/api/auth/config")
        assert limit == HEALTH_CHECK_LIMIT
        assert str(limit) == "60 per 1 minute"

    def test_deploy_health_check_rate_within_limit(self):
        """Deploy health check (12 requests/min) should be well under 60/min limit."""
        from app.core.ratelimit import HEALTH_CHECK_LIMIT

        limit = HEALTH_CHECK_LIMIT
        assert limit.amount >= 12


class TestRetryAfterFormat:
    """Test Retry-After header format consistency."""

    def test_retry_after_is_integer_seconds(self):
        """Retry-After should be an integer number of seconds."""
        from app.core.ratelimit import _rate_limit_exceeded_handler

        exc = MagicMock()
        exc.retry_after = 45
        exc.limit = "10/minute"

        request = MagicMock()
        response = _rate_limit_exceeded_handler(request, exc)

        assert response.headers["Retry-After"] == "45"
        assert response.headers["Retry-After"].isdigit()

    def test_retry_after_handles_string_input(self):
        """Handler should convert string retry_after to integer."""
        from app.core.ratelimit import _rate_limit_exceeded_handler

        exc = MagicMock()
        exc.retry_after = "30"
        exc.limit = "10/minute"

        request = MagicMock()
        response = _rate_limit_exceeded_handler(request, exc)

        assert response.headers["Retry-After"] == "30"


class TestRateLimitIntegration:
    """Integration tests using the real limiter (no mocks)."""

    def test_auth_route_rate_limit_triggers_429_on_11th_request(self):
        """Test that real rate limiting works: 10 allowed, 11th returns 429."""
        from app.core.ratelimit import storage

        class ClientIPOverrideApp:
            """ASGI wrapper that overrides the client IP in scope."""

            def __init__(self, wrapped_app, client_ip: str, client_port: int = 50000):
                self.app = wrapped_app
                self.client = (client_ip, client_port)

            async def __call__(self, scope, receive, send):
                if scope["type"] == "http":
                    scope = dict(scope)
                    scope["client"] = self.client
                await self.app(scope, receive, send)

        test_client_ip = "203.0.113.10"
        storage.reset()

        try:
            with patch.dict(os.environ, {"TESTING": "0"}, clear=False):
                wrapped_app = ClientIPOverrideApp(app, test_client_ip)
                with TestClient(wrapped_app, raise_server_exceptions=False) as client:
                    for i in range(10):
                        response = client.get("/auth/login")
                        assert response.status_code != 429, f"Request {i+1} should not be rate limited"

                    response = client.get("/auth/login")
                    assert response.status_code == 429, "11th request should be rate limited"

                    retry_after = response.headers.get("Retry-After")
                    assert retry_after is not None, "Retry-After header should be present"
                    assert retry_after.isdigit(), f"Retry-After should be digits, got: {retry_after}"
                    assert int(retry_after) >= 1, f"Retry-After should be >= 1, got: {retry_after}"

                    body = response.json()
                    assert body["detail"] == "Rate limit exceeded. Please slow down."
                    assert "retry_after" in body
        finally:
            storage.reset()
