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
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# Set test environment variables BEFORE any src imports, because db.py
# runs init_db() and _seed_default_admin() at import time.
TEST_ADMIN_SECRET = "test-secret-for-ci"


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Give every test its own SQLite database.

    Monkeypatches DB_PATH in the db module and re-runs schema creation
    so each test starts with a clean state including the organizations
    table, users (with organization_id), and the default admin seed.
    """
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("CHAT_DB_PATH", str(db_file))

    import db as db_module
    monkeypatch.setattr(db_module, "DB_PATH", db_file)
    db_module.init_db()
    db_module._seed_default_admin()

    yield


@pytest.fixture()
def default_org():
    """Create and return a default test organization."""
    import db
    return db.create_organization("Test Corp")


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
        from limiter import rate_limiter
        rate_limiter.reset()
        yield TestClient(api_module.app)


@pytest.fixture()
def admin_headers():
    """Return HTTP headers that pass _require_admin validation."""
    return {"Authorization": f"Bearer {TEST_ADMIN_SECRET}"}


# ---------------------------------------------------------------------------
# chat_client — shared fixture for tests that need a working mock LLM chain
# ---------------------------------------------------------------------------

def _make_doc(content: str, source_file: str = "guide.pdf", page: int = 1):
    return SimpleNamespace(
        page_content=content,
        metadata={"source_file": source_file, "page": page},
    )


async def _fake_astream(*args, **kwargs):
    """Async generator that yields tokens like a real LLM chain."""
    for token in ["Hello", " ", "world", "!"]:
        yield token


@pytest.fixture()
def chat_client(monkeypatch):
    """TestClient where _get_components returns a controllable mock chain.

    The mock LLM is wired so that `prompt | llm | StrOutputParser()` produces
    an object whose `.astream()` yields predictable tokens.
    """
    monkeypatch.setenv("INTERNAL_ADMIN_SECRET", TEST_ADMIN_SECRET)

    mock_retriever = MagicMock()
    mock_retriever.invoke.return_value = [
        _make_doc("Paris is the capital of France.", "geo.pdf", 7),
        _make_doc("Berlin is the capital of Germany.", "geo.pdf", 12),
    ]

    # Build a mock LLM that, when piped with | operator, returns an object
    # whose astream yields tokens.
    mock_chain_result = MagicMock()
    mock_chain_result.astream = _fake_astream

    mock_llm = MagicMock()
    # prompt | llm produces an intermediate; intermediate | StrOutputParser produces final
    mock_pipe_intermediate = MagicMock()
    mock_pipe_intermediate.__or__ = MagicMock(return_value=mock_chain_result)
    mock_llm.__ror__ = MagicMock(return_value=mock_pipe_intermediate)

    mock_prompt = MagicMock()
    mock_prompt.__or__ = MagicMock(return_value=mock_pipe_intermediate)

    with patch("api._get_components") as mock_gc:
        mock_gc.return_value = (mock_retriever, mock_llm, mock_prompt)

        import api as api_module
        monkeypatch.setattr(api_module, "INTERNAL_ADMIN_SECRET", TEST_ADMIN_SECRET)
        # Disable widget key requirement for chat tests.
        monkeypatch.setattr(api_module, "WIDGET_API_KEY_LEGACY", "")
        # Disable rate limiting so tests don't hit the 5/minute wall.
        monkeypatch.setattr(api_module, "CHAT_RATE_LIMIT", "9999/minute")

        from fastapi.testclient import TestClient
        # Reset both the slowapi and tier-based limiter state between fixtures.
        api_module.limiter.reset()
        from limiter import rate_limiter
        rate_limiter.reset()
        yield TestClient(api_module.app)
