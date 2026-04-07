"""API-level tests for multi-tenant data isolation.

Verifies that:
  - Documents uploaded by Tenant A are invisible to Tenant B.
  - Tenant A cannot delete Tenant B's documents.
  - Chat (RAG retrieval) is scoped to the caller's organisation.
  - Tenant resolution works via both user_id and API key.
  - Audit log records organization_id.

These tests use a real ChromaDB PersistentClient (in tmp_path) and the
full FastAPI application — only the LLM is mocked.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import db
import vectorstore as vs_module
from vectorstore import ChromaVectorStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_ADMIN_SECRET = "test-secret-for-ci"


def _fake_embed(documents: list[str]) -> list[list[float]]:
    """Deterministic 10-d embeddings so we don't need OpenAI keys."""
    return [[float(len(d) % (i + 1)) for i in range(10)] for d in documents]


@pytest.fixture()
def two_tenants():
    """Create two organisations and one user in each. Returns a dict with
    org/user data for tenant_a and tenant_b."""
    org_a = db.create_organization("Acme Corp")
    org_b = db.create_organization("Globex Inc")
    user_a = db.create_user(
        "alice", "password1", "Alice", organization_id=org_a["id"],
    )
    user_b = db.create_user(
        "bob", "password2", "Bob", organization_id=org_b["id"],
    )
    return {
        "org_a": org_a, "org_b": org_b,
        "user_a": user_a, "user_b": user_b,
    }


@pytest.fixture()
def tenant_client(monkeypatch, tmp_path, two_tenants):
    """FastAPI TestClient backed by a real ChromaDB in tmp_path.

    The vector store singleton is replaced with a test-local instance so
    documents inserted here don't leak across tests.  The LLM is mocked
    but the retriever is real.
    """
    monkeypatch.setenv("INTERNAL_ADMIN_SECRET", TEST_ADMIN_SECRET)

    # Wire up a real ChromaVectorStore in a temp directory.
    chroma_dir = tmp_path / "chroma"
    chroma_dir.mkdir()
    test_store = ChromaVectorStore(
        chroma_path=str(chroma_dir), collection_name="tenant_test",
    )
    monkeypatch.setattr(vs_module, "_instance", test_store)

    # Mock OpenAIEmbeddings so we never call the real API.
    mock_embeddings = MagicMock()
    mock_embeddings.embed_documents = _fake_embed

    # Mock LLM — we only care about retrieval scoping, not generation.
    mock_llm = MagicMock()
    mock_prompt = MagicMock()

    # Make prompt | llm | StrOutputParser() produce an astream-able chain.
    async def _fake_astream(*args, **kwargs):
        for tok in ["Answer"]:
            yield tok

    mock_chain = MagicMock()
    mock_chain.astream = _fake_astream
    mock_pipe = MagicMock()
    mock_pipe.__or__ = MagicMock(return_value=mock_chain)
    mock_llm.__ror__ = MagicMock(return_value=mock_pipe)
    mock_prompt.__or__ = MagicMock(return_value=mock_pipe)

    import api as api_module
    monkeypatch.setattr(api_module, "INTERNAL_ADMIN_SECRET", TEST_ADMIN_SECRET)
    monkeypatch.setattr(api_module, "WIDGET_API_KEY_LEGACY", "")
    monkeypatch.setattr(api_module, "CHAT_RATE_LIMIT", "9999/minute")
    # Patch _get_components to return real tenant-scoped retriever + mock LLM.
    # We need to let the real retriever be built per-tenant, so we patch only
    # the LLM/prompt part via the module-level cache.
    monkeypatch.setattr(api_module, "_llm", mock_llm)
    monkeypatch.setattr(api_module, "_prompt", mock_prompt)

    api_module.limiter.reset()
    from limiter import rate_limiter
    rate_limiter.reset()

    yield TestClient(api_module.app), test_store, mock_embeddings, two_tenants

    # Clean up singleton.
    vs_module._instance = None


