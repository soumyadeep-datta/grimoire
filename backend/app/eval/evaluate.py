"""
RAGAS evaluation pipeline.

Measures 4 core retrieval + generation quality metrics:
- context_precision:  Are retrieved chunks relevant to the question?
- context_recall:     Does the retrieved context contain the ground truth answer?
- faithfulness:       Is the generated answer grounded in the retrieved context?
- answer_relevancy:   Does the answer actually address the question?

Usage:
    python -m app.eval.evaluate --dataset eval_dataset.json --output eval_report.json

Scores are written to JSON and printed to stdout for README inclusion.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from datasets import Dataset
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
from pydantic import SecretStr
from ragas import evaluate
from ragas.metrics import (
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)

from app.agent.prompts import RAG_CONTEXT_TEMPLATE
from app.config import get_settings
from app.rag.retriever import get_vector_store

logger = logging.getLogger(__name__)

METRICS = [context_precision, context_recall, faithfulness, answer_relevancy]


def run_evaluation(
    dataset_path: str | Path = "eval_dataset.json",
    output_path: str | Path = "eval_report.json",
    k: int | None = None,
) -> dict[str, float]:
    """
    Run RAGAS evaluation over the QA dataset.

    For each question:
    1. Retrieve top-k chunks from ChromaDB
    2. Generate an answer using direct RAG (no agent overhead)
    3. Collect (question, answer, contexts, ground_truth) into a HuggingFace Dataset
    4. Pass to RAGAS evaluate()
    """
    settings = get_settings()
    k = k or settings.retrieval_top_k

    dataset_path = Path(dataset_path)
    if not dataset_path.exists():
        raise FileNotFoundError(
            f"Eval dataset not found: {dataset_path}. "
            "Run `python -m app.eval.dataset` first."
        )

    qa_pairs: list[dict] = json.loads(dataset_path.read_text())
    if not qa_pairs:
        raise ValueError("Eval dataset is empty.")

    logger.info("Running RAGAS eval on %d questions (k=%d)…", len(qa_pairs), k)

    store = get_vector_store()

    llm = ChatAnthropic(
        model_name=settings.claude_model,
        api_key=SecretStr(settings.anthropic_api_key),
        max_tokens_to_sample=1024,
        temperature=0.0,
        timeout=60.0,
        stop=None,
    )

    questions: list[str] = []
    answers: list[str] = []
    contexts: list[list[str]] = []
    ground_truths: list[str] = []

    start = time.monotonic()

    for i, pair in enumerate(qa_pairs, start=1):
        question = pair["question"]
        ground_truth = pair["ground_truth"]

        try:
            results = store.similarity_search(question, k=k)
            context_texts = [r.content for r in results]
        except Exception as exc:
            logger.warning("Retrieval failed for question %d: %s", i, exc)
            context_texts = []

        context_str = "\n\n---\n\n".join(context_texts) if context_texts else "No context found."
        prompt = RAG_CONTEXT_TEMPLATE.format(
            context=context_str,
            source="",
            chunk_index="",
            question=question,
        )
        try:
            response = llm.invoke([HumanMessage(content=prompt)])
            answer = response.content
        except Exception as exc:
            logger.warning("Generation failed for question %d: %s", i, exc)
            answer = ""

        questions.append(question)
        answers.append(answer)
        contexts.append(context_texts)
        ground_truths.append(ground_truth)

        if i % 5 == 0:
            logger.info("  Evaluated %d/%d questions…", i, len(qa_pairs))

    elapsed = time.monotonic() - start
    logger.info("Data collection complete in %.1fs. Running RAGAS metrics…", elapsed)

    hf_dataset = Dataset.from_dict(
        {
            "question": questions,
            "answer": answers,
            "contexts": contexts,
            "ground_truth": ground_truths,
        }
    )

    result = evaluate(hf_dataset, metrics=METRICS)
    scores: dict[str, float] = {
        "context_precision": float(result["context_precision"]),
        "context_recall": float(result["context_recall"]),
        "faithfulness": float(result["faithfulness"]),
        "answer_relevancy": float(result["answer_relevancy"]),
        "n_questions": len(qa_pairs),
        "retrieval_k": k,
        "model": settings.claude_model,
        "embedding_model": settings.embedding_model,
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(scores, indent=2))

    print("\n" + "=" * 50)
    print("  RAGAS Evaluation Results")
    print("=" * 50)
    print(f"  Questions evaluated : {scores['n_questions']}")
    print(f"  Retrieval k         : {scores['retrieval_k']}")
    print(f"  LLM                 : {scores['model']}")
    print(f"  Embeddings          : {scores['embedding_model']}")
    print("-" * 50)
    print(f"  Context Precision   : {scores['context_precision']:.4f}")
    print(f"  Context Recall      : {scores['context_recall']:.4f}")
    print(f"  Faithfulness        : {scores['faithfulness']:.4f}")
    print(f"  Answer Relevancy    : {scores['answer_relevancy']:.4f}")
    print("=" * 50)
    print(f"\nFull report saved to: {output_path}\n")

    return scores


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run RAGAS evaluation")
    parser.add_argument("--dataset", default="eval_dataset.json")
    parser.add_argument("--output", default="eval_report.json")
    parser.add_argument("--k", type=int, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    run_evaluation(dataset_path=args.dataset, output_path=args.output, k=args.k)