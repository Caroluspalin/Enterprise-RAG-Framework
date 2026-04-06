# B2B RAG Chatbot

A Retrieval-Augmented Generation (RAG) chatbot that ingests PDF documents and answers questions about them using LangChain and ChromaDB. Available as a terminal chat and a web UI (Next.js + FastAPI).

---

## Overview

This project enables B2B teams to query internal documents (contracts, specs, reports, manuals) through a conversational terminal interface. Documents are chunked, embedded, and stored in a local vector database. At query time, relevant chunks are retrieved and passed to an LLM to generate grounded answers.

---

## Architecture

```
b2b-rag-chatbot/
├── docs/                   # Drop your PDF files here
├── chroma_db/              # Persisted ChromaDB vector store (auto-created)
├── src/
│   ├── ingest.py           # Loads, chunks, and embeds PDFs into ChromaDB
│   ├── retriever.py        # Wraps ChromaDB with a LangChain retriever
│   ├── chain.py            # Builds the RAG chain (retriever + LLM + prompt)
│   ├── chat.py             # Terminal chat loop (entry point)
│   └── api.py              # FastAPI backend (SSE streaming, upload, doc list)
├── frontend/               # Next.js 15 web UI
│   ├── app/                # App Router pages and layout
│   │   └── widget/         # Embeddable chat widget (no sidebar, no auth)
│   ├── components/         # ChatWindow, MessageBubble, Sidebar, UploadPanel…
│   ├── public/widget.js        # Embeddable chat widget script (vanilla JS, Shadow DOM)
│   ├── public/embed-test.html  # Demo page showing the widget.js integration
│   ├── lib/api.ts          # Fetch wrappers for the FastAPI backend
│   └── types/index.ts      # Shared TypeScript types
├── .env                    # API keys and config (not committed)
├── .env.example            # Template for required environment variables
├── requirements.txt
└── CLAUDE.md
```

### Data Flow

```
PDFs in docs/
     │
     ▼
[ingest.py]
  PyPDFLoader → text chunks (RecursiveCharacterTextSplitter)
     │
     ▼
  OpenAI / local embeddings
     │
     ▼
  ChromaDB (persisted to chroma_db/)
     │
     ▼
[chat.py] ← user question
     │
     ▼
[retriever.py] → top-k relevant chunks
     │
     ▼
[chain.py] → LLM (Claude / OpenAI / Ollama) + context
     │
     ▼
  Answer printed to terminal
```

---

## Dependencies

### Core

| Package | Purpose |
|---|---|
| `langchain` | Orchestration framework (chains, retrievers, prompts) |
| `langchain-community` | PDF loaders, ChromaDB integration |
| `langchain-openai` | OpenAI LLM and embedding wrappers |
| `chromadb` | Local persistent vector database |
| `pypdf` | PDF text extraction |
| `python-dotenv` | Load environment variables from `.env` |
| `bcrypt` | Secure password hashing (bcrypt algorithm) |

### Optional

| Package | Purpose |
|---|---|
| `langchain-anthropic` | Use Claude models instead of OpenAI |
| `ollama` | Run local LLMs (no API key required) |
| `tiktoken` | Token counting for chunking strategies |
| `rich` | Prettier terminal output |

Install all dependencies:

