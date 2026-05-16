"""
FastAPI application entry point.

Routes:
    POST /query       — answer a question using the ReAct agent or direct RAG
    POST /ingest      — upload and index a new document (file upload or raw text)
    GET  /history     — conversation history for a session
    DELETE /history   — clear a session
    GET  /collections — vector store stats
    GET  /health      — liveness check

All routes use async handlers. CPU-bound work (embeddings, ChromaDB)
is offloaded to a thread executor so the event loop stays responsive.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agent.orchestrator import get_agent
from app.config import Settings, get_settings
from app.exceptions import (
    AgentError,
    AgentTimeoutError,
    CollectionNotFoundError,
    GrimoireError,
    IngestionError,
    UnsupportedFileTypeError,
)
from app.memory.conversation import (
    add_exchange,
    clear_session,
    get_history_list,
    get_history_string,
)
from app.models import (
    CollectionStatsResponse,
    ErrorResponse,
    HealthResponse,
    HistoryMessage,
    HistoryResponse,
    IngestResponse,
    IngestTextRequest,
    QueryRequest,
    QueryResponse,
    ToolTrace,
)
from app.rag.ingestion import load_document, load_text
from app.rag.retriever import get_vector_store

logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Run startup/shutdown logic around the app's lifetime.

    Startup: validate settings, warm up the embedding model.
    Shutdown: log graceful shutdown.
    """
    settings = get_settings()
    logger.info("Grimoire starting up | env=%s", settings.environment)

    # Eagerly load the embedding model so the first request isn't slow
    try:
        from app.rag.embeddings import get_embeddings
        get_embeddings()
        logger.info("Embedding model warmed up.")
    except Exception as exc:
        logger.error("Embedding model warm-up failed: %s", exc)
        # Don't crash — allow the app to start; ingestion will fail gracefully

    yield

    logger.info("Grimoire shutting down.")


# ── App factory ───────────────────────────────────────────────────────────────

