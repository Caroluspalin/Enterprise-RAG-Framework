"""Unit and integration tests for billing / usage tracking.

Tests verify:
  - Plan limit enforcement (free=100, pro=10k, enterprise=unlimited)
  - check_and_track_usage() increments counters and writes usage_logs
  - UsageLimitExceeded raised at the exact boundary
  - HTTP 402 returned from /api/chat and /api/upload when quota is exhausted
  - Organizations without a DB record get a pass (DEFAULT_TENANT fallback)
  - Existing tests (172+) remain unaffected by billing gates
"""

import json
from unittest.mock import patch

import pytest

import db
from billing import PLAN_LIMITS, UsageLimitExceeded, check_and_track_usage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _admin_id():
    user = db.get_user_by_username("admin")
    return user["id"]


def _create_org_with_plan(plan: str, name: str = "Test Org") -> dict:
    """Create an organization with a specific subscription plan."""
    org = db.create_organization(name, subscription_plan=plan)
    return org


def _exhaust_quota(org_id: str, calls: int) -> None:
    """Simulate the org having used exactly `calls` API calls."""
    with db._connect() as conn:
        conn.execute(
            "UPDATE organizations SET api_calls_count = ? WHERE id = ?",
            (calls, org_id),
        )


# ---------------------------------------------------------------------------
# Unit tests — PLAN_LIMITS constant
# ---------------------------------------------------------------------------

class TestPlanLimits:
    def test_free_plan_limit(self):
        assert PLAN_LIMITS["free"] == 100

    def test_pro_plan_limit(self):
        assert PLAN_LIMITS["pro"] == 10_000

    def test_enterprise_unlimited(self):
        assert PLAN_LIMITS["enterprise"] is None


# ---------------------------------------------------------------------------
# Unit tests — check_and_track_usage()
# ---------------------------------------------------------------------------

class TestCheckAndTrackUsage:
    """Direct tests of the billing enforcement function."""

    def test_increments_counter_on_success(self):
        org = _create_org_with_plan("free")
        check_and_track_usage(org["id"], "/api/v1/chat")
        updated = db.get_organization(org["id"])
        assert updated["api_calls_count"] == 1

    def test_writes_usage_log(self):
        org = _create_org_with_plan("free")
        check_and_track_usage(org["id"], "/api/v1/chat", tokens=42)
        logs = db.get_usage_logs(org["id"])
        assert len(logs) == 1
        assert logs[0]["endpoint"] == "/api/v1/chat"
        assert logs[0]["tokens_used"] == 42

    def test_free_plan_allows_100_calls(self):
        """The 100th call should succeed (counter goes from 99 to 100)."""
        org = _create_org_with_plan("free")
        _exhaust_quota(org["id"], 99)
        # This is call #100 — still within the limit.
        check_and_track_usage(org["id"], "/api/v1/chat")
        updated = db.get_organization(org["id"])
        assert updated["api_calls_count"] == 100

    def test_free_plan_blocks_101st_call(self):
        """The 101st call must raise UsageLimitExceeded."""
        org = _create_org_with_plan("free")
        _exhaust_quota(org["id"], 100)
        with pytest.raises(UsageLimitExceeded) as exc_info:
            check_and_track_usage(org["id"], "/api/v1/chat")
        assert exc_info.value.plan == "free"
        assert exc_info.value.limit == 100
        assert exc_info.value.current == 100

    def test_pro_plan_blocks_at_limit(self):
        org = _create_org_with_plan("pro")
        _exhaust_quota(org["id"], 10_000)
        with pytest.raises(UsageLimitExceeded) as exc_info:
            check_and_track_usage(org["id"], "/api/v1/chat")
        assert exc_info.value.plan == "pro"
        assert exc_info.value.limit == 10_000

    def test_enterprise_plan_never_blocks(self):
        """Enterprise orgs have no ceiling — even absurd counts pass."""
        org = _create_org_with_plan("enterprise")
        _exhaust_quota(org["id"], 999_999)
        # Should NOT raise.
        check_and_track_usage(org["id"], "/api/v1/chat")
        updated = db.get_organization(org["id"])
        assert updated["api_calls_count"] == 1_000_000

    def test_nonexistent_org_gets_pass(self):
        """DEFAULT_TENANT or unknown org_id should not crash."""
        check_and_track_usage("nonexistent-org-id", "/api/v1/chat")
        # No exception, no crash — the function silently skips.

    def test_multiple_calls_increment_sequentially(self):
        org = _create_org_with_plan("free")
        for _ in range(5):
            check_and_track_usage(org["id"], "/api/v1/chat")
        updated = db.get_organization(org["id"])
        assert updated["api_calls_count"] == 5
        logs = db.get_usage_logs(org["id"])
        assert len(logs) == 5

    def test_usage_log_records_different_endpoints(self):
        org = _create_org_with_plan("pro")
        check_and_track_usage(org["id"], "/api/v1/chat", tokens=10)
        check_and_track_usage(org["id"], "/api/v1/upload", tokens=0)
        logs = db.get_usage_logs(org["id"])
        endpoints = {log["endpoint"] for log in logs}
        assert endpoints == {"/api/v1/chat", "/api/v1/upload"}


