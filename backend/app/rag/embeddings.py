"""
Voyage AI embedding provider.

Uses voyage-code-3, the domain-specific embedding model for code and
technical documentation. Optimized for retrieval tasks — significantly
outperforms general-purpose models like all-MiniLM-L6-v2 on code corpora.

MTEB score: ~67+ vs ~56 for all-MiniLM-L6-v2
Dimension: 1024 (default), normalized to unit length
Input types: "document" for indexing, "query" for search queries

Source: https://docs.voyageai.com/docs/embeddings
"""

from __future__ import annotations

import logging
import threading
from typing import Any, List

import voyageai  # type: ignore[import]

from app.config import get_settings

logger = logging.getLogger(__name__)

_client: Any = None  # voyageai.Client — typed as Any to avoid stub issues
_lock = threading.Lock()

# voyage-code-3 default dimension
EMBEDDING_DIM = 1024


def get_embedding_client() -> Any:
    """Return the singleton Voyage AI client (thread-safe, lazy init)."""
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                settings = get_settings()
                _client = voyageai.Client(api_key=settings.voyage_api_key)  # type: ignore[attr-defined]
                logger.info(
                    "Voyage AI client initialised | model=%s | dim=%d",
                    settings.embedding_model, EMBEDDING_DIM,
                )
    return _client


def embed_documents(texts: List[str]) -> List[List[float]]:
    """
    Embed a list of document chunks for indexing.

    Uses input_type="document" per Voyage docs — automatically prepends
    the document retrieval prompt for optimal retrieval performance.
    Batches in groups of 128 to respect the 120K token-per-request limit.
    """
    if not texts:
        return []

    settings = get_settings()
    client = get_embedding_client()
    model = settings.embedding_model

    embeddings: List[List[float]] = []
    batch_size = 128

    for i in range(0, len(texts), batch_size):
        batch = texts[i: i + batch_size]
        result = client.embed(batch, model=model, input_type="document")
        # output_dtype defaults to "float" — cast to silence Pylance union warning
        batch_embeddings: List[List[float]] = [list(map(float, e)) for e in result.embeddings]
        embeddings.extend(batch_embeddings)
        logger.debug("Embedded batch %d-%d / %d", i, i + len(batch), len(texts))

    return embeddings


def embed_query(text: str) -> List[float]:
    """
    Embed a single search query.

    Uses input_type="query" per Voyage docs — prepends the query retrieval
    prompt which is distinct from the document prompt for better retrieval.
    """
    settings = get_settings()
    client = get_embedding_client()
    result = client.embed([text], model=settings.embedding_model, input_type="query")
    # output_dtype defaults to "float" — cast to silence Pylance union warning
    return list(map(float, result.embeddings[0]))