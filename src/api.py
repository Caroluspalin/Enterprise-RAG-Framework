"""
api.py

FastAPI backend that exposes the RAG pipeline over HTTP.

The terminal chat.py and this API share the same ingest/retriever/chain logic.
We build a streaming-friendly LCEL chain here instead of using
ConversationalRetrievalChain because LCEL's .astream() natively yields tokens,
while the older chain class requires callback hacks to achieve the same effect.

Endpoints:
  POST /api/chat       — streaming chat via Server-Sent Events
  POST /api/upload     — upload a PDF and trigger incremental ingestion
  GET  /api/documents  — list PDFs currently in DOCS_PATH
"""

import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pydantic import BaseModel

load_dotenv()

from logger import get_logger
from retriever import get_retriever

log = get_logger("api")

DOCS_PATH = Path(os.getenv("DOCS_PATH", "./docs"))

# Identical wording to chain.py so terminal and web give consistent answers.
SYSTEM_PROMPT = """You are a helpful assistant for a B2B company. \
Answer the user's question using ONLY the information provided in the context below. \
If the answer cannot be found in the context, say clearly that you don't know \
and do not make up information.

When answering, cite the source document and page number where relevant.

Context:
{context}"""


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="B2B RAG API", version="1.0.0")

# Allow the Next.js dev server and any localhost variant.
# In production, restrict this to the actual frontend origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Lazy-initialised singletons — ChromaDB and LLM clients are expensive to spin
# up on every request, so we create them once and reuse.
# ---------------------------------------------------------------------------

_retriever = None
_llm = None
_prompt = None


def _build_llm():
    """Instantiate the LLM selected by LLM_BACKEND (mirrors chain.py)."""
    backend = os.getenv("LLM_BACKEND", "openai").lower()

    if backend == "anthropic":
        from langchain_anthropic import ChatAnthropic
        # streaming=True is required for .astream() to yield tokens incrementally.
        return ChatAnthropic(model="claude-sonnet-4-6", temperature=0, streaming=True)

    if backend == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model=os.getenv("OLLAMA_MODEL", "llama3"), temperature=0)

    # Default: OpenAI
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model="gpt-4o", temperature=0, streaming=True)


def _build_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        # MessagesPlaceholder injects the conversation history as-is so the LLM
        # can interpret follow-up questions without a separate condensation step.
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{question}"),
    ])


def _get_components():
    """Return (retriever, llm, prompt), building them on first call."""
    global _retriever, _llm, _prompt
    if _retriever is None:
        log.info("Initialising retriever, LLM, and prompt (first request)")
        _retriever = get_retriever()
        _llm = _build_llm()
        _prompt = _build_prompt()
    return _retriever, _llm, _prompt


def _invalidate_components():
    """Drop cached singletons so the next request picks up newly ingested docs."""
    global _retriever, _llm, _prompt
    _retriever = None
    _llm = None
    _prompt = None


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str   # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    question: str
    history: list[ChatMessage] = []


# ---------------------------------------------------------------------------
# Streaming SSE generator
# ---------------------------------------------------------------------------

async def _stream_sse(question: str, history: list[ChatMessage]) -> AsyncIterator[str]:
    """Yield Server-Sent Event strings for each token, then sources, then done.

    Retrieval runs first (synchronously in a thread, because ChromaDB is sync).
    The retrieved context is then injected directly into the prompt so the LLM
    generation step can stream without waiting for a second async retrieval call.
    """
    retriever, llm, prompt = _get_components()

    # ChromaDB's client is synchronous — run it in a thread pool to avoid
    # blocking the event loop.
    source_docs = await asyncio.to_thread(retriever.invoke, question)

    context = "\n\n".join(doc.page_content for doc in source_docs)

    # Convert the client-supplied history to LangChain message objects.
    lc_history = []
    for msg in history:
        if msg.role == "user":
            lc_history.append(HumanMessage(content=msg.content))
        else:
            lc_history.append(AIMessage(content=msg.content))

    # Stream the answer token by token.
    chain = prompt | llm | StrOutputParser()
    async for token in chain.astream({
        "context": context,
        "question": question,
        "chat_history": lc_history,
    }):
        if token:
            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

    # Deduplicate and send source citations after the answer is complete.
    seen: set[tuple] = set()
    sources = []
    for doc in source_docs:
        filename = doc.metadata.get("source_file", "unknown")
        page = doc.metadata.get("page", "?")
        key = (filename, page)
        if key not in seen:
            seen.add(key)
            sources.append({"filename": filename, "page": page})

    yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
    yield f"data: {json.dumps({'type': 'done'})}\n\n"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/chat")
