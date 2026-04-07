"""Tests for admin endpoints (/api/admin/*).

All admin endpoints require the Authorization: Bearer <INTERNAL_ADMIN_SECRET> header.
The admin_headers fixture provides this.
"""

import db


class TestAdminAuth:
    """Verify that admin endpoints reject unauthenticated requests."""

    def test_no_auth_header(self, client):
        resp = client.get("/api/v1/admin/users")
        assert resp.status_code == 401

    def test_wrong_secret(self, client):
        resp = client.get("/api/v1/admin/users", headers={
            "Authorization": "Bearer wrong-secret",
        })
        assert resp.status_code == 401

    def test_malformed_header(self, client):
        resp = client.get("/api/v1/admin/users", headers={
            "Authorization": "Basic dXNlcjpwYXNz",
        })
        assert resp.status_code == 401


class TestAdminUsers:
    def test_list_users(self, client, admin_headers):
        resp = client.get("/api/v1/admin/users", headers=admin_headers)
        assert resp.status_code == 200
        users = resp.json()["users"]
        # Default admin seed exists.
        assert any(u["username"] == "admin" for u in users)

    def test_delete_user(self, client, admin_headers):
        user = db.create_user("deleteme", "pass", "Delete Me")
        resp = client.delete(f"/api/v1/admin/users/{user['id']}", headers=admin_headers)
        assert resp.status_code == 200
        assert db.get_user_by_username("deleteme") is None

    def test_delete_nonexistent_user(self, client, admin_headers):
        resp = client.delete("/api/v1/admin/users/fake-id", headers=admin_headers)
        assert resp.status_code == 404

    def test_change_password(self, client, admin_headers):
        user = db.create_user("pwuser", "oldpass123", "PW User")
        resp = client.post(
            f"/api/v1/admin/users/{user['id']}/change-password",
            json={"old_password": "oldpass123", "new_password": "newpass123"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        # Verify the new password works.
        assert db.verify_user("pwuser", "newpass123") is not None

    def test_change_password_wrong_old(self, client, admin_headers):
        user = db.create_user("pwuser2", "correct", "PW User 2")
        resp = client.post(
            f"/api/v1/admin/users/{user['id']}/change-password",
            json={"old_password": "wrong", "new_password": "newpass123"},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_change_password_too_short(self, client, admin_headers):
        user = db.create_user("pwuser3", "oldpass123", "PW User 3")
        resp = client.post(
            f"/api/v1/admin/users/{user['id']}/change-password",
            json={"old_password": "oldpass123", "new_password": "short"},
            headers=admin_headers,
        )
        assert resp.status_code == 400


class TestAdminApiKeys:
    def test_create_api_key(self, client, admin_headers):
        user = db.create_user("keyowner", "pass", "Key Owner")
        resp = client.post("/api/v1/admin/api-keys", json={
            "user_id": user["id"],
            "label": "test-key",
        }, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["raw_key"].startswith("rag_")
        assert data["label"] == "test-key"

    def test_list_api_keys(self, client, admin_headers):
        user = db.create_user("keyowner2", "pass", "Key Owner 2")
        db.create_api_key(user["id"], "key-a")
        resp = client.get("/api/v1/admin/api-keys", params={
            "user_id": user["id"],
        }, headers=admin_headers)
        assert resp.status_code == 200
        assert len(resp.json()["api_keys"]) == 1

    def test_revoke_api_key(self, client, admin_headers):
        user = db.create_user("keyowner3", "pass", "Key Owner 3")
        key = db.create_api_key(user["id"], "revoke-me")
        resp = client.delete(
            f"/api/v1/admin/api-keys/{key['id']}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        # Revoked key should fail verification.
        assert db.verify_api_key(key["raw_key"]) is None

    def test_revoke_nonexistent_key(self, client, admin_headers):
        resp = client.delete("/api/v1/admin/api-keys/fake-id", headers=admin_headers)
        assert resp.status_code == 404