def _seed_docs(store, mock_embeddings, tenant_id: str, filenames: list[str]):
    """Insert fake document chunks into the vector store for a given tenant."""
    for fname in filenames:
        texts = [f"Content of {fname} for tenant {tenant_id}"]
        ids = [f"{tenant_id}_{fname}_0"]
        metadatas = [{"source_file": fname, "file_hash": f"hash_{tenant_id}_{fname}"}]
        embeddings = mock_embeddings.embed_documents(texts)
        store.add_documents(
            ids=ids, documents=texts, metadatas=metadatas,
            embeddings=embeddings, tenant_id=tenant_id,
        )


# ---------------------------------------------------------------------------
# Document list isolation
# ---------------------------------------------------------------------------

class TestDocumentListIsolation:
    def test_tenant_a_sees_only_own_docs(self, tenant_client):
        client, store, mock_embed, tenants = tenant_client
        org_a_id = tenants["org_a"]["id"]
        org_b_id = tenants["org_b"]["id"]

        _seed_docs(store, mock_embed, org_a_id, ["alpha.pdf"])
        _seed_docs(store, mock_embed, org_b_id, ["beta.pdf"])

        resp = client.get(
            "/api/documents",
            params={"user_id": tenants["user_a"]["id"]},
        )
        assert resp.status_code == 200
        names = [d["name"] for d in resp.json()["documents"]]
        assert "alpha.pdf" in names
        assert "beta.pdf" not in names

    def test_tenant_b_sees_only_own_docs(self, tenant_client):
        client, store, mock_embed, tenants = tenant_client
        org_a_id = tenants["org_a"]["id"]
        org_b_id = tenants["org_b"]["id"]

        _seed_docs(store, mock_embed, org_a_id, ["alpha.pdf"])
        _seed_docs(store, mock_embed, org_b_id, ["beta.pdf"])

        resp = client.get(
            "/api/documents",
            params={"user_id": tenants["user_b"]["id"]},
        )
        assert resp.status_code == 200
        names = [d["name"] for d in resp.json()["documents"]]
        assert "beta.pdf" in names
        assert "alpha.pdf" not in names

    def test_anonymous_user_sees_default_tenant_only(self, tenant_client):
        client, store, mock_embed, tenants = tenant_client
        org_a_id = tenants["org_a"]["id"]

        _seed_docs(store, mock_embed, org_a_id, ["secret.pdf"])
        _seed_docs(store, mock_embed, "default", ["public.pdf"])

        resp = client.get("/api/documents")
        names = [d["name"] for d in resp.json()["documents"]]
        assert "public.pdf" in names
        assert "secret.pdf" not in names


# ---------------------------------------------------------------------------
# Document deletion isolation
# ---------------------------------------------------------------------------

class TestDocumentDeleteIsolation:
    def test_tenant_a_cannot_delete_tenant_b_doc(self, tenant_client):
        """Attempting to delete a file that exists in another tenant's
        namespace should return 404 — not touch the other tenant's data."""
        client, store, mock_embed, tenants = tenant_client
        org_a_id = tenants["org_a"]["id"]
        org_b_id = tenants["org_b"]["id"]

        _seed_docs(store, mock_embed, org_a_id, ["only_a.pdf"])
        _seed_docs(store, mock_embed, org_b_id, ["only_b.pdf"])

        # Tenant A tries to delete Tenant B's document.
        resp = client.delete(
            "/api/documents/only_b.pdf",
            params={"user_id": tenants["user_a"]["id"]},
        )
        assert resp.status_code == 404

        # Tenant B's document must still exist.
        assert store.count(tenant_id=org_b_id) == 1

    def test_tenant_deletes_own_doc_successfully(self, tenant_client):
        client, store, mock_embed, tenants = tenant_client
        org_a_id = tenants["org_a"]["id"]

        _seed_docs(store, mock_embed, org_a_id, ["mine.pdf"])

        resp = client.delete(
            "/api/documents/mine.pdf",
            params={"user_id": tenants["user_a"]["id"]},
        )
        assert resp.status_code == 200
        assert store.count(tenant_id=org_a_id) == 0

    def test_same_filename_different_tenants(self, tenant_client):
        """Two tenants upload 'report.pdf'. Deleting it in Tenant A must not
        affect Tenant B's copy."""
        client, store, mock_embed, tenants = tenant_client
        org_a_id = tenants["org_a"]["id"]
        org_b_id = tenants["org_b"]["id"]

        _seed_docs(store, mock_embed, org_a_id, ["report.pdf"])
        _seed_docs(store, mock_embed, org_b_id, ["report.pdf"])

        resp = client.delete(
            "/api/documents/report.pdf",
            params={"user_id": tenants["user_a"]["id"]},
        )
        assert resp.status_code == 200
        # Tenant A's chunks gone, Tenant B's untouched.
        assert store.count(tenant_id=org_a_id) == 0
        assert store.count(tenant_id=org_b_id) == 1


