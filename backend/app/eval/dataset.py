"""
Evaluation dataset generator.

Generates question-answer pairs from ingested document chunks using Claude,
then serialises them to JSON for reproducible DeepEval evaluation runs.

Usage:
    python -m app.eval.dataset --output eval_dataset.json --n-questions 20
"""

from __future__ import annotations

import json
import logging
import math
import random
import time
from pathlib import Path
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
from pydantic import SecretStr

from app.agent.prompts import EVAL_GENERATION_PROMPT
from app.config import get_settings
from app.rag.retriever import get_vector_store

logger = logging.getLogger(__name__)


def generate_eval_dataset(
    n_questions: int = 20,
    output_path: str | Path = "eval_dataset.json",
    seed: int = 42,
) -> list[dict[str, str]]:
    """
    Sample chunks from Qdrant and ask Claude to generate QA pairs.

    Args:
        n_questions: Total number of question-answer pairs to generate.
        output_path: Where to write the JSON dataset.
        seed: Random seed for reproducibility.

    Returns:
        List of {"question": ..., "ground_truth": ..., "source": ...} dicts.
    """
    random.seed(seed)
    settings = get_settings()

    store = get_vector_store()
    stats = store.collection_stats()
    total_chunks = stats["total_chunks"]

    if total_chunks == 0:
        raise RuntimeError(
            "No documents ingested. Run POST /ingest before generating the eval dataset."
        )

    logger.info("Generating %d QA pairs from %d available chunks.", n_questions, total_chunks)

    llm = ChatAnthropic(
        model=settings.claude_model,
        api_key=SecretStr(settings.anthropic_api_key),
        max_tokens=2048,
        temperature=0.3,
        timeout=60.0,
    )

    all_points, _ = store._client.scroll(
        collection_name=store._collection,
        limit=10000,
        with_payload=True,
        with_vectors=False,
    )

    all_chunks = [
        {
            "text": (p.payload or {}).get("content", ""),
            "source": (p.payload or {}).get("source", "unknown"),
        }
        for p in all_points
        if (p.payload or {}).get("content", "").strip()
    ]

    if not all_chunks:
        raise RuntimeError("Qdrant returned no text content.")

    indices = random.sample(range(len(all_chunks)), min(n_questions, len(all_chunks)))
    sampled = [all_chunks[i] for i in indices]

    all_qa_pairs: list[dict[str, str]] = []
    
    # Calculate how many questions to ask per chunk to hit the target
    questions_per_chunk = math.ceil(n_questions / len(sampled))

    for i, chunk in enumerate(sampled):
        chunk_text = chunk["text"]
        source = chunk["source"]

        # Pace requests to avoid Anthropic rate limits
        if i > 0:
            time.sleep(5)

        prompt = EVAL_GENERATION_PROMPT.format(
            context=chunk_text,
            n_questions=questions_per_chunk,
            source=source,
        )

        try:
            response = llm.invoke([HumanMessage(content=prompt)])
            raw = str(response.content).strip()

            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

            parsed: dict[str, Any] = json.loads(raw)
            qa_pairs: list[dict] = parsed.get("qa_pairs", [])
            all_qa_pairs.extend(qa_pairs)

        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Failed to parse QA pair (source=%s): %s", source, exc)
            continue

        if len(all_qa_pairs) >= n_questions:
            break

    all_qa_pairs = all_qa_pairs[:n_questions]

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(all_qa_pairs, indent=2))
    logger.info("Wrote %d QA pairs to %s", len(all_qa_pairs), output)

    return all_qa_pairs


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate DeepEval evaluation dataset")
    parser.add_argument("--output", default="eval_dataset.json")
    parser.add_argument("--n-questions", type=int, default=20)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    pairs = generate_eval_dataset(n_questions=args.n_questions, output_path=args.output)
    print(f"Generated {len(pairs)} QA pairs → {args.output}")