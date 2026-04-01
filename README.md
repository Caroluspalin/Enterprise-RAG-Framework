# 🤖 B2B RAG Chatbot

> **Ask your company documents anything — and get cited, grounded answers in seconds.**

An enterprise-ready Retrieval-Augmented Generation (RAG) chatbot that turns your internal PDF library into a conversational knowledge base. Built with LangChain, ChromaDB, and OpenAI — runs entirely on your machine, no cloud infrastructure required.

---

## ✨ Key Features

### 🧠 Smart Ingestion
- Recursively scans a document folder and ingests all PDFs automatically
- **SHA-256 deduplication** — unchanged files are never re-embedded, saving time and API costs
- Chunk-level metadata (filename, page number) preserved for precise source citations

### 🔍 Semantic Vector Search
- Embeddings stored in a **local ChromaDB** instance — your data never leaves your machine
- Configurable `TOP_K`, `CHUNK_SIZE`, and `CHUNK_OVERLAP` for tuning retrieval quality
- Persistent storage survives restarts; re-ingest only what changed

### 💬 Conversational Memory
- Follow-up questions work naturally — the chain reformulates them as standalone queries before hitting the retriever
- Session memory resets cleanly with `/reset` without touching the vector store

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
# Compare retrieval strategies side-by-side
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

### 3. Add your documents

```bash
cp your-company-docs/*.pdf docs/
```

### 4. Ingest

```bash
python src/ingest.py
```

### 5. Chat

```bash
python src/chat.py
```

---

## 💬 Chat Commands

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
├── docs/                   # Drop PDF files here
├── logs/                   # Auto-created; rotating app.log + eval reports
├── chroma_db/              # Persisted vector store (auto-created on first ingest)
├── src/
│   ├── ingest.py           # PDF loader, chunker, embedder, deduplicator
│   ├── retriever.py        # ChromaDB wrapper exposing a LangChain retriever
│   ├── chain.py            # RAG chain: prompt + LLM + memory + logging
│   ├── chat.py             # Interactive terminal UI
│   ├── evaluate.py         # Automated evaluation suite
│   └── logger.py           # Centralised rotating-file logger
├── eval_questions.json     # Test cases for evaluate.py
├── .env.example            # All configurable parameters with defaults
├── requirements.txt
└── CLAUDE.md               # Project context and build roadmap
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
| `CHUNK_OVERLAP` | `200` | Overlap between consecutive chunks |
| `TOP_K` | `5` | Chunks retrieved per query |
| `LOG_DIR` | `./logs` | Log file output directory |
| `LOG_LEVEL` | `INFO` | Logging verbosity: `DEBUG`, `INFO`, `WARNING` |

---

## 🏛️ Architecture

```
PDFs in docs/
     │
     ▼
[ ingest.py ]
  SHA-256 dedup → PyPDFLoader → RecursiveCharacterTextSplitter
     │
     ▼
  OpenAI text-embedding-3-small
     │
     ▼
  ChromaDB  (persisted to chroma_db/)
     │
     ▼
[ chat.py ]  ←  user question
     │
     ▼
[ retriever.py ]  →  top-k semantically similar chunks
     │
     ▼
[ chain.py ]  →  system prompt + context + conversation history
     │
     ▼
  LLM (OpenAI / Anthropic / Ollama)
     │
     ▼
  Answer + source citations printed to terminal
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Orchestration | LangChain 0.3 |
| Vector store | ChromaDB 1.5 (local) |
| Embeddings | OpenAI `text-embedding-3-small` |
| LLM | GPT-4o / Claude Sonnet / Llama 3 |
| PDF parsing | PyPDF |
| Terminal UI | Rich |
| Logging | Python `logging` + `RotatingFileHandler` |

---

## 📄 License

MIT
