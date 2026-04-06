"""
Shared pytest fixtures for the B2B RAG Chatbot test suite.

Key design decisions:
- Each test gets a fresh temporary SQLite database to prevent cross-test contamination.
- The ChromaDB retriever is mocked at the api module level so tests don't need
  OpenAI keys or a real vector store.
- INTERNAL_ADMIN_SECRET is set to a known value so admin endpoint tests can
  authenticate without relying on .env files.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Set test environment variables BEFORE any src imports, because db.py
# runs init_db() and _seed_default_admin() at import time.
TEST_ADMIN_SECRET = "test-secret-for-ci"


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Give every test its own SQLite database.

    Monkeypatches DB_PATH in the db module and re-runs schema creation
    so each test starts with a clean users/sessions/messages/api_keys state
    (plus the default admin seed).
    """
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("CHAT_DB_PATH", str(db_file))

    import db as db_module
    monkeypatch.setattr(db_module, "DB_PATH", db_file)
    db_module.init_db()
    db_module._seed_default_admin()

    yield


@pytest.fixture()
def client(monkeypatch):
    """Return a FastAPI TestClient with the retriever mocked out.

    The mock retriever returns an empty list — tests that need specific
    retrieval results should patch _get_components themselves.
    """
    monkeypatch.setenv("INTERNAL_ADMIN_SECRET", TEST_ADMIN_SECRET)

    # Prevent api.py from actually connecting to ChromaDB on import.
    mock_retriever = MagicMock()
    mock_retriever.invoke.return_value = []

    with patch("api._get_components") as mock_gc:
        mock_gc.return_value = (mock_retriever, MagicMock(), MagicMock())

        # Patch the module-level variable so _require_admin reads our test secret.
        import api as api_module
        monkeypatch.setattr(api_module, "INTERNAL_ADMIN_SECRET", TEST_ADMIN_SECRET)

        from fastapi.testclient import TestClient
        yield TestClient(api_module.app)


@pytest.fixture()
def admin_headers():
    """Return HTTP headers that pass _require_admin validation."""
    return {"Authorization": f"Bearer {TEST_ADMIN_SECRET}"}
