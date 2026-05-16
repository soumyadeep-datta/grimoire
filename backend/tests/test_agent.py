"""Tests for agent tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from app.exceptions import CollectionNotFoundError, ToolExecutionError


class TestRagRetrieval:
    def test_formats_results(self, mock_vector_store):
        from app.agent.tools import rag_retrieval
        with patch("app.agent.tools.get_vector_store", return_value=mock_vector_store):
            result = rag_retrieval.invoke({"query": "FastAPI async", "k": 3})
        assert "Source:" in result and "Similarity:" in result

    def test_empty_collection_helpful_message(self):
        from app.agent.tools import rag_retrieval
        mock = MagicMock()
        mock.similarity_search.side_effect = CollectionNotFoundError()
        with patch("app.agent.tools.get_vector_store", return_value=mock):
            assert "No documents" in rag_retrieval.invoke({"query": "test", "k": 3})

    def test_k_clamped(self, mock_vector_store):
        from app.agent.tools import rag_retrieval
        with patch("app.agent.tools.get_vector_store", return_value=mock_vector_store):
            result = rag_retrieval.invoke({"query": "test", "k": 999})
        assert isinstance(result, str)


class TestWebSearch:
    def test_formats_results(self):
        from app.agent.tools import web_search
        mock_client = MagicMock()
        mock_client.search.return_value = {
            "answer": "FastAPI is fast.",
            "results": [{"title": "Docs", "url": "https://fastapi.tiangolo.com", "content": "FastAPI is fast."}],
        }
        with patch("app.agent.tools.TavilyClient", return_value=mock_client):
            assert "fastapi.tiangolo.com" in web_search.invoke({"query": "FastAPI", "max_results": 1})

    def test_api_failure_raises_tool_error(self):
        from app.agent.tools import web_search
        mock_client = MagicMock()
        mock_client.search.side_effect = Exception("rate limit")
        with patch("app.agent.tools.TavilyClient", return_value=mock_client):
            with pytest.raises(ToolExecutionError):
                web_search.invoke({"query": "test", "max_results": 1})


class TestDatabaseQuery:
    def test_blocks_writes(self):
        from app.agent.tools import database_query
        assert "Only SELECT" in database_query.invoke(
            {"natural_language_query": "delete all", "sql_query": "DELETE FROM x"}
        )

    def test_nonexistent_db_returns_message(self):
        from app.agent.tools import database_query
        from pathlib import Path
        mock_settings = MagicMock()
        mock_settings.sqlite_db_path = Path("/nonexistent/db.sqlite")
        with patch("app.agent.tools.get_settings", return_value=mock_settings):
            result = database_query.invoke(
                {"natural_language_query": "list tables",
                 "sql_query": "SELECT name FROM sqlite_master"}
            )
        assert "not found" in result.lower() or "No structured" in result


class TestCodeExecutor:
    def test_basic_math(self):
        from app.agent.tools import code_executor
        # Use math that doesn't require import — math is pre-loaded in globals
        result = code_executor.invoke({"code": "print(2 ** 10)", "description": "power"})
        assert "1024" in result

    def test_math_module_via_globals(self):
        from app.agent.tools import code_executor
        # math is pre-injected into allowed_globals — access it directly, no import needed
        result = code_executor.invoke(
            {"code": "print(round(math.pi, 4))", "description": "pi"}
        )
        assert "3.1416" in result

    def test_file_access_blocked(self):
        from app.agent.tools import code_executor
        result = code_executor.invoke(
            {"code": "open('/etc/passwd').read()", "description": "file test"}
        )
        assert "error" in result.lower() or "not defined" in result.lower()

    def test_syntax_error_safe(self):
        from app.agent.tools import code_executor
        result = code_executor.invoke({"code": "def broken(\n    pass", "description": "bad"})
        assert "error" in result.lower()

    def test_statistics_module(self):
        from app.agent.tools import code_executor
        result = code_executor.invoke(
            {"code": "print(statistics.mean([1, 2, 3, 4, 5]))", "description": "mean"}
        )
        assert "3" in result

    def test_list_comprehension(self):
        from app.agent.tools import code_executor
        result = code_executor.invoke(
            {"code": "print(sum([x*x for x in range(5)]))", "description": "squares"}
        )
        assert "30" in result