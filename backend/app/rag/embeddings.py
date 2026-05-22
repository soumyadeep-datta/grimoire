"""
Embedding provider with automatic fallback.

Priority:
    1. Voyage-code-3.5  — if VOYAGE_API_KEY is set (production, MTEB ~67)
    2. all-MiniLM-L6-v2 — local fallback, no key needed (MTEB ~56, dim=384)

The provider is selected once at startup and cached for the process lifetime.
Switching providers requires wiping the Qdrant collection and re-ingesting,
since embedding dimensions differ (1024 vs 384).

Interface is identical regardless of provider:
    embed_documents(texts) -> List[List[float]]
    embed_query(text)      -> List[float]
    EMBEDDING_DIM          -> int
"""

from __future__ import annotations

import logging
import threading
from typing import Any, List

from app.config import get_settings

logger = logging.getLogger(__name__)

_client: Any = None
_lock = threading.Lock()
EMBEDDING_DIM: int = 1024  # updated at init time


def _init_voyage() -> tuple[Any, int]:
    """Initialize Voyage AI client."""
    import voyageai  # type: ignore[import]
    settings = get_settings()
    client = voyageai.Client(api_key=settings.voyage_api_key)  # type: ignore[attr-defined]
    logger.info("Embedder: Voyage-code-3.5 | dim=1024 | mode=production")
    return ("voyage", client), 1024


def _init_local() -> tuple[Any, int]:
    """Initialize local SentenceTransformer model."""
    import warnings
    warnings.filterwarnings("ignore", category=UserWarning)
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")
    dim = model.get_embedding_dimension()
    logger.info(
        "Embedder: all-MiniLM-L6-v2 | dim=%d | mode=local-fallback "
        "(set VOYAGE_API_KEY for production embeddings)",
        dim
    )
    return ("local", model), dim


def get_embedding_client() -> Any:
    """
    Return the singleton embedding client (thread-safe, lazy init).
    Selects Voyage if VOYAGE_API_KEY is set, otherwise local fallback.
    """
    global _client, EMBEDDING_DIM
    if _client is None:
        with _lock:
            if _client is None:
                settings = get_settings()
                if settings.voyage_api_key:
                    _client, EMBEDDING_DIM = _init_voyage()
                else:
                    _client, EMBEDDING_DIM = _init_local()
    return _client


def embed_documents(texts: List[str]) -> List[List[float]]:
    """Embed a list of document chunks for indexing."""
    if not texts:
        return []

    provider, client = get_embedding_client()
    settings = get_settings()

    if provider == "voyage":
        embeddings: List[List[float]] = []
        for i in range(0, len(texts), 128):
            batch = texts[i: i + 128]
            try:
                result = client.embed(batch, model=settings.embedding_model, input_type="document")
            except Exception as exc:
                err_str = str(exc)
                if "429" in err_str or "rate" in err_str.lower():
                    from app.exceptions import RateLimitError
                    raise RateLimitError(
                        "Voyage AI rate limit exceeded. Please wait and try again."
                    ) from exc
                from app.exceptions import UpstreamProviderError
                raise UpstreamProviderError(
                    f"Voyage AI embedding failed: {exc}"
                ) from exc
            embeddings.extend([list(map(float, e)) for e in result.embeddings])
        return embeddings
    else:
        # Local SentenceTransformer
        vecs = client.encode(texts, show_progress_bar=False, convert_to_numpy=True)
        return [v.tolist() for v in vecs]


def embed_query(text: str) -> List[float]:
    """Embed a single search query."""
    provider, client = get_embedding_client()
    settings = get_settings()

    if provider == "voyage":
        try:
            result = client.embed([text], model=settings.embedding_model, input_type="query")
        except Exception as exc:
            err_str = str(exc)
            if "429" in err_str or "rate" in err_str.lower():
                from app.exceptions import RateLimitError
                raise RateLimitError(
                    "Voyage AI rate limit exceeded. Please wait and try again."
                ) from exc
            from app.exceptions import UpstreamProviderError
            raise UpstreamProviderError(f"Voyage AI embedding failed: {exc}") from exc
        return list(map(float, result.embeddings[0]))
    else:
        vec = client.encode([text], show_progress_bar=False, convert_to_numpy=True)
        return vec[0].tolist()