def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = get_settings()

    app = FastAPI(
        title="Grimoire API",
        description="Agentic Developer Knowledge Assistant — RAG + multi-agent QA over your docs.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.backend_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception handlers ────────────────────────────────────────────────────

    @app.exception_handler(CollectionNotFoundError)
    async def collection_not_found_handler(request, exc: CollectionNotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(error="Not Found", detail=exc.message).model_dump(),
        )

    @app.exception_handler(UnsupportedFileTypeError)
    async def unsupported_file_handler(request, exc: UnsupportedFileTypeError):
        return JSONResponse(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            content=ErrorResponse(error="Unsupported Media Type", detail=exc.message).model_dump(),
        )

    @app.exception_handler(AgentTimeoutError)
    async def agent_timeout_handler(request, exc: AgentTimeoutError):
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content=ErrorResponse(error="Agent Timeout", detail=exc.message).model_dump(),
        )

    @app.exception_handler(GrimoireError)
    async def grimoire_error_handler(request, exc: GrimoireError):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(error="Internal Error", detail=exc.message).model_dump(),
        )

    # ── Routes ────────────────────────────────────────────────────────────────

    @app.get("/health", response_model=HealthResponse, tags=["System"])
    async def health_check():
        """Liveness probe — returns vector store stats and config summary."""
        store = get_vector_store()
        return HealthResponse(
            status="ok",
            environment=settings.environment,
            vector_store=store.collection_stats(),
        )

    @app.get("/collections", response_model=CollectionStatsResponse, tags=["RAG"])
    async def collection_stats():
        """Return the number of indexed chunks and list of unique source files."""
        store = get_vector_store()
        stats = store.collection_stats()
        return CollectionStatsResponse(**stats)

    @app.post(
        "/ingest",
        response_model=IngestResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["RAG"],
        summary="Upload and index a document",
    )
    async def ingest_file(
        file: Annotated[UploadFile, File(description="Document to index (PDF, MD, TXT, code)")],
        settings: Settings = Depends(get_settings),
    ):
        """
        Upload a file and add it to the vector store.

        Supported formats: PDF, Markdown, TXT, HTML, Python, JavaScript,
        TypeScript, Go, Rust, Java, C/C++, YAML, JSON, TOML, RST.
        """
        import asyncio
        import tempfile
        from pathlib import Path

        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must have a filename.",
            )

        # Write upload to a temp file so loaders can access it by path
        suffix = Path(file.filename).suffix
        content = await file.read()

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            chunks = await asyncio.get_event_loop().run_in_executor(
                None, load_document, tmp_path
            )
            # Restore original filename in metadata
            for chunk in chunks:
                chunk.metadata["source"] = file.filename

            store = get_vector_store()
            added = await asyncio.get_event_loop().run_in_executor(
                None, store.add_documents, chunks
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        logger.info("Ingested '%s': %d chunks added.", file.filename, added)
        return IngestResponse(
            message=f"Successfully indexed '{file.filename}'.",
            chunks_added=added,
            source=file.filename,
        )

    @app.post(
        "/ingest/text",
        response_model=IngestResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["RAG"],
        summary="Index raw text directly",
    )
    async def ingest_text(body: IngestTextRequest):
        """Ingest raw text content without a file upload."""
        import asyncio

        chunks = await asyncio.get_event_loop().run_in_executor(
            None, load_text, body.content, body.source_name
        )
        store = get_vector_store()
        added = await asyncio.get_event_loop().run_in_executor(
            None, store.add_documents, chunks
        )
        return IngestResponse(
            message=f"Successfully indexed text as '{body.source_name}'.",
            chunks_added=added,
            source=body.source_name,
        )

    @app.post(
        "/query",
        response_model=QueryResponse,
        tags=["Agent"],
        summary="Ask a question",
    )
    async def query(body: QueryRequest):
        """
        Answer a developer question using the ReAct agent.

        The agent will:
        1. Search your ingested documentation (rag_retrieval)
        2. Fall back to web search if needed (web_search)
        3. Query structured data if relevant (database_query)
        4. Run code for computations (code_executor)

        Set `use_agent=false` for a faster, cheaper direct-RAG-only response.
        """
        import asyncio

        start = time.monotonic()

        # Retrieve conversation history for context injection
        chat_history = get_history_string(body.session_id)

        if body.use_agent:
            agent = get_agent()
            agent_response = await agent.arun(
                question=body.question,
                chat_history=chat_history,
            )
            answer = agent_response.answer
            tools_used = [ToolTrace(**t) for t in agent_response.tools_used]
            sources = agent_response.sources
            token_usage = agent_response.token_usage
        else:
            # Direct RAG mode — no agent overhead
            answer, sources, token_usage = await _direct_rag(
                body.question, body.retrieval_k, settings
            )
            tools_used = [ToolTrace(tool="rag_retrieval", input=body.question, output_preview="")]

        # Persist to memory
        add_exchange(body.session_id, body.question, answer)

        latency_ms = (time.monotonic() - start) * 1000
        logger.info(
            "Query answered | session=%s | latency=%.0fms | tools=%d",
            body.session_id, latency_ms, len(tools_used),
        )

        return QueryResponse(
            question=body.question,
            answer=answer,
            session_id=body.session_id,
            tools_used=tools_used,
            sources=sources,
            token_usage=token_usage,
            latency_ms=round(latency_ms, 2),
        )

    @app.get(
        "/history",
        response_model=HistoryResponse,
        tags=["Memory"],
        summary="Get conversation history",
    )
    async def get_history(
        session_id: str = Query(default="default", description="Session ID"),
    ):
        messages = [HistoryMessage(**m) for m in get_history_list(session_id)]
        return HistoryResponse(session_id=session_id, messages=messages)

    @app.delete(
        "/history",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["Memory"],
        summary="Clear conversation history",
    )
    async def delete_history(
        session_id: str = Query(default="default", description="Session ID"),
    ):
        clear_session(session_id)

    @app.delete(
        "/collections",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["RAG"],
        summary="Wipe the vector store",
    )
    async def delete_collection():
        """
        Delete all indexed documents from ChromaDB.
        Use with caution — this is irreversible.
        """
        store = get_vector_store()
        store.delete_collection()

    return app


# ── Direct RAG helper (no agent) ──────────────────────────────────────────────

async def _direct_rag(
    question: str,
    k: int,
    settings: Settings,
) -> tuple[str, list[str], dict]:
    """
    Retrieve top-k chunks and generate an answer directly with Claude.
    No agent loop — lower latency, lower cost.
    """
    import asyncio
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage, SystemMessage
    from app.agent.prompts import RAG_CONTEXT_TEMPLATE

    store = get_vector_store()
    results = await asyncio.get_event_loop().run_in_executor(
        None, store.similarity_search, question, k
    )

    if not results:
        context = "No relevant documentation found."
        sources: list[str] = []
    else:
        context_parts = []
        sources = []
        for r in results:
            meta = r.document.metadata
            source = meta.get("source", "unknown")
            chunk_idx = meta.get("chunk_index", "?")
            context_parts.append(
                f"[Source: {source}, chunk {chunk_idx}]\n{r.content}"
            )
            sources.append(f"{source} (chunk {chunk_idx})")
        context = "\n\n---\n\n".join(context_parts)

    prompt = RAG_CONTEXT_TEMPLATE.format(
        context=context,
        source="",
        chunk_index="",
        question=question,
    )

    from pydantic import SecretStr
    llm = ChatAnthropic(
        model_name=settings.claude_model,
        api_key=SecretStr(settings.anthropic_api_key),
        max_tokens_to_sample=2048,
        temperature=0.0,
        timeout=60.0,
        stop=None,
    )
    response = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: llm.invoke([HumanMessage(content=prompt)]),
    )

    return str(response.content), sources, {}


# ── Entry point ───────────────────────────────────────────────────────────────

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )