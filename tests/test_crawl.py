"""
Tests for the URL crawling feature.

Covers:
  - db.py CRUD for crawled_urls table
  - crawl.py: content hashing, link discovery, crawl_site, index_crawled_pages
  - api.py: POST /api/v1/crawl, GET /api/v1/crawled-urls, DELETE /api/v1/crawled-urls/{id}

All network I/O (trafilatura.fetch_url) is mocked — no real HTTP requests
are made during tests.
"""

import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import db


# ---------------------------------------------------------------------------
# DB CRUD tests for crawled_urls
# ---------------------------------------------------------------------------

class TestCrawledUrlsCRUD:
    """Verify crawled_urls table operations."""

    def test_create_and_get(self):
        record = db.create_crawled_url("https://example.com", tenant_id="t1")
        assert record["url"] == "https://example.com"
        assert record["tenant_id"] == "t1"
        assert record["status"] == "pending"
        assert record["page_count"] == 0

        fetched = db.get_crawled_url(record["id"])
        assert fetched is not None
        assert fetched["url"] == "https://example.com"

    def test_get_by_url(self):
        db.create_crawled_url("https://a.com", tenant_id="t1")
        db.create_crawled_url("https://a.com", tenant_id="t2")

        found = db.get_crawled_url_by_url("https://a.com", "t1")
        assert found is not None
        assert found["tenant_id"] == "t1"

        # Different tenant should find the other record.
        found2 = db.get_crawled_url_by_url("https://a.com", "t2")
        assert found2 is not None
        assert found2["tenant_id"] == "t2"

        # Non-existent combination returns None.
        assert db.get_crawled_url_by_url("https://a.com", "t_missing") is None

    def test_list_crawled_urls_tenant_scoped(self):
        db.create_crawled_url("https://a.com", tenant_id="t1")
        db.create_crawled_url("https://b.com", tenant_id="t1")
        db.create_crawled_url("https://c.com", tenant_id="t2")

        t1_urls = db.list_crawled_urls("t1")
        assert len(t1_urls) == 2

        t2_urls = db.list_crawled_urls("t2")
        assert len(t2_urls) == 1

    def test_update_crawled_url(self):
        record = db.create_crawled_url("https://example.com", tenant_id="t1")

        updated = db.update_crawled_url(
            record["id"],
            status="done",
            page_count=5,
            content_hash="abc123",
            last_crawled_at="2026-04-08T12:00:00Z",
        )
        assert updated is True

        fetched = db.get_crawled_url(record["id"])
        assert fetched["status"] == "done"
        assert fetched["page_count"] == 5
        assert fetched["content_hash"] == "abc123"

    def test_update_error_message(self):
        record = db.create_crawled_url("https://fail.com", tenant_id="t1")
        db.update_crawled_url(record["id"], status="error", error_message="Connection timed out")
        fetched = db.get_crawled_url(record["id"])
        assert fetched["status"] == "error"
        assert fetched["error_message"] == "Connection timed out"

    def test_update_nonexistent(self):
        assert db.update_crawled_url("nonexistent", status="done") is False

    def test_delete_crawled_url(self):
        record = db.create_crawled_url("https://example.com", tenant_id="t1")
        assert db.delete_crawled_url(record["id"]) is True
        assert db.get_crawled_url(record["id"]) is None

    def test_delete_nonexistent(self):
        assert db.delete_crawled_url("nonexistent") is False


# ---------------------------------------------------------------------------
# crawl.py unit tests
# ---------------------------------------------------------------------------

