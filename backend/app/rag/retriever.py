"""
Qdrant vector store with hybrid retrieval pipeline.

Architecture:
    1. Dense search  — Qdrant + embeddings (Voyage-code-3.5 or local fallback)
    2. Sparse search — BM25S lexical search (exact token matching)
    3. RRF fusion    — Reciprocal Rank Fusion (k=60) merges both ranked lists
    4. Reranking     — Cohere Rerank v4 (if COHERE_API_KEY set, else skip)

BM25S index is built once at startup and refreshed on document changes.

Embedding dimension is determined at runtime based on active provider:
    Voyage-code-3.5 → 1024 dimensions
    all-MiniLM-L6-v2 → 384 dimensions

A metadata file (qdrant_data/.embedder) tracks the active provider.
If provider changes, the collection must be wiped and re-ingested.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import bm25s
from langchain_core.documents import Document
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
)

from app.config import get_settings
from app.exceptions import CollectionNotFoundError
from app.rag.embeddings import embed_documents, embed_query, get_embedding_client, EMBEDDING_DIM

logger = logging.getLogger(__name__)

RERANK_MODEL = "rerank-v4.0-fast"
RRF_K = 60
CANDIDATE_MULTIPLIER = 4

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


def _reciprocal_rank_fusion(
    ranked_lists: list[list[int]], k: int = RRF_K
) -> list[tuple[int, float]]:
    """Merge multiple ranked lists via Reciprocal Rank Fusion."""
    scores: dict[int, float] = {}
    for ranked_list in ranked_lists:
        for rank, doc_idx in enumerate(ranked_list, start=1):
            scores[doc_idx] = scores.get(doc_idx, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


class VectorStore:
    """
    Qdrant-backed vector store with hybrid BM25S + dense retrieval.
    Cohere reranking is applied if COHERE_API_KEY is set, otherwise
    results are returned in RRF order.
    """

    def __init__(self) -> None:
        settings = get_settings()

        # Force embedding client init so EMBEDDING_DIM is set
        get_embedding_client()
        from app.rag.embeddings import EMBEDDING_DIM as dim
        self._embedding_dim = dim

        self._client = QdrantClient(path=str(settings.qdrant_path))
        self._collection = settings.qdrant_collection_name

        # Optional Cohere reranker
        self._cohere = None
        if settings.cohere_api_key:
            import cohere
            self._cohere = cohere.ClientV2(api_key=settings.cohere_api_key)

        self._check_embedder_mismatch(settings)
        self._ensure_collection()

        # In-memory BM25S cache
        self._all_chunks: list[dict] = []
        self._bm25_retriever: bm25s.BM25 | None = None
        self._refresh_bm25_index()

        logger.info(
            "VectorStore initialised | dim=%d | reranking=%s",
            self._embedding_dim,
            "cohere" if self._cohere else "rrf-only",
        )

    def _check_embedder_mismatch(self, settings) -> None:
        """Warn if the embedding provider changed since last ingest."""
        meta_path = Path(settings.qdrant_path) / ".embedder"
        current = settings.embedding_provider
        if meta_path.exists():
            stored = meta_path.read_text().strip()
            if stored != current:
                logger.warning(
                    "Embedding provider changed: %s → %s. "
                    "Wipe the collection (DELETE /collections) and re-ingest.",
                    stored, current
                )
        meta_path.write_text(current)

    def _ensure_collection(self) -> None:
        if not self._client.collection_exists(self._collection):
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(
                    size=self._embedding_dim,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("Created Qdrant collection '%s' | dim=%d",
                        self._collection, self._embedding_dim)

    def _refresh_bm25_index(self) -> None:
        """Build BM25S index from all chunks. Called at init and after doc changes."""
        count = self._client.count(collection_name=self._collection).count
        if count == 0:
            self._all_chunks = []
            self._bm25_retriever = None
            return

        logger.info("Refreshing BM25S index | %d chunks...", count)
        self._all_chunks = self._fetch_all_chunks()
        corpus = [chunk["content"].lower().split() for chunk in self._all_chunks]
        retriever = bm25s.BM25()
        retriever.index(corpus)
        self._bm25_retriever = retriever
        logger.info("BM25S index built | %d chunks", len(self._all_chunks))

    def add_documents(self, documents: List[Document]) -> int:
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
        self._refresh_bm25_index()
        return len(points)

    def _fetch_all_chunks(self) -> list[dict]:
        all_points, _ = self._client.scroll(
            collection_name=self._collection,
            limit=10000,
            with_payload=True,
            with_vectors=False,
        )
        return [
            {
                "content": (p.payload or {}).get("content", ""),
                "source": (p.payload or {}).get("source", "unknown"),
                "chunk_index": (p.payload or {}).get("chunk_index", 0),
                "qdrant_id": str(p.id),
            }
            for p in all_points
        ]

    def _dense_search(self, query: str, n: int) -> list[str]:
        query_vector = embed_query(query)
        results = self._client.query_points(
            collection_name=self._collection,
            query=query_vector,
            limit=n,
            with_payload=["content", "source", "chunk_index"],
        ).points
        return [str(r.id) for r in results]

    def _bm25_search(self, query: str, n: int) -> list[int]:
        if self._bm25_retriever is None or not self._all_chunks:
            return []
        query_tokens = bm25s.tokenize(query.lower(), show_progress=False)
        results, _ = self._bm25_retriever.retrieve(
            query_tokens, k=min(n, len(self._all_chunks))
        )
        return list(results[0])

    def similarity_search(self, query: str, k: int = 5) -> List[RetrievalResult]:
        """
        Hybrid retrieval: BM25S + dense → RRF → Cohere Rerank (if available).
        Falls back to RRF order if Cohere key not set.
        """
        if not self._all_chunks:
            raise CollectionNotFoundError()

        n_candidates = min(k * CANDIDATE_MULTIPLIER, len(self._all_chunks))

        try:
            # Stage 1: Dense
            dense_ids = self._dense_search(query, n_candidates)
        except ValueError as exc:
            if "not aligned" in str(exc) or "shapes" in str(exc):
                from app.exceptions import CollectionMismatchError
                raise CollectionMismatchError() from exc
            raise
        id_to_idx = {chunk["qdrant_id"]: i for i, chunk in enumerate(self._all_chunks)}
        dense_ranked = [id_to_idx[did] for did in dense_ids if did in id_to_idx]

        # Stage 2: BM25S
        bm25_ranked = self._bm25_search(query, n_candidates)

        # Stage 3: RRF
        fused = _reciprocal_rank_fusion([dense_ranked, bm25_ranked], k=RRF_K)
        candidate_indices = [idx for idx, _ in fused[:n_candidates]]
        candidate_chunks = [self._all_chunks[i] for i in candidate_indices]

        # Stage 4: Rerank (optional)
        if self._cohere:
            try:
                candidate_texts = [c["content"] for c in candidate_chunks]
                rerank_response = self._cohere.rerank(
                    model=RERANK_MODEL,
                    query=query,
                    documents=candidate_texts,
                    top_n=k,
                )
                final_indices = [r.index for r in rerank_response.results]
                final_scores = [r.relevance_score for r in rerank_response.results]
            except Exception as exc:
                err_str = str(exc)
                if "429" in err_str or "rate" in err_str.lower():
                    from app.exceptions import RateLimitError
                    raise RateLimitError(
                        "Cohere API rate limit exceeded. Please wait and try again."
                    ) from exc
                # Other Cohere errors — fall back gracefully to RRF order
                logger.warning("Cohere rerank failed, falling back to RRF order: %s", exc)
                final_indices = list(range(min(k, len(candidate_chunks))))
                final_scores = [1.0 - i * 0.1 for i in final_indices]
        else:
            # No reranker — use RRF scores directly
            final_indices = list(range(min(k, len(candidate_chunks))))
            final_scores = [score for _, score in fused[:k]]

        logger.info(
            "Hybrid retrieval | query='%s' | dense=%d bm25=%d fused=%d final=%d | reranker=%s",
            query[:60], len(dense_ranked), len(bm25_ranked),
            len(candidate_indices), len(final_indices),
            "cohere" if self._cohere else "rrf",
        )

        return [
            RetrievalResult(
                content=candidate_chunks[i]["content"],
                score=score,
                source=candidate_chunks[i]["source"],
                chunk_index=candidate_chunks[i]["chunk_index"],
            )
            for i, score in zip(final_indices, final_scores)
        ]

    def collection_stats(self) -> dict:
        try:
            count = self._client.count(collection_name=self._collection).count
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
        self._client.delete_collection(self._collection)
        self._ensure_collection()
        self._refresh_bm25_index()
        logger.info("Collection '%s' wiped and recreated", self._collection)

    def delete_by_source(self, source: str) -> int:
        """Delete all chunks belonging to a specific source document."""
        from qdrant_client import models
        # Count first so we can return how many were deleted
        try:
            scroll_result = self._client.scroll(
                collection_name=self._collection,
                scroll_filter=models.Filter(
                    must=[models.FieldCondition(
                        key="source", match=models.MatchValue(value=source)
                    )]
                ),
                limit=10000,
                with_payload=False,
                with_vectors=False,
            )
            point_ids = [p.id for p in scroll_result[0]]
            count = len(point_ids)

            if count > 0:
                self._client.delete(
                    collection_name=self._collection,
                    points_selector=models.PointIdsList(points=point_ids),
                )
                self._refresh_bm25_index()

            logger.info("Deleted %d chunks for source '%s'", count, source)
            return count
        except Exception as exc:
            logger.error("Failed to delete source '%s': %s", source, exc)
            raise


def get_vector_store() -> VectorStore:
    """Return the singleton VectorStore (thread-safe, lazy init)."""
    global _store
    if _store is None:
        with _lock:
            if _store is None:
                _store = VectorStore()
    return _store