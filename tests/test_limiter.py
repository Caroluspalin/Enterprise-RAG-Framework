"""Tests for the tier-aware in-memory rate limiter (src/limiter.py).

Verifies:
  - FREE_USER is blocked after 5 requests in a window
  - PRO_USER allows up to 60 requests in a window
  - Unknown/admin tiers are always allowed
  - Remaining count decreases correctly
  - Different keys are tracked independently
  - reset() clears state
"""

from limiter import RateLimiter, TIER_LIMITS


class TestRateLimiterUnit:
    """Pure unit tests — no FastAPI or DB involved."""

    def test_free_user_allowed_up_to_limit(self):
        rl = RateLimiter()
        limit = TIER_LIMITS["FREE_USER"]
        for i in range(limit):
            allowed, max_req, remaining = rl.check("user-1", "FREE_USER")
            assert allowed is True
            assert max_req == limit
            assert remaining == limit - i - 1

    def test_free_user_blocked_after_limit(self):
        rl = RateLimiter()
        limit = TIER_LIMITS["FREE_USER"]
        for _ in range(limit):
            rl.check("user-1", "FREE_USER")
        # Next request should be blocked.
        allowed, max_req, remaining = rl.check("user-1", "FREE_USER")
        assert allowed is False
        assert remaining == 0

    def test_pro_user_allows_more(self):
        rl = RateLimiter()
        pro_limit = TIER_LIMITS["PRO_USER"]
        for i in range(pro_limit):
            allowed, _, _ = rl.check("pro-1", "PRO_USER")
            assert allowed is True
        # One more should be blocked.
        allowed, _, remaining = rl.check("pro-1", "PRO_USER")
        assert allowed is False
        assert remaining == 0

    def test_admin_tier_always_allowed(self):
        rl = RateLimiter()
        for _ in range(200):
            allowed, _, _ = rl.check("admin-1", "ADMIN")
            assert allowed is True

    def test_different_keys_independent(self):
        rl = RateLimiter()
        limit = TIER_LIMITS["FREE_USER"]
        # Exhaust user-a's quota.
        for _ in range(limit):
            rl.check("user-a", "FREE_USER")
        assert rl.check("user-a", "FREE_USER")[0] is False
        # user-b should still be allowed.
        assert rl.check("user-b", "FREE_USER")[0] is True

    def test_reset_clears_specific_key(self):
        rl = RateLimiter()
        limit = TIER_LIMITS["FREE_USER"]
        for _ in range(limit):
            rl.check("user-x", "FREE_USER")
        assert rl.check("user-x", "FREE_USER")[0] is False

        rl.reset("user-x")
        assert rl.check("user-x", "FREE_USER")[0] is True

    def test_reset_all(self):
        rl = RateLimiter()
        limit = TIER_LIMITS["FREE_USER"]
        for _ in range(limit):
            rl.check("user-y", "FREE_USER")
        assert rl.check("user-y", "FREE_USER")[0] is False

        rl.reset()
        assert rl.check("user-y", "FREE_USER")[0] is True


class TestRateLimitIntegration:
    """Test that the rate limiter is wired into the /api/chat endpoint."""

    def test_chat_returns_rate_limit_headers(self, chat_client):
        resp = chat_client.post("/api/chat", json={"question": "Hi"})
        assert resp.status_code == 200
        assert "X-RateLimit-Limit" in resp.headers
        assert "X-RateLimit-Remaining" in resp.headers

    def test_chat_returns_429_after_free_limit(self, chat_client):
        """Anonymous user defaults to FREE_USER (5/min).  The 6th request
        should return 429."""
        from limiter import rate_limiter, TIER_LIMITS
        rate_limiter.reset()

        limit = TIER_LIMITS["FREE_USER"]
        for _ in range(limit):
            resp = chat_client.post("/api/chat", json={"question": "Hi"})
            assert resp.status_code == 200

        resp = chat_client.post("/api/chat", json={"question": "One too many"})
        assert resp.status_code == 429
        assert "Rate limit" in resp.json()["detail"]