# ---------------------------------------------------------------------------
# Unit tests — UsageLimitExceeded exception
# ---------------------------------------------------------------------------

class TestUsageLimitExceededException:
    def test_attributes(self):
        exc = UsageLimitExceeded("free", 100, 100)
        assert exc.plan == "free"
        assert exc.limit == 100
        assert exc.current == 100

    def test_message_format(self):
        exc = UsageLimitExceeded("pro", 10_000, 10_000)
        assert "pro" in str(exc)
        assert "10000" in str(exc)


# ---------------------------------------------------------------------------
# Unit tests — db.py billing helpers
# ---------------------------------------------------------------------------

class TestDbBillingHelpers:
    def test_increment_api_calls(self):
        org = _create_org_with_plan("free")
        new_count = db.increment_api_calls(org["id"])
        assert new_count == 1
        new_count = db.increment_api_calls(org["id"])
        assert new_count == 2

    def test_reset_api_calls(self):
        org = _create_org_with_plan("free")
        _exhaust_quota(org["id"], 50)
        db.reset_api_calls(org["id"])
        updated = db.get_organization(org["id"])
        assert updated["api_calls_count"] == 0

    def test_add_usage_log(self):
        org = _create_org_with_plan("free")
        log_entry = db.add_usage_log(org["id"], "/api/v1/chat", tokens_used=123)
        assert log_entry["organization_id"] == org["id"]
        assert log_entry["tokens_used"] == 123
        assert log_entry["endpoint"] == "/api/v1/chat"

    def test_get_usage_logs_ordered_by_timestamp(self):
        org = _create_org_with_plan("free")
        db.add_usage_log(org["id"], "/api/v1/chat", tokens_used=10)
        db.add_usage_log(org["id"], "/api/v1/upload", tokens_used=20)
        logs = db.get_usage_logs(org["id"])
        # Newest first.
        assert logs[0]["tokens_used"] == 20
        assert logs[1]["tokens_used"] == 10

    def test_get_usage_logs_limit(self):
        org = _create_org_with_plan("free")
        for i in range(10):
            db.add_usage_log(org["id"], "/api/v1/chat", tokens_used=i)
        logs = db.get_usage_logs(org["id"], limit=3)
        assert len(logs) == 3

    def test_create_organization_with_plan(self):
        org = db.create_organization("Pro Corp", subscription_plan="pro")
        assert org["subscription_plan"] == "pro"
        assert org["api_calls_count"] == 0
        assert org["stripe_customer_id"] is None

    def test_organization_default_plan_is_free(self):
        org = db.create_organization("Startup Inc")
        assert org["subscription_plan"] == "free"


# ---------------------------------------------------------------------------
# Integration tests — HTTP 402 from /api/chat
# ---------------------------------------------------------------------------

