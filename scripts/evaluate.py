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
        "question": "Mikä on TechCorp Solutions Oy:n kriittisen vian (Taso 1) vasteaika ja korjaustavoite?",
        "ground_truth": (
            "Taso 1 (Kriittinen vika) tarkoittaa, että koko tuotantojärjestelmä on alhaalla. "
            "Vasteaika on 15 minuuttia ja korjaustavoite on 2 tuntia."
        ),
    },
    {
        "question": "Kuinka suuri laitebudjetti TechCorpin kokoaikaisella työntekijällä on ja mihin sen voi käyttää?",
        "ground_truth": (
            "Jokaisella kokoaikaisella työntekijällä on oikeus 1500 euron laitebudjettiin "
            "kahden vuoden välein. Budjetin voi käyttää kannettavaan tietokoneeseen, "
            "näyttöihin tai ergonomiseen työtuoliin."
        ),
    },
    {
        "question": "Mikä on B2B-asiakkaiden palautusoikeus virheelliselle palvelinlaitteistolle?",
        "ground_truth": (
            "Jos toimitettu palvelinlaitteisto on virheellinen, asiakkaalla on "
            "14 vuorokauden palautusoikeus laitteen vastaanottamisesta. Palautettavan "
            "laitteen tulee olla alkuperäisessä pakkauksessa. Aiheettomista palautuksista "
            "peritään 15 % käsittelykulun laitteen ostohinnasta."
        ),
    },
    {
        "question": "Missä TechCorp Solutions Oy:n pääkonttori sijaitsee ja kuka on toimitusjohtaja?",
        "ground_truth": (
            "TechCorpin pääkonttori sijaitsee osoitteessa Tekniikantie 1, 02150 Espoo. "
            "Toimitusjohtaja on Matti 'Masa' Meikäläinen."
        ),
    },
    {
        "question": "Millainen on TechCorpin hybridityömalli ja kuinka monta päivää viikossa toimistolla on oltava?",
        "ground_truth": (
            "TechCorp noudattaa joustavaa hybridityömallia: toimistolla on oltava "
            "vähintään kaksi päivää viikossa, loput kolme päivää voi työskennellä etänä."
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
        from ragas.llms import LangchainLLMWrapper
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from datasets import Dataset
    except ImportError:
        print(
            "\nERROR: ragas is not installed. Install it with:\n"
            "  pip install ragas\n"
        )
        sys.exit(1)

    from langchain_openai import ChatOpenAI, OpenAIEmbeddings

    # Explicitly configure the LLM judge and embedding model for Ragas.
    # Without an explicit embedding model, Answer Relevancy silently
    # returns NaN because it needs embeddings to compute cosine similarity
    # between the original question and questions generated from the answer.
    ragas_llm = LangchainLLMWrapper(ChatOpenAI(model="gpt-4o", temperature=0))
    ragas_embeddings = LangchainEmbeddingsWrapper(
        OpenAIEmbeddings(model="text-embedding-3-small")
    )

    # Build a HuggingFace Dataset in the format Ragas expects.
    eval_data = {
        "question": [r["question"] for r in results],
        "answer": [r["answer"] for r in results],
        "contexts": [r["contexts"] for r in results],
        "ground_truth": [r["ground_truth"] for r in results],
    }
    dataset = Dataset.from_dict(eval_data)

    print("\nScoring with Ragas (this calls the LLM judge)...\n")
    score = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy],
        llm=ragas_llm,
        embeddings=ragas_embeddings,
    )
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
