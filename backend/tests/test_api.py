"""Tests for FastAPI endpoints."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest


class TestHealth:
    def test_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_includes_vector_store(self, client):
        assert "vector_store" in client.get("/health").json()

    def test_includes_environment(self, client):
        assert "environment" in client.get("/health").json()


class TestCollections:
    def test_returns_stats(self, client):
        r = client.get("/collections")
        assert r.status_code == 200
        assert "total_chunks" in r.json()
        assert "unique_sources" in r.json()


class TestIngest:
    def test_text_returns_201(self, client, mock_vector_store):
        with patch("app.main.get_vector_store", return_value=mock_vector_store):
            with patch("app.main.load_text") as ml:
                from langchain_core.documents import Document
                ml.return_value = [
                    Document(page_content="test", metadata={"source": "t"})
                ] * 5
                r = client.post(
                    "/ingest/text",
                    json={"content": "Test content here " * 10, "source_name": "test.txt"},
                )
        assert r.status_code == 201
        assert r.json()["chunks_added"] > 0

    def test_short_content_422(self, client):
        assert client.post("/ingest/text", json={"content": "short"}).status_code == 422

    def test_empty_content_422(self, client):
        assert client.post("/ingest/text", json={"content": ""}).status_code == 422


class TestQuery:
    def test_direct_rag_returns_200(self, client, mock_vector_store, mock_agent):
        with patch("app.main.get_vector_store", return_value=mock_vector_store):
            with patch("app.main._direct_rag") as mock_rag:
                async def fake_rag(*args, **kwargs):
                    return (
                        "FastAPI uses async def for async endpoints.",
                        ["fastapi.md (chunk 0)"],
                        {},
                    )
                mock_rag.side_effect = fake_rag

                r = client.post(
                    "/query",
                    json={"question": "How does FastAPI handle async?", "use_agent": False},
                )
        assert r.status_code == 200
        data = r.json()
        assert len(data["answer"]) > 0
        assert "latency_ms" in data

    def test_empty_question_422(self, client):
        assert client.post(
            "/query", json={"question": "", "use_agent": False}
        ).status_code == 422

    def test_question_too_long_422(self, client):
        assert client.post(
            "/query", json={"question": "a" * 2001, "use_agent": False}
        ).status_code == 422


class TestHistory:
    def test_empty_history(self, client, mock_agent):
        """History endpoint returns empty list for new session."""
        mock_agent.get_history.return_value = []
        r = client.get("/history?session_id=fresh-xyz")
        assert r.status_code == 200
        assert r.json()["messages"] == []

    def test_history_returns_messages(self, client, mock_agent):
        """History endpoint returns messages from the unified checkpoint store."""
        mock_agent.get_history.return_value = [
            {"role": "user", "content": "What is FastAPI?"},
            {"role": "assistant", "content": "FastAPI is a web framework."},
        ]
        r = client.get("/history?session_id=test-session")
        assert r.status_code == 200
        messages = r.json()["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"

    def test_delete_204(self, client, mock_agent):
        """DELETE /history clears the session via agent.clear_session."""
        r = client.delete("/history?session_id=any")
        assert r.status_code == 204
        mock_agent.clear_session.assert_called_once_with("any")

    def test_session_isolation(self, client, mock_agent):
        """Different session_ids return isolated histories."""
        mock_agent.get_history.return_value = []
        r_a = client.get("/history?session_id=session-a")
        r_b = client.get("/history?session_id=session-b")
        assert r_a.json()["session_id"] == "session-a"
        assert r_b.json()["session_id"] == "session-b"


class TestUnifiedMemory:
    """
    Tests for the unified memory architecture.

    Both agent mode and direct RAG mode use the LangGraph SQLite checkpoint
    store as the single source of truth for conversation history.
    """

    def test_direct_rag_reads_history_from_agent(self, client, mock_agent, mock_vector_store):
        """Direct RAG mode reads prior conversation history from the checkpoint store."""
        mock_agent.get_history_string.return_value = "User: What is ChromaDB?\nGrimoire: It is a vector DB."

        with patch("app.main.get_vector_store", return_value=mock_vector_store):
            with patch("app.main._direct_rag") as mock_rag:
                async def fake_rag(question, k, settings, chat_history=""):
                    # Verify history was passed from the checkpoint store
                    assert "ChromaDB" in chat_history
                    return ("Qdrant replaced it.", ["source.md"], {})
                mock_rag.side_effect = fake_rag

                r = client.post(
                    "/query",
                    json={
                        "question": "What replaced it?",
                        "session_id": "unified-test",
                        "use_agent": False,
                    },
                )

        assert r.status_code == 200
        mock_agent.get_history_string.assert_called_with("unified-test")

    def test_direct_rag_writes_to_checkpoint(self, client, mock_agent, mock_vector_store):
        """Direct RAG mode writes exchanges into the checkpoint store after answering."""
        with patch("app.main.get_vector_store", return_value=mock_vector_store):
            with patch("app.main._direct_rag") as mock_rag:
                async def fake_rag(*args, **kwargs):
                    return ("FastAPI uses Pydantic.", ["fastapi.md"], {})
                mock_rag.side_effect = fake_rag

                client.post(
                    "/query",
                    json={
                        "question": "How does FastAPI validate data?",
                        "session_id": "write-test",
                        "use_agent": False,
                    },
                )

        # add_to_checkpoint should have been called with the question and answer
        mock_agent.add_to_checkpoint.assert_called_once()
        call_args = mock_agent.add_to_checkpoint.call_args
        assert call_args[0][0] == "write-test"  # session_id
        assert "How does FastAPI" in call_args[0][1]  # question
        assert "FastAPI uses Pydantic" in call_args[0][2]  # answer