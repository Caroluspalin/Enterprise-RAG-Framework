# 🤖 B2B RAG Chatbot

> **Ask your company documents anything — and get cited, grounded answers in seconds.**

An enterprise-ready Retrieval-Augmented Generation (RAG) chatbot that turns your internal PDF library into a conversational knowledge base. Available as a **terminal chat** and a **streaming web UI**. Built with LangChain, ChromaDB, and OpenAI — runs entirely on your machine, no cloud infrastructure required.

---

## ✨ Key Features

### 🌐 Web UI (New)
- Modern dark-themed chat interface built with **Next.js 16 + Tailwind CSS**
- **Streaming responses** — tokens appear word by word, just like ChatGPT
- **Drag-and-drop PDF upload** directly from the browser — no CLI needed
- **Source citation chips** shown beneath every answer (filename + page number)
- Live document list in the sidebar, auto-refreshed after each upload

### 🧠 Smart Ingestion
- Recursively scans a document folder and ingests all PDFs automatically
- **SHA-256 deduplication** — unchanged files are never re-embedded, saving time and API costs
- Chunk-level metadata (filename, page number) preserved for precise source citations

### 🔍 Semantic Vector Search
- Embeddings stored in a **local ChromaDB** instance — your data never leaves your machine
- Configurable `TOP_K`, `CHUNK_SIZE`, and `CHUNK_OVERLAP` for tuning retrieval quality
- Persistent storage survives restarts; re-ingest only what changed

### 💬 Conversational Memory
- Follow-up questions work naturally — chat history is passed as context on every request
- Terminal mode: session memory resets cleanly with `/reset` without touching the vector store

### 🔌 Multi-Backend LLM Support
Switch your LLM with a single environment variable — no code changes needed:

| Backend | Model | Use case |
|---|---|---|
| `openai` | `gpt-4o` | Default, highest quality |
| `anthropic` | `claude-sonnet-4-6` | Strong reasoning, longer context |
| `ollama` | `llama3` (or any local model) | Fully offline, zero API costs |

---

## 🏗️ Advanced Components

### 📋 Production-Grade Logging
Every ingestion run and chat query is logged to a rotating file (`logs/app.log`) with timestamps, elapsed time, retrieved sources, and keyword metrics. Third-party noise is silenced so logs stay readable. Log level is configurable via `LOG_LEVEL` in `.env`.

```
2025-01-15 14:32:01 | INFO     | ingest  | Ingested techcorp_ohjeet.pdf | chunks=4 hash=a3f92c1d
2025-01-15 14:33:12 | INFO     | chain   | Query complete | elapsed=1.83s chunks_retrieved=5 sources=['techcorp_ohjeet.pdf']
```

### 🧪 Automated Evaluation Suite
A dedicated `evaluate.py` script measures chatbot quality against a predefined test set — **without a second LLM call**:

- **Keyword hit rate** — fraction of expected terms found in each answer
- **Source retrieval accuracy** — did the retriever surface the right document?
- **Response time** — benchmarks across different `TOP_K` settings
- Timestamped reports saved to `logs/eval_<timestamp>.txt` for tracking quality over time

```bash
python src/evaluate.py --top-k 3
python src/evaluate.py --top-k 8
```

---

## 🚀 Quick Start

### 1. Clone & install

```bash
git clone <your-repo-url>
cd b2b-rag-chatbot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Open `.env` and add your API key:

```ini
OPENAI_API_KEY=sk-...
LLM_BACKEND=openai        # or: anthropic / ollama
```

### 3. Add your documents & ingest

```bash
cp your-company-docs/*.pdf docs/
python src/ingest.py
```

---

## 🌐 Web UI

Run the FastAPI backend and the Next.js frontend side by side:

```bash
# Terminal 1 — API backend (from the src/ directory)
cd src
uvicorn api:app --reload --port 8000

# Terminal 2 — Next.js frontend
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000** in your browser.

- Drag a PDF onto the sidebar upload area → it is ingested automatically
- Type a question and hit Enter → the answer streams in token by token
- Source citations appear below each answer

---

## 💬 Terminal Chat

```bash
python src/chat.py
```

| Command | Action |
|---|---|
| `/list` | Show all ingested documents |
| `/reset` | Clear conversation memory (ChromaDB intact) |
| `/help` | Show available commands |
| `/exit` | Quit |
| `Ctrl+C` | Quit gracefully |

---

## 📁 Project Structure

```
b2b-rag-chatbot/
├── docs/                   # Drop PDF files here (for CLI ingest)
├── logs/                   # Auto-created; rotating app.log + eval reports
├── chroma_db/              # Persisted vector store (auto-created on first ingest)
├── src/
│   ├── api.py              # FastAPI backend — SSE streaming, upload, doc list
│   ├── ingest.py           # PDF loader, chunker, embedder, deduplicator
│   ├── retriever.py        # ChromaDB wrapper exposing a LangChain retriever
│   ├── chain.py            # RAG chain: prompt + LLM + memory + logging
│   ├── chat.py             # Interactive terminal UI
│   ├── evaluate.py         # Automated evaluation suite
│   └── logger.py           # Centralised rotating-file logger
├── frontend/               # Next.js 16 web UI
│   ├── app/                # App Router: layout, page, global styles
│   ├── components/         # ChatWindow, MessageBubble, Sidebar, UploadPanel…
│   ├── lib/api.ts          # Fetch wrappers for the FastAPI backend
│   └── types/index.ts      # Shared TypeScript types
├── eval_questions.json     # Test cases for evaluate.py
├── .env.example            # All configurable parameters with defaults
├── requirements.txt        # Python dependencies
└── CLAUDE.md               # Project context and build roadmap
```

---

## 🏛️ Architecture

```
PDFs (drag-and-drop or CLI)
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
[ api.py ]  ←  HTTP POST /api/chat  ←  [ Next.js frontend ]
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
  Streaming answer + source citations
```

---

## ⚙️ Configuration Reference

All settings live in `.env`:

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
| `LOG_DIR` | `./logs` | Log file output directory |
| `LOG_LEVEL` | `INFO` | Logging verbosity: `DEBUG`, `INFO`, `WARNING` |

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Orchestration | LangChain 0.3 |
| Vector store | ChromaDB 1.5 (local, persistent) |
| Embeddings | OpenAI `text-embedding-3-small` |
| LLM | GPT-4o / Claude Sonnet / Llama 3 |
| PDF parsing | PyPDF |
| API backend | FastAPI + Uvicorn (SSE streaming) |
| Web frontend | Next.js 16, React 19, Tailwind CSS |
| Terminal UI | Rich |
| Logging | Python `logging` + `RotatingFileHandler` |

---

## 💡 Selling to B2B Customers

This stack is a solid foundation for a commercial product:

- **Data stays on-prem** — ChromaDB is local, no SaaS dependency
- **Any LLM backend** — swap OpenAI for a private Anthropic or Ollama deployment
- **Multi-document** — load an entire document library; the retriever handles relevance automatically
- **Audit trail** — every query and source citation is logged
- **Extensible** — add auth, multi-tenancy, or a cloud vector DB without touching core logic

---

## 📄 License

MIT
