"""
DeepEval evaluation pipeline for Grimoire RAG system.

Uses DeepEval 4.x with async_mode=False to score each question
synchronously — no executor, no timeouts, no async conflicts.

Metrics (per https://deepeval.com/docs/):
- Faithfulness:        Is the answer grounded in retrieved context?
- Contextual Recall:   Does retrieved context contain the ground truth?
- Answer Relevancy:    Does the answer address the question?
- Contextual Precision: Are relevant chunks ranked higher than irrelevant?

Answer generation: Claude Sonnet 4
RAGAS scoring:     GPT-4o-mini via DeepEval

Usage:
    python -m app.eval.evaluate --dataset eval_dataset.json --output eval_report.json
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import numpy as np
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
from pydantic import SecretStr

from deepeval import evaluate
from deepeval.test_case import LLMTestCase
from deepeval.metrics import (
    FaithfulnessMetric,
    ContextualRecallMetric,
    AnswerRelevancyMetric,
    ContextualPrecisionMetric,
)

from app.agent.prompts import RAG_CONTEXT_TEMPLATE
from app.config import get_settings
from app.rag.retriever import get_vector_store

logger = logging.getLogger(__name__)


def run_evaluation(
    dataset_path: str | Path = "eval_dataset.json",
    output_path: str | Path = "eval_report.json",
    k: int | None = None,
) -> dict[str, float]:
    settings = get_settings()
    k = k or settings.retrieval_top_k

    # DeepEval reads OPENAI_API_KEY from environment
    os.environ["OPENAI_API_KEY"] = settings.openai_api_key

    dataset_path = Path(dataset_path)
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    qa_pairs: list[dict] = json.loads(dataset_path.read_text())
    if not qa_pairs:
        raise ValueError("Dataset is empty.")

    logger.info("Evaluating %d questions (k=%d)…", len(qa_pairs), k)
    store = get_vector_store()

    # Claude for answer generation
    gen_llm = ChatAnthropic(
        model_name=settings.claude_model,
        api_key=SecretStr(settings.anthropic_api_key),
        max_tokens_to_sample=4096,
        temperature=0.0,
        timeout=60.0,
        stop=None,
    )

    # DeepEval metrics — async_mode=False = synchronous, no concurrent jobs
    # model="gpt-4o-mini" = cheap and fast, no rate limit issues
    eval_model = "gpt-4o-mini"
    faithfulness = FaithfulnessMetric(
        threshold=0.5, model=eval_model, include_reason=False, async_mode=False
    )
    contextual_recall = ContextualRecallMetric(
        threshold=0.5, model=eval_model, include_reason=False, async_mode=False
    )
    answer_relevancy = AnswerRelevancyMetric(
        threshold=0.5, model=eval_model, include_reason=False, async_mode=False
    )
    contextual_precision = ContextualPrecisionMetric(
        threshold=0.5, model=eval_model, include_reason=False, async_mode=False
    )

    metrics = [faithfulness, contextual_recall, answer_relevancy, contextual_precision]

    # Score per question
    faith_scores, recall_scores, relevancy_scores, precision_scores = [], [], [], []
    start = time.monotonic()

    for i, pair in enumerate(qa_pairs, start=1):
        question = pair["question"]
        ground_truth = pair["ground_truth"]

        # Retrieve
        try:
            results = store.similarity_search(question, k=k)
            contexts = [r.content for r in results]
        except Exception as exc:
            logger.warning("Retrieval failed q%d: %s", i, exc)
            contexts = []

        # Generate with Claude
        context_str = "\n\n---\n\n".join(contexts) if contexts else "No context."
        prompt = RAG_CONTEXT_TEMPLATE.format(
            context=context_str, source="", chunk_index="", question=question,
        )
        try:
            resp = gen_llm.invoke([HumanMessage(content=prompt)])
            answer = str(resp.content)
        except Exception as exc:
            logger.warning("Generation failed q%d: %s", i, exc)
            answer = ""

        # Build DeepEval test case
        # ContextualRecall needs expected_output = ground_truth
        test_case = LLMTestCase(
            input=question,
            actual_output=answer,
            expected_output=ground_truth,
            retrieval_context=contexts,
        )

        # Score each metric individually — synchronous, one at a time
        for metric, score_list, name in [
            (faithfulness, faith_scores, "faithfulness"),
            (contextual_recall, recall_scores, "contextual_recall"),
            (answer_relevancy, relevancy_scores, "answer_relevancy"),
            (contextual_precision, precision_scores, "contextual_precision"),
        ]:
            try:
                metric.measure(test_case)
                score = float(metric.score)
                score_list.append(score)
                logger.debug("  q%d %s=%.3f", i, name, score)
            except Exception as exc:
                logger.warning("  q%d %s failed: %s", i, name, exc)
                score_list.append(float("nan"))

        logger.info(
            "  q%d/%d | faith=%.2f recall=%.2f relevancy=%.2f precision=%.2f",
            i, len(qa_pairs),
            faith_scores[-1], recall_scores[-1],
            relevancy_scores[-1], precision_scores[-1],
        )

    elapsed = time.monotonic() - start

    def avg(lst: list) -> float:
        valid = [x for x in lst if not np.isnan(x)]
        return float(np.mean(valid)) if valid else 0.0

    scores = {
        "faithfulness": avg(faith_scores),
        "contextual_recall": avg(recall_scores),
        "answer_relevancy": avg(relevancy_scores),
        "contextual_precision": avg(precision_scores),
        "n_questions": len(qa_pairs),
        "retrieval_k": k,
        "generation_model": settings.claude_model,
        "evaluation_model": eval_model,
        "elapsed_seconds": round(elapsed, 1),
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(scores, indent=2))

    print("\n" + "=" * 50)
    print("  DeepEval RAG Evaluation Results")
    print("=" * 50)
    print(f"  Questions evaluated  : {scores['n_questions']}")
    print(f"  Generation model     : {scores['generation_model']}")
    print(f"  Evaluation model     : {scores['evaluation_model']}")
    print(f"  Time elapsed         : {scores['elapsed_seconds']}s")
    print("-" * 50)
    print(f"  Faithfulness         : {scores['faithfulness']:.4f}")
    print(f"  Contextual Recall    : {scores['contextual_recall']:.4f}")
    print(f"  Answer Relevancy     : {scores['answer_relevancy']:.4f}")
    print(f"  Contextual Precision : {scores['contextual_precision']:.4f}")
    print("=" * 50)
    print(f"\nSaved to: {output_path}\n")

    return scores


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="eval_dataset.json")
    parser.add_argument("--output", default="eval_report.json")
    parser.add_argument("--k", type=int, default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    run_evaluation(dataset_path=args.dataset, output_path=args.output, k=args.k)