"""
Custom exception hierarchy for Grimoire.

Structured exceptions allow FastAPI exception handlers to map each
error type to the correct HTTP status code and response shape without
leaking internal details to clients.

HTTP status mapping:
    400 Bad Request          — ValidationError, UnsupportedFileTypeError
    404 Not Found            — CollectionNotFoundError (empty)
    409 Conflict             — CollectionMismatchError (dimension mismatch)
    415 Unsupported Media    — UnsupportedFileTypeError
    429 Too Many Requests    — RateLimitError
    500 Internal Server      — GrimoireError (base), IngestionError, etc.
    502 Bad Gateway          — UpstreamProviderError (Voyage/Cohere failures)
    503 Service Unavailable  — ServiceOverloadedError (Anthropic 529)
    504 Gateway Timeout      — AgentTimeoutError
"""

from __future__ import annotations


class GrimoireError(Exception):
    """Base class for all application-level exceptions."""

    default_message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


# ── RAG / Ingestion ───────────────────────────────────────────────────────────

class IngestionError(GrimoireError):
    """Raised when document ingestion fails."""
    default_message = "Failed to ingest document."


class UnsupportedFileTypeError(IngestionError):
    """Raised when an unsupported file extension is provided."""
    default_message = "Unsupported file type."


class EmbeddingError(GrimoireError):
    """Raised when embedding generation fails."""
    default_message = "Failed to generate embeddings."


class RetrievalError(GrimoireError):
    """Raised when vector store retrieval fails."""
    default_message = "Failed to retrieve relevant documents."


class CollectionNotFoundError(RetrievalError):
    """Raised when the vector store is empty."""
    default_message = "No documents have been ingested yet. Use POST /ingest first."


class CollectionMismatchError(RetrievalError):
    """
    Raised when the embedding dimension doesn't match the stored collection.
    This is a 409 Conflict — the server state conflicts with the request.
    """
    default_message = (
        "Embedding dimension mismatch — the collection was built with a different "
        "embedding model. Wipe the collection (DELETE /collections) and re-ingest."
    )


# ── Agent ─────────────────────────────────────────────────────────────────────

class AgentError(GrimoireError):
    """Raised when the ReAct agent fails."""
    default_message = "Agent encountered an error during execution."


class AgentTimeoutError(AgentError):
    """Raised when the agent exceeds its execution time limit."""
    default_message = "Agent timed out. Try a more specific question."


class ToolExecutionError(AgentError):
    """Raised when a specific agent tool fails."""

    def __init__(self, tool_name: str, reason: str) -> None:
        self.tool_name = tool_name
        self.reason = reason
        super().__init__(f"Tool '{tool_name}' failed: {reason}")


# ── External API errors ───────────────────────────────────────────────────────

class RateLimitError(GrimoireError):
    """
    Raised when any upstream API returns a 429 rate limit response.
    Returns 429 to the client so they can implement backoff.
    """
    default_message = (
        "API rate limit exceeded. Please wait a moment and try again."
    )


class ServiceOverloadedError(GrimoireError):
    """
    Raised when an upstream provider is temporarily overloaded (e.g. Anthropic 529).
    Returns 503 Service Unavailable — not a code bug, a transient upstream issue.
    """
    default_message = (
        "An upstream service is temporarily overloaded. "
        "Please wait a moment and try again."
    )


class UpstreamProviderError(GrimoireError):
    """
    Raised when Voyage, Cohere, or Tavily returns an unexpected error.
    Returns 502 Bad Gateway — the server got an invalid response from upstream.
    """
    default_message = "An upstream provider returned an error. Please try again."


class LLMError(GrimoireError):
    """Raised when the Claude API call fails."""
    default_message = "LLM API call failed."


class SearchAPIError(GrimoireError):
    """Raised when the Tavily search API call fails."""
    default_message = "Web search failed."


# ── Validation ────────────────────────────────────────────────────────────────

class ValidationError(GrimoireError):
    """Raised on invalid user input (supplements Pydantic validation)."""
    default_message = "Invalid input."