"""
test_jwt_auth.py

Tests for Phase 13 Step 5 — JWT authentication and Stripe webhook readiness.

Coverage:
  - jwt_auth.make_access_token / decode_access_token unit tests
  - JWT Bearer tokens accepted by RBAC-protected endpoints (via rbac.resolve_role)
  - Invalid / expired JWTs are rejected
  - POST /api/v1/webhooks/stripe — valid signature returns 200
  - POST /api/v1/webhooks/stripe — invalid signature returns 400
  - POST /api/v1/webhooks/stripe — missing secret passes through
"""

import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers shared by chat-based JWT tests
# ---------------------------------------------------------------------------

async def _fake_astream(*args, **kwargs):
    for tok in ["Hi", "!"]:
        yield tok


TEST_ADMIN_SECRET = "test-secret-for-ci"


@pytest.fixture()
def jwt_chat_client(monkeypatch):
    """TestClient with mocked chain, suitable for JWT RBAC tests on /api/v1/chat."""
    monkeypatch.setenv("INTERNAL_ADMIN_SECRET", TEST_ADMIN_SECRET)

    mock_retriever = MagicMock()
    mock_retriever.invoke.return_value = [
        SimpleNamespace(page_content="Test.", metadata={"source_file": "t.pdf", "page": 1}),
    ]

    mock_chain = MagicMock()
    mock_chain.astream = _fake_astream
    mock_pipe = MagicMock()
    mock_pipe.__or__ = MagicMock(return_value=mock_chain)
    mock_llm = MagicMock()
    mock_llm.__ror__ = MagicMock(return_value=mock_pipe)
    mock_prompt = MagicMock()
    mock_prompt.__or__ = MagicMock(return_value=mock_pipe)

    with patch("api._get_components") as mock_gc:
        mock_gc.return_value = (mock_retriever, mock_llm, mock_prompt)

        import api as api_module
        monkeypatch.setattr(api_module, "INTERNAL_ADMIN_SECRET", TEST_ADMIN_SECRET)
        monkeypatch.setattr(api_module, "WIDGET_API_KEY_LEGACY", "")
        monkeypatch.setattr(api_module, "CHAT_RATE_LIMIT", "9999/minute")

        from fastapi.testclient import TestClient
        api_module.limiter.reset()
        from limiter import rate_limiter
        rate_limiter.reset()
        yield TestClient(api_module.app)


