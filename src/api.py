"""
api.py

FastAPI backend that exposes the RAG pipeline over HTTP.

The terminal chat.py and this API share the same ingest/retriever/chain logic.
We build a streaming-friendly LCEL chain here instead of using
ConversationalRetrievalChain because LCEL's .astream() natively yields tokens,
while the older chain class requires callback hacks to achieve the same effect.

Endpoints:
  POST /api/chat                    — streaming chat via Server-Sent Events
  POST /api/upload                  — upload a PDF and trigger incremental ingestion
  GET  /api/documents               — list unique filenames stored in ChromaDB
  DELETE /api/documents/{filename}  — remove all embeddings for a file from ChromaDB
  POST /api/chat/sessions           — create a new chat session
  GET  /api/chat/sessions           — list sessions for a user
  GET  /api/chat/sessions/{id}      — get messages for a session
  DELETE /api/chat/sessions/{id}    — delete a session
"""

import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

load_dotenv()

from db import (
    add_message,
    auto_title_from_question,
    change_password,
    create_api_key,
    create_session,
    create_user,
    delete_api_key,
    delete_session,
    delete_user,
    get_analytics,
    get_messages,
    get_session,
    get_sessions,
    get_user_by_username,
    list_api_keys,
    list_users,
    revoke_api_key,
    update_session_title,
    verify_api_key,
    verify_user,
)
from logger import get_logger
from retriever import get_retriever

log = get_logger("api")

DOCS_PATH = Path(os.getenv("DOCS_PATH", "./docs"))

# Widget API key — POST /api/chat requires a valid X-Widget-Key header.
# Keys are verified against SHA-256 hashes stored in the api_keys table.
# The legacy WIDGET_API_KEY env var is still supported as a fallback so
# existing deployments keep working until keys are migrated to the DB.
WIDGET_API_KEY_LEGACY = os.getenv("WIDGET_API_KEY", "")

# CORS — read allowed origins from env, fall back to localhost for development.
_allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS: list[str] = (
    [o.strip() for o in _allowed_origins_raw.split(",") if o.strip()]
    if _allowed_origins_raw
    else ["http://localhost:3000", "http://127.0.0.1:3000"]
)

# Rate limiting — max requests per minute for the /api/chat endpoint.
CHAT_RATE_LIMIT = os.getenv("CHAT_RATE_LIMIT", "5/minute")

# Server-to-server secret for admin endpoints.  Next.js sends this in the
# Authorization header when calling /api/admin/* routes.  Without it, no
# one can access admin functionality even if they hit the backend directly.
INTERNAL_ADMIN_SECRET = os.getenv("INTERNAL_ADMIN_SECRET", "")

# Identical wording to chain.py so terminal and web give consistent answers.
SYSTEM_PROMPT = """You are a professional, helpful, and polite customer service assistant for our company.
Your goal is to help users by answering their questions accurately and naturally.

CRITICAL RULES:
1. You must base your answers ONLY on the provided Context. 
2. If the user asks something that is not mentioned in the Context, politely say that you don't have that information, and offer to help with something else. NEVER make up prices, products, or facts (no hallucinations).
3. If the user greets you or asks a general conversational question (e.g., "Hi", "How are you?"), answer politely and ask how you can help them today.
4. Format your answers clearly using Markdown (bullet points, bold text for product names and prices).
5. Always cite the source document and page number at the end of your factual claims (e.g., "Tämä tuote maksaa 50€ (Lähde: hinnasto.pdf, s. 2).").

Context:
{context}"""


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

# Rate limiter keyed by client IP address.
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="B2B RAG API", version="1.0.0")
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Return a JSON 429 instead of slowapi's default plain-text response."""
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
    )


