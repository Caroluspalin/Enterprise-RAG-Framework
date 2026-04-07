"""Tests for chat session endpoints."""


class TestSessionCRUD:
    def test_create_session(self, client):
        resp = client.post("/api/v1/chat/sessions", json={
            "user_id": "user1",
            "title": "Test session",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Test session"
        assert "id" in data

    def test_list_sessions(self, client):
        client.post("/api/v1/chat/sessions", json={"user_id": "user1", "title": "A"})
        client.post("/api/v1/chat/sessions", json={"user_id": "user1", "title": "B"})
        resp = client.get("/api/v1/chat/sessions", params={"user_id": "user1"})
        assert resp.status_code == 200
        sessions = resp.json()["sessions"]
        assert len(sessions) == 2

    def test_get_session_messages(self, client):
        create_resp = client.post("/api/v1/chat/sessions", json={"user_id": "u1"})
        sid = create_resp.json()["id"]
        resp = client.get(f"/api/v1/chat/sessions/{sid}")
        assert resp.status_code == 200
        assert resp.json()["session"]["id"] == sid
        assert resp.json()["messages"] == []

    def test_get_nonexistent_session(self, client):
        resp = client.get("/api/v1/chat/sessions/no-such-id")
        assert resp.status_code == 404

    def test_delete_session(self, client):
        create_resp = client.post("/api/v1/chat/sessions", json={"user_id": "u1"})
        sid = create_resp.json()["id"]
        del_resp = client.delete(f"/api/v1/chat/sessions/{sid}")
        assert del_resp.status_code == 200
        # Confirm it's gone.
        assert client.get(f"/api/v1/chat/sessions/{sid}").status_code == 404

    def test_delete_nonexistent_session(self, client):
        resp = client.delete("/api/v1/chat/sessions/nonexistent")
        assert resp.status_code == 404
