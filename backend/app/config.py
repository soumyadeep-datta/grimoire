"""
Application configuration loaded from environment variables / .env file.

All settings are validated at startup — the app refuses to start if
required keys are missing, surfacing config errors immediately.

Minimum required: ANTHROPIC_API_KEY only.
Optional keys unlock additional capabilities:
    VOYAGE_API_KEY  → Voyage-code-3.5 embeddings (recommended)
    COHERE_API_KEY  → Cohere Rerank v4 (recommended)
    TAVILY_API_KEY  → Web search tool
    OPENAI_API_KEY  → DeepEval evaluation scoring
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Environment ────────────────────────────────────────────────────────────
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")

    # ── LLM (Required) ────────────────────────────────────────────────────────
    anthropic_api_key: str = Field(..., description="Required — Claude for generation")
    claude_model: str = Field(default="claude-sonnet-4-6")
    claude_max_tokens: int = Field(default=4096, ge=256, le=8192)
    claude_temperature: float = Field(default=0.0, ge=0.0, le=1.0)

    # ── Embeddings (Optional — falls back to local all-MiniLM-L6-v2) ──────────
    voyage_api_key: str | None = Field(
        default=None,
        description="Optional — enables Voyage-code-3.5 embeddings (recommended)"
    )
    embedding_model: str = Field(default="voyage-code-3.5")

    # ── Reranking (Optional — skips reranking stage if not set) ───────────────
    cohere_api_key: str | None = Field(
        default=None,
        description="Optional — enables Cohere Rerank v4 (recommended)"
    )

    # ── Web Search (Optional — disables web search tool if not set) ───────────
    tavily_api_key: str | None = Field(
        default=None,
        description="Optional — enables Tavily web search tool"
    )

    # ── Evaluation (Optional — only needed for DeepEval scoring) ──────────────
    openai_api_key: str | None = Field(default=None)

    # ── Observability ──────────────────────────────────────────────────────────
    langchain_api_key: str | None = Field(default=None)
    langchain_tracing_v2: bool = Field(default=False)
    langchain_project: str = Field(default="grimoire")

    # ── Storage ────────────────────────────────────────────────────────────────
    qdrant_path: Path = Field(default=Path("./qdrant_data"))
    sqlite_db_path: Path = Field(default=Path("./data/knowledge.db"))

    # ── CORS ───────────────────────────────────────────────────────────────────
    backend_cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"]
    )

    # ── RAG Tuning ─────────────────────────────────────────────────────────────
    chunk_size: int = Field(default=1000, ge=100, le=4000)
    chunk_overlap: int = Field(default=200, ge=0, le=1000)
    retrieval_top_k: int = Field(default=5, ge=1, le=20)

    # ── Agent ──────────────────────────────────────────────────────────────────
    agent_max_iterations: int = Field(default=10, ge=1, le=25)
    agent_max_execution_time: float = Field(default=60.0, ge=5.0, le=300.0)

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"log_level must be one of {valid}, got '{v}'")
        return upper

    @field_validator("chunk_overlap")
    @classmethod
    def overlap_less_than_chunk(cls, v: int, info: Any) -> int:
        chunk_size = info.data.get("chunk_size", 1000)
        if v >= chunk_size:
            raise ValueError(f"chunk_overlap ({v}) must be < chunk_size ({chunk_size})")
        return v

    @model_validator(mode="after")
    def ensure_dirs_exist(self) -> "Settings":
        self.qdrant_path.mkdir(parents=True, exist_ok=True)
        self.sqlite_db_path.parent.mkdir(parents=True, exist_ok=True)
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_tracing_enabled(self) -> bool:
        return self.langchain_tracing_v2 and bool(self.langchain_api_key)

    @property
    def embedding_provider(self) -> str:
        """Locked at startup based on VOYAGE_API_KEY availability."""
        return "voyage" if self.voyage_api_key else "local"

    @property
    def qdrant_collection_name(self) -> str:
        """
        Each embedding provider gets its own Qdrant collection.
        Eliminates dimension mismatch errors when switching providers.
        """
        return f"grimoire_docs_{self.embedding_provider}"

    @property
    def reranking_enabled(self) -> bool:
        return bool(self.cohere_api_key)

    @property
    def web_search_enabled(self) -> bool:
        return bool(self.tavily_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the singleton Settings instance.
    .env is parsed exactly once per process.
    Tests: call get_settings.cache_clear() before patching env vars.
    """
    settings = Settings()
    _configure_logging(settings.log_level)
    logger.info(
        "Settings loaded | env=%s | model=%s | embedder=%s | reranking=%s | web_search=%s",
        settings.environment,
        settings.claude_model,
        settings.embedding_provider,
        settings.reranking_enabled,
        settings.web_search_enabled,
    )
    return settings


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("qdrant_client").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)