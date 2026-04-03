"""
db.py

Lightweight SQLite persistence for chat sessions and messages.

Uses Python's built-in sqlite3 module — no extra dependencies required.
The database file is created alongside the ChromaDB data directory so that
all persistent state lives in one predictable location.

Tables:
  sessions  — one row per conversation (user_id groups by user)
  messages  — one row per user or assistant turn within a session
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from passlib.hash import bcrypt

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
    created_at    TEXT NOT NULL
);

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
"""


def _connect() -> sqlite3.Connection:
    """Open a connection with foreign-key enforcement and Row factory."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create tables and indexes if they don't already exist."""
    with _connect() as conn:
        conn.executescript(_SCHEMA_SQL)


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

def create_user(username: str, password: str, name: str, role: str = "user") -> dict:
    """Create a new user with a bcrypt-hashed password."""
    user_id = uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    password_hash = bcrypt.hash(password)
    with _connect() as conn:
        conn.execute(
            "INSERT INTO users (id, username, password_hash, name, role, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, password_hash, name, role, now),
        )
    return {"id": user_id, "username": username, "name": name, "role": role, "created_at": now}


def verify_user(username: str, password: str) -> dict | None:
    """Look up a user by username and verify the password.

    Returns the user dict (without password_hash) on success, None on failure.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, name, role, created_at "
            "FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if not row:
        return None
    user = dict(row)
    if not bcrypt.verify(password, user["password_hash"]):
        return None
    # Never return the hash to callers.
    del user["password_hash"]
    return user


def get_user_by_username(username: str) -> dict | None:
    """Return a user by username (without password_hash), or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, username, name, role, created_at FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    return dict(row) if row else None


def list_users() -> list[dict]:
    """Return all users (without password hashes)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, username, name, role, created_at FROM users ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


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


# ---------------------------------------------------------------------------
# Initialise on import so tables exist before the API serves requests.
# ---------------------------------------------------------------------------
init_db()
_seed_default_admin()
