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
    """Unified interface that all vector store backends must implement."""

    @abstractmethod
    def add_documents(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict],
        embeddings: list[list[float]],
    ) -> None:
        """Add document chunks with their embeddings and metadata."""

    @abstractmethod
    def get_all_metadata(self) -> list[dict]:
        """Return metadata dicts for every stored chunk."""

    @abstractmethod
    def delete_by_ids(self, ids: list[str]) -> None:
        """Delete chunks by their IDs."""

    @abstractmethod
    def delete_by_metadata(self, field: str, value: str) -> int:
        """Delete all chunks where metadata[field] == value. Return count."""

    @abstractmethod
    def count(self) -> int:
        """Return the total number of chunks in the store."""

    @abstractmethod
    def reset(self) -> None:
        """Delete the entire collection and recreate it empty."""

    @abstractmethod
    def as_langchain_retriever(self, k: int = 5):
        """Return a LangChain-compatible retriever for similarity search."""


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

    def add_documents(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict],
        embeddings: list[list[float]],
    ) -> None:
        self._collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )

    def get_all_metadata(self) -> list[dict]:
        results = self._collection.get(include=["metadatas"])
        return results["metadatas"]

    def delete_by_ids(self, ids: list[str]) -> None:
        self._collection.delete(ids=ids)

    def delete_by_metadata(self, field: str, value: str) -> int:
        results = self._collection.get(
            where={field: value}, include=["metadatas"]
        )
        ids = results["ids"]
        if ids:
            self._collection.delete(ids=ids)
        return len(ids)

    def count(self) -> int:
        return self._collection.count()

    def reset(self) -> None:
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(self._collection_name)

    def as_langchain_retriever(self, k: int = 5):
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
            search_kwargs={"k": k},
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
