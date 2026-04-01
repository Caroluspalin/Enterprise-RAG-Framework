"""
evaluate.py

Runs a predefined set of test questions through the RAG chain and measures
retrieval and answer quality without requiring a second LLM call.

Two metrics per question:
  - Keyword hit rate  : fraction of expected_keywords found in the answer
  - Source hit        : was the expected source document among the retrieved chunks?

Results are printed as a table and written to logs/eval_<timestamp>.log.

Usage:
    python src/evaluate.py
    python src/evaluate.py --questions path/to/custom_questions.json
    python src/evaluate.py --top-k 8   # override TOP_K for this run only
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

# Allow imports from src/ when running as: python src/evaluate.py
sys.path.insert(0, str(Path(__file__).parent))

from chain import build_chain, format_sources, invoke_chain
from logger import get_logger
from retriever import get_retriever

load_dotenv()

DEFAULT_QUESTIONS_FILE = Path(__file__).parent.parent / "eval_questions.json"

console = Console()
log = get_logger("evaluate")


# ---------------------------------------------------------------------------
# Evaluation logic
# ---------------------------------------------------------------------------

def load_questions(path: Path) -> list[dict]:
    """Load test cases from a JSON file.

    Each entry must have: id, question, expected_keywords (list), expected_source (str).
    """
    with open(path, encoding="utf-8") as f:
        cases = json.load(f)

    required_keys = {"id", "question", "expected_keywords", "expected_source"}
    for case in cases:
        missing = required_keys - case.keys()
        if missing:
            raise ValueError(f"Test case {case.get('id', '?')} is missing fields: {missing}")

    return cases


def evaluate_answer(answer: str, expected_keywords: list[str]) -> tuple[int, int]:
    """Count how many expected keywords appear in the answer (case-insensitive).

    Returns (hits, total) so the caller can compute the hit rate.
    """
    answer_lower = answer.lower()
    hits = sum(1 for kw in expected_keywords if kw.lower() in answer_lower)
    return hits, len(expected_keywords)


def evaluate_retrieval(source_documents: list, expected_source: str) -> bool:
    """Return True if the expected source file appears in the retrieved chunks."""
    retrieved_files = {
        doc.metadata.get("source_file", "") for doc in source_documents
    }
    return expected_source in retrieved_files


def run_evaluation(questions_path: Path, top_k: int | None = None) -> None:
    cases = load_questions(questions_path)
    log.info("Evaluation started | questions=%d file=%s", len(cases), questions_path)

    # Build a fresh chain so evaluation is independent of any live chat session.
    retriever = get_retriever(k=top_k) if top_k else get_retriever()
    chain = build_chain()
    # Swap the retriever if a custom top_k was requested.
    if top_k:
        chain.retriever = retriever

    results = []

    console.print()
    console.print(f"[bold]Running {len(cases)} test questions...[/bold]")
    console.print()

    for case in cases:
        qid = case["id"]
        question = case["question"]
        expected_keywords = case["expected_keywords"]
        expected_source = case["expected_source"]

        t0 = time.perf_counter()
        result = invoke_chain(chain, question)
        elapsed = time.perf_counter() - t0

        answer = result.get("answer", "")
        source_docs = result.get("source_documents", [])

        kw_hits, kw_total = evaluate_answer(answer, expected_keywords)
        source_hit = evaluate_retrieval(source_docs, expected_source)
        kw_rate = kw_hits / kw_total if kw_total > 0 else 0.0

        results.append({
            "id": qid,
            "question": question,
            "answer": answer,
            "kw_hits": kw_hits,
            "kw_total": kw_total,
            "kw_rate": kw_rate,
            "source_hit": source_hit,
            "elapsed": elapsed,
        })

        log.info(
            "Eval %s | kw_rate=%.2f (%d/%d) source_hit=%s elapsed=%.2fs",
            qid, kw_rate, kw_hits, kw_total, source_hit, elapsed,
        )

    _print_results_table(results)
    _print_summary(results)
    _write_eval_log(results, questions_path)


def _print_results_table(results: list[dict]) -> None:
    table = Table(title="Evaluation Results", show_lines=True)
    table.add_column("ID", style="cyan", width=6)
    table.add_column("Question", max_width=40)
    table.add_column("Keywords", justify="center", width=12)
    table.add_column("Source", justify="center", width=8)
    table.add_column("Time", justify="right", width=7)

    for r in results:
        kw_label = f"{r['kw_hits']}/{r['kw_total']}"
        kw_color = "green" if r["kw_rate"] == 1.0 else ("yellow" if r["kw_rate"] > 0 else "red")
        source_label = "[green]PASS[/green]" if r["source_hit"] else "[red]FAIL[/red]"

        table.add_row(
            r["id"],
            r["question"][:80],
            f"[{kw_color}]{kw_label}[/{kw_color}]",
            source_label,
            f"{r['elapsed']:.1f}s",
        )

    console.print(table)


def _print_summary(results: list[dict]) -> None:
    n = len(results)
    avg_kw_rate = sum(r["kw_rate"] for r in results) / n
    source_pass = sum(1 for r in results if r["source_hit"])
    avg_elapsed = sum(r["elapsed"] for r in results) / n

    color = "green" if avg_kw_rate >= 0.8 else ("yellow" if avg_kw_rate >= 0.5 else "red")

    console.print()
    console.print(f"[bold]Summary[/bold]")
    console.print(f"  Questions evaluated : {n}")
    console.print(f"  Avg keyword hit rate: [{color}]{avg_kw_rate:.0%}[/{color}]")
    console.print(f"  Source retrieval    : {source_pass}/{n} correct")
    console.print(f"  Avg response time   : {avg_elapsed:.1f}s")
    console.print()

    log.info(
        "Eval summary | n=%d avg_kw_rate=%.2f source_pass=%d/%d avg_elapsed=%.2fs",
        n, avg_kw_rate, source_pass, n, avg_elapsed,
    )


def _write_eval_log(results: list[dict], questions_path: Path) -> None:
    """Write a full plain-text evaluation report to logs/ for later comparison.

    Timestamped filenames let you track how quality changes as you tune
    CHUNK_SIZE, CHUNK_OVERLAP, or TOP_K between runs.
    """
    from pathlib import Path as P
    import os

    log_dir = P(os.getenv("LOG_DIR", "./logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = log_dir / f"eval_{timestamp}.txt"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"Evaluation run: {timestamp}\n")
        f.write(f"Questions file: {questions_path}\n")
        f.write("=" * 60 + "\n\n")

        for r in results:
            f.write(f"[{r['id']}] {r['question']}\n")
            f.write(f"  Keywords : {r['kw_hits']}/{r['kw_total']} ({r['kw_rate']:.0%})\n")
            f.write(f"  Source   : {'PASS' if r['source_hit'] else 'FAIL'}\n")
            f.write(f"  Time     : {r['elapsed']:.2f}s\n")
            f.write(f"  Answer   :\n{r['answer']}\n\n")

    console.print(f"[dim]Full report saved to {report_path}[/dim]")
    log.info("Eval report written to %s", report_path)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate RAG chain quality.")
    parser.add_argument(
        "--questions",
        type=Path,
        default=DEFAULT_QUESTIONS_FILE,
        help="Path to a JSON file containing test cases.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Override TOP_K for this evaluation run.",
    )
    args = parser.parse_args()

    if not args.questions.exists():
        console.print(f"[red]Questions file not found: {args.questions}[/red]")
        sys.exit(1)

    run_evaluation(args.questions, top_k=args.top_k)
