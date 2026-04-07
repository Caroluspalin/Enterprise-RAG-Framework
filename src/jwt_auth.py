"""
jwt_auth.py

JWT access token generation and validation for API authentication.

Provides a lightweight JWT layer on top of the existing API key auth so
that browser clients and external integrations can authenticate with
short-lived signed tokens instead of long-lived API keys:

  make_access_token(user_id, role) → opaque signed token string
  decode_access_token(token)       → {"sub": user_id, "role": role} or None

Tokens expire after JWT_EXPIRY_SECONDS (default 3600 = 1 hour).
The signing key is JWT_SECRET from the environment.  In production this
MUST be a cryptographically random string (min 32 bytes).  The default
value is only safe for local development.

Algorithm: HS256 (HMAC-SHA256) — symmetric, fast, suitable for single-
service tokens.  Switch to RS256 if tokens need to be verified by
multiple independent services.
"""

import os
from datetime import datetime, timedelta, timezone

import jwt

JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-jwt-secret-change-in-production")
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRY_SECONDS: int = int(os.getenv("JWT_EXPIRY_SECONDS", "3600"))


def make_access_token(
    user_id: str,
    role: str,
    exp_seconds: int = JWT_EXPIRY_SECONDS,
) -> str:
    """Create a signed JWT access token carrying the user's identity and role.

    The token is short-lived (default 1 h) and must be re-issued after
    expiry.  It is self-contained — no DB lookup is needed to verify it.
    """
    now = datetime.now(timezone.utc)
    payload: dict = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(seconds=exp_seconds),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Validate and decode a JWT access token.

    Returns the payload dict (with at least "sub" and "role") on success,
    or None if the token is invalid, expired, or tampered with.

    Callers must NOT trust the returned role without calling this function —
    it performs full signature verification and expiry checks.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        # Both claims must be present for this to be a valid auth token.
        if "sub" not in payload or "role" not in payload:
            return None
        return payload
    except jwt.PyJWTError:
        # Catches ExpiredSignatureError, InvalidSignatureError, etc.
        return None
