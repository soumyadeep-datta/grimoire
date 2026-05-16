"""
Evaluation dataset generator.
Samples chunks from ChromaDB, asks Claude to generate QA pairs.
Run AFTER ingesting documents.

Usage: python -m app.eval.dataset --output eval_dataset.json --n-questions 30
"""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from app.agent.prompts import EVAL_GENERATION_PROMPT
from app.config import get_settings
from app.rag.retriever import get_vector_store

logger = logging.getLogger(__name__)


def generate_eval_dataset(
    n_questions: int = 30,
    output_path: str | Path = "eval_dataset.json",
    seed: int = 42,
) -> list[dict]:
    random.seed(seed)
    s = get_settings()
    store = get_vector_store()
    stats = store.collection_stats()

    if stats["total_chunks"] == 0:
        raise RuntimeError("No documents ingested. Run POST /ingest first.")

    llm = ChatAnthropic(model=s.claude_model, api_key=s.anthropic_api_key, max_tokens=2048, temperature=0.3)
    sample = store._chroma._collection.get(limit=stats["total_chunks"], include=["documents", "metadatas"])
    texts = sample.get("documents") or []
    metas = sample.get("metadatas") or []

    indices = random.sample(range(len(texts)), min(n_questions, len(texts)))
    all_pairs: list[dict] = []

    for i in indices:
        source = metas[i].get("source", "unknown")
        try:
            raw = llm.invoke([HumanMessage(content=EVAL_GENERATION_PROMPT.format(
                context=texts[i], n_questions=1, source=source
            ))]).content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1].lstrip("json")
            all_pairs.extend(json.loads(raw).get("qa_pairs", []))
        except Exception as exc:
            logger.warning("Failed QA pair from %s: %s", source, exc)
        if len(all_pairs) >= n_questions:
            break

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(all_pairs[:n_questions], indent=2))
    logger.info("Wrote %d QA pairs to %s", len(all_pairs), output)
    return all_pairs


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="eval_dataset.json")
    p.add_argument("--n-questions", type=int, default=30)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO)
    generate_eval_dataset(n_questions=args.n_questions, output_path=args.output)