```bash
pip install -r requirements.txt
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

```ini
# .env.example
OPENAI_API_KEY=sk-...          # Required if using OpenAI embeddings or LLM
ANTHROPIC_API_KEY=...          # Required if using Claude as the LLM
COLLECTION_NAME=b2b_docs       # ChromaDB collection name
DOCS_PATH=./docs               # Folder to scan for PDFs
CHROMA_PATH=./chroma_db        # Where ChromaDB persists data
CHUNK_SIZE=1000                # Characters per chunk
CHUNK_OVERLAP=200              # Overlap between chunks
TOP_K=5                        # Number of chunks retrieved per query
ALLOWED_ORIGINS=https://myapp.vercel.app  # Comma-separated CORS origins
WIDGET_API_KEY=                # Secret for X-Widget-Key header (generate with secrets.token_urlsafe)
CHAT_RATE_LIMIT=5/minute       # Rate limit for /api/chat per IP
BACKEND_URL=http://localhost:8000  # FastAPI URL for NextAuth server-side credential verification
```

---

## Build Roadmap

### Phase 1 — Project Scaffold
- [ ] Create directory structure (`docs/`, `src/`, `chroma_db/`)
- [ ] Write `requirements.txt`
- [ ] Write `.env.example`
- [ ] Initialize git repository and add `.gitignore` (exclude `chroma_db/`, `.env`, `docs/`)

### Phase 2 — Document Ingestion (`src/ingest.py`)
- [ ] Recursively discover all `.pdf` files under `DOCS_PATH`
- [ ] Load each PDF with `PyPDFLoader`
- [ ] Split documents into chunks with `RecursiveCharacterTextSplitter`
- [ ] Generate embeddings (OpenAI `text-embedding-3-small` or local)
- [ ] Persist chunks and embeddings to ChromaDB
- [ ] Print ingestion summary (files processed, chunks stored)
- [ ] Add `--reset` flag to wipe and re-ingest from scratch

### Phase 3 — Retriever (`src/retriever.py`)
- [ ] Load the persisted ChromaDB collection
- [ ] Expose a `get_retriever(k: int)` function returning a LangChain `VectorStoreRetriever`
- [ ] Optionally add metadata filtering (e.g. by filename or date)

### Phase 4 — RAG Chain (`src/chain.py`)
- [ ] Write a system prompt that instructs the LLM to answer only from provided context
- [ ] Build a `RetrievalQA` or `ConversationalRetrievalChain` using the retriever
- [ ] Include source document metadata (filename, page number) in the response
- [ ] Support swappable LLM backends via environment variable (`OPENAI`, `ANTHROPIC`, `OLLAMA`)

### Phase 5 — Terminal Chat Interface (`src/chat.py`)
- [ ] Print startup banner with loaded document count
- [ ] Run an input loop: read question → invoke chain → print answer + sources
- [ ] Handle `/exit`, `/reset`, `/list` commands
- [ ] Maintain conversation history for follow-up questions

### Phase 6 — Quality & Hardening
- [x] Add chunk deduplication (skip re-ingesting unchanged files via content hash)
- [x] Add logging to file for debugging ingestion and retrieval
- [x] Evaluate retrieval quality with a small test question set
- [ ] Tune `CHUNK_SIZE`, `CHUNK_OVERLAP`, and `TOP_K` based on evaluation

### Phase 7 — Web UI (Next.js + FastAPI)
- [x] FastAPI backend (`src/api.py`) with SSE streaming, PDF upload, document list endpoints
- [x] Next.js 15 frontend scaffold (App Router, Tailwind CSS, TypeScript)
- [x] Chat UI: streaming message bubbles, blinking cursor, auto-scroll
- [x] PDF upload panel with drag-and-drop in the sidebar
- [x] Source citation chips displayed below each assistant message
- [x] Document list in sidebar (live-refreshed after upload)
- [x] Markdown rendering in assistant messages (react-markdown + remark-gfm + rehype-highlight)
- [x] Mobile-responsive layout (slide-over sidebar, hamburger menu, wider bubbles)

### Phase 7b — Chat History & Analytics Foundation
- [x] SQLite database module (`src/db.py`) with `sessions` and `messages` tables
- [x] CRUD functions: create/get/list/delete sessions, add/get messages
- [x] Auto-title sessions from first user question
- [x] API endpoints: POST/GET/DELETE `/api/chat/sessions`, GET `/api/chat/sessions/{id}`
- [x] Chat endpoint (`POST /api/chat`) auto-persists Q&A when `session_id` is provided
- [x] Frontend: session management, history sidebar, load past conversations
- [x] Analytics dashboard (message counts, popular questions, usage over time)

### Phase 8 — Embeddable Chat Widget
- [x] Standalone `/widget` route (full-screen chat, no sidebar, no auth)
- [x] `embed-test.html` demo page with floating iframe toggle
- [x] Disable Next.js dev indicator so it does not overlap widget input
- [x] Configurable widget theme (colors, title) via query params (?title=, ?accent=, ?bg=)
- [x] Origin allowlist for iframe embedding (CSP frame-ancestors via middleware + WIDGET_ALLOWED_ORIGINS env)
- [x] `widget.js` — standalone embeddable script (vanilla JS, Shadow DOM, zero dependencies)
- [x] One-line `<script>` integration for any external website
- [x] SSE streaming direct to FastAPI backend with X-Widget-Key auth
- [x] SessionStorage-based session persistence (chat history across page navigations)
- [x] Safe text rendering (no innerHTML, XSS-proof, basic Markdown support)
- [x] ARIA attributes, keyboard navigation (Enter/Escape), screen reader support
- [x] Mobile-responsive (full-screen on small viewports)
- [x] Typing indicator (animated dots), error banners, rate-limit handling
- [x] Configurable via data-* attributes (api, key, title, accent, bg, position)

### Phase 9 — User Management & Auth Hardening
- [x] `users` table in SQLite with bcrypt password hashing (passlib)
- [x] CRUD functions: create_user, verify_user, get_user_by_username, list_users
- [x] Default admin seed on first run (`admin` / `admin123` — change immediately)
- [x] `POST /api/auth/login` — verify credentials against hashed passwords
- [x] `POST /api/auth/register` — create new users with bcrypt hashing
- [x] `auth.ts` calls FastAPI backend instead of hardcoded demo users
- [x] `BACKEND_URL` env var for server-side auth calls
- [x] `GET /api/analytics` endpoint with message counts, per-day stats, popular & recent questions
- [x] Admin panel analytics tab with stat cards, bar chart, question lists
- [ ] Admin panel user management (list / create / delete users)
- [ ] Password change endpoint and UI
- [ ] JWT-based API authentication (replace widget key with proper tokens)

---

## Quick Start (once built)

```bash
# 1. Install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your API key

# 3. Add PDFs
cp your-documents/*.pdf docs/

# 4. Ingest documents
python src/ingest.py

# 5. Start chatting
python src/chat.py
```

---

## Design Decisions

**ChromaDB over cloud vector DBs** — zero infrastructure, data stays local, suitable for sensitive B2B documents.

**Chunk overlap** — prevents answers from being cut off at chunk boundaries; tune based on document type.

**Source citation** — every answer includes filename and page number so users can verify claims in the source document.

**Swappable LLM** — the chain is decoupled from the model provider; switch between OpenAI, Claude, or a local Ollama model by changing one env variable.

---

## Instructions for Claude

- Keep this file up to date as the project evolves — file structure, roadmap checkboxes, design decisions. This is the primary source of truth for project state across sessions.
- Do not use emojis in code comments.
- Comment code well: explain the *why* behind non-obvious logic, not just what the code does.
