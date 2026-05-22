"""Tests for the RAG ingestion and retrieval pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from app.exceptions import CollectionNotFoundError, IngestionError, UnsupportedFileTypeError
from app.rag.ingestion import _build_splitter, load_text


class TestLoadText:
    def test_returns_chunks(self, sample_text):
        chunks = load_text(sample_text, source_name="test.txt")
        assert len(chunks) >= 1
        assert all(isinstance(c, Document) for c in chunks)

    def test_metadata_enriched(self, sample_text):
        chunks = load_text(sample_text, source_name="my_doc.txt")
        for chunk in chunks:
            assert chunk.metadata["source"] == "my_doc.txt"
            assert "chunk_index" in chunk.metadata
            assert "total_chunks" in chunk.metadata

    def test_empty_text_raises(self):
        with pytest.raises(IngestionError, match="empty"):
            load_text("   ")

    def test_long_text_multiple_chunks(self):
        chunks = load_text("This is a sentence about software. " * 200)
        assert len(chunks) > 1

    def test_chunk_index_sequential(self, sample_text):
        chunks = load_text("word " * 500, source_name="test.txt")
        indices = [c.metadata["chunk_index"] for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_source_name_propagated(self):
        chunks = load_text("Some content about APIs and REST. " * 20, source_name="api_docs.md")
        assert all(c.metadata["source"] == "api_docs.md" for c in chunks)


class TestUnsupportedFileType:
    def test_unknown_extension_raises(self):
        from app.rag.ingestion import load_document
        with pytest.raises(UnsupportedFileTypeError):
            load_document("/fake/file.xyz")

    def test_error_message_includes_extension(self):
        from app.rag.ingestion import load_document
        try:
            load_document("/fake/file.xyz")
        except UnsupportedFileTypeError as e:
            assert ".xyz" in e.message


class TestBuildSplitter:
    def test_python_uses_code_separators(self):
        splitter = _build_splitter(".py")
        assert "\nclass " in splitter._separators or "\ndef " in splitter._separators

    def test_markdown_splitter_returned(self):
        assert _build_splitter(".md") is not None

    def test_chunk_size_respected(self):
        splitter = _build_splitter(".txt")
        from app.config import get_settings
        assert splitter._chunk_size == get_settings().chunk_size

    def test_overlap_respected(self):
        splitter = _build_splitter(".txt")
        from app.config import get_settings
        assert splitter._chunk_overlap == get_settings().chunk_overlap


class TestVectorStore:
    def test_add_and_retrieve(self, mock_vector_store):
        docs = [Document(
            page_content="FastAPI is great.",
            metadata={"source": "t.txt", "chunk_index": 0}
        )]
        assert mock_vector_store.add_documents(docs) == 5
        results = mock_vector_store.similarity_search("FastAPI")
        assert results[0].score > 0.5

    def test_collection_stats_shape(self, mock_vector_store):
        stats = mock_vector_store.collection_stats()
        assert "total_chunks" in stats
        assert isinstance(stats["unique_sources"], list)

    def test_empty_documents_returns_zero(self, mock_vector_store):
        mock_vector_store.add_documents.return_value = 0
        result = mock_vector_store.add_documents([])
        assert result == 0

    def test_retrieval_result_properties(self, mock_vector_store):
        results = mock_vector_store.similarity_search("test")
        assert results[0].source == "fastapi.md"
        assert len(results[0].content) > 0

    def test_real_store_empty_collection_raises(self, tmp_path):
        """Test the real VectorStore raises CollectionNotFoundError on empty collection."""
        from app.rag.retriever import VectorStore
        with patch("app.rag.retriever.get_settings") as mock_settings, \
             patch("app.rag.retriever.get_embedding_client"), \
             patch("app.rag.retriever.EMBEDDING_DIM", 1024):
            mock_settings.return_value.qdrant_path = tmp_path / "qdrant"
            mock_settings.return_value.embedding_model = "voyage-code-3.5"
            mock_settings.return_value.cohere_api_key = None
            mock_settings.return_value.voyage_api_key = "test"
            mock_settings.return_value.embedding_provider = "voyage"
            store = VectorStore()
            mock_count = MagicMock()
            mock_count.count = 0
            store._client.count = MagicMock(return_value=mock_count)
            store._all_chunks = []
            with pytest.raises(CollectionNotFoundError):
                store.similarity_search("anything")

    def test_real_store_add_empty_returns_zero(self, tmp_path):
        from app.rag.retriever import VectorStore
        with patch("app.rag.retriever.get_settings") as mock_settings, \
             patch("app.rag.retriever.get_embedding_client"), \
             patch("app.rag.retriever.EMBEDDING_DIM", 1024):
            mock_settings.return_value.qdrant_path = tmp_path / "qdrant"
            mock_settings.return_value.embedding_model = "voyage-code-3.5"
            mock_settings.return_value.cohere_api_key = None
            mock_settings.return_value.voyage_api_key = "test"
            mock_settings.return_value.embedding_provider = "voyage"
            store = VectorStore()
            result = store.add_documents([])
            assert result == 0

    def test_collection_stats_on_error(self, tmp_path):
        from app.rag.retriever import VectorStore
        with patch("app.rag.retriever.get_settings") as mock_settings, \
             patch("app.rag.retriever.get_embedding_client"), \
             patch("app.rag.retriever.EMBEDDING_DIM", 1024):
            mock_settings.return_value.qdrant_path = tmp_path / "qdrant"
            mock_settings.return_value.embedding_model = "voyage-code-3.5"
            mock_settings.return_value.cohere_api_key = None
            mock_settings.return_value.voyage_api_key = "test"
            mock_settings.return_value.embedding_provider = "voyage"
            store = VectorStore()
            store._client.count = MagicMock(side_effect=Exception("db error"))
            stats = store.collection_stats()
            assert stats["total_chunks"] == 0
            assert stats["unique_sources"] == []