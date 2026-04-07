"""
rbac.py

Role-Based Access Control dependency for FastAPI endpoints.

Provides a require_role() factory that returns a FastAPI dependency.
The dependency resolves the caller's role from either:
  1. An API key (X-Widget-Key header) — uses the key's stored role.
  2. A user_id in query params or JSON body — looks up the user's role in DB.
  3. Falls back to None (anonymous) if neither is present.

If the resolved role is not in the allowed list, HTTP 403 is returned.

Role hierarchy (most to least privileged):
  owner  — full control over the organisation
  admin  — manage users, documents, settings
  member — chat + read documents
  viewer — read-only access
"""

from fastapi import HTTPException, Request

from db import get_user_by_id, verify_api_key


# Ordered from most to least privileged for reference.
ROLE_HIERARCHY = ["owner", "admin", "member", "viewer"]


def _extract_user_id_from_request(request: Request) -> str | None:
    """Best-effort extraction of user_id from the request.

    Checks query parameters first (used by GET/DELETE endpoints), then
    falls back to peeking at the cached JSON body if available.
    """
    user_id = request.query_params.get("user_id")
    if user_id and user_id != "anonymous":
        return user_id
    return None


async def resolve_role(request: Request) -> str | None:
    """Determine the RBAC role for the current request.

    Resolution order:
      0. JWT Bearer token (Authorization: Bearer <signed-jwt>).
      1. API key's role (from X-Widget-Key header).
      2. Authenticated user's role (from user_id query param or JSON body).
      3. None for anonymous requests.
    """
    import asyncio

    # 0. Try JWT Bearer token — browser / API clients using short-lived tokens.
    #    We try JWT before API keys because JWT carries an explicit role claim
    #    and does not require a DB lookup.  If decoding fails (invalid, expired,
    #    or the Bearer value is actually the INTERNAL_ADMIN_SECRET string),
    #    we fall through to the next resolution step.
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        from jwt_auth import decode_access_token
        payload = decode_access_token(token)
        if payload is not None:
            return payload.get("role")

    # 1. Try API key first — widget/external integrations.
    client_key = request.headers.get("X-Widget-Key", "")
    if client_key:
        api_key_info = await asyncio.to_thread(verify_api_key, client_key)
        if api_key_info:
            return api_key_info.get("role", "member")

    # 2. Try user_id from query params.
    user_id = _extract_user_id_from_request(request)
    if user_id:
        user = await asyncio.to_thread(get_user_by_id, user_id)
        if user:
            return user["role"]

    # 3. Try user_id from JSON body (for POST endpoints like /api/chat).
    # request.body() is idempotent in Starlette — the bytes are cached
    # internally, so FastAPI's Pydantic parsing still works afterwards.
    try:
        body_bytes = await request.body()
        if body_bytes:
            import json
            body = json.loads(body_bytes)
            body_user_id = body.get("user_id")
            if body_user_id and body_user_id != "anonymous":
                user = await asyncio.to_thread(get_user_by_id, body_user_id)
                if user:
                    return user["role"]
    except Exception:
        # Not JSON (e.g. multipart form) — fall through.
        pass

    # 4. Try user_id from form data (for multipart endpoints like /api/upload).
    try:
        form = await request.form()
        form_user_id = form.get("user_id")
        if form_user_id and form_user_id != "anonymous":
            user = await asyncio.to_thread(get_user_by_id, str(form_user_id))
            if user:
                return user["role"]
    except Exception:
        pass

    return None


def require_role(allowed_roles: list[str]):
    """Factory that returns a FastAPI dependency enforcing RBAC.

    Usage:
        @app.post("/api/upload", dependencies=[Depends(require_role(["owner", "admin"]))])

    If the caller's role is not in allowed_roles, raises HTTP 403.
    Anonymous requests (no identifiable user or API key) are also rejected
    with 403 unless the endpoint explicitly allows unauthenticated access
    by other means.
    """
    async def _check_role(request: Request):
        role = await resolve_role(request)
        if role is None or role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Forbidden: requires one of {allowed_roles}, got '{role}'.",
            )
        # Stash the resolved role on request.state so endpoints can use it
        # without re-resolving.
        request.state.rbac_role = role

    return _check_role
