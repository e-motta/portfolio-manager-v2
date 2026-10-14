"""Tests for rate limiting functionality."""

import os
from unittest.mock import patch

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
        """Localhost should return 127.0.0.1."""
        from app.core.ratelimit import get_client_ip
        from unittest.mock import MagicMock

        request = MagicMock()
        request.client.host = "127.0.0.1"
        request.headers = {}

        assert get_client_ip(request) == "127.0.0.1"

    def test_get_client_ip_trusts_xff_from_docker_network(self):
        """X-Forwarded-For should be trusted from Docker internal network."""
        from app.core.ratelimit import get_client_ip
        from unittest.mock import MagicMock

        request = MagicMock()
        request.client.host = "172.18.0.2"
        request.headers = {"x-forwarded-for": "203.0.113.50"}

        assert get_client_ip(request) == "203.0.113.50"

    def test_get_client_ip_ignores_xff_from_external_ip(self):
        """X-Forwarded-For should NOT be trusted from external IPs."""
        from app.core.ratelimit import get_client_ip
        from unittest.mock import MagicMock

        request = MagicMock()
        request.client.host = "203.0.113.100"
        request.headers = {"x-forwarded-for": "10.0.0.1"}

        assert get_client_ip(request) == "203.0.113.100"

    def test_get_client_ip_handles_multiple_xff_values(self):
        """First IP in X-Forwarded-For chain should be used."""
        from app.core.ratelimit import get_client_ip
        from unittest.mock import MagicMock

        request = MagicMock()
        request.client.host = "172.18.0.2"
        request.headers = {"x-forwarded-for": "203.0.113.50, 10.0.0.1, 172.18.0.1"}

        assert get_client_ip(request) == "203.0.113.50"


class TestExemptPathDetection:
    """Test path-based rate limit exemptions."""

    def test_auth_config_exempt_from_internal_network(self):
        """Health check endpoint should be exempt when accessed internally."""
        from app.core.ratelimit import _should_exempt
        from unittest.mock import MagicMock

        request = MagicMock()
        request.url.path = "/api/auth/config"
        request.client.host = "172.18.0.2"
        request.headers = {"x-forwarded-for": "127.0.0.1"}

        with patch.dict(os.environ, {"TESTING": "0"}, clear=False):
            assert _should_exempt(request) is True

    def test_static_assets_exempt(self):
        """Static asset paths should be exempt."""
        from app.core.ratelimit import _should_exempt
        from unittest.mock import MagicMock

        request = MagicMock()
        request.url.path = "/assets/index.css"
        request.client.host = "203.0.113.50"
        request.headers = {}

        with patch.dict(os.environ, {"TESTING": "0"}, clear=False):
            assert _should_exempt(request) is True

    def test_api_routes_not_exempt_from_external(self):
        """Regular API routes should not be exempt from external IPs."""
        from app.core.ratelimit import _should_exempt
        from unittest.mock import MagicMock

        request = MagicMock()
        request.url.path = "/api/portfolio/holdings"
        request.client.host = "203.0.113.50"
        request.headers = {}

        with patch.dict(os.environ, {"TESTING": "0"}, clear=False):
            assert _should_exempt(request) is False


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
