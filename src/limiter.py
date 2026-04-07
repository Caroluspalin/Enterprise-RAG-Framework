"""
limiter.py

In-memory, tier-aware rate limiter for FastAPI endpoints.

Uses a sliding window algorithm: each key (user_id, API key, or IP) keeps a
list of request timestamps.  When a new request arrives, expired entries are
pruned and the current count is compared against the tier's limit.

Tier hierarchy:
  - admin role  -> unlimited (not checked at all)
  - PRO_USER    -> 60 requests per minute
  - FREE_USER   -> 5 requests per minute

The limiter is intentionally in-memory.  When the process restarts, all
windows reset — acceptable for a single-instance deployment.  For
multi-instance setups a Redis backend should replace this module.
"""

import threading
import time
from dataclasses import dataclass, field

# Requests per 60-second sliding window, keyed by tier name.
TIER_LIMITS: dict[str, int] = {
    "FREE_USER": 5,
    "PRO_USER": 60,
}

WINDOW_SECONDS = 60


@dataclass
class _BucketEntry:
    timestamps: list[float] = field(default_factory=list)


class RateLimiter:
    """Thread-safe, in-memory sliding-window rate limiter."""

    def __init__(self) -> None:
        self._buckets: dict[str, _BucketEntry] = {}
        self._lock = threading.Lock()

    def check(
        self,
        key: str,
        tier: str,
        *,
        max_requests: int | None = None,
        window: int | None = None,
    ) -> tuple[bool, int, int]:
        """Test whether *key* may proceed under *tier* limits.

        Parameters:
            key:           Unique identifier (user_id, IP, etc.).
            tier:          Tier name looked up in TIER_LIMITS.
            max_requests:  Override the tier's default limit.
            window:        Override the default window (seconds).

        Returns:
            (allowed, limit, remaining)
            - allowed:   True if the request is within quota.
            - limit:     The maximum requests per window for this tier.
            - remaining: How many requests the caller has left in the current
                         window (0 if blocked).
        """
        limit = max_requests if max_requests is not None else TIER_LIMITS.get(tier)
        if limit is None:
            # Unknown tier (or admin bypass) — allow unconditionally.
            return True, 0, 0

        effective_window = window if window is not None else WINDOW_SECONDS
        now = time.monotonic()
        cutoff = now - effective_window

        with self._lock:
            entry = self._buckets.setdefault(key, _BucketEntry())
            # Prune timestamps that have fallen outside the window.
            entry.timestamps = [t for t in entry.timestamps if t > cutoff]

            current = len(entry.timestamps)
            if current >= limit:
                return False, limit, 0

            entry.timestamps.append(now)
            remaining = limit - current - 1
            return True, limit, remaining

    def reset(self, key: str | None = None) -> None:
        """Clear rate-limit state.  If key is None, clear everything."""
        with self._lock:
            if key is None:
                self._buckets.clear()
            else:
                self._buckets.pop(key, None)


# Module-level singleton used by the FastAPI dependency.
rate_limiter = RateLimiter()