class TestCrawlHelpers:
    """Test pure functions and crawl logic with mocked network I/O."""

    def test_compute_content_hash(self):
        from crawl import compute_content_hash
        h = compute_content_hash("hello world")
        assert h == hashlib.sha256(b"hello world").hexdigest()

    def test_is_same_domain(self):
        from crawl import _is_same_domain
        assert _is_same_domain("https://example.com/a", "https://example.com/b")
        assert not _is_same_domain("https://example.com", "https://other.com/x")

    def test_normalise_url(self):
        from crawl import _normalise_url
        assert _normalise_url("https://example.com/page/") == "https://example.com/page"
        assert _normalise_url("https://example.com/page#section") == "https://example.com/page"
        # Root path normalised to /
        assert _normalise_url("https://example.com") == "https://example.com/"

    @patch("crawl.trafilatura.fetch_url")
    @patch("crawl.trafilatura.extract")
    def test_fetch_and_extract_success(self, mock_extract, mock_fetch):
        from crawl import fetch_and_extract
        mock_fetch.return_value = "<html>Hello</html>"
        mock_extract.return_value = "Extracted text content"
        result = fetch_and_extract("https://example.com")
        assert result == "Extracted text content"

    @patch("crawl.trafilatura.fetch_url")
    def test_fetch_and_extract_failure(self, mock_fetch):
        from crawl import fetch_and_extract
        mock_fetch.return_value = None
        assert fetch_and_extract("https://example.com") is None

    @patch("crawl.trafilatura.fetch_url")
    @patch("crawl.trafilatura.extract")
    def test_fetch_and_extract_empty_text(self, mock_extract, mock_fetch):
        from crawl import fetch_and_extract
        mock_fetch.return_value = "<html></html>"
        mock_extract.return_value = ""
        assert fetch_and_extract("https://example.com") is None

    @patch("crawl.trafilatura.fetch_url")
    def test_discover_links(self, mock_fetch):
        from crawl import discover_links
        mock_fetch.return_value = """
        <html><body>
            <a href="/about">About</a>
            <a href="https://example.com/contact">Contact</a>
            <a href="https://external.com/nope">External</a>
        </body></html>
        """
        links = discover_links("https://example.com/")
        # Should only include same-domain links.
        assert "https://example.com/about" in links
        assert "https://example.com/contact" in links
        # External link should be excluded.
        assert not any("external.com" in l for l in links)

    @patch("crawl.discover_links")
    @patch("crawl.fetch_and_extract")
    def test_crawl_site_respects_max_pages(self, mock_extract, mock_links):
        from crawl import crawl_site
        mock_extract.return_value = "Some page text"
        mock_links.return_value = [
            f"https://example.com/page{i}" for i in range(20)
        ]
        results = crawl_site("https://example.com", max_depth=1, max_pages=3)
        assert len(results) == 3

    @patch("crawl.discover_links")
    @patch("crawl.fetch_and_extract")
    def test_crawl_site_respects_max_depth(self, mock_extract, mock_links):
        from crawl import crawl_site
        # Only the start URL returns links.
        call_count = {"n": 0}

        def _extract(url):
            return f"Content of {url}"

        def _links(url):
            call_count["n"] += 1
            if call_count["n"] <= 1:
                return ["https://example.com/page1"]
            return []

        mock_extract.side_effect = _extract
        mock_links.side_effect = _links

        results = crawl_site("https://example.com", max_depth=0, max_pages=50)
        # With depth=0, only the start URL is crawled — no links followed.
        assert len(results) == 1

    @patch("crawl.discover_links")
    @patch("crawl.fetch_and_extract")
    def test_crawl_site_deduplicates_urls(self, mock_extract, mock_links):
        from crawl import crawl_site
        mock_extract.return_value = "Page text"
        # All links point back to the same URL.
        mock_links.return_value = ["https://example.com/"]
        results = crawl_site("https://example.com/", max_depth=2, max_pages=10)
        assert len(results) == 1


class TestIndexCrawledPages:
    """Test index_crawled_pages with a mocked vector store and embeddings."""

    def _make_pages(self, n: int = 2) -> list[dict]:
        return [
            {
                "url": f"https://example.com/page{i}",
                "text": f"Content of page {i}. " * 50,
                "content_hash": hashlib.sha256(f"page{i}".encode()).hexdigest(),
            }
            for i in range(n)
        ]

    @patch("crawl.OpenAIEmbeddings")
    @patch("crawl.get_vector_store")
    def test_indexes_pages(self, mock_get_store, mock_embeddings_cls):
        from crawl import index_crawled_pages

        mock_store = MagicMock()
        mock_get_store.return_value = mock_store

        mock_embed = MagicMock()
        mock_embed.embed_documents.return_value = [[0.1] * 10] * 100
        mock_embeddings_cls.return_value = mock_embed

        pages = self._make_pages(2)
        chunks_added, content_hash = index_crawled_pages(
            pages, tenant_id="t1", crawl_record_id="crawl-1",
        )

        assert chunks_added > 0
        assert content_hash != ""
        mock_store.add_documents.assert_called_once()
        mock_store.delete_by_metadata.assert_called_once_with(
            "crawl_record_id", "crawl-1", tenant_id="t1",
        )

    @patch("crawl.OpenAIEmbeddings")
    @patch("crawl.get_vector_store")
    def test_skips_when_content_unchanged(self, mock_get_store, mock_embeddings_cls):
        from crawl import index_crawled_pages, compute_content_hash
        import hashlib as _hashlib

        pages = self._make_pages(1)
        # Compute what the combined hash would be.
        combined = _hashlib.sha256()
        for page in sorted(pages, key=lambda p: p["url"]):
            combined.update(page["content_hash"].encode())
        expected_hash = combined.hexdigest()

        chunks_added, content_hash = index_crawled_pages(
            pages, tenant_id="t1", crawl_record_id="crawl-2",
            previous_content_hash=expected_hash,
        )
        assert chunks_added == 0
        assert content_hash == expected_hash
        # Vector store should NOT have been called.
        mock_get_store.assert_not_called()

    def test_empty_pages(self):
        from crawl import index_crawled_pages
        chunks, h = index_crawled_pages([], "t1", "crawl-3")
        assert chunks == 0
        assert h == ""


