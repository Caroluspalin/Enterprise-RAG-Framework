# B2B RAG Chatbot

> Ask your company documents anything — and get cited, grounded answers in seconds.

A production-ready Retrieval-Augmented Generation (RAG) chatbot that turns an internal PDF library into a conversational knowledge base. Ships with a streaming web UI, role-based authentication, an admin panel for document management, and a terminal chat interface. Built with LangChain, ChromaDB, FastAPI, and Next.js — runs entirely on your own infrastructure.

---

## Features

### Web UI
- Dark-themed chat interface built with **Next.js 15 + Tailwind CSS**
- **Streaming responses** via Server-Sent Events — tokens appear word by word
- **Source citation chips** beneath every answer (filename + page number)
- Live document list in the sidebar, reflecting what is actually in the vector store

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
- Includes a ready-made `embed-test.html` demo page with a floating toggle button in the bottom-right corner

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
git clone <your-repo-url>
cd b2b-rag-chatbot
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

Two terminals — one for the API, one for the frontend:

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

The `/widget` route serves a lightweight, auth-free chat interface meant to live inside an `<iframe>` on any external site:

```html
<iframe
  src="https://your-domain.com/widget"
  style="width: 380px; height: 520px; border: none; border-radius: 12px;"
  title="Chat"
></iframe>
```

To try it locally, open **http://localhost:3000/embed-test.html** while the dev server is running — it simulates a customer website with a floating chat button.

---

## Project Structure

```
b2b-rag-chatbot/
├── docs/                      # Drop PDF files here (CLI ingest)
├── logs/                      # Rotating app.log + evaluation reports (auto-created)
├── chroma_db/                 # Persisted vector store (auto-created on first ingest)
├── src/
│   ├── api.py                 # FastAPI — SSE chat, PDF upload, document list & delete
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
│   │   ├── widget/page.tsx    # Embeddable chat widget (no auth, no sidebar)
│   │   ├── layout.tsx         # Root layout with SessionProvider
│   │   └── page.tsx           # Chat UI
│   ├── public/
│   │   └── embed-test.html    # Demo page: simulated client site with iframe widget
│   ├── components/
│   │   ├── AdminPanel.tsx     # Document table with upload + delete
│   │   ├── ChatWindow.tsx     # Streaming message list
│   │   ├── ChatInput.tsx      # Question input bar
│   │   ├── MessageBubble.tsx  # Individual message with source chips
│   │   ├── Sidebar.tsx        # Document list, admin link, sign-out
│   │   ├── SignOutButton.tsx  # NextAuth sign-out
│   │   └── UploadPanel.tsx    # Drag-and-drop PDF uploader
│   ├── lib/api.ts             # Fetch wrappers for the FastAPI backend
│   ├── types/index.ts         # Shared TypeScript types
│   ├── auth.ts                # Auth.js config (Credentials provider, role callbacks)
│   └── middleware.ts          # Route protection — redirects unauthenticated users
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
     ▼
  LLM  (OpenAI / Anthropic / Ollama)
     │
     ▼
  Streaming answer + source citations  →  browser (SSE) or terminal
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/chat` | Streaming SSE chat |
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

---

## Advanced: Automated Evaluation

`evaluate.py` measures retrieval and answer quality against a predefined test set without requiring a human reviewer:

- **Keyword hit rate** — fraction of expected terms found in each answer
- **Source retrieval accuracy** — did the retriever surface the right document?
- **Response time** — benchmarks across different `TOP_K` settings

```bash
python src/evaluate.py --top-k 5
```

Reports are saved to `logs/eval_<timestamp>.txt`.

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
| Authentication | Auth.js v5 (next-auth beta) |
| Web frontend | Next.js 15, React 19, Tailwind CSS |
| Terminal UI | Rich |
| Logging | Python `logging` + `RotatingFileHandler` |

---

## License

MIT
