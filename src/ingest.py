"""
ingest.py

Scans DOCS_PATH for PDF files, splits them into overlapping text chunks,
generates embeddings, and persists everything to a local ChromaDB collection.

Run once before starting the chat:
    python src/ingest.py

Use --reset to wipe the existing collection and re-ingest from scratch:
    python src/ingest.py --reset
"""

import argparse
import hashlib
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rich.console import Console
from rich.progress import track

from logger import get_logger
from vectorstore import get_vector_store, reset_vector_store

load_dotenv()

console = Console()
log = get_logger("ingest")

# ---------------------------------------------------------------------------
# Configuration — all values come from .env with sensible fallbacks
# ---------------------------------------------------------------------------

DOCS_PATH = Path(os.getenv("DOCS_PATH", "./docs"))
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 1000))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 200))


def compute_file_hash(path: Path) -> str:
    """Return a SHA-256 hex digest of the file contents.

    Used to detect whether a PDF has already been ingested so we can skip
    re-processing unchanged files on subsequent runs.
    """
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            sha.update(block)
    return sha.hexdigest()


def find_pdfs(root: Path) -> list[Path]:
    """Recursively collect all .pdf files under root."""
    return sorted(root.rglob("*.pdf"))


def load_and_split(pdf_path: Path) -> list:
    """Load a single PDF and split it into overlapping chunks.

    PyPDFLoader extracts text page-by-page and preserves page numbers in
    document metadata, which we later surface as source citations in answers.
    """
    loader = PyPDFLoader(str(pdf_path))
    pages = loader.load()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        # Keep sentences and paragraphs together as long as possible before
        # falling back to character-level splits.
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_documents(pages)

    # Attach the source filename to every chunk so the retriever can cite it.
    for chunk in chunks:
        chunk.metadata["source_file"] = pdf_path.name

    return chunks


def get_already_ingested_hashes(store) -> set[str]:
    """Return the set of file hashes already stored in the vector store.

    Querying existing hashes lets us skip PDFs that have not changed since
    the last ingest run, avoiding duplicate embeddings and wasted API calls.
    """
    metadatas = store.get_all_metadata()
    return {m["file_hash"] for m in metadatas if "file_hash" in m}


def ingest(reset: bool = False) -> None:
    pdfs = find_pdfs(DOCS_PATH)
    if not pdfs:
        console.print(f"[yellow]No PDF files found in {DOCS_PATH}[/yellow]")
        log.warning("Ingest called but no PDF files found in %s", DOCS_PATH)
        sys.exit(0)

    log.info("Ingest started | docs_path=%s chunk_size=%d overlap=%d reset=%s",
             DOCS_PATH, CHUNK_SIZE, CHUNK_OVERLAP, reset)

    # Get the vector store via the abstraction layer.
    store = get_vector_store()

    if reset:
        console.print("[red]Resetting collection — deleting all existing chunks...[/red]")
        log.info("Resetting vector store collection")
        store.reset()

    embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")

    already_ingested = get_already_ingested_hashes(store)

    total_chunks_added = 0
    skipped_files = 0

    for pdf_path in track(pdfs, description="Processing PDFs..."):
        file_hash = compute_file_hash(pdf_path)

        if file_hash in already_ingested:
            # File content is unchanged — no need to re-embed.
            skipped_files += 1
            log.debug("Skipping unchanged file: %s (hash=%s)", pdf_path.name, file_hash[:8])
            continue

        chunks = load_and_split(pdf_path)
        if not chunks:
            console.print(f"[yellow]  Skipping {pdf_path.name} — no extractable text[/yellow]")
            log.warning("No extractable text in %s — skipping", pdf_path.name)
            continue

        # Build parallel lists that ChromaDB expects: ids, documents, metadatas, embeddings.
        ids = [f"{file_hash}_{i}" for i in range(len(chunks))]
        documents = [chunk.page_content for chunk in chunks]
        metadatas = [
            {
                **chunk.metadata,
                "file_hash": file_hash,
                # page is 0-indexed from PyPDFLoader; store 1-indexed for display.
                "page": chunk.metadata.get("page", 0) + 1,
            }
            for chunk in chunks
        ]

        # Generate all embeddings for this file in one batched API call.
        vectors = embeddings_model.embed_documents(documents)

        store.add_documents(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=vectors,
        )

        total_chunks_added += len(chunks)
        log.info("Ingested %s | chunks=%d hash=%s", pdf_path.name, len(chunks), file_hash[:8])
        console.print(f"  [green]Ingested[/green] {pdf_path.name} — {len(chunks)} chunks")

    log.info(
        "Ingest complete | processed=%d skipped=%d chunks_added=%d total_in_db=%d",
        len(pdfs) - skipped_files, skipped_files, total_chunks_added, store.count(),
    )
    console.print()
    console.print(f"[bold]Ingestion complete.[/bold]")
    console.print(f"  PDFs processed : {len(pdfs) - skipped_files}")
    console.print(f"  PDFs skipped   : {skipped_files} (unchanged)")
    console.print(f"  Chunks added   : {total_chunks_added}")
    console.print(f"  Collection size: {store.count()} total chunks")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest PDF documents into ChromaDB.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the existing collection and re-ingest all PDFs from scratch.",
    )
    args = parser.parse_args()
    ingest(reset=args.reset)