async def chat(req: ChatRequest):
    log.info("Chat | question=%r history_len=%d", req.question, len(req.history))
    return StreamingResponse(
        _stream_sse(req.question, req.history),
        media_type="text/event-stream",
        headers={
            # Prevent proxies and the browser from buffering the stream.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    """Save an uploaded PDF to DOCS_PATH and ingest it into ChromaDB."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    DOCS_PATH.mkdir(parents=True, exist_ok=True)
    dest = DOCS_PATH / file.filename

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    log.info("PDF received: %s (%.1f KB)", file.filename, dest.stat().st_size / 1024)

    # Ingestion is CPU/IO-bound — run it in a thread so we don't block the loop.
    try:
        await asyncio.to_thread(_ingest_pdf, dest)
    except Exception as exc:
        log.exception("Ingestion failed for %s", file.filename)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc

    # Invalidate the retriever so the next chat request picks up the new content.
    _invalidate_components()

    return {"message": f"'{file.filename}' ingested successfully."}


def _ingest_pdf(pdf_path: Path) -> None:
    """Ingest a single PDF into ChromaDB (called from a thread pool).

    Reuses load_and_split() and compute_file_hash() from ingest.py to keep
    chunking behaviour identical between the CLI and the web upload path.
    """
    # Local imports avoid polluting the module namespace and allow ingest.py
    # to be imported without triggering its __main__ block.
    from ingest import compute_file_hash, load_and_split, CHROMA_PATH, COLLECTION_NAME
    from chromadb import PersistentClient
    from langchain_openai import OpenAIEmbeddings

    client = PersistentClient(path=str(CHROMA_PATH))
    collection = client.get_or_create_collection(COLLECTION_NAME)
    embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")

    file_hash = compute_file_hash(pdf_path)

    # Skip re-ingestion if the file content has not changed.
    existing = collection.get(include=["metadatas"])
    existing_hashes = {m.get("file_hash") for m in existing["metadatas"]}
    if file_hash in existing_hashes:
        log.info("Skipping unchanged file: %s", pdf_path.name)
        return

    chunks = load_and_split(pdf_path)
    if not chunks:
        log.warning("No extractable text in %s", pdf_path.name)
        return

    ids = [f"{file_hash}_{i}" for i in range(len(chunks))]
    documents = [c.page_content for c in chunks]
    metadatas = [
        {**c.metadata, "file_hash": file_hash, "page": c.metadata.get("page", 0) + 1}
        for c in chunks
    ]
    vectors = embeddings_model.embed_documents(documents)

    collection.add(ids=ids, documents=documents, metadatas=metadatas, embeddings=vectors)
    log.info("Ingested %s | chunks=%d", pdf_path.name, len(chunks))


@app.get("/api/documents")
async def list_documents():
    """Return the list of PDFs currently available in DOCS_PATH."""
    if not DOCS_PATH.exists():
        return {"documents": []}

    pdfs = [
        {
            "name": p.name,
            "size_kb": round(p.stat().st_size / 1024, 1),
        }
        for p in sorted(DOCS_PATH.rglob("*.pdf"))
    ]
    return {"documents": pdfs}


@app.get("/api/health")
async def health():
    return {"status": "ok"}
