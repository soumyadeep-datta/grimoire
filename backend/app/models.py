"""
Pydantic v2 request and response models for all API endpoints.

Strict typing here means FastAPI generates accurate OpenAPI docs
and request validation failures return 422 with clear error messages.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ── /query ────────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Natural language question to answer.",
        examples=["How do I configure middleware in FastAPI?"],
    )
    session_id: str = Field(
        default="default",
        max_length=128,
        description="Session identifier for conversation memory.",
    )
    use_agent: bool = Field(
        default=True,
        description="If True, use the full ReAct agent with tools. "
                    "If False, use direct RAG-only mode (faster, cheaper).",
    )
    retrieval_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of document chunks to retrieve.",
    )

    @field_validator("question")
    @classmethod
    def strip_question(cls, v: str) -> str:
        return v.strip()


class ToolTrace(BaseModel):
    """Represents a single tool invocation by the agent."""
    tool: str
    input: str | dict[str, Any]
    output_preview: str | None = None


class QueryResponse(BaseModel):
    question: str
    answer: str
    session_id: str
    tools_used: list[ToolTrace] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    token_usage: dict[str, int] = Field(default_factory=dict)
    latency_ms: float = Field(description="End-to-end response time in milliseconds.")


# ── /ingest ───────────────────────────────────────────────────────────────────

class IngestTextRequest(BaseModel):
    """Ingest raw text directly (no file upload required)."""
    content: str = Field(..., min_length=10, max_length=500_000)
    source_name: str = Field(
        default="inline",
        max_length=256,
        description="Label for this content in citations.",
    )


class IngestResponse(BaseModel):
    message: str
    chunks_added: int
    source: str


# ── /history ─────────────────────────────────────────────────────────────────

class HistoryMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class HistoryResponse(BaseModel):
    session_id: str
    messages: list[HistoryMessage]


# ── /health ───────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    environment: str
    vector_store: dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ── /collections ─────────────────────────────────────────────────────────────

class CollectionStatsResponse(BaseModel):
    total_chunks: int
    unique_sources: list[str]


# ── Error response ────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    code: str | None = None