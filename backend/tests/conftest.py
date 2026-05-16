"""
Shared fixtures. Mocks all external dependencies so tests need no API keys.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Set fake keys BEFORE app imports — Pydantic validates at import time
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("TAVILY_API_KEY", "test-key")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")


@pytest.fixture(scope="session")
def sample_text() -> str:
    return (
        "FastAPI is a modern, fast web framework for building APIs with Python. "
        "It uses Pydantic for data validation and Starlette under the hood. "
        "FastAPI generates OpenAPI documentation automatically. " * 10
    )


@pytest.fixture
def mock_embeddings():
    mock = MagicMock()
    mock.embed_documents.return_value = [[0.1] * 384] * 10
    mock.embed_query.return_value = [0.1] * 384
    return mock


@pytest.fixture
def mock_vector_store():
    from app.rag.retriever import RetrievalResult
    from langchain_core.documents import Document
    mock = MagicMock()
    mock.similarity_search.return_value = [
        RetrievalResult(
            document=Document(
                page_content="FastAPI supports async endpoints.",
                metadata={"source": "fastapi.md", "chunk_index": 0},
            ),
            score=0.92,
        )
    ]
    mock.add_documents.return_value = 5
    mock.collection_stats.return_value = {"total_chunks": 42, "unique_sources": ["fastapi.md"]}
    return mock


@pytest.fixture
def client(mock_vector_store):
    from app.main import create_app
    app = create_app()
    with patch("app.main.get_vector_store", return_value=mock_vector_store):
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c