def _stripe_sig(payload: bytes, secret: str, timestamp: str = "1700000000") -> str:
    """Build a Stripe-Signature header value for the given payload and secret."""
    signed = f"{timestamp}.{payload.decode('utf-8')}"
    digest = hmac.new(
        secret.encode("utf-8"),
        signed.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


# ===========================================================================
# Unit tests — jwt_auth module
# ===========================================================================

class TestMakeAccessToken:
    def test_returns_non_empty_string(self):
        from jwt_auth import make_access_token
        token = make_access_token("user-abc", "member")
        assert isinstance(token, str) and len(token) > 0

    def test_token_has_three_dot_segments(self):
        """HS256 JWTs always have exactly three base64url segments."""
        from jwt_auth import make_access_token
        token = make_access_token("u1", "owner")
        assert token.count(".") == 2

    def test_different_users_produce_different_tokens(self):
        from jwt_auth import make_access_token
        t1 = make_access_token("user-1", "member")
        t2 = make_access_token("user-2", "member")
        assert t1 != t2


class TestDecodeAccessToken:
    def test_round_trip_preserves_sub_and_role(self):
        from jwt_auth import decode_access_token, make_access_token
        token = make_access_token("user-xyz", "owner")
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "user-xyz"
        assert payload["role"] == "owner"

    def test_invalid_token_returns_none(self):
        from jwt_auth import decode_access_token
        assert decode_access_token("not.a.valid.jwt") is None

    def test_garbage_string_returns_none(self):
        from jwt_auth import decode_access_token
        assert decode_access_token("totallyrandom") is None

    def test_expired_token_returns_none(self):
        from jwt_auth import decode_access_token, make_access_token
        token = make_access_token("old-user", "member", exp_seconds=-1)
        assert decode_access_token(token) is None

    def test_tampered_token_returns_none(self):
        """Changing one character in the signature should fail verification."""
        from jwt_auth import decode_access_token, make_access_token
        token = make_access_token("user-t", "admin")
        # Flip the last character of the signature segment.
        parts = token.split(".")
        sig = parts[2]
        tampered_sig = sig[:-1] + ("A" if sig[-1] != "A" else "B")
        tampered = ".".join(parts[:2] + [tampered_sig])
        assert decode_access_token(tampered) is None

    def test_missing_role_claim_returns_none(self):
        """A JWT missing the 'role' claim is rejected even if otherwise valid."""
        import jwt as _jwt
        from jwt_auth import JWT_ALGORITHM, JWT_SECRET, decode_access_token
        from datetime import datetime, timedelta, timezone

        payload = {"sub": "user-norole", "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
        token = _jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        assert decode_access_token(token) is None


# ===========================================================================
# Integration tests — JWT Bearer auth through RBAC-protected endpoints
# ===========================================================================

class TestJWTBearerRBAC:
    def test_member_jwt_can_chat(self, jwt_chat_client, make_jwt):
        token = make_jwt("u-member", "member")
        resp = jwt_chat_client.post(
            "/api/v1/chat",
            json={"question": "Hello?"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_owner_jwt_can_chat(self, jwt_chat_client, make_jwt):
        token = make_jwt("u-owner", "owner")
        resp = jwt_chat_client.post(
            "/api/v1/chat",
            json={"question": "Hello?"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_viewer_jwt_cannot_chat(self, jwt_chat_client, make_jwt):
        """Viewer role is not in the allowed list for /api/v1/chat."""
        token = make_jwt("u-viewer", "viewer")
        resp = jwt_chat_client.post(
            "/api/v1/chat",
            json={"question": "Can I?"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    def test_invalid_jwt_rejected(self, jwt_chat_client):
        resp = jwt_chat_client.post(
            "/api/v1/chat",
            json={"question": "Hi"},
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 403

    def test_expired_jwt_rejected(self, jwt_chat_client, make_jwt):
        token = make_jwt("u-expired", "member", exp_seconds=-1)
        resp = jwt_chat_client.post(
            "/api/v1/chat",
            json={"question": "Hi"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    def test_admin_jwt_can_list_documents(self, client, make_jwt):
        token = make_jwt("u-admin", "admin")
        resp = client.get(
            "/api/v1/documents",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_viewer_jwt_can_list_documents(self, client, make_jwt):
        """Viewer role IS allowed to list documents."""
        token = make_jwt("u-viewer", "viewer")
        resp = client.get(
            "/api/v1/documents",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_viewer_jwt_cannot_delete_document(self, client, make_jwt):
        """Viewer cannot delete — RBAC returns 403 before reaching the store."""
        token = make_jwt("u-viewer", "viewer")
        resp = client.delete(
            "/api/v1/documents/test.pdf",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    def test_admin_jwt_can_delete_document(self, client, make_jwt):
        """Admin JWT gets past RBAC; 404 means the file just doesn't exist."""
        token = make_jwt("u-admin", "admin")
        resp = client.delete(
            "/api/v1/documents/nonexistent.pdf",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code in (200, 404)
        assert resp.status_code != 403


# ===========================================================================
# Integration tests — POST /api/v1/webhooks/stripe
# ===========================================================================

class TestStripeWebhook:
    ENDPOINT = "/api/v1/webhooks/stripe"

    def test_valid_signature_returns_200(self, client, monkeypatch):
        import api
        monkeypatch.setattr(api, "STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
        payload = b'{"type":"payment_intent.succeeded","data":{}}'
        sig = _stripe_sig(payload, "whsec_test_secret")
        resp = client.post(
            self.ENDPOINT,
            content=payload,
            headers={"stripe-signature": sig, "Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"received": True}

    def test_invalid_signature_returns_400(self, client, monkeypatch):
        import api
        monkeypatch.setattr(api, "STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
        payload = b'{"type":"payment_intent.succeeded"}'
        resp = client.post(
            self.ENDPOINT,
            content=payload,
            headers={
                "stripe-signature": "t=1234567890,v1=deadbeefdeadbeefdeadbeef",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 400
        assert "signature" in resp.json()["detail"].lower()

    def test_missing_signature_header_returns_400(self, client, monkeypatch):
        import api
        monkeypatch.setattr(api, "STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
        resp = client.post(
            self.ENDPOINT,
            content=b'{"type":"test"}',
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    def test_malformed_signature_header_returns_400(self, client, monkeypatch):
        """A Stripe-Signature header with no t= or v1= is rejected."""
        import api
        monkeypatch.setattr(api, "STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
        resp = client.post(
            self.ENDPOINT,
            content=b'{}',
            headers={"stripe-signature": "garbage_value"},
        )
        assert resp.status_code == 400

    def test_no_secret_configured_passes_through(self, client, monkeypatch):
        """When STRIPE_WEBHOOK_SECRET is empty, events are accepted without validation."""
        import api
        monkeypatch.setattr(api, "STRIPE_WEBHOOK_SECRET", "")
        resp = client.post(
            self.ENDPOINT,
            content=b'{"type":"test.event"}',
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["received"] is True

    def test_different_timestamp_changes_signature(self, client, monkeypatch):
        """Replaying a webhook with a different timestamp should fail."""
        import api
        monkeypatch.setattr(api, "STRIPE_WEBHOOK_SECRET", "whsec_replay_test")
        payload = b'{"type":"charge.succeeded"}'
        # Generate sig with timestamp A
        real_sig = _stripe_sig(payload, "whsec_replay_test", "1111111111")
        # But send with timestamp B in header — the t= does not match the sig
        tampered_header = real_sig.replace("t=1111111111", "t=9999999999")
        resp = client.post(
            self.ENDPOINT,
            content=payload,
            headers={"stripe-signature": tampered_header},
        )
        assert resp.status_code == 400
