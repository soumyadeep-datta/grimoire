"""
Qdrant vector store wrapper.

Replaces ChromaDB with Qdrant for production-grade vector storage.
Uses local persistent mode (QdrantClient(path=...)) — no Docker required
for development; upgrade to QdrantClient(url="http://localhost:6333") for
Docker/production deployment.

Source: https://github.com/qdrant/qdrant-client
        https://python-client.qdrant.tech/quickstart
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from typing import List

from langchain_core.documents import Document
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

from app.config import get_settings
from app.exceptions import CollectionNotFoundError
from app.rag.embeddings import embed_documents, embed_query, EMBEDDING_DIM

logger = logging.getLogger(__name__)

COLLECTION_NAME = "grimoire_docs"

_store: "VectorStore | None" = None
_lock = threading.Lock()


@dataclass
class RetrievalResult:
    """A single retrieved chunk with its source metadata and similarity score."""
    content: str
    score: float
    source: str
    chunk_index: int

    @property
    def document(self) -> Document:
        return Document(
            page_content=self.content,
            metadata={"source": self.source, "chunk_index": self.chunk_index},
        )


class VectorStore:
    """
    Qdrant-backed vector store using Voyage-code-3 embeddings.

    Local persistent mode: data survives process restarts, stored in qdrant_data/.
    Collection is created on first use with cosine similarity (appropriate for
    normalized Voyage embeddings — dot product equals cosine when vectors are
    unit-length, per Voyage docs).
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._client = QdrantClient(path=str(settings.qdrant_path))
        self._collection = COLLECTION_NAME
        self._ensure_collection()
        logger.info(
            "Qdrant VectorStore initialised | path=%s | collection=%s | dim=%d",
            settings.qdrant_path, COLLECTION_NAME, EMBEDDING_DIM,
        )

    def _ensure_collection(self) -> None:
        """Create the collection if it doesn't exist yet."""
        if not self._client.collection_exists(self._collection):
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIM,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("Created Qdrant collection '%s'", self._collection)

    def add_documents(self, documents: List[Document]) -> int:
        """
        Embed and upsert documents into Qdrant.

        Returns the number of chunks added.
        """
        if not documents:
            return 0

        texts = [doc.page_content for doc in documents]
        embeddings = embed_documents(texts)

        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={
                    "content": doc.page_content,
                    "source": doc.metadata.get("source", "unknown"),
                    "chunk_index": doc.metadata.get("chunk_index", 0),
                    "total_chunks": doc.metadata.get("total_chunks", 1),
                },
            )
            for doc, embedding in zip(documents, embeddings)
        ]

        self._client.upsert(collection_name=self._collection, points=points)
        logger.info("Upserted %d chunks into Qdrant", len(points))
        return len(points)

    def similarity_search(
        self, query: str, k: int = 5
    ) -> List[RetrievalResult]:
        """
        Semantic similarity search using Voyage query embeddings.

        Raises CollectionNotFoundError if the collection is empty.
        """
        count = self._client.count(collection_name=self._collection).count
        if count == 0:
            raise CollectionNotFoundError()

        query_vector = embed_query(query)

        results = self._client.query_points(
            collection_name=self._collection,
            query=query_vector,
            limit=k,
            with_payload=True,
        ).points

        return [
            RetrievalResult(
                content=(r.payload or {}).get("content", ""),
                score=r.score,
                source=(r.payload or {}).get("source", "unknown"),
                chunk_index=(r.payload or {}).get("chunk_index", 0),
            )
            for r in results
        ]

    def collection_stats(self) -> dict:
        """Return stats about the current collection."""
        try:
            count = self._client.count(collection_name=self._collection).count
            # Scroll to get unique sources
            all_points, _ = self._client.scroll(
                collection_name=self._collection,
                limit=10000,
                with_payload=["source"],
            )
            sources = list({(p.payload or {}).get("source", "unknown") for p in all_points})
            return {"total_chunks": count, "unique_sources": sources}
        except Exception as exc:
            logger.error("collection_stats failed: %s", exc)
            return {"total_chunks": 0, "unique_sources": []}

    def delete_collection(self) -> None:
        """Wipe the entire collection."""
        self._client.delete_collection(self._collection)
        self._ensure_collection()
        logger.info("Collection '%s' wiped and recreated", self._collection)


def get_vector_store() -> VectorStore:
    """Return the singleton VectorStore (thread-safe, lazy init)."""
    global _store
    if _store is None:
        with _lock:
            if _store is None:
                _store = VectorStore()
    return _store