"""
evaluate.py

RAG evaluation pipeline using the Ragas framework.

Runs a golden dataset of question-answer pairs through the live RAG pipeline
(retriever + chain) and measures two critical metrics:

  - Faithfulness:      Does the answer stay grounded in the retrieved context?
                       (Lower = hallucination risk)
  - Answer Relevancy:  Does the answer actually address the question asked?

Usage:
    python scripts/evaluate.py

Requirements:
    pip install ragas

The script needs a working ChromaDB collection (run ingest.py first) and a
valid OPENAI_API_KEY in .env (Ragas uses an LLM judge under the hood).
"""

import json
import os
import sys
import time

# Allow imports from src/ when running from the project root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv

load_dotenv()

from chain import build_chain, invoke_chain, format_sources
from retriever import get_retriever

# ---------------------------------------------------------------------------
# Golden dataset
#
# Each entry has:
#   question        - the user query
#   ground_truth    - an ideal reference answer (used by some Ragas metrics)
#   expected_source - filename we expect the retriever to surface (optional)
#
# Adapt these to match the documents you have ingested into ChromaDB.
# ---------------------------------------------------------------------------

GOLDEN_DATASET = [
    {
        "question": "What is the purpose of this company's product?",
        "ground_truth": (
            "The product is a RAG-based chatbot that ingests PDF documents "
            "and answers questions about them using retrieval-augmented generation."
        ),
    },
    {
        "question": "How does the system prevent hallucinations?",
        "ground_truth": (
            "The system prompt instructs the LLM to answer ONLY from the "
            "provided context and to explicitly say it does not know if the "
            "context is insufficient."
        ),
    },
    {
        "question": "What embedding model is used for document indexing?",
        "ground_truth": (
            "The system uses OpenAI's text-embedding-3-small model to generate "
            "vector embeddings for document chunks."
        ),
    },
    {
        "question": "How are duplicate documents handled during ingestion?",
        "ground_truth": (
            "A SHA-256 content hash is computed for each PDF file. Files whose "
            "hash already exists in the vector store are skipped to avoid "
            "re-embedding unchanged documents."
        ),
    },
    {
        "question": "What vector database does the system use?",
        "ground_truth": (
            "The system uses ChromaDB as its vector database, persisted locally "
            "to the chroma_db/ directory."
        ),
    },
]


def _collect_rag_results(dataset: list[dict]) -> list[dict]:
    """Run each golden question through the live RAG pipeline.

    Returns a list of dicts with keys needed by Ragas:
      - question, answer, contexts, ground_truth
    """
    chain = build_chain()
    retriever = get_retriever()
    results = []

    for i, entry in enumerate(dataset, 1):
        question = entry["question"]
        print(f"  [{i}/{len(dataset)}] {question}")

        t0 = time.perf_counter()

        # Retrieve context chunks independently so we can pass raw text to Ragas.
        retrieved_docs = retriever.invoke(question)
        contexts = [doc.page_content for doc in retrieved_docs]

        # Run the full chain for the generated answer.
        chain_result = invoke_chain(chain, question)
        answer = chain_result.get("answer", "")

        elapsed = time.perf_counter() - t0

        results.append({
            "question": question,
            "answer": answer,
            "contexts": contexts,
            "ground_truth": entry.get("ground_truth", ""),
            "elapsed_s": round(elapsed, 2),
        })

    return results


def _evaluate_with_ragas(results: list[dict]) -> None:
    """Score the collected results using Ragas metrics and print a report."""
    try:
        from ragas import evaluate
        from ragas.metrics import faithfulness, answer_relevancy
        from datasets import Dataset
    except ImportError:
        print(
            "\nERROR: ragas is not installed. Install it with:\n"
            "  pip install ragas\n"
        )
        sys.exit(1)

    # Build a HuggingFace Dataset in the format Ragas expects.
    eval_data = {
        "question": [r["question"] for r in results],
        "answer": [r["answer"] for r in results],
        "contexts": [r["contexts"] for r in results],
        "ground_truth": [r["ground_truth"] for r in results],
    }
    dataset = Dataset.from_dict(eval_data)

    print("\nScoring with Ragas (this calls the LLM judge)...\n")
    score = evaluate(dataset, metrics=[faithfulness, answer_relevancy])
    df = score.to_pandas()

    # Per-question results
    print("=" * 72)
    print("PER-QUESTION RESULTS")
    print("=" * 72)
    for i, row in df.iterrows():
        entry = results[i]
        print(f"\nQ{i+1}: {entry['question']}")
        print(f"  Answer (truncated): {entry['answer'][:120]}...")
        print(f"  Contexts retrieved: {len(entry['contexts'])}")
        print(f"  Faithfulness:       {row.get('faithfulness', 'N/A'):.3f}")
        print(f"  Answer Relevancy:   {row.get('answer_relevancy', 'N/A'):.3f}")
        print(f"  Response time:      {entry['elapsed_s']}s")

    # Aggregate summary
    print("\n" + "=" * 72)
    print("AGGREGATE SCORES")
    print("=" * 72)
    for metric in ["faithfulness", "answer_relevancy"]:
        if metric in df.columns:
            mean_val = df[metric].mean()
            min_val = df[metric].min()
            print(f"  {metric:20s}  mean={mean_val:.3f}  min={min_val:.3f}")

    print(f"\n  Total questions evaluated: {len(results)}")
    total_time = sum(r["elapsed_s"] for r in results)
    print(f"  Total pipeline time:      {total_time:.1f}s")
    print()

    # Save raw results to JSON for CI artifact / historical comparison.
    output_path = os.path.join(os.path.dirname(__file__), "..", "eval_results.json")
    export = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "aggregate": {m: float(df[m].mean()) for m in ["faithfulness", "answer_relevancy"] if m in df.columns},
        "per_question": results,
    }
    with open(output_path, "w") as f:
        json.dump(export, f, indent=2, ensure_ascii=False)
    print(f"  Raw results saved to: {output_path}")


def main():
    print("=" * 72)
    print("RAG Evaluation Pipeline (Ragas)")
    print("=" * 72)
    print(f"\nGolden dataset: {len(GOLDEN_DATASET)} questions")
    print("Metrics: faithfulness, answer_relevancy\n")

    print("Running questions through the RAG pipeline...\n")
    results = _collect_rag_results(GOLDEN_DATASET)

    _evaluate_with_ragas(results)


if __name__ == "__main__":
    main()
