"""
Embedding provider with startup-locked configuration.

Mode is determined ONCE at startup based on VOYAGE_API_KEY availability.
No runtime switching — eliminates dimension mismatch and silent degradation risks.

Production mode (VOYAGE_API_KEY set):
    Voyage-code-3.5 (1024-dim) | reranking enabled | full pipeline
Demo mode (no VOYAGE_API_KEY):
    all-MiniLM-L6-v2 (384-dim) | no reranking | quick start

Rate limit handling (production mode):
    Voyage calls wrapped with exponential backoff — 1s/2s/4s/8s retries.
    On exhausted retries, raises RateLimitError (429) — no silent fallback.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, List

from app.config import get_settings

logger = logging.getLogger(__name__)

_client: Any = None
_lock = threading.Lock()
EMBEDDING_DIM: int = 1024  # set at init time

# Retry config — mirrors Anthropic SDK defaults
_MAX_RETRIES = 4
_BASE_DELAY = 1.0  # seconds


def _with_backoff(fn, *args, **kwargs) -> Any:
    """
    Call fn with exponential backoff on rate limit errors.
    Retries up to _MAX_RETRIES times with 1s, 2s, 4s, 8s delays.
    On exhausted retries, raises RateLimitError — never silently falls back.
    """
    delay = _BASE_DELAY
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            err_str = str(exc)
            is_rate_limit = (
                "429" in err_str
                or "rate" in err_str.lower()
                or "RPM" in err_str
                or "TPM" in err_str
            )
            if is_rate_limit and attempt < _MAX_RETRIES:
                logger.warning(
                    "Voyage rate limit hit (attempt %d/%d) — retrying in %.0fs",
                    attempt + 1, _MAX_RETRIES, delay
                )
                time.sleep(delay)
                delay *= 2
                continue
            if is_rate_limit:
                from app.exceptions import RateLimitError
                raise RateLimitError(
                    "Voyage AI rate limit exceeded after retries. "
                    "Please wait a moment and try again."
                ) from exc
            from app.exceptions import UpstreamProviderError
            raise UpstreamProviderError(f"Voyage AI embedding failed: {exc}") from exc


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
    dim = model.get_embedding_dimension() or 384
    logger.info(
        "Embedder: all-MiniLM-L6-v2 | dim=%d | mode=demo "
        "(set VOYAGE_API_KEY for production embeddings)",
        dim
    )
    return ("local", model), dim


def get_embedding_client() -> Any:
    """
    Return the singleton embedding client (thread-safe, lazy init).
    Mode is locked at first init — never changes during runtime.
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
            result = _with_backoff(
                client.embed, batch,
                model=settings.embedding_model,
                input_type="document"
            )
            embeddings.extend([list(map(float, e)) for e in result.embeddings])
        return embeddings
    else:
        vecs = client.encode(texts, show_progress_bar=False, convert_to_numpy=True)
        return [v.tolist() for v in vecs]


def embed_query(text: str) -> List[float]:
    """Embed a single search query."""
    provider, client = get_embedding_client()
    settings = get_settings()

    if provider == "voyage":
        result = _with_backoff(
            client.embed, [text],
            model=settings.embedding_model,
            input_type="query"
        )
        return list(map(float, result.embeddings[0]))
    else:
        vec = client.encode([text], show_progress_bar=False, convert_to_numpy=True)
        return vec[0].tolist()