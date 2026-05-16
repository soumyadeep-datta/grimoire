"""
RAGAS evaluation pipeline.

Metrics: context_precision, context_recall, faithfulness, answer_relevancy.

Usage: python -m app.eval.evaluate --dataset eval_dataset.json --output eval_report.json
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

from app.config import get_settings
from app.rag.retriever import get_vector_store

logger = logging.getLogger(__name__)
METRICS = [context_precision, context_recall, faithfulness, answer_relevancy]


def run_evaluation(
    dataset_path: str | Path = "eval_dataset.json",
    output_path: str | Path = "eval_report.json",
    k: int | None = None,
) -> dict:
    s = get_settings()
    k = k or s.retrieval_top_k
    qa_pairs = json.loads(Path(dataset_path).read_text())

    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage
    from app.agent.prompts import RAG_CONTEXT_TEMPLATE

    store = get_vector_store()
    llm = ChatAnthropic(model=s.claude_model, api_key=s.anthropic_api_key, max_tokens=1024, temperature=0.0)
    questions, answers, contexts, ground_truths = [], [], [], []

    for i, pair in enumerate(qa_pairs, 1):
        q, gt = pair["question"], pair["ground_truth"]
        try:
            ctx = [r.content for r in store.similarity_search(q, k=k)]
        except Exception:
            ctx = []

        try:
            ans = llm.invoke([HumanMessage(content=RAG_CONTEXT_TEMPLATE.format(
                context="\n\n---\n\n".join(ctx) or "No context.",
                source="", chunk_index="", question=q,
            ))]).content
        except Exception:
            ans = ""

        questions.append(q); answers.append(ans)
        contexts.append(ctx); ground_truths.append(gt)
        if i % 5 == 0:
            logger.info("Evaluated %d/%d", i, len(qa_pairs))

    result = evaluate(
        Dataset.from_dict({"question": questions, "answer": answers, "contexts": contexts, "ground_truth": ground_truths}),
        metrics=METRICS,
    )

    scores = {
        "context_precision": float(result["context_precision"]),
        "context_recall": float(result["context_recall"]),
        "faithfulness": float(result["faithfulness"]),
        "answer_relevancy": float(result["answer_relevancy"]),
        "n_questions": len(qa_pairs), "retrieval_k": k,
        "model": s.claude_model, "embedding_model": s.embedding_model,
    }
    Path(output_path).write_text(json.dumps(scores, indent=2))

    print("\n" + "=" * 50)
    print("  RAGAS Evaluation Results")
    print("=" * 50)
    for metric in ["context_precision", "context_recall", "faithfulness", "answer_relevancy"]:
        print(f"  {metric:<25}: {scores[metric]:.4f}")
    print("=" * 50)
    return scores


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", default="eval_dataset.json")
    p.add_argument("--output", default="eval_report.json")
    p.add_argument("--k", type=int, default=None)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO)
    run_evaluation(dataset_path=args.dataset, output_path=args.output, k=args.k)
