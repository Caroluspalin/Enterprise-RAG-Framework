# B2B RAG Chatbot

> **SOP (Standard Operating Procedure):**
> - Aina kun aloitamme uuden chatin, lue valittomasti `CLAUDE.md`, `ROADMAP.md` ja `STATE.md` ennen kuin teet mitaan oletuksia.
> - Aina kun kayttaja antaa komennon **"Save state"**, sinun ON automaattisesti paivitettava `ROADMAP.md` tehdyilla asioilla ja kirjoitettava `STATE.md` -tiedostoon paivitetty nykytila ja uusi seuraava askel.

---

## Overview

A Retrieval-Augmented Generation (RAG) chatbot that ingests PDF documents and answers questions about them using LangChain and ChromaDB. Available as a terminal chat, a web UI (Next.js + FastAPI), and an embeddable widget for external sites.

**Live:** https://enterprise-rag-framework.vercel.app

---

## Architecture

```
b2b-rag-chatbot/
├── docs/                       # Drop PDF files here
├── chroma_db/                  # Persisted ChromaDB vector store (auto-created)
├── src/
│   ├── ingest.py               # Loads, chunks, and embeds PDFs into ChromaDB
│   ├── retriever.py            # Wraps ChromaDB with a LangChain retriever
│   ├── chain.py                # Builds the RAG chain (retriever + LLM + prompt)
│   ├── chat.py                 # Terminal chat loop (entry point)
│   ├── api.py                  # FastAPI backend (SSE streaming, admin, auth, upload)
│   ├── db.py                   # SQLite persistence (users, sessions, messages, api_keys)
│   └── logger.py               # Shared logging configuration
├── frontend/                   # Next.js 15 web UI
│   ├── app/                    # App Router pages and layout
│   │   ├── admin/              # Admin panel page (server component, role guard)
│   │   ├── api/admin/          # Next.js BFF routes (inject INTERNAL_ADMIN_SECRET)
│   │   ├── widget/             # Embeddable chat widget (no sidebar, no auth)
│   │   └── login/              # Login page
│   ├── components/             # React components
│   │   ├── AdminPanel.tsx      # Tabbed admin (Documents, Analytics, Users, API Keys)
│   │   ├── UsersTab.tsx        # User CRUD + password change modals
│   │   ├── ApiKeysTab.tsx      # API key management + "show once" secret banner
│   │   ├── Toast.tsx           # Toast notification system
│   │   ├── ChatWindow.tsx      # Message list with auto-scroll
│   │   ├── ChatInput.tsx       # Input with Enter/Shift+Enter
│   │   ├── MessageBubble.tsx   # User/assistant bubbles with markdown
│   │   ├── Sidebar.tsx         # Session list, doc list, upload
│   │   └── UploadPanel.tsx     # Drag-and-drop PDF upload
│   ├── lib/
│   │   ├── api.ts              # Browser-side fetch wrappers (chat, docs, sessions)
│   │   └── admin.ts            # Server-side only BFF (injects admin secret)
│   ├── public/
│   │   ├── widget.js           # Standalone embeddable widget (vanilla JS, Shadow DOM)
│   │   └── embed-test.html     # Demo page for widget.js
│   ├── types/index.ts          # Shared TypeScript types
│   ├── auth.ts                 # NextAuth v5 config (Credentials → FastAPI)
│   └── middleware.ts           # Auth guard + widget CSP headers
├── CLAUDE.md                   # This file — permanent architecture & rules
├── ROADMAP.md                  # Build phases and checkboxes
├── STATE.md                    # Current project state and next step
├── .env                        # API keys and config (not committed)
├── .env.example                # Template for required environment variables
└── requirements.txt
```

### Data Flow

```
PDFs in docs/
     │
     ▼
[ingest.py] → PyPDFLoader → RecursiveCharacterTextSplitter → OpenAI embeddings
     │
     ▼
ChromaDB (persisted to chroma_db/)
     │
     ▼
[api.py] POST /api/chat ← user question + X-Widget-Key header
     │
     ▼
[retriever.py] → top-k relevant chunks
     │
     ▼
LCEL chain (prompt + LLM + StrOutputParser) → SSE token stream
```

### Security Architecture

