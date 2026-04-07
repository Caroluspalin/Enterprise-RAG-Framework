"""
chat.py

Interactive terminal interface for the B2B RAG chatbot.

Start the chat session:
    python src/chat.py

Available commands during chat:
    /exit   - quit the session
    /list   - show all ingested documents
    /reset  - clear conversation memory (keeps ChromaDB intact)
    /help   - show available commands
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule

# Allow imports from src/ when running as: python src/chat.py
sys.path.insert(0, str(Path(__file__).parent))

from chain import build_chain, format_sources, invoke_chain
from vectorstore import get_vector_store as get_vs

load_dotenv()

DOCS_PATH = Path(os.getenv("DOCS_PATH", "./docs"))

console = Console()


def get_document_count() -> int:
    """Return the total number of chunks stored in the vector store."""
    try:
        store = get_vs()
        return store.count()
    except Exception:
        return 0


def list_ingested_files() -> list[str]:
    """Return deduplicated list of source filenames stored in the vector store."""
    try:
        store = get_vs()
        metadatas = store.get_all_metadata()
        files = sorted({
            m["source_file"]
            for m in metadatas
            if "source_file" in m
        })
        return files
    except Exception:
        return []


def print_banner(chunk_count: int) -> None:
    """Print the startup banner with collection stats."""
    console.print()
    console.print(Panel.fit(
        f"[bold cyan]B2B RAG Chatbot[/bold cyan]\n"
        f"Collection: [yellow]{COLLECTION_NAME}[/yellow]  |  "
        f"Chunks in memory: [green]{chunk_count}[/green]\n"
        f"Type [bold]/help[/bold] for commands, [bold]/exit[/bold] to quit.",
        border_style="cyan",
    ))
    console.print()


def print_help() -> None:
    console.print(Panel(
        "[bold]/exit[/bold]   - quit the session\n"
        "[bold]/list[/bold]   - show all ingested documents\n"
        "[bold]/reset[/bold]  - clear conversation memory\n"
        "[bold]/help[/bold]   - show this message",
        title="Commands",
        border_style="dim",
    ))


def handle_list() -> None:
    files = list_ingested_files()
    if not files:
        console.print("[yellow]No documents found. Run python src/ingest.py first.[/yellow]")
        return
    console.print(f"\n[bold]Ingested documents ({len(files)}):[/bold]")
    for f in files:
        console.print(f"  [cyan]-[/cyan] {f}")
    console.print()


def ask(chain, question: str) -> None:
    """Send a question through the RAG chain and print the answer with sources."""
    with console.status("[dim]Thinking...[/dim]", spinner="dots"):
        result = invoke_chain(chain, question)

    answer = result.get("answer", "No answer returned.")
    sources = result.get("source_documents", [])

    console.print()
    console.print(Rule("[dim]Answer[/dim]", style="dim"))
    # Render the answer as Markdown so bullet points and bold text display nicely.
    console.print(Markdown(answer))

    console.print()
    console.print(Rule("[dim]Sources[/dim]", style="dim"))
    console.print(format_sources(sources))
    console.print()


def main() -> None:
    chunk_count = get_document_count()

    if chunk_count == 0:
        console.print(
            "[red]No documents found in ChromaDB.[/red] "
            "Run [bold]python src/ingest.py[/bold] first."
        )
        sys.exit(1)

    print_banner(chunk_count)

    chain = build_chain()

    while True:
        try:
            question = console.input("[bold cyan]You:[/bold cyan] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Exiting...[/dim]")
            break

        if not question:
            continue

        if question.lower() == "/exit":
            console.print("[dim]Goodbye.[/dim]")
            break

        if question.lower() == "/help":
            print_help()
            continue

        if question.lower() == "/list":
            handle_list()
            continue

        if question.lower() == "/reset":
            # Rebuild the chain to get a fresh ConversationBufferMemory.
            chain = build_chain()
            console.print("[green]Conversation memory cleared.[/green]\n")
            continue

        ask(chain, question)


if __name__ == "__main__":
    main()
