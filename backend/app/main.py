"""
FastAPI application entry point.

Routes:
    POST /query       — answer a question using the ReAct agent or direct RAG
    POST /ingest      — upload and index a new document (file upload or raw text)
    GET  /history     — conversation history for a session
    DELETE /history   — clear a session
    GET  /collections — vector store stats
    GET  /health      — liveness check

Memory architecture:
    Both agent mode and direct RAG mode use the LangGraph SQLite checkpoint
    store as the single source of truth for conversation history. session_id
    is a unified key across both query paths — history persists across server
    restarts and is consistent regardless of which mode was used.

Startup:
    The lifespan block eagerly initialises both the Voyage embedding client
    and the Qdrant VectorStore (which builds the BM25S in-memory index).
    This eliminates the cold-start penalty on the first user request.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from app.agent.orchestrator import get_agent
from app.config import Settings, get_settings
from app.exceptions import (
    AgentError,
    AgentTimeoutError,
    CollectionMismatchError,
    CollectionNotFoundError,
    GrimoireError,
    IngestionError,
    RateLimitError,
    ServiceOverloadedError,
    UpstreamProviderError,
    UnsupportedFileTypeError,
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
    Eager initialisation of heavy resources at startup.

    Shifts the cold-start penalty from the first user request to server boot,
    ensuring consistent low-latency responses from the first query onwards.
    """
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    settings = get_settings()
    logger.info("Grimoire starting up | env=%s", settings.environment)

    # 1. Warm up embedding client — mode locked at startup
    from app.rag.embeddings import get_embedding_client
    try:
        get_embedding_client()
        logger.info("Embedding client initialized and warmed up.")
    except Exception as exc:
        logger.error("Embedding client warm-up failed: %s", exc)

    # 2. Eager init of VectorStore — builds BM25S in-memory index at startup
    try:
        get_vector_store()
        logger.info("Vector store initialized and BM25S index built.")
    except Exception as exc:
        logger.error("Vector store warm-up failed: %s", exc)

    # 3. Initialize AsyncSqliteSaver for streaming endpoint
    async with AsyncSqliteSaver.from_conn_string("checkpoints.db") as async_saver:
        agent = get_agent()
        agent.set_async_checkpointer(async_saver)
        logger.info("Async graph initialized for streaming.")

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

    @app.exception_handler(CollectionMismatchError)
    async def collection_mismatch_handler(request, exc: CollectionMismatchError):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=ErrorResponse(error="Conflict", detail=exc.message).model_dump(),
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
            content=ErrorResponse(error="Gateway Timeout", detail=exc.message).model_dump(),
        )

    @app.exception_handler(RateLimitError)
    async def rate_limit_handler(request, exc: RateLimitError):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=ErrorResponse(error="Rate Limited", detail=exc.message).model_dump(),
        )

    @app.exception_handler(ServiceOverloadedError)
    async def service_overloaded_handler(request, exc: ServiceOverloadedError):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=ErrorResponse(error="Service Unavailable", detail=exc.message).model_dump(),
        )

    @app.exception_handler(UpstreamProviderError)
    async def upstream_provider_handler(request, exc: UpstreamProviderError):
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=ErrorResponse(error="Bad Gateway", detail=exc.message).model_dump(),
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
        store = get_vector_store()
        return HealthResponse(
            status="ok",
            environment=settings.environment,
            vector_store=store.collection_stats(),
        )

    @app.get("/collections", response_model=CollectionStatsResponse, tags=["RAG"])
    async def collection_stats():
        store = get_vector_store()
        return CollectionStatsResponse(**store.collection_stats())

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
        import tempfile
        from pathlib import Path

        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must have a filename.",
            )

        suffix = Path(file.filename).suffix
        content = await file.read()

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            chunks = await asyncio.get_running_loop().run_in_executor(
                None, load_document, tmp_path
            )
            for chunk in chunks:
                chunk.metadata["source"] = file.filename

            store = get_vector_store()
            added = await asyncio.get_running_loop().run_in_executor(
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
        chunks = await asyncio.get_running_loop().run_in_executor(
            None, load_text, body.content, body.source_name
        )
        store = get_vector_store()
        added = await asyncio.get_running_loop().run_in_executor(
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
        Answer a question via the ReAct agent or direct RAG.

        Both modes share the LangGraph SQLite checkpoint store for memory —
        session_id is a unified conversation key across query modes.

        use_agent=true:  Full ReAct agent with tool orchestration (~15-30s)
        use_agent=false: Direct RAG, lower latency, lower cost (~3-7s)
        """
        start = time.monotonic()
        agent = get_agent()

        if body.use_agent:
            # LangGraph handles memory automatically via checkpointing
            agent_response = await agent.arun(
                question=body.question,
                session_id=body.session_id,
            )
            answer = agent_response.answer
            tools_used = [ToolTrace(**t) for t in agent_response.tools_used]
            sources = agent_response.sources
            token_usage = agent_response.token_usage

        else:
            # Read history from unified checkpoint store for context
            chat_history = agent.get_history_string(body.session_id)
            answer, sources, token_usage = await _direct_rag(
                body.question, body.retrieval_k, settings, chat_history
            )
            tools_used = [ToolTrace(tool="rag_retrieval", input=body.question)]

            # Write exchange into checkpoint store so agent mode sees it too
            await asyncio.get_running_loop().run_in_executor(
                None, agent.add_to_checkpoint, body.session_id, body.question, answer
            )

        latency_ms = (time.monotonic() - start) * 1000
        logger.info(
            "Query answered | session=%s | mode=%s | latency=%.0fms | tools=%d",
            body.session_id,
            "agent" if body.use_agent else "direct_rag",
            latency_ms,
            len(tools_used),
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

    @app.post(
        "/query/stream",
        tags=["Agent"],
        summary="Ask a question with streaming response (SSE)",
    )
    async def query_stream(body: QueryRequest):
        """
        Stream agent responses via Server-Sent Events.

        Event types:
            status  — tool execution status updates
            token   — text tokens as they generate
            sources — final sources list
            done    — signals stream complete with latency
            error   — error message if something fails
        """
        async def event_generator():
            import json
            import time

            start = time.monotonic()
            agent = get_agent()
            config = {"configurable": {"thread_id": body.session_id}}
            graph = agent.get_async_graph()

            if graph is None:
                yield f"event: error\ndata: {json.dumps({'message': 'Streaming not available - server still initializing.'})}\n\n"
                return

            sources: set[str] = set()
            answer_parts: list[str] = []

            async def _run_stream(g, cfg):
                async for event in g.astream_events(
                    {"messages": [{"role": "user", "content": body.question}]},
                    config=cfg,
                    version="v2",
                ):
                    yield event

            try:
                async for event in _run_stream(graph, config):
                    kind = event["event"]
                    name = event.get("name", "")

                    if kind == "on_tool_start":
                        tool_name = name
                        status_msg = {
                            "rag_retrieval": "Searching documentation...",
                            "web_search": "Searching the web...",
                            "database_query": "Querying database...",
                            "code_executor": "Executing code...",
                        }.get(tool_name, f"Running {tool_name}...")
                        yield f"event: status\ndata: {json.dumps({'tool': tool_name, 'status': status_msg})}\n\n"

                    elif kind == "on_tool_end":
                        tool_name = name
                        output = str(event.get("data", {}).get("output", ""))
                        if tool_name == "rag_retrieval":
                            for line in output.splitlines():
                                if "Source:" in line and "Chunk:" in line:
                                    try:
                                        src_part = line.split("Source:")[1].split("|")[0].strip()
                                        chunk_part = line.split("Chunk:")[1].split("|")[0].strip()
                                        sources.add(f"{src_part} (chunk {chunk_part})")
                                    except IndexError:
                                        pass
                        yield f"event: status\ndata: {json.dumps({'tool': tool_name, 'status': 'Done', 'done': True})}\n\n"

                    elif kind == "on_chat_model_stream":
                        chunk = event.get("data", {}).get("chunk")
                        if chunk and hasattr(chunk, "content") and chunk.content:
                            content = chunk.content
                            if isinstance(content, list):
                                for block in content:
                                    if isinstance(block, dict) and block.get("type") == "text":
                                        text = block.get("text", "")
                                        if text:
                                            answer_parts.append(text)
                                            yield f"event: token\ndata: {json.dumps({'text': text})}\n\n"
                            elif isinstance(content, str) and content:
                                answer_parts.append(content)
                                yield f"event: token\ndata: {json.dumps({'text': content})}\n\n"

                latency_ms = round((time.monotonic() - start) * 1000, 2)
                full_answer = "".join(answer_parts)
                await asyncio.get_running_loop().run_in_executor(
                    None, agent.add_to_checkpoint,
                    body.session_id, body.question, full_answer
                )
                yield f"event: sources\ndata: {json.dumps({'sources': sorted(sources)})}\n\n"
                yield f"event: done\ndata: {json.dumps({'latency_ms': latency_ms})}\n\n"

            except Exception as exc:
                err = str(exc)
                if "INVALID_CHAT_HISTORY" in err or "ToolMessage" in err:
                    logger.warning("Corrupted checkpoint for session '%s' — clearing and retrying", body.session_id)
                    agent.clear_session(body.session_id)
                    sources = set()
                    answer_parts = []
                    try:
                        async for event in _run_stream(graph, config):
                            kind = event["event"]
                            name = event.get("name", "")
                            if kind == "on_tool_start":
                                tool_name = name
                                status_msg = {"rag_retrieval": "Searching documentation...", "web_search": "Searching the web...", "database_query": "Querying database...", "code_executor": "Executing code..."}.get(tool_name, f"Running {tool_name}...")
                                yield f"event: status\ndata: {json.dumps({'tool': tool_name, 'status': status_msg})}\n\n"
                            elif kind == "on_tool_end":
                                yield f"event: status\ndata: {json.dumps({'tool': name, 'status': 'Done', 'done': True})}\n\n"
                            elif kind == "on_chat_model_stream":
                                chunk = event.get("data", {}).get("chunk")
                                if chunk and hasattr(chunk, "content") and chunk.content:
                                    c = chunk.content
                                    if isinstance(c, list):
                                        for block in c:
                                            if isinstance(block, dict) and block.get("type") == "text":
                                                text = block.get("text", "")
                                                if text:
                                                    answer_parts.append(text)
                                                    yield f"event: token\ndata: {json.dumps({'text': text})}\n\n"
                                    elif isinstance(c, str) and c:
                                        answer_parts.append(c)
                                        yield f"event: token\ndata: {json.dumps({'text': c})}\n\n"
                        latency_ms = round((time.monotonic() - start) * 1000, 2)
                        full_answer = "".join(answer_parts)
                        await asyncio.get_running_loop().run_in_executor(None, agent.add_to_checkpoint, body.session_id, body.question, full_answer)
                        yield f"event: done\ndata: {json.dumps({'latency_ms': latency_ms})}\n\n"
                    except Exception as retry_exc:
                        yield f"event: error\ndata: {json.dumps({'message': str(retry_exc)})}\n\n"
                elif "overloaded" in err.lower() or "529" in err:
                    yield f"event: error\ndata: {json.dumps({'message': 'Anthropic servers temporarily overloaded. Please try again.'})}\n\n"
                elif "rate" in err.lower() or "429" in err:
                    yield f"event: error\ndata: {json.dumps({'message': 'Rate limit exceeded. Please wait a moment.'})}\n\n"
                else:
                    yield f"event: error\ndata: {json.dumps({'message': f'An error occurred: {err}'})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",  # disable nginx buffering
                "Connection": "keep-alive",
            },
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
        """
        Returns full conversation history from the LangGraph checkpoint store.
        Includes both agent mode and direct RAG turns for this session.
        """
        agent = get_agent()
        messages = [HistoryMessage(**m) for m in agent.get_history(session_id)]
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
        agent = get_agent()
        agent.clear_session(session_id)

    @app.delete(
        "/collections",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["RAG"],
        summary="Wipe the vector store",
    )
    async def delete_collection():
        """Delete all indexed documents from Qdrant. Irreversible."""
        store = get_vector_store()
        store.delete_collection()

    @app.delete(
        "/collections/source",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["RAG"],
        summary="Delete all chunks for a specific source",
    )
    async def delete_source(
        source: str = Query(description="Source filename to delete"),
    ):
        """Delete all chunks from a specific source document. Irreversible."""
        store = get_vector_store()
        deleted = await asyncio.get_running_loop().run_in_executor(
            None, store.delete_by_source, source
        )
        logger.info("Deleted %d chunks for source '%s'", deleted, source)

    @app.get(
        "/collections/source/content",
        tags=["RAG"],
        summary="Get all chunks for a specific source",
    )
    async def get_source_content(
        source: str = Query(description="Source filename to fetch chunks for"),
    ):
        """Return all chunks belonging to a specific source document."""
        store = get_vector_store()
        chunks = await asyncio.get_running_loop().run_in_executor(
            None, store.get_chunks_by_source, source
        )
        return {"source": source, "chunks": chunks}

    return app


# ── Direct RAG helper ─────────────────────────────────────────────────────────

async def _direct_rag(
    question: str,
    k: int,
    settings: Settings,
    chat_history: str = "",
) -> tuple[str, list[str], dict]:
    """
    Retrieve top-k chunks and generate an answer directly with Claude.
    No agent loop — lower latency, lower cost.
    Injects conversation history from the unified checkpoint store.
    """
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage
    from pydantic import SecretStr
    from app.agent.prompts import RAG_CONTEXT_TEMPLATE

    store = get_vector_store()
    results = await asyncio.get_running_loop().run_in_executor(
        None, store.similarity_search, question, k
    )

    if not results:
        context = "No relevant documentation found."
        sources: list[str] = []
    else:
        context_parts = []
        sources = []
        for r in results:
            context_parts.append(
                f"[Source: {r.source}, chunk {r.chunk_index}]\n{r.content}"
            )
            sources.append(f"{r.source} (chunk {r.chunk_index})")
        context = "\n\n---\n\n".join(context_parts)

    history_block = f"\n\nConversation so far:\n{chat_history}\n" if chat_history else ""

    prompt = RAG_CONTEXT_TEMPLATE.format(
        context=context,
        source="",
        chunk_index="",
        question=question,
    ) + history_block

    llm = ChatAnthropic(
        model=settings.claude_model,
        api_key=SecretStr(settings.anthropic_api_key),
        max_tokens=2048,
        temperature=0.0,
        timeout=60.0,
    )

    response = await llm.ainvoke([HumanMessage(content=prompt)])
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