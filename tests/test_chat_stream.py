"""Integration tests for POST /api/chat — SSE streaming endpoint.

The LLM and retriever are fully mocked so no external API calls are made.
Tests verify:
  - SSE event format (token, sources, done)
  - Source citation deduplication
  - Session persistence (messages saved to SQLite when session_id given)
  - Widget API key validation
  - History conversion to LangChain message objects

The chat_client fixture is defined in conftest.py.
"""

import json

import db

# RBAC requires a valid user with an allowed role. Helper to get the
# seeded admin's ID for tests that don't care about role granularity.
def _admin_id():
    user = db.get_user_by_username("admin")
    return user["id"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_sse_events(raw_text: str) -> list[dict]:
    """Parse SSE text into a list of JSON event payloads."""
    events = []
    for line in raw_text.strip().split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


# ---------------------------------------------------------------------------
# SSE format tests
# ---------------------------------------------------------------------------

class TestSSEStreamFormat:
    def test_stream_returns_token_sources_done(self, chat_client):
        resp = chat_client.post("/api/v1/chat", json={"question": "What is the capital?", "user_id": _admin_id()})
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        events = _parse_sse_events(resp.text)
        types = [e["type"] for e in events]

        # Must contain at least one token, then sources, then done.
        assert "token" in types
        assert "sources" in types
        assert "done" in types
        # done must be last.
        assert types[-1] == "done"

    def test_token_events_carry_content(self, chat_client):
        resp = chat_client.post("/api/v1/chat", json={"question": "Hello?", "user_id": _admin_id()})
        events = _parse_sse_events(resp.text)
        token_events = [e for e in events if e["type"] == "token"]
        assert len(token_events) >= 1
        # Concatenated tokens should form the full answer.
        full = "".join(e["content"] for e in token_events)
        assert "Hello" in full

    def test_sources_are_deduplicated(self, chat_client):
        """The mock retriever returns two chunks from the same file (geo.pdf).
        Source citations should be deduplicated by (filename, page)."""
        resp = chat_client.post("/api/v1/chat", json={"question": "Capitals?", "user_id": _admin_id()})
        events = _parse_sse_events(resp.text)
        source_event = next(e for e in events if e["type"] == "sources")
        sources = source_event["sources"]
        # Two unique pages: 7 and 12.
        assert len(sources) == 2
        filenames = {s["filename"] for s in sources}
        assert filenames == {"geo.pdf"}
        pages = {s["page"] for s in sources}
        assert pages == {7, 12}


# ---------------------------------------------------------------------------
# Session persistence
# ---------------------------------------------------------------------------

class TestSSESessionPersistence:
    def test_messages_persisted_when_session_id_given(self, chat_client):
        uid = _admin_id()
        session = db.create_session(uid, "Test chat")
        sid = session["id"]

        resp = chat_client.post("/api/v1/chat", json={
            "question": "What is the capital of France?",
            "session_id": sid,
            "user_id": uid,
        })
        assert resp.status_code == 200

        messages = db.get_messages(sid)
        # Expect user message + assistant message.
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "What is the capital of France?"
        assert messages[1]["role"] == "assistant"
        # Assistant content should be the concatenated tokens.
        assert "Hello" in messages[1]["content"]

    def test_no_persistence_without_session_id(self, chat_client):
        uid = _admin_id()
        resp = chat_client.post("/api/v1/chat", json={"question": "No session", "user_id": uid})
        assert resp.status_code == 200
        # No sessions should have been created for this user beyond any existing ones.
        sessions = db.get_sessions(uid)
        assert len(sessions) == 0

    def test_auto_creates_session_if_id_not_found(self, chat_client):
        uid = _admin_id()
        fake_sid = "auto-created-session-id-123"
        resp = chat_client.post("/api/v1/chat", json={
            "question": "Create session for me",
            "session_id": fake_sid,
            "user_id": uid,
        })
        assert resp.status_code == 200
        # Session should now exist.
        session = db.get_session(fake_sid)
        assert session is not None
        assert session["user_id"] == uid

    def test_auto_title_from_first_question(self, chat_client):
        uid = _admin_id()
        session = db.create_session(uid, "New chat")
        resp = chat_client.post("/api/v1/chat", json={
            "question": "How does RAG work?",
            "session_id": session["id"],
            "user_id": uid,
        })
        assert resp.status_code == 200
        updated = db.get_session(session["id"])
        # Title should have been updated from "New chat" to the question text.
        assert updated["title"] == "How does RAG work?"


# ---------------------------------------------------------------------------
# Widget API key validation
# ---------------------------------------------------------------------------

class TestChatWidgetAuth:
    def test_valid_db_key_accepted(self, chat_client):
        user = db.create_user("widgetuser", "pass", "Widget User")
        key_data = db.create_api_key(user["id"], "my-widget")
        resp = chat_client.post(
            "/api/v1/chat",
            json={"question": "Hi"},
            headers={"X-Widget-Key": key_data["raw_key"]},
        )
        assert resp.status_code == 200

    def test_invalid_key_rejected_when_legacy_set(self, chat_client, monkeypatch):
        import api as api_module
        monkeypatch.setattr(api_module, "WIDGET_API_KEY_LEGACY", "real-legacy-key")
        resp = chat_client.post(
            "/api/v1/chat",
            json={"question": "Hi", "user_id": _admin_id()},
            headers={"X-Widget-Key": "wrong-key"},
        )
        assert resp.status_code == 403

    def test_missing_key_rejected_when_legacy_set(self, chat_client, monkeypatch):
        import api as api_module
        monkeypatch.setattr(api_module, "WIDGET_API_KEY_LEGACY", "real-legacy-key")
        resp = chat_client.post("/api/v1/chat", json={"question": "Hi", "user_id": _admin_id()})
        assert resp.status_code == 403

    def test_legacy_key_accepted(self, chat_client, monkeypatch):
        import api as api_module
        monkeypatch.setattr(api_module, "WIDGET_API_KEY_LEGACY", "my-legacy-key")
        resp = chat_client.post(
            "/api/v1/chat",
            json={"question": "Hi", "user_id": _admin_id()},
            headers={"X-Widget-Key": "my-legacy-key"},
        )
        assert resp.status_code == 200

    def test_revoked_key_rejected(self, chat_client, monkeypatch):
        import api as api_module
        monkeypatch.setattr(api_module, "WIDGET_API_KEY_LEGACY", "fallback")
        user = db.create_user("revokeuser", "pass", "Revoke User")
        key_data = db.create_api_key(user["id"], "temp-key")
        db.revoke_api_key(key_data["id"])
        resp = chat_client.post(
            "/api/v1/chat",
            json={"question": "Hi", "user_id": _admin_id()},
            headers={"X-Widget-Key": key_data["raw_key"]},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Chat history conversion
# ---------------------------------------------------------------------------

class TestChatHistory:
    def test_history_passed_through(self, chat_client):
        """Sending history should not crash — we verify via successful stream."""
        resp = chat_client.post("/api/v1/chat", json={
            "question": "Follow up",
            "user_id": _admin_id(),
            "history": [
                {"role": "user", "content": "First question"},
                {"role": "assistant", "content": "First answer"},
            ],
        })
        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)
        assert any(e["type"] == "done" for e in events)
