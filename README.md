# B2B RAG Chatbot

[![CI](https://github.com/Caroluspalin/Enterprise-RAG-Framework/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/Caroluspalin/Enterprise-RAG-Framework/actions/workflows/ci.yml)

> Ask your company documents anything — and get cited, grounded answers in seconds.

A production-ready Retrieval-Augmented Generation (RAG) chatbot that turns an internal PDF library into a conversational knowledge base. Ships with a streaming web UI, chat history, role-based authentication, an admin panel for document management, an embeddable widget, and a terminal chat interface. Built with LangChain, ChromaDB, FastAPI, and Next.js — runs entirely on your own infrastructure.

---

## Features

### Web UI
- Dark-themed chat interface built with **Next.js 15 + Tailwind CSS**
- **Streaming responses** via Server-Sent Events — tokens appear word by word
- **Markdown rendering** in assistant messages — code blocks with syntax highlighting, bold, lists, tables (react-markdown + remark-gfm + rehype-highlight)
- **Source citation chips** beneath every answer (filename + page number)
- **Mobile-responsive layout** — slide-over sidebar with hamburger menu on small screens
- Live document list in the sidebar, reflecting what is actually in the vector store

### Chat History
- Conversations are automatically persisted to a **lightweight SQLite database**
- **Session list** in the sidebar — click any past conversation to reload it
- Sessions are **auto-titled** from the first user question
- **"New chat"** button starts a fresh conversation
- **Delete sessions** with a trash icon on hover
- History is tied to the authenticated user (via NextAuth email)

### Authentication & Access Control
- **Role-based login** powered by Auth.js (next-auth v5)
- Two roles out of the box: `user` (chat only) and `admin` (full management)
- All routes protected by Next.js middleware — unauthenticated users are redirected to the login page immediately, server-side

### Admin Panel
- Upload PDFs via drag-and-drop — ingested into ChromaDB automatically
- Live document table showing every file currently embedded in the vector store
- **Delete individual documents** — removes all embeddings from ChromaDB and the file from disk in one click

### Embeddable Chat Widget
- Standalone `/widget` route — a full-screen chat UI with no sidebar and no authentication
- Designed for **iframe embedding** on external websites (e.g. customer support bot on a client's site)
- **Configurable theme** via query parameters: `?title=`, `?accent=`, `?bg=`
- **CSP frame-ancestors** controlled via `WIDGET_ALLOWED_ORIGINS` env var
- Includes a ready-made `embed-test.html` demo page with a floating toggle button

### Smart Ingestion
- Recursively scans a folder and ingests all PDFs automatically
- **SHA-256 deduplication** — unchanged files are never re-embedded, saving time and API costs
- Chunk-level metadata (filename, page number) preserved for precise source citations

### Semantic Vector Search
- Embeddings stored in a **local ChromaDB** instance — data never leaves your machine
- Configurable `TOP_K`, `CHUNK_SIZE`, and `CHUNK_OVERLAP` for tuning retrieval quality
- Persistent storage survives restarts; re-ingest only what changed

### Multi-Backend LLM Support
Switch your LLM with a single environment variable — no code changes needed:

| Backend | Model | Use case |
|---|---|---|
| `openai` | `gpt-4o` | Default, highest quality |
| `anthropic` | `claude-sonnet-4-6` | Strong reasoning, longer context |
| `ollama` | any local model | Fully offline, zero API costs |

---

## Quick Start

### 1. Clone & install Python dependencies

```bash
git clone https://github.com/Caroluspalin/Enterprise-RAG-Framework.git
cd Enterprise-RAG-Framework
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure the backend environment

```bash
cp .env.example .env
```

Edit `.env` and add your API key:

```ini
OPENAI_API_KEY=sk-...
LLM_BACKEND=openai        # or: anthropic / ollama
```

### 3. Add your documents and ingest

```bash
cp your-company-docs/*.pdf docs/
python src/ingest.py
```

---

## Running the Web UI

Two terminals — one for the API, one for the frontend.

The database (SQLite tables + default admin user) is created automatically when FastAPI starts via its lifespan event — no manual setup needed.

```bash
# Terminal 1 — FastAPI backend
cd src
uvicorn api:app --reload --port 8000

# Terminal 2 — Next.js frontend
cd frontend
npm install
cp .env.local.example .env.local   # add AUTH_SECRET (see below)
npm run dev
```

Open **http://localhost:3000**.

### Frontend environment variables

Create `frontend/.env.local`:

```ini
AUTH_SECRET=<random-string-min-32-chars>   # generate with: openssl rand -base64 32
NEXT_PUBLIC_API_URL=http://localhost:8000  # optional, this is the default
```

### Demo credentials

| Username | Password | Role |
|---|---|---|
| `user` | `user123` | Chat only |
| `admin` | `admin123` | Chat + Admin Panel |

> Replace these with a real database lookup before going to production.

---

## Terminal Chat

```bash
python src/chat.py
```

| Command | Action |
|---|---|
| `/list` | Show all ingested documents |
| `/reset` | Clear conversation memory (ChromaDB intact) |
| `/help` | Show available commands |
| `/exit` | Quit |

---

## Embedding the Chat Widget

The `/widget` route serves a lightweight, auth-free chat interface meant to live inside an `<iframe>` on any external site.

### Basic embed

```html
<iframe
  src="https://your-domain.com/widget"
  style="width: 380px; height: 520px; border: none; border-radius: 12px;"
  title="Chat"
></iframe>
```

### Themed embed

Customise the widget appearance with query parameters:

| Parameter | Description | Example |
|---|---|---|
| `title` | Header bar text | `?title=Support%20Bot` |
| `accent` | Hex color for header and send button (no `#`) | `?accent=16a34a` |
| `bg` | Hex color for background (no `#`) | `?bg=0f172a` |

```html
<iframe
  src="https://your-domain.com/widget?title=Acme%20Support&accent=16a34a&bg=1e293b"
  style="width: 380px; height: 520px; border: none; border-radius: 12px;"
  title="Chat"
></iframe>
```

### Restricting embedding origins

By default, any origin can embed the widget. Set `WIDGET_ALLOWED_ORIGINS` in your environment to lock it down:

```ini
# Only allow these domains to embed the widget
WIDGET_ALLOWED_ORIGINS=https://example.com https://app.example.com
```

To try it locally, open **http://localhost:3000/embed-test.html** while the dev server is running.

---

## Project Structure

```
b2b-rag-chatbot/
├── docs/                      # Drop PDF files here (CLI ingest)
├── logs/                      # Rotating app.log + evaluation reports (auto-created)
├── chroma_db/                 # Persisted vector store (auto-created on first ingest)
├── src/
│   ├── api.py                 # FastAPI — SSE chat, PDF upload, documents, sessions
│   ├── db.py                  # SQLite chat history — sessions & messages
│   ├── ingest.py              # PDF loader, chunker, embedder, SHA-256 deduplicator
│   ├── retriever.py           # ChromaDB wrapper exposing a LangChain retriever
│   ├── chain.py               # RAG chain: prompt + LLM + conversation history
│   ├── chat.py                # Interactive terminal UI
│   ├── evaluate.py            # Automated evaluation suite
│   └── logger.py              # Centralised rotating-file logger
├── frontend/
│   ├── app/
│   │   ├── admin/page.tsx     # Admin panel (server-side role guard)
│   │   ├── api/auth/          # NextAuth route handler
│   │   ├── login/page.tsx     # Login page
│   │   ├── widget/page.tsx    # Embeddable chat widget (no auth, themed via query params)
│   │   ├── layout.tsx         # Root layout with SessionProvider
│   │   └── page.tsx           # Main chat UI with session management
│   ├── public/
│   │   └── embed-test.html    # Demo page: simulated client site with iframe widget
│   ├── components/
│   │   ├── AdminPanel.tsx     # Document table with upload + delete
│   │   ├── ChatWindow.tsx     # Streaming message list with auto-scroll
│   │   ├── ChatInput.tsx      # Question input bar (supports accent color override)
│   │   ├── MessageBubble.tsx  # Message with markdown rendering + source chips
│   │   ├── Sidebar.tsx        # Chat history list, document list, admin link
│   │   ├── SignOutButton.tsx  # NextAuth sign-out
│   │   └── UploadPanel.tsx    # Drag-and-drop PDF uploader
│   ├── lib/api.ts             # Fetch wrappers for the FastAPI backend
│   ├── types/index.ts         # Shared TypeScript types
│   ├── auth.ts                # Auth.js config (Credentials provider, role callbacks)
│   └── middleware.ts          # Route protection + widget CSP headers
├── eval_questions.json        # Test cases for evaluate.py
├── .env.example               # All configurable backend parameters with defaults
└── requirements.txt           # Python dependencies
```

---

## Architecture

```
PDFs (drag-and-drop in Admin Panel or CLI)
     │
     ▼
[ ingest.py / api.py ]
  SHA-256 dedup → PyPDFLoader → RecursiveCharacterTextSplitter
     │
     ▼
  OpenAI text-embedding-3-small
     │
     ▼
  ChromaDB  (persisted to chroma_db/)
     │
     ▼
[ api.py ]  ←  POST /api/chat  ←  [ Next.js frontend ]
[ chat.py ] ←  terminal input
     │
     ▼
[ retriever.py ]  →  top-k semantically similar chunks
     │
     ▼
  LCEL chain: system prompt + context + conversation history
     │
     ▼                                ┌──────────────┐
  LLM  (OpenAI / Anthropic / Ollama)  │  SQLite DB   │
     │                                │  (sessions   │
     ▼                                │   & messages) │
  Streaming answer + source citations └──────┬───────┘
     │                                       │
     ▼                                       ▼
  Browser (SSE) or terminal           Chat history persisted
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/chat` | Streaming SSE chat (optionally persists to session) |
| `POST` | `/api/chat/sessions` | Create a new chat session |
| `GET` | `/api/chat/sessions?user_id=X` | List sessions for a user |
| `GET` | `/api/chat/sessions/{id}` | Get session metadata and messages |
| `DELETE` | `/api/chat/sessions/{id}` | Delete a session and its messages |
| `POST` | `/api/upload` | Upload and ingest a PDF |
| `GET` | `/api/documents` | List files in the vector store |
| `DELETE` | `/api/documents/{filename}` | Remove a file's embeddings + file from disk |
| `GET` | `/api/health` | Health check |

---

## Configuration Reference

All backend settings live in `.env`:

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | Required for OpenAI embeddings and LLM |
| `ANTHROPIC_API_KEY` | — | Required if `LLM_BACKEND=anthropic` |
| `LLM_BACKEND` | `openai` | LLM provider: `openai`, `anthropic`, `ollama` |
| `DOCS_PATH` | `./docs` | Folder scanned for PDFs |
| `CHROMA_PATH` | `./chroma_db` | ChromaDB persistence directory |
| `COLLECTION_NAME` | `b2b_docs` | ChromaDB collection name |
| `CHUNK_SIZE` | `1000` | Characters per chunk |
| `CHUNK_OVERLAP` | `200` | Overlap between chunks |
| `TOP_K` | `5` | Chunks retrieved per query |
| `LOG_LEVEL` | `INFO` | Logging verbosity: `DEBUG`, `INFO`, `WARNING` |
| `CHAT_DB_PATH` | `./chat_history.db` | SQLite database for chat history |
| `WIDGET_ALLOWED_ORIGINS` | `*` | Origins allowed to embed `/widget` (space-separated) |

Frontend settings live in `frontend/.env.local`:

| Variable | Description |
|---|---|
| `AUTH_SECRET` | Auth.js session encryption key (min 32 chars) |
| `NEXT_PUBLIC_API_URL` | FastAPI backend URL (default: `http://localhost:8000`) |

---

## Testing

Backend tests run with pytest. The test suite uses in-memory SQLite and mocked LLM/retriever, so no API keys or external services are needed.

```bash
pip install pytest pytest-mock pytest-cov httpx fpdf2
python -m pytest tests/ -q
```

A CI pipeline (GitHub Actions) runs these tests plus a Bandit security scan on every push to `master` and on pull requests.

---

## Advanced: RAG Evaluation (Ragas)

`scripts/evaluate.py` measures RAG quality against a golden dataset using the [Ragas](https://docs.ragas.io/) framework:

- **Faithfulness** — is the answer grounded in the retrieved context, or does it hallucinate?
- **Answer Relevancy** — does the generated answer actually address the question?

```bash
pip install ragas
python scripts/evaluate.py
```

Results are printed as a per-question table and an aggregate summary.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Orchestration | LangChain 0.3 |
| Vector store | ChromaDB (local, persistent) |
| Embeddings | OpenAI `text-embedding-3-small` |
| LLM | GPT-4o / Claude Sonnet / Llama 3 |
| PDF parsing | PyPDF |
| API backend | FastAPI + Uvicorn (SSE streaming) |
| Chat persistence | SQLite (Python `sqlite3`) |
| Authentication | Auth.js v5 (next-auth beta) |
| Web frontend | Next.js 15, React 19, Tailwind CSS |
| Markdown rendering | react-markdown, remark-gfm, rehype-highlight |
| Terminal UI | Rich |
| Logging | Python `logging` + `RotatingFileHandler` |

---

## License

MIT
