"""
audit.py

Audit logging for security-critical operations.

Every admin action, authentication event, and document mutation is recorded
in the audit_log table so that incidents can be investigated after the fact.
"""

import json
from datetime import datetime, timezone
from uuid import uuid4

from db import _connect


def log_event(
    user_id: str | None,
    action: str,
    ip_address: str | None = None,
    details: dict | None = None,
    organization_id: str | None = None,
) -> None:
    """Write a single audit log entry to the database.

    Parameters:
        user_id:         The acting user's ID, or None for anonymous/failed attempts.
        action:          A short uppercase label (e.g. LOGIN_SUCCESS, DOC_UPLOADED).
        ip_address:      Client IP from the request, if available.
        details:         Arbitrary metadata stored as a JSON string.
        organization_id: The tenant this event belongs to, for per-org audit trails.
    """
    entry_id = uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    details_json = json.dumps(details) if details else None
    with _connect() as conn:
        conn.execute(
            "INSERT INTO audit_log (id, timestamp, user_id, organization_id, action, ip_address, details) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (entry_id, now, user_id, organization_id, action, ip_address, details_json),
        )


def get_audit_logs(limit: int = 100) -> list[dict]:
    """Return the most recent audit log entries, newest first.

    The details column is deserialised from JSON back to a dict.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, timestamp, user_id, organization_id, action, ip_address, details "
            "FROM audit_log ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()

    logs = []
    for r in rows:
        entry = dict(r)
        if entry["details"]:
            entry["details"] = json.loads(entry["details"])
        logs.append(entry)
    return logs
