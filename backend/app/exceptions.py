"""
Custom exception hierarchy for Grimoire.

Each type maps to a specific HTTP status code in main.py.
Internal tracebacks never reach the client.
"""

from __future__ import annotations


class GrimoireError(Exception):
    """Base class. Provides .message attribute for client responses."""
    default_message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


# ── RAG / Ingestion ───────────────────────────────────────────────────────────

class IngestionError(GrimoireError):
    default_message = "Failed to ingest document."

class UnsupportedFileTypeError(IngestionError):
    default_message = "Unsupported file type."

class EmbeddingError(GrimoireError):
    default_message = "Failed to generate embeddings."

class RetrievalError(GrimoireError):
    default_message = "Failed to retrieve relevant documents."

class CollectionNotFoundError(RetrievalError):
    default_message = "No documents ingested yet. Use POST /ingest first."


# ── Agent ─────────────────────────────────────────────────────────────────────

class AgentError(GrimoireError):
    default_message = "Agent encountered an error during execution."

class AgentTimeoutError(AgentError):
    default_message = "Agent timed out. Try a more specific question."

class ToolExecutionError(AgentError):
    """Includes tool name so logs identify exactly which tool failed."""
    def __init__(self, tool_name: str, reason: str) -> None:
        self.tool_name = tool_name
        self.reason = reason
        super().__init__(f"Tool '{tool_name}' failed: {reason}")


# ── External APIs ─────────────────────────────────────────────────────────────

class LLMError(GrimoireError):
    default_message = "LLM API call failed."

class SearchAPIError(GrimoireError):
    default_message = "Web search failed."

class ValidationError(GrimoireError):
    default_message = "Invalid input."
