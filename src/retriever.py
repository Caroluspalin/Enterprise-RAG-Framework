"""
retriever.py

Loads the persisted ChromaDB collection and exposes a LangChain retriever
that the RAG chain uses to fetch relevant chunks for a given query.
"""

import os
from pathlib import Path

from chromadb import PersistentClient
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

load_dotenv()

CHROMA_PATH = Path(os.getenv("CHROMA_PATH", "./chroma_db"))
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "b2b_docs")
TOP_K = int(os.getenv("TOP_K", 5))


def get_retriever(k: int = TOP_K):
    """Return a LangChain VectorStoreRetriever backed by the local ChromaDB collection.

    k controls how many chunks are returned per query. Higher values give the
    LLM more context but increase token usage and may dilute relevance.
    """
    embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")

    # Reuse the same PersistentClient that ingest.py writes to, so both
    # scripts always point at the same on-disk collection.
    client = PersistentClient(path=str(CHROMA_PATH))

    vector_store = Chroma(
        client=client,
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings_model,
    )

    return vector_store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": k},
    )


def get_vector_store():
    """Return the raw Chroma vector store instance.

    Useful when you need direct access to the store, e.g. for metadata
    filtering or similarity score thresholds beyond what the retriever exposes.
    """
    embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")
    client = PersistentClient(path=str(CHROMA_PATH))

    return Chroma(
        client=client,
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings_model,
    )
