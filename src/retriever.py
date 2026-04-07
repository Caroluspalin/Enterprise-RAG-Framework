"""
retriever.py

Exposes a LangChain retriever backed by the configured vector store.

All ChromaDB-specific logic now lives in vectorstore.py.  This module is a
thin wrapper that provides the get_retriever() function expected by chain.py,
api.py, and evaluate.py.
"""

import os

from dotenv import load_dotenv

load_dotenv()

TOP_K = int(os.getenv("TOP_K", 5))


def get_retriever(k: int = TOP_K):
    """Return a LangChain VectorStoreRetriever from the active vector store.

    k controls how many chunks are returned per query. Higher values give the
    LLM more context but increase token usage and may dilute relevance.
    """
    from vectorstore import get_vector_store

    store = get_vector_store()
    return store.as_langchain_retriever(k=k)