```
Browser (React / widget.js)
  │ — NEVER sees INTERNAL_ADMIN_SECRET
  │ — Sends X-Widget-Key for /api/chat
  ▼
Next.js (Vercel)
  │ — NextAuth session check (role === "admin")
  │ — Injects Authorization: Bearer <INTERNAL_ADMIN_SECRET>
  ▼
FastAPI (Render)
  │ — Validates INTERNAL_ADMIN_SECRET on /api/admin/* routes
  │ — Validates X-Widget-Key (DB hash lookup) on /api/chat
  │ — Rate limiting (slowapi, per IP)
  │ — CORS restricted to ALLOWED_ORIGINS
  ▼
SQLite (users, sessions, messages, api_keys)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM orchestration | LangChain (LCEL chains) |
| Vector DB | ChromaDB (local, persistent) |
| Embeddings | OpenAI `text-embedding-3-small` |
| LLM | Swappable: OpenAI GPT-4o / Claude / Ollama (via `LLM_BACKEND` env) |
| Backend API | FastAPI + uvicorn, SSE streaming |
| Database | SQLite (users, sessions, messages, api_keys) |
| Frontend | Next.js 15 (App Router, Tailwind CSS, TypeScript) |
| Auth | NextAuth v5 (Credentials provider → FastAPI bcrypt verification) |
| Rate limiting | slowapi |
| Widget | Vanilla JS, Shadow DOM, zero dependencies |

---

## Dependencies

### Python (requirements.txt)

| Package | Purpose |
|---|---|
| `langchain` | Orchestration framework |
| `langchain-openai` | OpenAI LLM and embedding wrappers |
| `langchain-anthropic` | Claude models (optional) |
| `langchain-chroma` | ChromaDB integration |
| `chromadb` | Local vector database |
| `pypdf` | PDF text extraction |
| `fastapi` + `uvicorn` | Web API |
| `slowapi` | Rate limiting |
| `python-dotenv` | Environment variables |
| `bcrypt` | Password hashing |

### Frontend (package.json)

Next.js 15, React 19, Tailwind CSS, next-auth v5, react-markdown, uuid

---

## Environment Variables

See `.env.example` for the full list. Key variables:

```ini
OPENAI_API_KEY=sk-...              # Required for embeddings and LLM
LLM_BACKEND=openai                 # openai | anthropic | ollama
ALLOWED_ORIGINS=https://...        # Comma-separated CORS origins
WIDGET_API_KEY=                    # Legacy widget key (fallback)
CHAT_RATE_LIMIT=5/minute           # Rate limit for /api/chat
INTERNAL_ADMIN_SECRET=             # Server-to-server secret for admin endpoints
BACKEND_URL=http://localhost:8000  # FastAPI URL (used by Next.js server-side)
```

---

## Quick Start

```bash
# Backend
cd src && pip install -r ../requirements.txt
uvicorn api:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev

# Open http://localhost:3000
# Admin panel: /admin (requires admin role)
# Widget demo: /embed-test.html
```

---

## Design Decisions

**ChromaDB over cloud vector DBs** — zero infrastructure, data stays local, suitable for sensitive B2B documents.

**Chunk overlap** — prevents answers from being cut off at chunk boundaries; tune based on document type.

**Source citation** — every answer includes filename and page number so users can verify claims.

**Swappable LLM** — decoupled from the model provider; switch via one env variable.

**Shadow DOM widget** — CSS-isolated, zero dependencies, works on any site with one `<script>` tag.

**Server-to-server admin auth** — INTERNAL_ADMIN_SECRET shared between Next.js and FastAPI. Browser never sees it. NextAuth session + role check on the Next.js side, secret validation on the FastAPI side.

**API key hashing** — raw keys shown once at creation, only SHA-256 hashes stored. Same model as GitHub/Stripe.

---

## Instructions for Claude

- Keep `CLAUDE.md` focused on permanent architecture, stack, and rules. Mutable state goes in `STATE.md`, roadmap progress in `ROADMAP.md`.
- Do not use emojis in code comments.
- Comment code well: explain the *why* behind non-obvious logic, not just what the code does.
- When completing work, update `ROADMAP.md` checkboxes and `STATE.md` accordingly.
