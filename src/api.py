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
    get_user_by_id,
    get_user_by_username,
    init_db,
    list_api_keys,
    list_users,
    revoke_api_key,
    update_session_title,
    verify_api_key,
    verify_user,
)
from audit import get_audit_logs, log_event
from chain import SYSTEM_PROMPT, load_llm
from limiter import rate_limiter
from logger import get_logger
from retriever import get_retriever
from security import SecurityHeadersMiddleware
from vectorstore import get_vector_store, reset_vector_store

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



# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Initialise the database (tables + default admin seed) at startup."""
    init_db()
    yield


# Rate limiter keyed by client IP address.
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="B2B RAG API", version="1.0.0", lifespan=lifespan)
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
if "*" in ALLOWED_ORIGINS:
    log.warning(
        "ALLOWED_ORIGINS contains '*' — this disables CORS protection. "
        "Never use wildcard origins in production."
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    # Explicitly list X-Widget-Key so CORS preflight accepts it from any origin.
    allow_headers=["*"],
    expose_headers=["X-Widget-Key", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
)

# Security headers (X-Content-Type-Options, X-Frame-Options, CSP, HSTS).
# Must be added AFTER CORSMiddleware so both layers run on every response.
app.add_middleware(SecurityHeadersMiddleware)


# ---------------------------------------------------------------------------
# Lazy-initialised singletons — ChromaDB and LLM clients are expensive to spin
# up on every request, so we create them once and reuse.
# ---------------------------------------------------------------------------

_retriever = None
_llm = None
_prompt = None


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
        _llm = load_llm()
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
# Tier-aware rate limiting helper
# ---------------------------------------------------------------------------

def _resolve_tier(user_id: str | None, role: str | None = None) -> str:
    """Determine the rate-limit tier for a given user.

    Admin users are exempt from rate limiting (returns 'ADMIN').
    If the user is found in the database, their stored tier is used.
    Falls back to FREE_USER for anonymous or unknown users.
    """
    if role == "admin":
        return "ADMIN"
    if user_id and user_id != "anonymous":
        user = get_user_by_id(user_id)
        if user:
            if user["role"] == "admin":
                return "ADMIN"
            return user.get("tier", "FREE_USER")
    return "FREE_USER"


def _apply_rate_limit(key: str, tier: str) -> dict[str, str]:
    """Check the rate limiter and raise HTTP 429 if exceeded.

    Returns a dict of rate-limit headers to include in the response.
    """
    allowed, limit, remaining = rate_limiter.check(key, tier)
    headers = {
        "X-RateLimit-Limit": str(limit),
        "X-RateLimit-Remaining": str(remaining),
    }
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please try again later.",
            headers=headers,
        )
    return headers


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/chat")
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

    # Tier-aware rate limiting — keyed by user_id (or IP for anonymous).
    rate_key = req.user_id if req.user_id != "anonymous" else (
        request.client.host if request.client else "unknown"
    )
    tier = await asyncio.to_thread(_resolve_tier, req.user_id)
    rl_headers = _apply_rate_limit(rate_key, tier)

    log.info(
        "Chat | question=%r history_len=%d session_id=%s",
        req.question, len(req.history), req.session_id,
    )
    return StreamingResponse(
        _stream_sse(req.question, req.history, req.session_id, req.user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            **rl_headers,
        },
    )


@app.post("/api/upload")
async def upload(request: Request, file: UploadFile = File(...)):
    """Save an uploaded PDF to DOCS_PATH and ingest it into ChromaDB."""
    # Rate limit uploads by IP — there is no authenticated user context here.
    upload_key = request.client.host if request.client else "unknown"
    tier = "FREE_USER"
    _apply_rate_limit(f"upload:{upload_key}", tier)

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    DOCS_PATH.mkdir(parents=True, exist_ok=True)
    dest = DOCS_PATH / file.filename

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    size_kb = round(dest.stat().st_size / 1024, 1)
    log.info("PDF received: %s (%.1f KB)", file.filename, size_kb)

    # Ingestion is CPU/IO-bound — run it in a thread so we don't block the loop.
    try:
        await asyncio.to_thread(_ingest_pdf, dest)
    except Exception as exc:
        log.exception("Ingestion failed for %s", file.filename)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc

    # Invalidate the retriever so the next chat request picks up the new content.
    _invalidate_components()

    ip = request.client.host if request.client else None
    await asyncio.to_thread(
        log_event, None, "DOC_UPLOADED", ip,
        {"filename": file.filename, "size_kb": size_kb},
    )

    return {"message": f"'{file.filename}' ingested successfully."}


def _ingest_pdf(pdf_path: Path) -> None:
    """Ingest a single PDF into the vector store (called from a thread pool).

    Reuses load_and_split() and compute_file_hash() from ingest.py to keep
    chunking behaviour identical between the CLI and the web upload path.
    """
    from ingest import compute_file_hash, load_and_split
    from langchain_openai import OpenAIEmbeddings

    store = get_vector_store()
    embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")

    file_hash = compute_file_hash(pdf_path)

    # Skip re-ingestion if the file content has not changed.
    existing_hashes = {m.get("file_hash") for m in store.get_all_metadata()}
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

    store.add_documents(ids=ids, documents=documents, metadatas=metadatas, embeddings=vectors)
    log.info("Ingested %s | chunks=%d", pdf_path.name, len(chunks))


