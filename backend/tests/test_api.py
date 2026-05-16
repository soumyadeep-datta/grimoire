"""Tests for FastAPI endpoints."""

from __future__ import annotations

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
    def test_direct_rag_returns_200(self, client, mock_vector_store):
        # ChatAnthropic is imported inside _direct_rag() so patch it there
        with patch("app.main.get_vector_store", return_value=mock_vector_store):
            with patch("app.main._direct_rag") as mock_rag:
                mock_rag.return_value = (
                    "FastAPI uses async def for async endpoints.",
                    ["fastapi.md (chunk 0)"],
                    {},
                )
                # _direct_rag is async — return a coroutine
                import asyncio
                async def fake_rag(*args, **kwargs):
                    return mock_rag.return_value
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
    def test_empty_history(self, client):
        r = client.get("/history?session_id=fresh-xyz")
        assert r.status_code == 200
        assert r.json()["messages"] == []

    def test_delete_204(self, client):
        assert client.delete("/history?session_id=any").status_code == 204

    def test_session_isolation(self, client):
        r_a = client.get("/history?session_id=session-a")
        r_b = client.get("/history?session_id=session-b")
        assert r_a.json()["session_id"] == "session-a"
        assert r_b.json()["session_id"] == "session-b"