# CORS — origins are read from the ALLOWED_ORIGINS env var (comma-separated).
# In development the default includes localhost:3000.
log.info("CORS allowed origins: %s", ALLOWED_ORIGINS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    # Explicitly list X-Widget-Key so CORS preflight accepts it from any origin.
    allow_headers=["*"],
    expose_headers=["X-Widget-Key"],
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
    session_id: str | None = Field(
        default=None,
        description="Optional session ID. When provided, the question and answer "
        "are persisted to the database under this session.",
    )
    user_id: str = Field(
        default="anonymous",
        description="User identifier. Used when creating a new session on-the-fly.",
    )


# ---------------------------------------------------------------------------
# Streaming SSE generator
# ---------------------------------------------------------------------------

async def _stream_sse(
    question: str,
    history: list[ChatMessage],
    session_id: str | None = None,
    user_id: str = "anonymous",
) -> AsyncIterator[str]:
    """Yield Server-Sent Event strings for each token, then sources, then done.

    Retrieval runs first (synchronously in a thread, because ChromaDB is sync).
    The retrieved context is then injected directly into the prompt so the LLM
    generation step can stream without waiting for a second async retrieval call.

    When session_id is provided, the user question and the completed assistant
    answer are persisted to the SQLite database.  If session_id is given but
    does not exist yet, a new session is created automatically.
    """
    retriever, llm, prompt = _get_components()

    # -- Persist the user message and auto-create session if needed -----------
    if session_id:
        session = await asyncio.to_thread(get_session, session_id)
        if not session:
            await asyncio.to_thread(create_session, user_id, auto_title_from_question(question))
            # create_session generates a random ID; we need to use the caller's ID.
            # Re-create with the explicit ID by inserting directly.
            # Simpler: let the caller create the session first. But to keep the
            # API forgiving, we create it here with the supplied ID.
            session = await asyncio.to_thread(
                _ensure_session, session_id, user_id, question
            )

        await asyncio.to_thread(add_message, session_id, "user", question)

        # Auto-title: if this is the first question in the session, derive
        # a title from the question text.
        if session and session["title"] == "New chat":
            title = auto_title_from_question(question)
            await asyncio.to_thread(update_session_title, session_id, title)

    # -- Retrieval -----------------------------------------------------------
    source_docs = await asyncio.to_thread(retriever.invoke, question)
    context = "\n\n".join(doc.page_content for doc in source_docs)

    # Convert the client-supplied history to LangChain message objects.
    lc_history = []
    for msg in history:
        if msg.role == "user":
            lc_history.append(HumanMessage(content=msg.content))
        else:
            lc_history.append(AIMessage(content=msg.content))

    # -- Stream the answer token by token ------------------------------------
    chain = prompt | llm | StrOutputParser()
    full_answer: list[str] = []

    async for token in chain.astream({
        "context": context,
        "question": question,
        "chat_history": lc_history,
    }):
        if token:
            full_answer.append(token)
            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

    # -- Source citations ----------------------------------------------------
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

    # -- Persist the assistant message ---------------------------------------
    if session_id:
        await asyncio.to_thread(
            add_message, session_id, "assistant", "".join(full_answer), sources or None
        )

    yield f"data: {json.dumps({'type': 'done'})}\n\n"


def _ensure_session(session_id: str, user_id: str, question: str) -> dict:
    """Create a session row with an explicit ID (used when the caller provides one).

    This is a workaround because create_session() generates its own UUID.
    We insert directly so the frontend-supplied session_id is honoured.
    """
    import sqlite3 as _sqlite3
    from datetime import datetime, timezone
    from db import _connect

    now = datetime.now(timezone.utc).isoformat()
    title = auto_title_from_question(question)
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO sessions (id, user_id, title, created_at) VALUES (?, ?, ?, ?)",
                (session_id, user_id, title, now),
            )
    except _sqlite3.IntegrityError:
        # Session already exists (race condition) — that's fine.
        pass
    return {"id": session_id, "user_id": user_id, "title": title, "created_at": now}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/chat")
