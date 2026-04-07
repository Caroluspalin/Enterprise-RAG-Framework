"""
security.py

HTTP security headers middleware and error-safe exception handling for FastAPI.

Adds defense-in-depth headers to every response.  These protect against
clickjacking, MIME-sniffing, XSS, and downgrade attacks even if the
reverse proxy (Render / Vercel) doesn't add them.

Also catches unhandled exceptions at the middleware level to prevent stack
traces and internal details from leaking to clients.
"""

import logging
import os

from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

log = logging.getLogger("api")

# In production (HTTPS) we enable HSTS.  In development we skip it so that
# localhost over plain HTTP keeps working without browser warnings.
_ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Content-Security-Policy — restrictive baseline.  Endpoints that need
# relaxed rules (e.g. SSE streaming) still work because CSP applies to
# rendered HTML, not raw JSON/SSE responses consumed by JS.
_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject standard security headers and catch unhandled exceptions."""

    async def dispatch(self, request: Request, call_next) -> Response:
        try:
            response = await call_next(request)
        except Exception:
            # Catch any unhandled exception that bubbled through the ASGI
            # stack so that raw tracebacks never reach the client.
            log.exception(
                "Unhandled error on %s %s", request.method, request.url.path
            )
            response = JSONResponse(
                status_code=500,
                content={"detail": "Internal server error."},
            )

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = _CSP
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )

        # HSTS only in production — tells browsers to always use HTTPS
        # for this domain for the next year.
        if _ENVIRONMENT == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        return response
