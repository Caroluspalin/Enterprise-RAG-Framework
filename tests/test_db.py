"""Unit tests for src/db.py — SQLite persistence layer.

Each test runs against a fresh temporary database (via the autouse
_isolated_db fixture in conftest.py).
"""

import db


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class TestUsers:
    def test_default_admin_is_seeded(self):
        users = db.list_users()
        assert len(users) == 1
        assert users[0]["username"] == "admin"
        assert users[0]["role"] == "admin"

    def test_create_user(self):
        user = db.create_user("alice", "password123", "Alice", "user")
        assert user["username"] == "alice"
        assert user["role"] == "user"
        assert "password_hash" not in user

    def test_create_duplicate_username_raises(self):
        db.create_user("bob", "pass1", "Bob")
        import sqlite3
        with __import__("pytest").raises(sqlite3.IntegrityError):
            db.create_user("bob", "pass2", "Bob2")

    def test_verify_user_correct_password(self):
        db.create_user("carol", "secret", "Carol")
        result = db.verify_user("carol", "secret")
        assert result is not None
        assert result["username"] == "carol"
        assert "password_hash" not in result

    def test_verify_user_wrong_password(self):
        db.create_user("dave", "correct", "Dave")
        assert db.verify_user("dave", "wrong") is None

    def test_verify_nonexistent_user(self):
        assert db.verify_user("ghost", "anything") is None

    def test_delete_user(self):
        user = db.create_user("temp", "pass", "Temp")
        assert db.delete_user(user["id"]) is True
        assert db.get_user_by_username("temp") is None

    def test_delete_nonexistent_user(self):
        assert db.delete_user("nonexistent-id") is False

    def test_change_password(self):
        user = db.create_user("eve", "oldpass", "Eve")
        assert db.change_password(user["id"], "oldpass", "newpass") is True
        # Old password no longer works.
        assert db.verify_user("eve", "oldpass") is None
        # New password works.
        assert db.verify_user("eve", "newpass") is not None

    def test_change_password_wrong_old(self):
        user = db.create_user("frank", "correct", "Frank")
        assert db.change_password(user["id"], "wrong", "new") is False


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

class TestSessions:
    def test_create_and_get_session(self):
        session = db.create_session("user1", "My first chat")
        assert session["title"] == "My first chat"
        fetched = db.get_session(session["id"])
        assert fetched is not None
        assert fetched["title"] == "My first chat"

    def test_list_sessions_ordered_by_recency(self):
        db.create_session("user1", "First")
        db.create_session("user1", "Second")
        sessions = db.get_sessions("user1")
        assert len(sessions) == 2
        # Most recent first.
        assert sessions[0]["title"] == "Second"

    def test_delete_session_cascades_messages(self):
        session = db.create_session("user1")
        db.add_message(session["id"], "user", "Hello")
        db.delete_session(session["id"])
        assert db.get_session(session["id"]) is None
        assert db.get_messages(session["id"]) == []

    def test_get_nonexistent_session(self):
        assert db.get_session("no-such-id") is None

    def test_update_session_title(self):
        session = db.create_session("user1", "Old title")
        db.update_session_title(session["id"], "New title")
        assert db.get_session(session["id"])["title"] == "New title"


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

class TestMessages:
    def test_add_and_get_messages(self):
        session = db.create_session("user1")
        db.add_message(session["id"], "user", "What is X?")
        db.add_message(session["id"], "assistant", "X is Y.", [{"filename": "doc.pdf", "page": 1}])
        msgs = db.get_messages(session["id"])
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["sources"] == [{"filename": "doc.pdf", "page": 1}]

    def test_user_message_sources_are_none(self):
        session = db.create_session("user1")
        msg = db.add_message(session["id"], "user", "Hi")
        assert msg["sources"] is None


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------

class TestApiKeys:
    def test_create_and_verify_api_key(self):
        user = db.create_user("keyuser", "pass", "Key User")
        result = db.create_api_key(user["id"], "test-key")
        assert result["raw_key"].startswith("rag_")
        assert result["prefix"].endswith("...")

        # Verification with the raw key should succeed.
        verified = db.verify_api_key(result["raw_key"])
        assert verified is not None
        assert verified["user_id"] == user["id"]

    def test_revoked_key_fails_verification(self):
        user = db.create_user("keyuser2", "pass", "Key User 2")
        result = db.create_api_key(user["id"], "revoke-me")
        db.revoke_api_key(result["id"])
        assert db.verify_api_key(result["raw_key"]) is None

    def test_invalid_key_returns_none(self):
        assert db.verify_api_key("rag_totally_fake_key") is None

    def test_list_api_keys(self):
        user = db.create_user("keyuser3", "pass", "Key User 3")
        db.create_api_key(user["id"], "key-a")
        db.create_api_key(user["id"], "key-b")
        keys = db.list_api_keys(user["id"])
        assert len(keys) == 2
        # No raw_key or key_hash exposed in list.
        for k in keys:
            assert "raw_key" not in k
            assert "key_hash" not in k


# ---------------------------------------------------------------------------
# Auto-title
# ---------------------------------------------------------------------------

class TestAutoTitle:
    def test_short_question_unchanged(self):
        assert db.auto_title_from_question("Hello") == "Hello"

    def test_long_question_truncated(self):
        long_q = "This is a very long question that should be truncated at a word boundary to fit within sixty chars"
        title = db.auto_title_from_question(long_q)
        assert len(title) <= 63  # 60 + "..."
        assert title.endswith("...")


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

class TestAnalytics:
    def test_analytics_empty_db(self):
        data = db.get_analytics()
        assert data["total_messages"] == 0
        # Seed creates a user, not a session.
        assert data["total_sessions"] == 0
        assert data["messages_per_day"] == []

    def test_analytics_with_messages(self):
        session = db.create_session("user1", "Test session")
        db.add_message(session["id"], "user", "What is RAG?")
        db.add_message(session["id"], "assistant", "RAG is...")
        data = db.get_analytics(days=30)
        assert data["total_messages"] == 2
        assert data["total_sessions"] == 1
        assert len(data["recent_questions"]) == 1
        assert data["recent_questions"][0]["question"] == "What is RAG?"
