"""
pytest configuration and shared fixtures.

Uses dependency injection overrides and mocking to run the test suite
without real API keys, a real Voyage AI client, or a running Qdrant instance.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ── Env setup (before any app imports) ────────────────────────────────────────
# Force-set all required env vars so pydantic-settings never reads from .env
# during tests. os.environ[] takes precedence over .env file.
os.environ["ANTHROPIC_API_KEY"] = "test-anthropic-key"
os.environ["TAVILY_API_KEY"] = "test-tavily-key"
os.environ["VOYAGE_API_KEY"] = "test-voyage-key"
os.environ["ENVIRONMENT"] = "test"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

# Clear the settings cache immediately so the FIRST call to get_settings()
# anywhere in the test session uses the test env vars above.
from app.config import get_settings  # noqa: E402
get_settings.cache_clear()


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Clear settings cache before and after every test."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def sample_text() -> str:
    return (
        "FastAPI is a modern, fast (high-performance) web framework for building APIs "
        "with Python based on standard Python type hints. It is one of the fastest Python "
        "frameworks available. FastAPI uses Starlette under the hood and Pydantic for data "
        "validation. Features include automatic documentation with Swagger UI and ReDoc, "
        "dependency injection, and async support."
    )


@pytest.fixture(scope="session")
def sample_pdf_path(tmp_path_factory) -> Path:
    """Create a minimal text file to stand in for a real document."""
    tmp = tmp_path_factory.mktemp("docs")
    doc = tmp / "test_doc.txt"
    doc.write_text(
        "This is a test document about Python FastAPI.\n"
        "FastAPI supports async endpoints and automatic OpenAPI docs.\n"
        "It uses Pydantic for request and response validation.\n" * 20
    )
    return doc


@pytest.fixture
def mock_vector_store():
    """Return a mock VectorStore with the Qdrant-based RetrievalResult interface."""
    from app.rag.retriever import RetrievalResult

    mock = MagicMock()
    mock.similarity_search.return_value = [
        RetrievalResult(
            content="FastAPI supports async endpoints.",
            score=0.92,
            source="fastapi.md",
            chunk_index=0,
        )
    ]
    mock.add_documents.return_value = 5
    mock.collection_stats.return_value = {
        "total_chunks": 42,
        "unique_sources": ["fastapi.md"],
    }
    return mock


@pytest.fixture
def mock_agent():
    """
    Return a mock GrimoireAgent for tests that exercise memory/history endpoints.

    The unified memory architecture routes all history through the agent's
    checkpoint store, so tests must mock the agent rather than the old
    in-memory conversation store.
    """
    mock = MagicMock()
    mock.get_history.return_value = []
    mock.get_history_string.return_value = ""
    mock.add_to_checkpoint.return_value = None
    mock.clear_session.return_value = None
    return mock


@pytest.fixture
def client(mock_vector_store, mock_agent):
    """FastAPI TestClient with all external dependencies mocked."""
    from app.main import create_app
    from app.rag.retriever import get_vector_store

    app = create_app()
    app.dependency_overrides[get_vector_store] = lambda: mock_vector_store

    with patch("app.main.get_vector_store", return_value=mock_vector_store):
        with patch("app.main.get_agent", return_value=mock_agent):
            with TestClient(app, raise_server_exceptions=True) as c:
                yield c
