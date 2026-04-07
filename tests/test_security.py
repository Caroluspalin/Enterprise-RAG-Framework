"""Tests for security hardening (Phase 12, Step 4).

Verifies:
  - HTTP security headers are present on every response
  - Login rate limiting blocks after 5 attempts
  - Global exception handler does not leak tracebacks
  - HSTS is environment-dependent
"""

from unittest.mock import patch

from limiter import rate_limiter


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------

class TestSecurityHeaders:
    """Every response should include the standard security headers."""

    def test_health_has_security_headers(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert "default-src" in resp.headers["Content-Security-Policy"]
        assert "strict-origin" in resp.headers["Referrer-Policy"]
        assert "camera=()" in resp.headers["Permissions-Policy"]

    def test_json_endpoint_has_security_headers(self, client):
        resp = client.get("/api/chat/sessions?user_id=nobody")
        assert resp.status_code == 200
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"

    def test_hsts_absent_in_development(self, client):
        """HSTS should NOT be set in development (default)."""
        resp = client.get("/api/health")
        assert "Strict-Transport-Security" not in resp.headers

    def test_hsts_present_in_production(self, client, monkeypatch):
        """HSTS should be set when ENVIRONMENT=production."""
        import security
        monkeypatch.setattr(security, "_ENVIRONMENT", "production")
        resp = client.get("/api/health")
        assert "max-age=" in resp.headers.get("Strict-Transport-Security", "")


# ---------------------------------------------------------------------------
# Login rate limiting
# ---------------------------------------------------------------------------

class TestLoginRateLimit:
    def test_login_blocked_after_max_attempts(self, client):
        """After 5 failed logins from the same IP, the 6th should be 429."""
        rate_limiter.reset()
        for _ in range(5):
            resp = client.post("/api/auth/login", json={
                "username": "admin", "password": "wrong",
            })
            assert resp.status_code == 401

        resp = client.post("/api/auth/login", json={
            "username": "admin", "password": "wrong",
        })
        assert resp.status_code == 429
        assert "Too many login attempts" in resp.json()["detail"]

    def test_successful_login_also_counts(self, client):
        """Successful logins consume the rate limit too, preventing enumeration."""
        rate_limiter.reset()
        for _ in range(5):
            client.post("/api/auth/login", json={
                "username": "admin", "password": "admin123",
            })
        resp = client.post("/api/auth/login", json={
            "username": "admin", "password": "admin123",
        })
        assert resp.status_code == 429


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------

class TestGlobalExceptionHandler:
    def test_unhandled_error_returns_generic_500(self, client, monkeypatch):
        """An unhandled exception should return a safe generic message,
        not a traceback or internal details."""
        import api as api_module

        # Force analytics to raise to simulate an unexpected crash.
        # Must patch on the api module because it imported get_analytics by name.
        def _boom(*args, **kwargs):
            raise RuntimeError("database exploded")

        monkeypatch.setattr(api_module, "get_analytics", _boom)

        resp = client.get("/api/analytics")
        assert resp.status_code == 500
        body = resp.json()
        assert body["detail"] == "Internal server error."
        # Ensure no traceback info leaked.
        assert "database exploded" not in resp.text
        assert "Traceback" not in resp.text
