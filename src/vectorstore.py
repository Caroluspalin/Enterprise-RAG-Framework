"""
vectorstore.py

Unified abstraction layer over vector databases.

All vector store operations (add, search, delete, list) go through the
BaseVectorStore interface.  Concrete implementations live in this file.
Currently only ChromaDB is implemented; adding Pinecone, Qdrant, or Weaviate
requires subclassing BaseVectorStore and registering in get_vector_store().

The active backend is selected via the VECTOR_DB_BACKEND env variable:
  - "chroma" (default) -> local ChromaDB with PersistentClient
"""

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from logger import get_logger

load_dotenv()

log = get_logger("vectorstore")

VECTOR_DB_BACKEND = os.getenv("VECTOR_DB_BACKEND", "chroma").lower()


class BaseVectorStore(ABC):
    """Unified interface that all vector store backends must implement.

    Every method that reads or writes data requires a tenant_id parameter
    to enforce strict multi-tenant isolation at the data layer.  The RAG
    engine must never be able to access documents without specifying which
    organization they belong to.
    """

    @abstractmethod
    def add_documents(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict],
        embeddings: list[list[float]],
        tenant_id: str = "default",
    ) -> None:
        """Add document chunks with their embeddings and metadata.

        tenant_id is injected into every chunk's metadata automatically.
        """

    @abstractmethod
    def get_all_metadata(self, tenant_id: str = "default") -> list[dict]:
        """Return metadata dicts for chunks belonging to tenant_id."""

    @abstractmethod
    def delete_by_ids(self, ids: list[str]) -> None:
        """Delete chunks by their IDs."""

    @abstractmethod
    def delete_by_metadata(self, field: str, value: str, tenant_id: str = "default") -> int:
        """Delete all chunks where metadata[field] == value within a tenant. Return count."""

    @abstractmethod
    def count(self, tenant_id: str | None = None) -> int:
        """Return the number of chunks. If tenant_id is given, count only that tenant's chunks."""

    @abstractmethod
    def reset(self) -> None:
        """Delete the entire collection and recreate it empty."""

    @abstractmethod
    def as_langchain_retriever(self, k: int = 5, tenant_id: str = "default"):
        """Return a LangChain-compatible retriever scoped to tenant_id."""


class ChromaVectorStore(BaseVectorStore):
    """ChromaDB implementation backed by a local PersistentClient."""

    def __init__(
        self,
        chroma_path: str | None = None,
        collection_name: str | None = None,
    ):
        from chromadb import PersistentClient

        self._chroma_path = Path(chroma_path or os.getenv("CHROMA_PATH", "./chroma_db"))
        self._collection_name = collection_name or os.getenv("COLLECTION_NAME", "b2b_docs")
        self._client = PersistentClient(path=str(self._chroma_path))
        self._collection = self._client.get_or_create_collection(self._collection_name)
        self._migrate_legacy_tenant_ids()

    def _migrate_legacy_tenant_ids(self) -> None:
        """Stamp tenant_id='default' on chunks ingested before multi-tenancy.

        Pre-Phase 12 chunks were stored without a tenant_id field, so
        tenant-scoped queries never find them.  This one-time migration
        patches their metadata in place.
        """
        results = self._collection.get(include=["metadatas"])
        ids_to_update: list[str] = []
        metas_to_update: list[dict] = []
        for doc_id, meta in zip(results["ids"], results["metadatas"]):
            if meta.get("tenant_id") is None:
                meta["tenant_id"] = "default"
                ids_to_update.append(doc_id)
                metas_to_update.append(meta)
        if ids_to_update:
            self._collection.update(ids=ids_to_update, metadatas=metas_to_update)
            log.info(
                "Migrated %d legacy chunks to tenant_id='default'",
                len(ids_to_update),
            )

    def add_documents(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict],
        embeddings: list[list[float]],
        tenant_id: str = "default",
    ) -> None:
        # Inject tenant_id into every chunk's metadata so queries can
        # filter by tenant later.  Never trust the caller to set this.
        tagged = [{**m, "tenant_id": tenant_id} for m in metadatas]
        self._collection.add(
            ids=ids,
            documents=documents,
            metadatas=tagged,
            embeddings=embeddings,
        )

    def get_all_metadata(self, tenant_id: str = "default") -> list[dict]:
        results = self._collection.get(
            where={"tenant_id": tenant_id},
            include=["metadatas"],
        )
        return results["metadatas"]

    def delete_by_ids(self, ids: list[str]) -> None:
        self._collection.delete(ids=ids)

    def delete_by_metadata(self, field: str, value: str, tenant_id: str = "default") -> int:
        # Combine tenant filter with the requested field filter using $and
        # to ensure we never touch another tenant's data.
        results = self._collection.get(
            where={"$and": [{"tenant_id": tenant_id}, {field: value}]},
            include=["metadatas"],
        )
        ids = results["ids"]
        if ids:
            self._collection.delete(ids=ids)
        return len(ids)

    def count(self, tenant_id: str | None = None) -> int:
        if tenant_id is None:
            return self._collection.count()
        results = self._collection.get(
            where={"tenant_id": tenant_id},
            include=[],
        )
        return len(results["ids"])

    def reset(self) -> None:
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(self._collection_name)

    def as_langchain_retriever(self, k: int = 5, tenant_id: str = "default"):
        from langchain_chroma import Chroma
        from langchain_openai import OpenAIEmbeddings

        embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")
        langchain_store = Chroma(
            client=self._client,
            collection_name=self._collection_name,
            embedding_function=embeddings_model,
        )
        return langchain_store.as_retriever(
            search_type="similarity",
            search_kwargs={"k": k, "filter": {"tenant_id": tenant_id}},
        )


# ---------------------------------------------------------------------------
# Factory — returns the correct backend based on VECTOR_DB_BACKEND
# ---------------------------------------------------------------------------

_instance: BaseVectorStore | None = None


def get_vector_store(
    backend: str | None = None,
    **kwargs: Any,
) -> BaseVectorStore:
    """Return a vector store instance for the requested backend.

    On first call, creates and caches the instance.  Subsequent calls return
    the cached singleton unless reset_vector_store() is called.
    """
    global _instance
    if _instance is not None:
        return _instance

    chosen = (backend or VECTOR_DB_BACKEND).lower()

    if chosen == "chroma":
        _instance = ChromaVectorStore(**kwargs)
    else:
        raise ValueError(
            f"Unknown VECTOR_DB_BACKEND: '{chosen}'. "
            f"Supported: chroma. "
            f"Pinecone/Qdrant/Weaviate adapters are not yet implemented."
        )

    log.info("Vector store initialised: backend=%s", chosen)
    return _instance


def reset_vector_store() -> None:
    """Drop the cached singleton so the next get_vector_store() creates a fresh one."""
    global _instance
    _instance = None
