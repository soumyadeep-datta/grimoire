"""
Qdrant vector store with hybrid retrieval pipeline.

Architecture:
    1. Dense search  — Qdrant + Voyage-code-3.5 embeddings (semantic)
    2. Sparse search — BM25S (lexical, exact token matching)
    3. RRF fusion    — Reciprocal Rank Fusion (k=60) merges both ranked lists
    4. Reranking     — Cohere Rerank v4 cross-encoder (precision boost)

This pipeline eliminates the failure modes of pure dense search:
- Exact function names, error codes, API identifiers → BM25S catches these
- Semantic similarity → Voyage-code-3.5 catches these
- Combined via RRF → neither approach's misses survive to the final result
- Cohere Rerank → cross-encoder precision over the fused candidate set

Sources:
    https://python-client.qdrant.tech/quickstart
    https://docs.cohere.com/reference/rerank
    https://github.com/xhluca/bm25s
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from typing import List, Optional

import bm25s
import cohere
from langchain_core.documents import Document
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
)

from app.config import get_settings
from app.exceptions import CollectionNotFoundError
from app.rag.embeddings import embed_documents, embed_query, EMBEDDING_DIM

logger = logging.getLogger(__name__)

COLLECTION_NAME = "grimoire_docs"
RERANK_MODEL = "rerank-v4.0-fast"   # fast for dev; switch to rerank-v4.0-pro for prod
RRF_K = 60                           # standard RRF constant; higher = less aggressive fusion
CANDIDATE_MULTIPLIER = 4             # retrieve k * CANDIDATE_MULTIPLIER before reranking

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
    """
    Reciprocal Rank Fusion — merges multiple ranked lists into a single ranking.

    For each document at rank r in a list, its RRF score contribution is 1/(k+r).
    Documents appearing in multiple lists accumulate scores.
    Returns (doc_index, rrf_score) pairs sorted by score descending.

    Reference: Cormack, Clarke, and Buettcher (2009) — standard k=60.
    """
    scores: dict[int, float] = {}
    for ranked_list in ranked_lists:
        for rank, doc_idx in enumerate(ranked_list, start=1):
            scores[doc_idx] = scores.get(doc_idx, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


class VectorStore:
    """
    Qdrant-backed vector store with hybrid BM25S + dense retrieval and Cohere reranking.

    Retrieval pipeline:
        dense_search(q, n=k*4) + bm25_search(q, n=k*4)
            → RRF fusion
            → Cohere Rerank v4 (top k)

    BM25S index is rebuilt in-memory on each query from the full Qdrant payload.
    For small-to-medium corpora (<100K chunks) this is fast enough; for larger
    corpora, persist the BM25S index to disk between queries.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._client = QdrantClient(path=str(settings.qdrant_path))
        self._cohere = cohere.ClientV2(api_key=settings.cohere_api_key)
        self._collection = COLLECTION_NAME
        self._ensure_collection()
        logger.info(
            "Qdrant VectorStore initialised | path=%s | collection=%s | dim=%d",
            settings.qdrant_path, COLLECTION_NAME, EMBEDDING_DIM,
        )

    def _ensure_collection(self) -> None:
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

    def _fetch_all_chunks(self) -> list[dict]:
        """Fetch all chunks from Qdrant for BM25S indexing."""
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
        """
        Dense vector search via Qdrant + Voyage-code-3.5.
        Returns Qdrant point IDs (str) for the top-n results.
        """
        query_vector = embed_query(query)
        results = self._client.query_points(
            collection_name=self._collection,
            query=query_vector,
            limit=n,
            with_payload=["content", "source", "chunk_index"],
        ).points
        return [str(r.id) for r in results]

    def _bm25_search(
        self, query: str, all_chunks: list[dict], n: int
    ) -> list[int]:
        """
        Sparse BM25S lexical search — exact token matching.
        Critical for code: function names, error codes, API identifiers.
        Returns indices into all_chunks.
        """
        corpus = [chunk["content"].lower().split() for chunk in all_chunks]
        retriever = bm25s.BM25()
        retriever.index(corpus)

        query_tokens = bm25s.tokenize(query.lower(), show_progress=False)
        results, _ = retriever.retrieve(query_tokens, k=min(n, len(all_chunks)))
        # results shape: (1, k) — indices into corpus
        return list(results[0])

    def similarity_search(
        self, query: str, k: int = 5
    ) -> List[RetrievalResult]:
        """
        Hybrid retrieval: BM25S + dense → RRF → Cohere Rerank v4.

        Raises CollectionNotFoundError if the collection is empty.
        """
        count = self._client.count(collection_name=self._collection).count
        if count == 0:
            raise CollectionNotFoundError()

        # Fetch all chunks for BM25S (in-memory index)
        all_chunks = self._fetch_all_chunks()
        n_candidates = min(k * CANDIDATE_MULTIPLIER, len(all_chunks))

        # --- Stage 1: Dense search (Qdrant IDs as str) ---
        dense_ids = self._dense_search(query, n_candidates)

        # Map Qdrant IDs → chunk indices
        id_to_idx = {chunk["qdrant_id"]: i for i, chunk in enumerate(all_chunks)}
        dense_ranked = [id_to_idx[did] for did in dense_ids if did in id_to_idx]

        # --- Stage 2: BM25S sparse search ---
        bm25_ranked = self._bm25_search(query, all_chunks, n_candidates)

        # --- Stage 3: Reciprocal Rank Fusion ---
        fused = _reciprocal_rank_fusion([dense_ranked, bm25_ranked], k=RRF_K)
        candidate_indices = [idx for idx, _ in fused[:n_candidates]]

        # --- Stage 4: Cohere Rerank v4 ---
        candidate_chunks = [all_chunks[i] for i in candidate_indices]
        candidate_texts = [c["content"] for c in candidate_chunks]

        try:
            rerank_response = self._cohere.rerank(
                model=RERANK_MODEL,
                query=query,
                documents=candidate_texts,
                top_n=k,
            )
            final_indices = [r.index for r in rerank_response.results]
            final_scores = [r.relevance_score for r in rerank_response.results]
        except Exception as exc:
            logger.warning("Cohere rerank failed, falling back to RRF order: %s", exc)
            final_indices = list(range(min(k, len(candidate_chunks))))
            final_scores = [1.0 - i * 0.1 for i in final_indices]

        logger.info(
            "Hybrid retrieval | query='%s' | dense=%d bm25=%d fused=%d reranked=%d",
            query[:60], len(dense_ranked), len(bm25_ranked),
            len(candidate_indices), len(final_indices),
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
        logger.info("Collection '%s' wiped and recreated", self._collection)


def get_vector_store() -> VectorStore:
    """Return the singleton VectorStore (thread-safe, lazy init)."""
    global _store
    if _store is None:
        with _lock:
            if _store is None:
                _store = VectorStore()
    return _store