@app.get("/api/documents")
async def list_documents():
    """Return unique filenames currently in the vector store.

    Reading from the vector store (not just DOCS_PATH) ensures the list
    accurately reflects what the RAG pipeline can actually retrieve from.
    """

    def _query_store():
        try:
            store = get_vector_store()
            metadatas = store.get_all_metadata()
        except Exception:
            return []

        seen: dict[str, bool] = {}
        for meta in metadatas:
            name = meta.get("source_file")
            if name:
                seen[name] = True

        documents = []
        for name in seen:
            disk_path = DOCS_PATH / name
            size_kb = round(disk_path.stat().st_size / 1024, 1) if disk_path.exists() else None
            documents.append({"name": name, "size_kb": size_kb})

        return documents

    documents = await asyncio.to_thread(_query_store)
    return {"documents": documents}


@app.delete("/api/documents/{filename}")
async def delete_document(request: Request, filename: str):
    """Remove all vector store embeddings for filename and delete the PDF from disk.

    Steps:
      1. Delete all chunks where source_file == filename via the vector store.
      2. Delete the physical PDF file from DOCS_PATH (if it exists).
      3. Invalidate the retriever cache so the next chat request does not
         serve stale results from the now-deleted document.
    """

    def _delete_from_store():
        try:
            store = get_vector_store()
        except Exception:
            raise HTTPException(status_code=404, detail="No documents have been ingested yet.")

        deleted = store.delete_by_metadata("source_file", filename)

        if deleted == 0:
            raise HTTPException(
                status_code=404,
                detail=f"'{filename}' was not found in the vector store.",
            )

        log.info("Deleted %d chunks for '%s' from vector store", deleted, filename)
        return deleted

    chunks_deleted = await asyncio.to_thread(_delete_from_store)

    # Also remove the physical file so it cannot be re-ingested accidentally.
    disk_path = DOCS_PATH / filename
    if disk_path.exists():
        disk_path.unlink()
        log.info("Deleted file from disk: %s", disk_path)

    # Drop cached retriever so the next request rebuilds it without this file.
    _invalidate_components()

    ip = request.client.host if request.client else None
    await asyncio.to_thread(
        log_event, None, "DOC_DELETED", ip,
        {"filename": filename, "chunks_removed": chunks_deleted},
    )

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


# Login attempts are rate-limited much more aggressively than chat:
# 5 attempts per 5 minutes per IP to mitigate brute-force attacks.
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_WINDOW_SECONDS = 300


@app.post("/api/auth/login")
async def login(request: Request, req: LoginRequest):
    """Verify credentials and return user info (without password hash).

    The actual session/token management lives in NextAuth on the frontend;
    this endpoint just validates username + bcrypt hash in SQLite.
    """
    ip = request.client.host if request.client else None

    # Tight rate limit on login attempts to slow down brute-force attacks.
    login_key = f"login:{ip or 'unknown'}"
    allowed, limit, remaining = rate_limiter.check(
        login_key, "LOGIN",
        max_requests=_LOGIN_MAX_ATTEMPTS,
        window=_LOGIN_WINDOW_SECONDS,
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again later.",
            headers={
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
            },
        )

    user = await asyncio.to_thread(verify_user, req.username, req.password)
    if not user:
        # Log the failed attempt — user_id is unknown, so record the username
        # in details for investigation purposes.
        await asyncio.to_thread(
            log_event, None, "LOGIN_FAILED", ip,
            {"username": req.username},
        )
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    await asyncio.to_thread(
        log_event, user["id"], "LOGIN_SUCCESS", ip,
        {"username": user["username"]},
    )
    log.info("Login successful | user=%s role=%s", user["username"], user["role"])
    return user


@app.post("/api/auth/register")
async def register(request: Request, req: RegisterRequest):
    """Create a new user account with a bcrypt-hashed password."""
    existing = await asyncio.to_thread(get_user_by_username, req.username)
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken.")
    user = await asyncio.to_thread(create_user, req.username, req.password, req.name, req.role)
    ip = request.client.host if request.client else None
    await asyncio.to_thread(
        log_event, user["id"], "USER_CREATED", ip,
        {"username": user["username"], "role": user["role"]},
    )
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
    ip = request.client.host if request.client else None
    await asyncio.to_thread(
        log_event, None, "USER_DELETED", ip,
        {"target_user_id": user_id},
    )
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
    ip = request.client.host if request.client else None
    await asyncio.to_thread(
        log_event, user_id, "PASSWORD_CHANGED", ip, None,
    )
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
    ip = request.client.host if request.client else None
    await asyncio.to_thread(
        log_event, req.user_id, "API_KEY_CREATED", ip,
        {"label": req.label, "prefix": result["prefix"]},
    )
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
    ip = request.client.host if request.client else None
    await asyncio.to_thread(
        log_event, None, "API_KEY_REVOKED", ip,
        {"key_id": key_id},
    )
    log.info("API key revoked | key_id=%s", key_id)
    return {"message": "API key revoked."}


# ---------------------------------------------------------------------------
# Admin — Audit log
# ---------------------------------------------------------------------------

@app.get("/api/admin/audit-logs")
async def admin_get_audit_logs(request: Request, limit: int = 100):
    """Return the most recent audit log entries (admin only)."""
    _require_admin(request)
    logs = await asyncio.to_thread(get_audit_logs, limit)
    return {"audit_logs": logs}


@app.get("/api/health")
async def health():
    return {"status": "ok"}