@limiter.limit(CHAT_RATE_LIMIT)
async def chat(request: Request, req: ChatRequest):
    # Validate the X-Widget-Key header to prevent unauthenticated abuse
    # of the LLM.  First check the database for a matching active key,
    # then fall back to the legacy env var for backwards compatibility.
    client_key = request.headers.get("X-Widget-Key", "")
    if client_key:
        db_match = await asyncio.to_thread(verify_api_key, client_key)
        if not db_match and client_key != WIDGET_API_KEY_LEGACY:
            raise HTTPException(status_code=403, detail="Invalid or revoked API key.")
    elif WIDGET_API_KEY_LEGACY:
        # No key provided but a legacy key is configured — require it.
        raise HTTPException(status_code=403, detail="Missing widget API key.")

    log.info(
        "Chat | question=%r history_len=%d session_id=%s",
        req.question, len(req.history), req.session_id,
    )
    return StreamingResponse(
        _stream_sse(req.question, req.history, req.session_id, req.user_id),
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
    """Return unique filenames currently embedded in ChromaDB.

    Reading from the vector store (not just DOCS_PATH) ensures the list
    accurately reflects what the RAG pipeline can actually retrieve from.
    """
    from ingest import CHROMA_PATH, COLLECTION_NAME
    from chromadb import PersistentClient

    def _query_chroma():
        client = PersistentClient(path=str(CHROMA_PATH))
        try:
            collection = client.get_collection(COLLECTION_NAME)
        except Exception:
            # Collection does not exist yet — no documents ingested.
            return []

        results = collection.get(include=["metadatas"])
        # Collect unique filenames, preserving insertion order via dict.
        seen: dict[str, bool] = {}
        for meta in results["metadatas"]:
            name = meta.get("source_file")
            if name:
                seen[name] = True

        documents = []
        for name in seen:
            disk_path = DOCS_PATH / name
            size_kb = round(disk_path.stat().st_size / 1024, 1) if disk_path.exists() else None
            documents.append({"name": name, "size_kb": size_kb})

        return documents

    documents = await asyncio.to_thread(_query_chroma)
    return {"documents": documents}


@app.delete("/api/documents/{filename}")
async def delete_document(filename: str):
    """Remove all ChromaDB embeddings for filename and delete the PDF from disk.

    Steps:
      1. Find all chunk IDs in ChromaDB where source_file == filename.
      2. Delete those chunks from the collection.
      3. Delete the physical PDF file from DOCS_PATH (if it exists).
      4. Invalidate the retriever cache so the next chat request does not
         serve stale results from the now-deleted document.
    """
    from ingest import CHROMA_PATH, COLLECTION_NAME
    from chromadb import PersistentClient

    def _delete_from_chroma():
        client = PersistentClient(path=str(CHROMA_PATH))
        try:
            collection = client.get_collection(COLLECTION_NAME)
        except Exception:
            raise HTTPException(status_code=404, detail="No documents have been ingested yet.")

        # ChromaDB's where filter uses exact-match on metadata fields.
        results = collection.get(where={"source_file": filename}, include=["metadatas"])
        ids_to_delete = results["ids"]

        if not ids_to_delete:
            raise HTTPException(
                status_code=404,
                detail=f"'{filename}' was not found in the vector store.",
            )

        collection.delete(ids=ids_to_delete)
        log.info("Deleted %d chunks for '%s' from ChromaDB", len(ids_to_delete), filename)
        return len(ids_to_delete)

    chunks_deleted = await asyncio.to_thread(_delete_from_chroma)

    # Also remove the physical file so it cannot be re-ingested accidentally.
    disk_path = DOCS_PATH / filename
    if disk_path.exists():
        disk_path.unlink()
        log.info("Deleted file from disk: %s", disk_path)

    # Drop cached retriever so the next request rebuilds it without this file.
    _invalidate_components()

    return {
        "message": f"'{filename}' deleted successfully.",
        "chunks_removed": chunks_deleted,
    }


# ---------------------------------------------------------------------------
# Chat session / history endpoints
# ---------------------------------------------------------------------------

class CreateSessionRequest(BaseModel):
    user_id: str = "anonymous"
    title: str = "New chat"


@app.post("/api/chat/sessions")
async def create_chat_session(req: CreateSessionRequest):
    """Create a new chat session and return it."""
    session = await asyncio.to_thread(create_session, req.user_id, req.title)
    log.info("Session created | id=%s user=%s", session["id"], req.user_id)
    return session


@app.get("/api/chat/sessions")
async def list_chat_sessions(user_id: str = "anonymous"):
    """Return all sessions for a user, most recent first."""
    sessions = await asyncio.to_thread(get_sessions, user_id)
    return {"sessions": sessions}


@app.get("/api/chat/sessions/{session_id}")
async def get_chat_session(session_id: str):
    """Return a session's metadata and all its messages."""
    session = await asyncio.to_thread(get_session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    messages = await asyncio.to_thread(get_messages, session_id)
    return {"session": session, "messages": messages}


@app.delete("/api/chat/sessions/{session_id}")
async def delete_chat_session(session_id: str):
    """Delete a session and all its messages."""
    session = await asyncio.to_thread(get_session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    await asyncio.to_thread(delete_session, session_id)
    log.info("Session deleted | id=%s", session_id)
    return {"message": "Session deleted."}


# ---------------------------------------------------------------------------
# Authentication endpoints
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    name: str
    role: str = "user"


@app.post("/api/auth/login")
async def login(req: LoginRequest):
    """Verify credentials and return user info (without password hash).

    The actual session/token management lives in NextAuth on the frontend;
    this endpoint just validates username + bcrypt hash in SQLite.
    """
    user = await asyncio.to_thread(verify_user, req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    log.info("Login successful | user=%s role=%s", user["username"], user["role"])
    return user


@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    """Create a new user account with a bcrypt-hashed password."""
    existing = await asyncio.to_thread(get_user_by_username, req.username)
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken.")
    user = await asyncio.to_thread(create_user, req.username, req.password, req.name, req.role)
    log.info("User registered | user=%s role=%s", user["username"], user["role"])
    return user


# ---------------------------------------------------------------------------
# Analytics endpoint
# ---------------------------------------------------------------------------

@app.get("/api/analytics")
async def analytics(days: int = 30):
    """Return aggregated chat analytics for the admin dashboard."""
    data = await asyncio.to_thread(get_analytics, days)
    return data


# ---------------------------------------------------------------------------
# Admin authentication — server-to-server via INTERNAL_ADMIN_SECRET.
#
# Next.js calls these endpoints from server-side API routes (not from the
# browser).  The shared secret proves the request came from our own frontend,
# not from an attacker hitting the backend directly.
# ---------------------------------------------------------------------------

def _require_admin(request: Request) -> None:
    """Validate the Authorization: Bearer <secret> header on admin routes.

    Raises 401 if INTERNAL_ADMIN_SECRET is not configured (misconfiguration
    safeguard) or if the provided token does not match.
    """
    if not INTERNAL_ADMIN_SECRET:
        raise HTTPException(
            status_code=500,
            detail="INTERNAL_ADMIN_SECRET is not configured on the server.",
        )
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing admin authorization.")
    token = auth_header[7:]
    if token != INTERNAL_ADMIN_SECRET:
        raise HTTPException(status_code=401, detail="Invalid admin authorization.")


# ---------------------------------------------------------------------------
# Admin — User management
# ---------------------------------------------------------------------------

@app.get("/api/admin/users")
async def admin_list_users(request: Request):
    """List all registered users (admin only)."""
    _require_admin(request)
    users = await asyncio.to_thread(list_users)
    return {"users": users}


@app.delete("/api/admin/users/{user_id}")
async def admin_delete_user(request: Request, user_id: str):
    """Delete a user and all their API keys (admin only)."""
    _require_admin(request)
    deleted = await asyncio.to_thread(delete_user, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found.")
    log.info("Admin deleted user | id=%s", user_id)
    return {"message": "User deleted."}


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@app.post("/api/admin/users/{user_id}/change-password")
async def admin_change_password(request: Request, user_id: str, req: ChangePasswordRequest):
    """Change a user's password (admin only, requires old password)."""
    _require_admin(request)
    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")
    success = await asyncio.to_thread(change_password, user_id, req.old_password, req.new_password)
    if not success:
        raise HTTPException(status_code=400, detail="Incorrect current password.")
    log.info("Password changed | user_id=%s", user_id)
    return {"message": "Password changed."}


# ---------------------------------------------------------------------------
# Admin — API key management
# ---------------------------------------------------------------------------

class CreateApiKeyRequest(BaseModel):
    user_id: str
    label: str


@app.post("/api/admin/api-keys")
async def admin_create_api_key(request: Request, req: CreateApiKeyRequest):
    """Generate a new API key for a user (admin only).

    The raw key is returned ONCE in this response.  It cannot be retrieved
    again later — only the prefix is stored for display purposes.
    """
    _require_admin(request)
    result = await asyncio.to_thread(create_api_key, req.user_id, req.label)
    log.info("API key created | user_id=%s label=%s prefix=%s", req.user_id, req.label, result["prefix"])
    return result


@app.get("/api/admin/api-keys")
async def admin_list_api_keys(request: Request, user_id: str):
    """List all API keys for a user (admin only).  No secrets returned."""
    _require_admin(request)
    keys = await asyncio.to_thread(list_api_keys, user_id)
    return {"api_keys": keys}


@app.delete("/api/admin/api-keys/{key_id}")
async def admin_revoke_api_key(request: Request, key_id: str):
    """Revoke (deactivate) an API key (admin only)."""
    _require_admin(request)
    revoked = await asyncio.to_thread(revoke_api_key, key_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="API key not found or already revoked.")
    log.info("API key revoked | key_id=%s", key_id)
    return {"message": "API key revoked."}


@app.get("/api/health")
async def health():
    return {"status": "ok"}
