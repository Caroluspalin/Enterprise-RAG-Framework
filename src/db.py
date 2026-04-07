"""
db.py

Lightweight SQLite persistence for chat sessions, messages, users, and API keys.

Uses Python's built-in sqlite3 module — no extra dependencies required.
The database file is created alongside the ChromaDB data directory so that
all persistent state lives in one predictable location.

Tables:
  users     — registered accounts with bcrypt-hashed passwords
  api_keys  — per-user widget API keys (SHA-256 hashed, revocable)
  sessions  — one row per conversation (user_id groups by user)
  messages  — one row per user or assistant turn within a session
"""

import hashlib
import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import bcrypt as _bcrypt
from dotenv import load_dotenv

load_dotenv()

DB_PATH = Path(os.getenv("CHAT_DB_PATH", "./chat_history.db"))

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    name          TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    tier          TEXT NOT NULL DEFAULT 'FREE_USER' CHECK (tier IN ('FREE_USER', 'PRO_USER')),
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_keys (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    key_hash   TEXT NOT NULL,
    label      TEXT NOT NULL,
    prefix     TEXT NOT NULL,
    is_active  INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_api_keys_user   ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_hash   ON api_keys(key_hash);

CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    title      TEXT NOT NULL DEFAULT 'New chat',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id         TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content    TEXT NOT NULL,
    sources    TEXT,          -- JSON array of source citations, NULL for user messages
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sessions_user    ON sessions(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at ASC);

CREATE TABLE IF NOT EXISTS audit_log (
    id         TEXT PRIMARY KEY,
    timestamp  TEXT NOT NULL,
    user_id    TEXT,
    action     TEXT NOT NULL,
    ip_address TEXT,
    details    TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_action    ON audit_log(action);
"""


def _connect() -> sqlite3.Connection:
    """Open a connection with foreign-key enforcement and Row factory."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create tables and indexes if they don't already exist, then seed the
    default admin user so the app is usable on first run."""
    with _connect() as conn:
        conn.executescript(_SCHEMA_SQL)
        # Migration: add tier column to existing users tables that lack it.
        existing_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        if "tier" not in existing_cols:
            conn.execute(
                "ALTER TABLE users ADD COLUMN tier TEXT NOT NULL DEFAULT 'FREE_USER'"
            )
    _seed_default_admin()


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def create_session(user_id: str, title: str = "New chat") -> dict:
    """Insert a new session and return it as a dict."""
    session_id = uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO sessions (id, user_id, title, created_at) VALUES (?, ?, ?, ?)",
            (session_id, user_id, title, now),
        )
    return {"id": session_id, "user_id": user_id, "title": title, "created_at": now}


def get_sessions(user_id: str) -> list[dict]:
    """Return all sessions for a user, most recent first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, user_id, title, created_at FROM sessions "
            "WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_session(session_id: str) -> dict | None:
    """Return a single session or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, user_id, title, created_at FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    return dict(row) if row else None


def update_session_title(session_id: str, title: str) -> None:
    """Update the display title for a session."""
    with _connect() as conn:
        conn.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))


def delete_session(session_id: str) -> None:
    """Delete a session and its messages (CASCADE)."""
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def add_message(
    session_id: str,
    role: str,
    content: str,
    sources: list[dict] | None = None,
) -> dict:
    """Append a message to a session and return it as a dict."""
    msg_id = uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    sources_json = json.dumps(sources) if sources else None
    with _connect() as conn:
        conn.execute(
            "INSERT INTO messages (id, session_id, role, content, sources, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (msg_id, session_id, role, content, sources_json, now),
        )
    return {
        "id": msg_id,
        "session_id": session_id,
        "role": role,
        "content": content,
        "sources": sources,
        "created_at": now,
    }


def get_messages(session_id: str) -> list[dict]:
    """Return all messages in a session, oldest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, session_id, role, content, sources, created_at "
            "FROM messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()

    messages = []
    for r in rows:
        msg = dict(r)
        # Deserialise the JSON sources column back to a list.
        if msg["sources"]:
            msg["sources"] = json.loads(msg["sources"])
        messages.append(msg)
    return messages


# ---------------------------------------------------------------------------
# Auto-title helper
# ---------------------------------------------------------------------------

def auto_title_from_question(question: str, max_length: int = 60) -> str:
    """Derive a short session title from the first user question.

    Truncates cleanly at the last word boundary within max_length.
    """
    text = question.strip().replace("\n", " ")
    if len(text) <= max_length:
        return text
    truncated = text[:max_length].rsplit(" ", 1)[0]
    return truncated + "..."


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def create_user(
    username: str,
    password: str,
    name: str,
    role: str = "user",
    tier: str = "FREE_USER",
) -> dict:
    """Create a new user with a bcrypt-hashed password."""
    user_id = uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    password_hash = _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO users (id, username, password_hash, name, role, tier, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, username, password_hash, name, role, tier, now),
        )
    return {
        "id": user_id, "username": username, "name": name,
        "role": role, "tier": tier, "created_at": now,
    }


def verify_user(username: str, password: str) -> dict | None:
    """Look up a user by username and verify the password.

    Returns the user dict (without password_hash) on success, None on failure.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, name, role, tier, created_at "
            "FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if not row:
        return None
    user = dict(row)
    if not _bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return None
    # Never return the hash to callers.
    del user["password_hash"]
    return user


def get_user_by_username(username: str) -> dict | None:
    """Return a user by username (without password_hash), or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, username, name, role, tier, created_at FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    return dict(row) if row else None


def list_users() -> list[dict]:
    """Return all users (without password hashes)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, username, name, role, tier, created_at FROM users ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_user_by_id(user_id: str) -> dict | None:
    """Return a user by ID (without password_hash), or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, username, name, role, tier, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def delete_user(user_id: str) -> bool:
    """Delete a user and all associated data (API keys cascade).

    Returns True if a row was deleted, False if user_id was not found.
    """
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return cursor.rowcount > 0


def change_password(user_id: str, old_password: str, new_password: str) -> bool:
    """Verify old_password and replace it with a bcrypt hash of new_password.

    Returns True on success, False if old_password is incorrect.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if not row:
        return False
    if not _bcrypt.checkpw(old_password.encode(), row["password_hash"].encode()):
        return False
    new_hash = _bcrypt.hashpw(new_password.encode(), _bcrypt.gensalt()).decode()
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id)
        )
    return True


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------

def _hash_api_key(raw_key: str) -> str:
    """One-way SHA-256 hash of a raw API key for storage and lookup."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def create_api_key(user_id: str, label: str) -> dict:
    """Generate a cryptographically secure API key for a user.

    The raw key is returned ONCE in the response.  Only its SHA-256 hash
    is stored in the database — the plaintext cannot be recovered later.
    """
    key_id = uuid4().hex
    raw_key = "rag_" + secrets.token_urlsafe(32)
    key_hash = _hash_api_key(raw_key)
    # Prefix is the first 12 chars — enough to identify the key in a list
    # without revealing the full secret.
    prefix = raw_key[:12] + "..."
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO api_keys (id, user_id, key_hash, label, prefix, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, 1, ?)",
            (key_id, user_id, key_hash, label, prefix, now),
        )
    return {
        "id": key_id,
        "raw_key": raw_key,   # Shown to the user once, never stored
        "label": label,
        "prefix": prefix,
        "is_active": True,
        "created_at": now,
    }


