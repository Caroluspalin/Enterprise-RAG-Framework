"""
billing.py

Subscription plan limits and usage tracking for multi-tenant billing.

Each organization has a subscription_plan (free / pro / enterprise) that
determines how many API calls it can make per billing cycle (calendar month).
The check_and_track_usage() function is called on every billable endpoint
to enforce limits and record usage.

Plan limits:
  free       — 100 API calls/month
  pro        — 10 000 API calls/month
  enterprise — unlimited
"""

from db import add_usage_log, get_organization, increment_api_calls
from logger import get_logger

log = get_logger("billing")

# Monthly API call limits per subscription plan.
PLAN_LIMITS: dict[str, int | None] = {
    "free": 100,
    "pro": 10_000,
    "enterprise": None,  # unlimited
}


class UsageLimitExceeded(Exception):
    """Raised when an organization exceeds its plan's API call quota."""

    def __init__(self, plan: str, limit: int, current: int):
        self.plan = plan
        self.limit = limit
        self.current = current
        super().__init__(
            f"Usage limit exceeded: plan '{plan}' allows {limit} calls/month, "
            f"current count is {current}."
        )


def check_and_track_usage(
    organization_id: str,
    endpoint: str,
    tokens: int = 0,
) -> None:
    """Verify the organization is within its plan limits, then record usage.

    Resolution:
      1. Look up the org's subscription_plan and current api_calls_count.
      2. If the plan has a limit and the count has reached it, raise
         UsageLimitExceeded (the API layer converts this to HTTP 402).
      3. Otherwise, atomically increment the counter and write a usage_log row.

    This function is synchronous — API endpoints call it via asyncio.to_thread().
    """
    org = get_organization(organization_id)

    # Orgs that don't exist in the DB (e.g. DEFAULT_TENANT before any org is
    # created) get a pass — they operate under implicit free-tier rules but
    # without a counter to increment.
    if not org:
        log.debug("No org record for tenant '%s' — skipping billing check", organization_id)
        return

    plan = org.get("subscription_plan", "free")
    limit = PLAN_LIMITS.get(plan)
    current_count = org.get("api_calls_count", 0)

    # Enterprise plans have no ceiling.
    if limit is not None and current_count >= limit:
        log.warning(
            "Usage limit hit | org=%s plan=%s limit=%d count=%d endpoint=%s",
            organization_id, plan, limit, current_count, endpoint,
        )
        raise UsageLimitExceeded(plan, limit, current_count)

    # Within limits — increment counter and log the call.
    new_count = increment_api_calls(organization_id)
    add_usage_log(organization_id, endpoint, tokens_used=tokens)

    log.debug(
        "Usage recorded | org=%s plan=%s count=%d/%s endpoint=%s tokens=%d",
        organization_id, plan, new_count,
        str(limit) if limit else "unlimited", endpoint, tokens,
    )
