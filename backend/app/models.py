"""
Pydantic v2 request and response models for all API endpoints.

FastAPI uses these to validate incoming data and auto-generate /docs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class QueryRequest(BaseModel):
    question: str = Field(
        ..., min_length=1, max_length=2000,
        examples=["How do I configure middleware in FastAPI?"],
    )
    session_id: str = Field(default="default", max_length=128)
    use_agent: bool = Field(
        default=True,
        description="True = full ReAct agent. False = direct RAG (faster, cheaper).",
    )
    retrieval_k: int = Field(default=5, ge=1, le=20)

    @field_validator("question")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()


class ToolTrace(BaseModel):
    """One tool invocation. Rendered by frontend ToolTrace.jsx component."""
    tool: str
    input: str | dict[str, Any]
    output_preview: str


class QueryResponse(BaseModel):
    question: str
    answer: str
    session_id: str
    tools_used: list[ToolTrace] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    token_usage: dict[str, int] = Field(default_factory=dict)
    latency_ms: float


class IngestTextRequest(BaseModel):
    content: str = Field(..., min_length=10, max_length=500_000)
    source_name: str = Field(default="inline", max_length=256)


class IngestResponse(BaseModel):
    message: str
    chunks_added: int
    source: str


class HistoryMessage(BaseModel):
    role: str   # "user" | "assistant"
    content: str


class HistoryResponse(BaseModel):
    session_id: str
    messages: list[HistoryMessage]


class HealthResponse(BaseModel):
    status: str
    environment: str
    vector_store: dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class CollectionStatsResponse(BaseModel):
    total_chunks: int
    unique_sources: list[str]


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    code: str | None = None