def list_api_keys(user_id: str) -> list[dict]:
    """Return all API keys for a user (without hashes)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, label, prefix, is_active, created_at "
            "FROM api_keys WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def revoke_api_key(key_id: str) -> bool:
    """Deactivate an API key. Returns True if found and updated."""
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE api_keys SET is_active = 0 WHERE id = ? AND is_active = 1",
            (key_id,),
        )
    return cursor.rowcount > 0


def delete_api_key(key_id: str) -> bool:
    """Permanently remove an API key. Returns True if found and deleted."""
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
    return cursor.rowcount > 0


def verify_api_key(raw_key: str) -> dict | None:
    """Hash the raw key and look up an active match in the database.

    Returns {"user_id": ..., "label": ...} on success, None if invalid
    or revoked.
    """
    key_hash = _hash_api_key(raw_key)
    with _connect() as conn:
        row = conn.execute(
            "SELECT user_id, label FROM api_keys "
            "WHERE key_hash = ? AND is_active = 1",
            (key_hash,),
        ).fetchone()
    return dict(row) if row else None


def _seed_default_admin() -> None:
    """Create a default admin user if no users exist yet.

    This ensures there is always at least one account to log in with after
    a fresh deployment.  The password should be changed immediately.
    """
    with _connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count == 0:
        create_user("admin", "admin123", "Admin", "admin")


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def get_analytics(days: int = 30) -> dict:
    """Aggregate chat analytics for the admin dashboard.

    Returns total messages, messages per day, recent questions, and active
    session count — all within the specified lookback window.
    """
    with _connect() as conn:
        # Total message count (all time).
        total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]

        # Total session count (all time).
        total_sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

        # Messages per day for the last N days.
        # SQLite date() works on ISO-8601 strings stored in created_at.
        per_day = conn.execute(
            "SELECT date(created_at) AS day, COUNT(*) AS count "
            "FROM messages "
            "WHERE created_at >= date('now', ?) "
            "GROUP BY day ORDER BY day ASC",
            (f"-{days} days",),
        ).fetchall()
        messages_per_day = [{"date": r["day"], "count": r["count"]} for r in per_day]

        # Active sessions (sessions that received a message in the window).
        active_sessions = conn.execute(
            "SELECT COUNT(DISTINCT session_id) FROM messages "
            "WHERE created_at >= date('now', ?)",
            (f"-{days} days",),
        ).fetchone()[0]

        # Recent user questions (newest first, deduplicated by content).
        recent_rows = conn.execute(
            "SELECT content, created_at FROM messages "
            "WHERE role = 'user' "
            "ORDER BY created_at DESC LIMIT 20"
        ).fetchall()
        recent_questions = [{"question": r["content"], "created_at": r["created_at"]} for r in recent_rows]

        # Most common questions (by exact text match).
        popular_rows = conn.execute(
            "SELECT content, COUNT(*) AS count FROM messages "
            "WHERE role = 'user' "
            "GROUP BY content ORDER BY count DESC LIMIT 10"
        ).fetchall()
        popular_questions = [{"question": r["content"], "count": r["count"]} for r in popular_rows]

    return {
        "total_messages": total,
        "total_sessions": total_sessions,
        "active_sessions": active_sessions,
        "messages_per_day": messages_per_day,
        "recent_questions": recent_questions,
        "popular_questions": popular_questions,
    }


