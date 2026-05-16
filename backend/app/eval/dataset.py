"""
Evaluation dataset generator.

Generates question-answer pairs from ingested document chunks using Claude,
then serialises them to JSON for reproducible RAGAS evaluation runs.

Usage:
    python -m app.eval.dataset --output eval_dataset.json --n-questions 30
"""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from typing import Any

from langchain_anthropic import ChatAnthropic
from pydantic import SecretStr
from langchain_core.messages import HumanMessage

from app.agent.prompts import EVAL_GENERATION_PROMPT
from app.config import get_settings
from app.rag.retriever import get_vector_store

logger = logging.getLogger(__name__)


def generate_eval_dataset(
    n_questions: int = 30,
    output_path: str | Path = "eval_dataset.json",
    seed: int = 42,
) -> list[dict[str, str]]:
    """
    Sample chunks from ChromaDB and ask Claude to generate QA pairs.

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

    logger.info(
        "Generating %d QA pairs from %d available chunks.", n_questions, total_chunks
    )

    llm = ChatAnthropic(
        model_name=settings.claude_model,
        api_key=SecretStr(settings.anthropic_api_key),
        max_tokens_to_sample=2048,
        temperature=0.3,
        timeout=60.0,
        stop=None,
    )

    # Sample random chunks from the collection
    sample = store._chroma._collection.get(limit=total_chunks, include=["documents", "metadatas"])
    all_texts: list[str] = sample.get("documents") or []
    all_metas: list[dict] = sample.get("metadatas") or []

    if not all_texts:
        raise RuntimeError("ChromaDB returned no text content.")

    # Sample up to n_questions chunks (one QA pair per chunk, deduplicated)
    indices = random.sample(range(len(all_texts)), min(n_questions, len(all_texts)))
    sampled = [(all_texts[i], all_metas[i]) for i in indices]

    all_qa_pairs: list[dict[str, str]] = []

    for chunk_text, meta in sampled:
        source = meta.get("source", "unknown")
        prompt = EVAL_GENERATION_PROMPT.format(
            context=chunk_text,
            n_questions=1,
            source=source,
        )

        try:
            response = llm.invoke([HumanMessage(content=prompt)])
            raw = response.content.strip()

            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

            parsed: dict[str, Any] = json.loads(raw)
            qa_pairs: list[dict] = parsed.get("qa_pairs", [])
            all_qa_pairs.extend(qa_pairs)

        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Failed to parse QA pair from chunk (source=%s): %s", source, exc)
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

    parser = argparse.ArgumentParser(description="Generate RAGAS evaluation dataset")
    parser.add_argument("--output", default="eval_dataset.json")
    parser.add_argument("--n-questions", type=int, default=30)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    pairs = generate_eval_dataset(n_questions=args.n_questions, output_path=args.output)
    print(f"Generated {len(pairs)} QA pairs → {args.output}")