class TestBillingGateChat:
    """Verify that /api/chat returns 402 when the org's quota is exhausted."""

    def test_chat_returns_402_when_free_quota_exhausted(self, chat_client):
        admin = db.get_user_by_username("admin")
        org = _create_org_with_plan("free", "Chat Org")
        # Assign admin to this org so _resolve_tenant_id finds it.
        with db._connect() as conn:
            conn.execute(
                "UPDATE users SET organization_id = ? WHERE id = ?",
                (org["id"], admin["id"]),
            )
        _exhaust_quota(org["id"], 100)

        resp = chat_client.post("/api/v1/chat", json={
            "question": "test question",
            "user_id": admin["id"],
        })
        assert resp.status_code == 402
        assert "limit" in resp.json()["detail"].lower()

    def test_chat_succeeds_within_quota(self, chat_client):
        admin = db.get_user_by_username("admin")
        org = _create_org_with_plan("free", "Within Quota Org")
        with db._connect() as conn:
            conn.execute(
                "UPDATE users SET organization_id = ? WHERE id = ?",
                (org["id"], admin["id"]),
            )
        _exhaust_quota(org["id"], 50)

        resp = chat_client.post("/api/v1/chat", json={
            "question": "test question",
            "user_id": admin["id"],
        })
        assert resp.status_code == 200

    def test_chat_402_includes_plan_name(self, chat_client):
        admin = db.get_user_by_username("admin")
        org = _create_org_with_plan("pro", "Pro Org")
        with db._connect() as conn:
            conn.execute(
                "UPDATE users SET organization_id = ? WHERE id = ?",
                (org["id"], admin["id"]),
            )
        _exhaust_quota(org["id"], 10_000)

        resp = chat_client.post("/api/v1/chat", json={
            "question": "test",
            "user_id": admin["id"],
        })
        assert resp.status_code == 402
        assert "pro" in resp.json()["detail"].lower()

    def test_enterprise_chat_never_blocked(self, chat_client):
        admin = db.get_user_by_username("admin")
        org = _create_org_with_plan("enterprise", "Enterprise Org")
        with db._connect() as conn:
            conn.execute(
                "UPDATE users SET organization_id = ? WHERE id = ?",
                (org["id"], admin["id"]),
            )
        _exhaust_quota(org["id"], 999_999)

        resp = chat_client.post("/api/v1/chat", json={
            "question": "enterprise question",
            "user_id": admin["id"],
        })
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Integration tests — HTTP 402 from /api/upload
# ---------------------------------------------------------------------------

class TestBillingGateUpload:
    """Verify that /api/upload returns 402 when the org's quota is exhausted."""

    def test_upload_returns_402_when_quota_exhausted(self, client):
        """Force tenant resolution to a known org, then verify 402."""
        org = _create_org_with_plan("free", "Upload Org")
        _exhaust_quota(org["id"], 100)

        # Patch _resolve_tenant_id to return our exhausted org, bypassing
        # the form-data extraction complexity in multipart uploads.
        with patch("api._resolve_tenant_id", return_value=org["id"]):
            admin = db.get_user_by_username("admin")
            resp = client.post(
                "/api/v1/upload",
                data={"user_id": admin["id"]},
                files={"file": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")},
            )
        assert resp.status_code == 402
        assert "limit" in resp.json()["detail"].lower()

    def test_upload_succeeds_within_quota(self, client):
        """Billing gate passes when org is within quota."""
        org = _create_org_with_plan("free", "Upload OK Org")
        _exhaust_quota(org["id"], 10)

        with patch("api._resolve_tenant_id", return_value=org["id"]), \
             patch("api._ingest_pdf"):
            admin = db.get_user_by_username("admin")
            resp = client.post(
                "/api/v1/upload",
                data={"user_id": admin["id"]},
                files={"file": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")},
            )
        # Not 402 means billing gate passed.
        assert resp.status_code != 402
