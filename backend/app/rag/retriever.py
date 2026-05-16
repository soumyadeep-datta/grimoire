"""
ChromaDB vector store wrapper.

Stores embedded document chunks and retrieves the most
semantically similar ones using cosine similarity search.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.config import get_settings
from app.exceptions import CollectionNotFoundError, RetrievalError
from app.rag.embeddings import get_embeddings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "grimoire_docs"


@dataclass
class RetrievalResult:
    """A retrieved chunk with its cosine similarity score (0-1, higher = better)."""
    document: Document
    score: float

    @property
    def source(self) -> str:
        return self.document.metadata.get("source", "unknown")

    @property
    def content(self) -> str:
        return self.document.page_content


class VectorStore:

    def __init__(self) -> None:
        s = get_settings()
        self._persist_dir = str(s.chroma_persist_dir)
        self._top_k = s.retrieval_top_k
        self._chroma: Chroma | None = None

    def _get_store(self) -> Chroma:
        if self._chroma is None:
            self._chroma = Chroma(
                collection_name=COLLECTION_NAME,
                embedding_function=get_embeddings(),
                persist_directory=self._persist_dir,
                collection_metadata={"hnsw:space": "cosine"},
            )
        return self._chroma

    def add_documents(self, documents: list[Document]) -> int:
        if not documents:
            return 0
        try:
            self._get_store().add_documents(documents)
            logger.info("Stored %d chunks in ChromaDB", len(documents))
            return len(documents)
        except Exception as exc:
            raise RetrievalError(f"ChromaDB write failed: {exc}") from exc

    def similarity_search(
        self,
        query: str,
        k: int | None = None,
        filter: dict[str, Any] | None = None,
    ) -> list[RetrievalResult]:
        k = k or self._top_k
        store = self._get_store()

        # Fast count check — raises helpful 404 before expensive search
        try:
            if store._collection.count() == 0:
                raise CollectionNotFoundError()
        except CollectionNotFoundError:
            raise
        except Exception:
            pass

        try:
            results = store.similarity_search_with_relevance_scores(query, k=k, filter=filter)
        except Exception as exc:
            raise RetrievalError(f"ChromaDB search failed: {exc}") from exc

        return [RetrievalResult(document=doc, score=score) for doc, score in results]

    def mmr_search(self, query: str, k: int | None = None, lambda_mult: float = 0.5) -> list[Document]:
        """Maximal Marginal Relevance — balances relevance with diversity."""
        k = k or self._top_k
        try:
            return self._get_store().max_marginal_relevance_search(
                query, k=k, fetch_k=k * 4, lambda_mult=lambda_mult
            )
        except Exception as exc:
            raise RetrievalError(f"MMR search failed: {exc}") from exc

    def collection_stats(self) -> dict[str, Any]:
        store = self._get_store()
        try:
            count = store._collection.count()
            sample = store._collection.get(limit=500, include=["metadatas"])
            sources = {m.get("source", "unknown") for m in (sample.get("metadatas") or [])}
            return {"total_chunks": count, "unique_sources": sorted(sources)}
        except Exception as exc:
            logger.error("collection_stats failed: %s", exc)
            return {"total_chunks": 0, "unique_sources": []}

    def delete_collection(self) -> None:
        try:
            self._get_store()._client.delete_collection(COLLECTION_NAME)
            self._chroma = None
            logger.info("Collection deleted.")
        except Exception as exc:
            raise RetrievalError(f"Delete failed: {exc}") from exc


_vector_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
