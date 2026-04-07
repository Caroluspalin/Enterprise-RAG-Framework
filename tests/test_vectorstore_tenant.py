"""Tests for multi-tenant isolation in the vector store layer.

Verifies that tenant_id metadata filtering prevents cross-tenant data leakage.
Uses a real local ChromaDB PersistentClient — no mocking of the vector store.
"""

import pytest
from chromadb import PersistentClient

from vectorstore import ChromaVectorStore


COLLECTION_NAME = "tenant_test"


@pytest.fixture()
def store(tmp_path):
    """Fresh ChromaVectorStore backed by a temporary directory."""
    return ChromaVectorStore(
        chroma_path=str(tmp_path / "chroma"),
        collection_name=COLLECTION_NAME,
    )


def _embed(n: int) -> list[list[float]]:
    """Generate n deterministic 10-dimensional embeddings."""
    return [[float(i % (d + 1)) for d in range(10)] for i in range(n)]


# ---------------------------------------------------------------------------
# add_documents injects tenant_id
# ---------------------------------------------------------------------------

class TestAddDocumentsTenantTag:
    def test_tenant_id_injected_into_metadata(self, store):
        store.add_documents(
            ids=["c1"],
            documents=["hello"],
            metadatas=[{"source_file": "a.pdf"}],
            embeddings=_embed(1),
            tenant_id="org_abc",
        )
        # Read directly from ChromaDB to verify the metadata was tagged.
        raw = store._collection.get(ids=["c1"], include=["metadatas"])
        assert raw["metadatas"][0]["tenant_id"] == "org_abc"

    def test_caller_cannot_override_tenant_id(self, store):
        """Even if the caller sneaks tenant_id into metadatas, our code
        overwrites it with the authoritative value."""
        store.add_documents(
            ids=["c2"],
            documents=["sneaky"],
            metadatas=[{"tenant_id": "evil_tenant", "source_file": "b.pdf"}],
            embeddings=_embed(1),
            tenant_id="real_tenant",
        )
        raw = store._collection.get(ids=["c2"], include=["metadatas"])
        assert raw["metadatas"][0]["tenant_id"] == "real_tenant"


# ---------------------------------------------------------------------------
# get_all_metadata — filtered by tenant
# ---------------------------------------------------------------------------

class TestGetAllMetadataTenant:
    def test_returns_only_own_tenant(self, store):
        store.add_documents(
            ids=["t1_c1"], documents=["doc1"],
            metadatas=[{"source_file": "x.pdf"}], embeddings=_embed(1),
            tenant_id="tenant_1",
        )
        store.add_documents(
            ids=["t2_c1"], documents=["doc2"],
            metadatas=[{"source_file": "y.pdf"}], embeddings=_embed(1),
            tenant_id="tenant_2",
        )
        metas = store.get_all_metadata(tenant_id="tenant_1")
        assert len(metas) == 1
        assert metas[0]["source_file"] == "x.pdf"

    def test_empty_for_unknown_tenant(self, store):
        store.add_documents(
            ids=["c1"], documents=["text"],
            metadatas=[{"source_file": "z.pdf"}], embeddings=_embed(1),
            tenant_id="known",
        )
        assert store.get_all_metadata(tenant_id="unknown") == []


# ---------------------------------------------------------------------------
# delete_by_metadata — scoped to tenant
# ---------------------------------------------------------------------------

class TestDeleteByMetadataTenant:
    def test_deletes_only_within_tenant(self, store):
        # Both tenants have a file called "shared.pdf".
        store.add_documents(
            ids=["t1_s1"], documents=["tenant1 content"],
            metadatas=[{"source_file": "shared.pdf"}], embeddings=_embed(1),
            tenant_id="tenant_1",
        )
        store.add_documents(
            ids=["t2_s1"], documents=["tenant2 content"],
            metadatas=[{"source_file": "shared.pdf"}], embeddings=_embed(1),
            tenant_id="tenant_2",
        )
        deleted = store.delete_by_metadata("source_file", "shared.pdf", tenant_id="tenant_1")
        assert deleted == 1
        # tenant_2's data must be untouched.
        assert store.count(tenant_id="tenant_2") == 1
        assert store.count(tenant_id="tenant_1") == 0


# ---------------------------------------------------------------------------
# count — with and without tenant filter
# ---------------------------------------------------------------------------

class TestCountTenant:
    def test_count_all(self, store):
        store.add_documents(
            ids=["a1"], documents=["a"], metadatas=[{}], embeddings=_embed(1),
            tenant_id="t1",
        )
        store.add_documents(
            ids=["b1"], documents=["b"], metadatas=[{}], embeddings=_embed(1),
            tenant_id="t2",
        )
        assert store.count() == 2

    def test_count_per_tenant(self, store):
        store.add_documents(
            ids=["a1", "a2"], documents=["a", "aa"],
            metadatas=[{}, {}], embeddings=_embed(2),
            tenant_id="t1",
        )
        store.add_documents(
            ids=["b1"], documents=["b"], metadatas=[{}], embeddings=_embed(1),
            tenant_id="t2",
        )
        assert store.count(tenant_id="t1") == 2
        assert store.count(tenant_id="t2") == 1
        assert store.count(tenant_id="t_nonexistent") == 0
