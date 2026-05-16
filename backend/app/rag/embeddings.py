"""
HuggingFace embedding model wrapper.

Loads all-MiniLM-L6-v2 once as a thread-safe singleton.
90MB weights are never re-loaded per request.
"""

from __future__ import annotations

import logging
import threading
from typing import ClassVar

from langchain_community.embeddings import HuggingFaceEmbeddings

from app.config import get_settings
from app.exceptions import EmbeddingError

logger = logging.getLogger(__name__)


class EmbeddingModel:
    """
    Thread-safe singleton around HuggingFaceEmbeddings.
    Loaded lazily on first access — import time stays fast.
    """

    _instance: ClassVar[HuggingFaceEmbeddings | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def get(cls) -> HuggingFaceEmbeddings:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:   # double-checked locking
                    cls._instance = cls._load()
        return cls._instance

    @classmethod
    def _load(cls) -> HuggingFaceEmbeddings:
        model_name = get_settings().embedding_model
        logger.info("Loading embedding model: %s (first load only)", model_name)
        try:
            embeddings = HuggingFaceEmbeddings(
                model_name=model_name,
                model_kwargs={"device": "cpu"},
                encode_kwargs={
                    "normalize_embeddings": True,  # unit vectors → fast cosine sim
                    "batch_size": 64,
                },
            )
            _ = embeddings.embed_query("warmup")  # surface load errors at startup
            logger.info("Embedding model ready: %s", model_name)
            return embeddings
        except Exception as exc:
            raise EmbeddingError(f"Failed to load '{model_name}': {exc}") from exc

    @classmethod
    def reset(cls) -> None:
        """Unload the model. Used in tests to force a fresh load."""
        with cls._lock:
            cls._instance = None


def get_embeddings() -> HuggingFaceEmbeddings:
    return EmbeddingModel.get()
