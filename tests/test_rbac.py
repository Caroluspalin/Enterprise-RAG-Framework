"""RBAC (Role-Based Access Control) tests for Phase 13, Step 3.

Verifies that:
  - owner and admin can upload and delete documents.
  - member can chat and list documents, but cannot upload or delete.
  - viewer can only list documents, cannot chat, upload, or delete.
  - Anonymous (no user_id, no API key) is blocked from all RBAC-protected endpoints.
  - API key role is enforced the same way as user role.

No real OpenAI/LLM calls — all external dependencies are mocked.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(role: str, org_id: str | None = None) -> dict:
    """Create a test user with a specific role."""
    import secrets
    username = f"rbac_{role}_{secrets.token_hex(4)}"
    return db.create_user(username, "testpass", f"Test {role}", role=role, organization_id=org_id)


def _parse_sse(raw: str) -> list[dict]:
    events = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_ADMIN_SECRET = "test-secret-for-ci"


async def _fake_astream(*args, **kwargs):
    for tok in ["OK"]:
        yield tok


@pytest.fixture()
def rbac_client(monkeypatch):
    """TestClient with mocked LLM/retriever, suitable for RBAC endpoint tests."""
    monkeypatch.setenv("INTERNAL_ADMIN_SECRET", TEST_ADMIN_SECRET)

    mock_retriever = MagicMock()
    mock_retriever.invoke.return_value = [
        SimpleNamespace(page_content="test", metadata={"source_file": "t.pdf", "page": 1}),
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


# ---------------------------------------------------------------------------
# POST /api/chat — owner, admin, member allowed; viewer denied
# ---------------------------------------------------------------------------

class TestChatRBAC:
    def test_owner_can_chat(self, rbac_client):
        user = _make_user("owner")
        resp = rbac_client.post("/api/chat", json={"question": "Hi", "user_id": user["id"]})
        assert resp.status_code == 200

    def test_admin_can_chat(self, rbac_client):
        user = _make_user("admin")
        resp = rbac_client.post("/api/chat", json={"question": "Hi", "user_id": user["id"]})
        assert resp.status_code == 200

    def test_member_can_chat(self, rbac_client):
        user = _make_user("member")
        resp = rbac_client.post("/api/chat", json={"question": "Hi", "user_id": user["id"]})
        assert resp.status_code == 200

    def test_viewer_cannot_chat(self, rbac_client):
        user = _make_user("viewer")
        resp = rbac_client.post("/api/chat", json={"question": "Hi", "user_id": user["id"]})
        assert resp.status_code == 403

    def test_anonymous_cannot_chat(self, rbac_client):
        resp = rbac_client.post("/api/chat", json={"question": "Hi"})
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/documents — all roles allowed; anonymous denied
# ---------------------------------------------------------------------------

class TestDocumentListRBAC:
    def test_owner_can_list(self, rbac_client):
        user = _make_user("owner")
        resp = rbac_client.get("/api/documents", params={"user_id": user["id"]})
        assert resp.status_code == 200

    def test_admin_can_list(self, rbac_client):
        user = _make_user("admin")
        resp = rbac_client.get("/api/documents", params={"user_id": user["id"]})
        assert resp.status_code == 200

    def test_member_can_list(self, rbac_client):
        user = _make_user("member")
        resp = rbac_client.get("/api/documents", params={"user_id": user["id"]})
        assert resp.status_code == 200

    def test_viewer_can_list(self, rbac_client):
        user = _make_user("viewer")
        resp = rbac_client.get("/api/documents", params={"user_id": user["id"]})
        assert resp.status_code == 200

    def test_anonymous_cannot_list(self, rbac_client):
        resp = rbac_client.get("/api/documents")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/documents/{filename} — only owner, admin; member & viewer denied
# ---------------------------------------------------------------------------

class TestDocumentDeleteRBAC:
    def test_member_cannot_delete_document(self, rbac_client):
        user = _make_user("member")
        resp = rbac_client.delete("/api/documents/test.pdf", params={"user_id": user["id"]})
        assert resp.status_code == 403

    def test_viewer_cannot_delete_document(self, rbac_client):
        user = _make_user("viewer")
        resp = rbac_client.delete("/api/documents/test.pdf", params={"user_id": user["id"]})
        assert resp.status_code == 403

    def test_admin_can_delete_document(self, rbac_client):
        """Admin is allowed by RBAC (the 404 comes from missing file, not access)."""
        user = _make_user("admin")
        resp = rbac_client.delete("/api/documents/nonexistent.pdf", params={"user_id": user["id"]})
        # 404 means RBAC passed but the file doesn't exist — which is correct.
        assert resp.status_code in (200, 404)
        assert resp.status_code != 403

    def test_owner_can_delete_document(self, rbac_client):
        user = _make_user("owner")
        resp = rbac_client.delete("/api/documents/nonexistent.pdf", params={"user_id": user["id"]})
        assert resp.status_code in (200, 404)
        assert resp.status_code != 403

    def test_anonymous_cannot_delete_document(self, rbac_client):
        resp = rbac_client.delete("/api/documents/test.pdf")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/upload — only owner, admin; member & viewer denied
# ---------------------------------------------------------------------------

class TestUploadRBAC:
    def test_member_cannot_upload(self, rbac_client):
        user = _make_user("member")
        key = db.create_api_key(user["id"], "member-upload", role="member")
        resp = rbac_client.post(
            "/api/upload",
            files={"file": ("test.pdf", b"%PDF-1.4 test content", "application/pdf")},
            headers={"X-Widget-Key": key["raw_key"]},
        )
        assert resp.status_code == 403

    def test_viewer_cannot_upload(self, rbac_client):
        user = _make_user("viewer")
        key = db.create_api_key(user["id"], "viewer-upload", role="viewer")
        resp = rbac_client.post(
            "/api/upload",
            files={"file": ("test.pdf", b"%PDF-1.4 test content", "application/pdf")},
            headers={"X-Widget-Key": key["raw_key"]},
        )
        assert resp.status_code == 403

    def test_anonymous_cannot_upload(self, rbac_client):
        resp = rbac_client.post(
            "/api/upload",
            files={"file": ("test.pdf", b"%PDF-1.4 test content", "application/pdf")},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# API key role enforcement — keys inherit RBAC restrictions
# ---------------------------------------------------------------------------

class TestApiKeyRBAC:
    def test_api_key_with_member_role_can_chat(self, rbac_client):
        user = _make_user("admin")
        key = db.create_api_key(user["id"], "member-key", role="member")
        resp = rbac_client.post(
            "/api/chat",
            json={"question": "Hi"},
            headers={"X-Widget-Key": key["raw_key"]},
        )
        assert resp.status_code == 200

    def test_api_key_with_viewer_role_cannot_chat(self, rbac_client):
        user = _make_user("admin")
        key = db.create_api_key(user["id"], "viewer-key", role="viewer")
        resp = rbac_client.post(
            "/api/chat",
            json={"question": "Hi"},
            headers={"X-Widget-Key": key["raw_key"]},
        )
        assert resp.status_code == 403

    def test_api_key_with_admin_role_can_delete(self, rbac_client):
        user = _make_user("admin")
        key = db.create_api_key(user["id"], "admin-key", role="admin")
        resp = rbac_client.delete(
            "/api/documents/nonexistent.pdf",
            headers={"X-Widget-Key": key["raw_key"]},
        )
        # 404 means RBAC passed — file doesn't exist.
        assert resp.status_code != 403

    def test_api_key_with_member_role_cannot_delete(self, rbac_client):
        user = _make_user("admin")
        key = db.create_api_key(user["id"], "member-key", role="member")
        resp = rbac_client.delete(
            "/api/documents/test.pdf",
            headers={"X-Widget-Key": key["raw_key"]},
        )
        assert resp.status_code == 403

    def test_api_key_with_viewer_role_can_list_documents(self, rbac_client):
        user = _make_user("admin")
        key = db.create_api_key(user["id"], "viewer-key", role="viewer")
        resp = rbac_client.get(
            "/api/documents",
            headers={"X-Widget-Key": key["raw_key"]},
        )
        assert resp.status_code == 200

    def test_api_key_role_stored_and_returned(self):
        """Verify that the role field is persisted and returned on verification."""
        user = _make_user("admin")
        key = db.create_api_key(user["id"], "role-test", role="viewer")
        assert key["role"] == "viewer"
        verified = db.verify_api_key(key["raw_key"])
        assert verified is not None
        assert verified["role"] == "viewer"