# ---------------------------------------------------------------------------
# API integration tests
# ---------------------------------------------------------------------------

TEST_ADMIN_SECRET = "test-secret-for-ci"


@pytest.fixture()
def crawl_client(monkeypatch):
    """TestClient with mocked crawl module and vector store."""
    monkeypatch.setenv("INTERNAL_ADMIN_SECRET", TEST_ADMIN_SECRET)

    mock_retriever = MagicMock()
    mock_retriever.invoke.return_value = []

    with patch("api._get_components") as mock_gc:
        mock_gc.return_value = (mock_retriever, MagicMock(), MagicMock())

        import api as api_module
        monkeypatch.setattr(api_module, "INTERNAL_ADMIN_SECRET", TEST_ADMIN_SECRET)
        monkeypatch.setattr(api_module, "WIDGET_API_KEY_LEGACY", "")
        monkeypatch.setattr(api_module, "CHAT_RATE_LIMIT", "9999/minute")

        from fastapi.testclient import TestClient
        from limiter import rate_limiter
        rate_limiter.reset()
        api_module.limiter.reset()
        yield TestClient(api_module.app)


class TestCrawlEndpoints:
    """Integration tests for crawl-related API endpoints."""

    def test_crawl_requires_auth(self, crawl_client):
        """POST /api/v1/crawl should reject unauthenticated requests."""
        resp = crawl_client.post("/api/v1/crawl", json={"url": "https://example.com"})
        assert resp.status_code == 403

    def test_crawl_rejects_viewer(self, crawl_client):
        """Viewer role cannot trigger crawls."""
        viewer = db.create_user("crawl_viewer", "pass", "Viewer", role="viewer")
        resp = crawl_client.post(
            "/api/v1/crawl",
            json={"url": "https://example.com", "user_id": viewer["id"]},
        )
        assert resp.status_code == 403

    def test_crawl_rejects_member(self, crawl_client):
        """Member role cannot trigger crawls."""
        member = db.create_user("crawl_member", "pass", "Member", role="member")
        resp = crawl_client.post(
            "/api/v1/crawl",
            json={"url": "https://example.com", "user_id": member["id"]},
        )
        assert resp.status_code == 403

    @patch("crawl.crawl_site")
    @patch("crawl.index_crawled_pages")
    def test_crawl_success(self, mock_index, mock_crawl, crawl_client):
        """Admin can trigger a successful crawl."""
        admin = db.get_user_by_username("admin")
        mock_crawl.return_value = [
            {"url": "https://example.com/", "text": "Hello", "content_hash": "abc"},
        ]
        mock_index.return_value = (5, "combined_hash")

        resp = crawl_client.post(
            "/api/v1/crawl",
            json={
                "url": "https://example.com",
                "max_depth": 1,
                "max_pages": 10,
                "user_id": admin["id"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["pages_crawled"] == 1
        assert data["chunks_indexed"] == 5
        assert "crawl_id" in data

    @patch("crawl.crawl_site")
    def test_crawl_failure_returns_500(self, mock_crawl, crawl_client):
        """If crawl_site raises, the endpoint returns 500."""
        admin = db.get_user_by_username("admin")
        mock_crawl.side_effect = RuntimeError("Connection refused")

        resp = crawl_client.post(
            "/api/v1/crawl",
            json={"url": "https://example.com", "user_id": admin["id"]},
        )
        assert resp.status_code == 500
        assert "Connection refused" in resp.json()["detail"]

    def test_list_crawled_urls_empty(self, crawl_client):
        """GET /api/v1/crawled-urls returns empty list when nothing crawled."""
        admin = db.get_user_by_username("admin")
        resp = crawl_client.get(
            f"/api/v1/crawled-urls?user_id={admin['id']}",
        )
        assert resp.status_code == 200
        assert resp.json()["crawled_urls"] == []

    @patch("crawl.crawl_site")
    @patch("crawl.index_crawled_pages")
    def test_list_crawled_urls_after_crawl(self, mock_index, mock_crawl, crawl_client):
        """After a crawl, the URL appears in the list."""
        admin = db.get_user_by_username("admin")
        mock_crawl.return_value = [
            {"url": "https://example.com/", "text": "Hi", "content_hash": "x"},
        ]
        mock_index.return_value = (3, "hash123")

        crawl_client.post(
            "/api/v1/crawl",
            json={"url": "https://example.com", "user_id": admin["id"]},
        )

        resp = crawl_client.get(
            f"/api/v1/crawled-urls?user_id={admin['id']}",
        )
        urls = resp.json()["crawled_urls"]
        assert len(urls) == 1
        assert urls[0]["url"] == "https://example.com"
        assert urls[0]["status"] == "done"

    @patch("crawl.crawl_site")
    @patch("crawl.index_crawled_pages")
    def test_delete_crawled_url(self, mock_index, mock_crawl, crawl_client):
        """DELETE /api/v1/crawled-urls/{id} removes the record and chunks."""
        admin = db.get_user_by_username("admin")
        mock_crawl.return_value = [
            {"url": "https://example.com/", "text": "Hi", "content_hash": "x"},
        ]
        mock_index.return_value = (3, "hash123")

        crawl_resp = crawl_client.post(
            "/api/v1/crawl",
            json={"url": "https://example.com", "user_id": admin["id"]},
        )
        crawl_id = crawl_resp.json()["crawl_id"]

        with patch("api.get_vector_store") as mock_vs:
            mock_store = MagicMock()
            mock_store.delete_by_metadata.return_value = 3
            mock_vs.return_value = mock_store

            resp = crawl_client.delete(
                f"/api/v1/crawled-urls/{crawl_id}?user_id={admin['id']}",
            )
        assert resp.status_code == 200
        assert resp.json()["chunks_removed"] == 3

        # Record should be gone from the list.
        list_resp = crawl_client.get(
            f"/api/v1/crawled-urls?user_id={admin['id']}",
        )
        assert len(list_resp.json()["crawled_urls"]) == 0

    def test_delete_nonexistent_crawl(self, crawl_client):
        """DELETE /api/v1/crawled-urls/{id} returns 404 for unknown id."""
        admin = db.get_user_by_username("admin")
        resp = crawl_client.delete(
            f"/api/v1/crawled-urls/nonexistent?user_id={admin['id']}",
        )
        assert resp.status_code == 404

    def test_delete_crawl_wrong_tenant(self, crawl_client):
        """Cannot delete another tenant's crawl record."""
        # Create a crawl record directly in the DB for tenant "other".
        record = db.create_crawled_url("https://other.com", tenant_id="other_tenant")

        admin = db.get_user_by_username("admin")
        resp = crawl_client.delete(
            f"/api/v1/crawled-urls/{record['id']}?user_id={admin['id']}",
        )
        # Admin is in DEFAULT_TENANT, record is in "other_tenant" — 404.
        assert resp.status_code == 404

    def test_list_crawled_urls_requires_auth(self, crawl_client):
        """Unauthenticated requests to list are rejected."""
        resp = crawl_client.get("/api/v1/crawled-urls")
        assert resp.status_code == 403

    def test_delete_crawl_viewer_forbidden(self, crawl_client):
        """Viewer cannot delete crawled URLs."""
        viewer = db.create_user("del_viewer", "pass", "V", role="viewer")
        record = db.create_crawled_url("https://example.com", tenant_id="default")
        resp = crawl_client.delete(
            f"/api/v1/crawled-urls/{record['id']}?user_id={viewer['id']}",
        )
        assert resp.status_code == 403
