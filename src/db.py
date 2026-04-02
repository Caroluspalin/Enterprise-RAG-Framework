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

load_dotenv()

DB_PATH = Path(os.getenv("CHAT_DB_PATH", "./chat_history.db"))

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
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
# Initialise on import so tables exist before the API serves requests.
# ---------------------------------------------------------------------------
init_db()