# ---------------------------------------------------------------------------
# Tenant resolution via API key
# ---------------------------------------------------------------------------

class TestTenantResolutionViaApiKey:
    def test_api_key_resolves_to_org(self, tenant_client):
        """An API key bound to org_a should scope document listing to org_a."""
        client, store, mock_embed, tenants = tenant_client
        org_a_id = tenants["org_a"]["id"]
        org_b_id = tenants["org_b"]["id"]

        key_data = db.create_api_key(
            tenants["user_a"]["id"], "widget-a",
            organization_id=org_a_id,
        )

        _seed_docs(store, mock_embed, org_a_id, ["a_doc.pdf"])
        _seed_docs(store, mock_embed, org_b_id, ["b_doc.pdf"])

        resp = client.get(
            "/api/documents",
            headers={"X-Widget-Key": key_data["raw_key"]},
        )
        assert resp.status_code == 200
        names = [d["name"] for d in resp.json()["documents"]]
        assert "a_doc.pdf" in names
        assert "b_doc.pdf" not in names


# ---------------------------------------------------------------------------
# Chat retrieval isolation
# ---------------------------------------------------------------------------

def _parse_sse(text: str) -> list[dict]:
    events = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


class TestChatTenantIsolation:
    def test_chat_retrieves_only_own_tenant_docs(self, tenant_client):
        """When user_a chats, the retriever must only search org_a's chunks."""
        client, store, mock_embed, tenants = tenant_client
        org_a_id = tenants["org_a"]["id"]
        org_b_id = tenants["org_b"]["id"]

        _seed_docs(store, mock_embed, org_a_id, ["a_guide.pdf"])
        _seed_docs(store, mock_embed, org_b_id, ["b_secret.pdf"])

        # Patch OpenAIEmbeddings so the LangChain retriever uses the same
        # 10-dimensional fake embeddings as our seeded test data.
        mock_oai = MagicMock()
        mock_oai.embed_documents = _fake_embed
        mock_oai.embed_query = lambda q: _fake_embed([q])[0]

        with patch("langchain_openai.OpenAIEmbeddings", return_value=mock_oai):
            resp = client.post("/api/chat", json={
                "question": "Tell me about the guide",
                "user_id": tenants["user_a"]["id"],
            })
        assert resp.status_code == 200

        events = _parse_sse(resp.text)
        source_event = next((e for e in events if e["type"] == "sources"), None)
        assert source_event is not None
        filenames = {s["filename"] for s in source_event["sources"]}
        # user_a should only see a_guide.pdf, never b_secret.pdf.
        assert "b_secret.pdf" not in filenames


# ---------------------------------------------------------------------------
# Audit log records organization_id
# ---------------------------------------------------------------------------

class TestAuditOrgId:
    def test_login_audit_includes_org_id(self, tenant_client):
        """A successful login should record the user's organization_id."""
        client, store, mock_embed, tenants = tenant_client
        from audit import get_audit_logs

        resp = client.post("/api/auth/login", json={
            "username": "alice", "password": "password1",
        })
        assert resp.status_code == 200

        logs = get_audit_logs(limit=5)
        login_log = next(
            (l for l in logs if l["action"] == "LOGIN_SUCCESS"), None,
        )
        assert login_log is not None
        assert login_log["organization_id"] == tenants["org_a"]["id"]
