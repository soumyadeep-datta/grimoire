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
import os
import logging
import re as re_module
import time
from contextlib import asynccontextmanager
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import AIMessage, ToolMessage

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
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    settings = get_settings()
    logger.info("Grimoire starting up | env=%s", settings.environment)

    from app.rag.embeddings import get_embedding_client
    try:
        get_embedding_client()
        logger.info("Embedding client initialized and warmed up.")
    except Exception as exc:
        logger.error("Embedding client warm-up failed: %s", exc)

    try:
        get_vector_store()
        logger.info("Vector store initialized and BM25S index built.")
    except Exception as exc:
        logger.error("Vector store warm-up failed: %s", exc)

    async with AsyncSqliteSaver.from_conn_string(os.environ.get("CHECKPOINT_DB_PATH", "checkpoints.db")) as async_saver:
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
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(error="Not Found", detail=exc.message).model_dump())

    @app.exception_handler(CollectionMismatchError)
    async def collection_mismatch_handler(request, exc: CollectionMismatchError):
        return JSONResponse(status_code=status.HTTP_409_CONFLICT,
            content=ErrorResponse(error="Conflict", detail=exc.message).model_dump())

    @app.exception_handler(UnsupportedFileTypeError)
    async def unsupported_file_handler(request, exc: UnsupportedFileTypeError):
        return JSONResponse(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            content=ErrorResponse(error="Unsupported Media Type", detail=exc.message).model_dump())

    @app.exception_handler(AgentTimeoutError)
    async def agent_timeout_handler(request, exc: AgentTimeoutError):
        return JSONResponse(status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content=ErrorResponse(error="Gateway Timeout", detail=exc.message).model_dump())

    @app.exception_handler(RateLimitError)
    async def rate_limit_handler(request, exc: RateLimitError):
        return JSONResponse(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=ErrorResponse(error="Rate Limited", detail=exc.message).model_dump())

    @app.exception_handler(ServiceOverloadedError)
    async def service_overloaded_handler(request, exc: ServiceOverloadedError):
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=ErrorResponse(error="Service Unavailable", detail=exc.message).model_dump())

    @app.exception_handler(UpstreamProviderError)
    async def upstream_provider_handler(request, exc: UpstreamProviderError):
        return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY,
            content=ErrorResponse(error="Bad Gateway", detail=exc.message).model_dump())

    @app.exception_handler(GrimoireError)
    async def grimoire_error_handler(request, exc: GrimoireError):
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(error="Internal Error", detail=exc.message).model_dump())

    # ── Routes ────────────────────────────────────────────────────────────────

    @app.get("/health", response_model=HealthResponse, tags=["System"])
    async def health_check():
        store = get_vector_store()
        return HealthResponse(status="ok", environment=settings.environment, vector_store=store.collection_stats())

    @app.get("/collections", response_model=CollectionStatsResponse, tags=["RAG"])
    async def collection_stats():
        store = get_vector_store()
        return CollectionStatsResponse(**store.collection_stats())

    @app.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_201_CREATED, tags=["RAG"], summary="Upload and index a document")
    async def ingest_file(
        file: Annotated[UploadFile, File(description="Document to index (PDF, MD, TXT, code)")],
        settings: Settings = Depends(get_settings),
    ):
        import tempfile
        from pathlib import Path

        if not file.filename:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must have a filename.")

        suffix = Path(file.filename).suffix
        content = await file.read()

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            chunks = await asyncio.get_running_loop().run_in_executor(None, load_document, tmp_path)
            for chunk in chunks:
                chunk.metadata["source"] = file.filename
            store = get_vector_store()
            added = await asyncio.get_running_loop().run_in_executor(None, store.add_documents, chunks)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        logger.info("Ingested '%s': %d chunks added.", file.filename, added)
        return IngestResponse(message=f"Successfully indexed '{file.filename}'.", chunks_added=added, source=file.filename)

    @app.post("/ingest/text", response_model=IngestResponse, status_code=status.HTTP_201_CREATED, tags=["RAG"], summary="Index raw text directly")
    async def ingest_text(body: IngestTextRequest):
        chunks = await asyncio.get_running_loop().run_in_executor(None, load_text, body.content, body.source_name)
        store = get_vector_store()
        added = await asyncio.get_running_loop().run_in_executor(None, store.add_documents, chunks)
        return IngestResponse(message=f"Successfully indexed text as '{body.source_name}'.", chunks_added=added, source=body.source_name)

    @app.post("/query", response_model=QueryResponse, tags=["Agent"], summary="Ask a question")
    async def query(body: QueryRequest):
        start = time.monotonic()
        agent = get_agent()

        if body.use_agent:
            agent_response = await agent.arun(question=body.question, session_id=body.session_id)
            answer = agent_response.answer
            tools_used = [ToolTrace(**t) for t in agent_response.tools_used]
            sources = agent_response.sources
            token_usage = agent_response.token_usage
        else:
            chat_history = agent.get_history_string(body.session_id)
            answer, sources, token_usage = await _direct_rag(body.question, body.retrieval_k, settings, chat_history)
            tools_used = [ToolTrace(tool="rag_retrieval", input=body.question)]
            await asyncio.get_running_loop().run_in_executor(None, agent.add_to_checkpoint, body.session_id, body.question, answer)

        latency_ms = (time.monotonic() - start) * 1000
        logger.info("Query answered | session=%s | mode=%s | latency=%.0fms | tools=%d",
            body.session_id, "agent" if body.use_agent else "direct_rag", latency_ms, len(tools_used))

        return QueryResponse(question=body.question, answer=answer, session_id=body.session_id,
            tools_used=tools_used, sources=sources, token_usage=token_usage, latency_ms=round(latency_ms, 2))

    # ── Streaming helpers ─────────────────────────────────────────────────────

    def _extract_tool_query(event: dict) -> str:
        tool_input = event.get("data", {}).get("input", {})
        query = ""
        if isinstance(tool_input, dict):
            query = tool_input.get("query", tool_input.get("code", tool_input.get("question", "")))
        if isinstance(query, str) and len(query) > 80:
            query = query[:77] + "..."
        return query

    def _tool_start_status(tool_name: str, query: str) -> str:
        if query:
            return {"rag_retrieval": f'Searching: "{query}"', "web_search": f'Web search: "{query}"',
                "database_query": f'SQL query: "{query}"', "code_executor": "Executing code..."
            }.get(tool_name, f"Running {tool_name}...")
        return {"rag_retrieval": "Searching documentation...", "web_search": "Searching the web...",
            "database_query": "Querying database...", "code_executor": "Executing code..."
        }.get(tool_name, f"Running {tool_name}...")

    def _tool_end_status(tool_name: str, output: str) -> dict:
        metrics: dict = {}
        if tool_name == "rag_retrieval":
            scores = re_module.findall(r'Similarity:\s*(\d+\.\d+)', output)
            # Count chunks from the scores we already extracted — more reliable
            # than counting lines starting with "[" which can break depending on
            # how the output is serialized through astream_events
            chunk_count = len(scores)
            if scores:
                metrics["top_score"] = max(float(s) for s in scores)
                metrics["chunks"] = chunk_count
            msg = f"Found {chunk_count} chunk{'s' if chunk_count != 1 else ''}" if chunk_count > 0 else "No results found"
            if metrics.get("top_score"):
                msg += f" (top: {metrics['top_score']:.3f})"
        elif tool_name == "web_search":
            result_count = output.count("http")
            msg = f"Found {result_count} result{'s' if result_count != 1 else ''}" if result_count > 0 else "No results"
        elif tool_name == "code_executor":
            msg = "Execution complete"
        elif tool_name == "database_query":
            row_count = output.count("\n")
            msg = f"Returned {row_count} row{'s' if row_count != 1 else ''}" if row_count > 0 else "Query complete"
        else:
            msg = "Done"
        return {"msg": msg, "metrics": metrics}

    def _extract_sources_from_output(output: str, sources: set[str]) -> None:
        for line in output.splitlines():
            if "Source:" in line and "Chunk:" in line:
                try:
                    src_part = line.split("Source:")[1].split("|")[0].strip()
                    chunk_part = line.split("Chunk:")[1].split("|")[0].strip()
                    sources.add(f"{src_part} (chunk {chunk_part})")
                except IndexError:
                    pass

    def _extract_text_from_chunk(chunk) -> list[str]:
        if not chunk or not hasattr(chunk, "content") or not chunk.content:
            return []
        content = chunk.content
        texts = []
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    if text:
                        texts.append(text)
        elif isinstance(content, str) and content:
            texts.append(content)
        return texts

    async def _heal_checkpoint(graph, config: dict, session_id: str) -> None:
        """
        Inspect the graph state after a stream cancellation and inject
        synthetic ToolMessages for any dangling tool_calls.

        Per LangGraph docs (INVALID_CHAT_HISTORY troubleshooting):
        "add ToolMessage objects with tool_call_ids that match unanswered
         tool calls, call graph.update_state(config, {'messages': ...})"

        This prevents INVALID_CHAT_HISTORY on the next invocation by
        ensuring every tool_call has a corresponding ToolMessage.
        """
        try:
            state = await graph.aget_state(config)
            messages = state.values.get("messages", [])
            if not messages:
                return

            last_msg = messages[-1]
            if isinstance(last_msg, AIMessage) and getattr(last_msg, "tool_calls", None):
                logger.info(
                    "Healing %d dangling tool_call(s) for session '%s'",
                    len(last_msg.tool_calls), session_id,
                )
                fallback_tool_messages = [
                    ToolMessage(
                        content="Stream cancelled by user.",
                        tool_call_id=tc["id"],
                    )
                    for tc in last_msg.tool_calls
                ]
                # as_node="tools" tells LangGraph these came from the tools
                # node, maintaining valid state machine transitions.
                await graph.aupdate_state(
                    config,
                    {"messages": fallback_tool_messages},
                    as_node="tools",
                )
                logger.info("Checkpoint healed for session '%s'", session_id)
        except Exception as exc:
            logger.warning("Could not heal checkpoint for session '%s': %s", session_id, exc)

    async def _stream_agent(graph, config, question, session_id, agent, request: Request):
        """
        Core streaming logic. Yields SSE events: thinking, status, token, sources, done.

        Collects polymorphic UI blocks during the stream and commits them to
        ui_history in the checkpoint at completion. These blocks allow the
        frontend to reconstruct thinking panels, tool traces, source pills,
        and metrics on history reload.
        """
        import json

        start = time.monotonic()
        sources: set[str] = set()
        answer_parts: list[str] = []
        thinking_parts: list[str] = []
        tool_blocks: list[dict] = []     # Collected tool execution blocks
        phase = "pre_tool"

        async for event in graph.astream_events(
            {"messages": [{"role": "user", "content": question}]},
            config=config,
            version="v2",
        ):
            if await request.is_disconnected():
                logger.info("Client disconnected mid-stream for session '%s'", session_id)
                return

            kind = event["event"]
            name = event.get("name", "")
            elapsed_ms = round((time.monotonic() - start) * 1000)

            if kind == "on_tool_start":
                phase = "in_tool"
                tool_name = name
                query = _extract_tool_query(event)
                status_msg = _tool_start_status(tool_name, query)
                # Record tool start for block collection
                tool_blocks.append({
                    "type": "tool",
                    "tool": tool_name,
                    "query": query,
                    "elapsed_ms": elapsed_ms,
                })
                yield f"event: status\ndata: {json.dumps({'tool': tool_name, 'status': status_msg, 'elapsed_ms': elapsed_ms})}\n\n"

            elif kind == "on_tool_end":
                phase = "post_tool"
                tool_name = name
                output = str(event.get("data", {}).get("output", ""))
                if tool_name == "rag_retrieval":
                    _extract_sources_from_output(output, sources)
                result = _tool_end_status(tool_name, output)
                # Merge end data into the matching tool block
                for tb in reversed(tool_blocks):
                    if tb["tool"] == tool_name and "status" not in tb:
                        tb["status"] = result["msg"]
                        tb["elapsed_ms"] = elapsed_ms
                        tb["metrics"] = result["metrics"]
                        break
                yield f"event: status\ndata: {json.dumps({'tool': tool_name, 'status': result['msg'], 'done': True, 'elapsed_ms': elapsed_ms, 'metrics': result['metrics']})}\n\n"

            elif kind == "on_chat_model_stream":
                # Filter out tokens from the CRAG grader — its internal
                # LLM call leaks through astream_events as chat model chunks.
                tags = event.get("tags", [])
                if "crag_grader" in tags:
                    continue

                chunk = event.get("data", {}).get("chunk")
                texts = _extract_text_from_chunk(chunk)
                for text in texts:
                    if phase == "pre_tool":
                        thinking_parts.append(text)
                        yield f"event: thinking\ndata: {json.dumps({'text': text})}\n\n"
                    else:
                        answer_parts.append(text)
                        yield f"event: token\ndata: {json.dumps({'text': text})}\n\n"

        # ── Stream completed — assemble blocks and commit ─────────────────
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        full_answer = "".join(answer_parts)

        if not answer_parts and thinking_parts:
            full_answer = "".join(thinking_parts)

        # Build the polymorphic block record for this turn
        ui_blocks: list[dict] = []
        if thinking_parts:
            ui_blocks.append({"type": "thinking", "text": "".join(thinking_parts)})
        ui_blocks.extend(tool_blocks)
        ui_blocks.append({"type": "text", "text": full_answer})
        for s in sorted(sources):
            ui_blocks.append({"type": "source", "name": s})
        ui_blocks.append({"type": "latency", "ms": latency_ms})

        # Commit UI blocks keyed by the AIMessage's unique ID.
        # NOTE: We do NOT call add_to_checkpoint here — the stream's internal
        # checkpointing already committed the messages. Adding them again would
        # create duplicates with different IDs, causing double messages on reload.
        # We only write ui_history (the rich block metadata).
        try:
            state = await graph.aget_state(config)
            msgs = state.values.get("messages", [])
            # Find the last AIMessage with content — that's the one we just generated
            msg_id = None
            for msg in reversed(msgs):
                if isinstance(msg, AIMessage) and getattr(msg, "content", None):
                    msg_id = msg.id
                    break
            if msg_id:
                await graph.aupdate_state(config, {"ui_history": {msg_id: ui_blocks}})
            else:
                logger.warning("No AIMessage ID found for ui_history commit | session=%s", session_id)
        except Exception as exc:
            logger.warning("Could not write ui_history for session '%s': %s", session_id, exc)

        yield f"event: sources\ndata: {json.dumps({'sources': sorted(sources)})}\n\n"
        yield f"event: done\ndata: {json.dumps({'latency_ms': latency_ms})}\n\n"

    @app.post("/query/stream", tags=["Agent"], summary="Ask a question with streaming response (SSE)")
    async def query_stream(body: QueryRequest, request: Request):
        """
        Stream agent responses via Server-Sent Events.

        Event types:
            thinking — agent reasoning before tool calls
            status   — tool execution status updates
            token    — answer text tokens as they generate
            sources  — final sources list
            done     — signals stream complete with latency
            error    — error message if something fails

        Disconnection handling:
            When the client drops the connection (AbortController fires),
            the stream exits and _heal_checkpoint() injects synthetic
            ToolMessages for any dangling tool_calls, preventing
            INVALID_CHAT_HISTORY on the next invocation.
        """
        async def event_generator():
            import json

            agent = get_agent()
            config = {"configurable": {"thread_id": body.session_id}}
            graph = agent.get_async_graph()

            if graph is None:
                yield f"event: error\ndata: {json.dumps({'message': 'Streaming not available - server still initializing.'})}\n\n"
                return

            stream_completed = False
            try:
                async for sse in _stream_agent(graph, config, body.question, body.session_id, agent, request):
                    yield sse
                stream_completed = True

            except asyncio.CancelledError:
                # Client disconnected — heal the checkpoint before exiting
                logger.info("Stream cancelled for session '%s' — healing checkpoint", body.session_id)
                await _heal_checkpoint(graph, config, body.session_id)
                return

            except Exception as exc:
                err = str(exc)
                if "INVALID_CHAT_HISTORY" in err or "ToolMessage" in err:
                    logger.warning("Corrupted checkpoint for session '%s' — clearing and retrying", body.session_id)
                    agent.clear_session(body.session_id)
                    try:
                        async for sse in _stream_agent(graph, config, body.question, body.session_id, agent, request):
                            yield sse
                        stream_completed = True
                    except Exception as retry_exc:
                        yield f"event: error\ndata: {json.dumps({'message': str(retry_exc)})}\n\n"
                elif "overloaded" in err.lower() or "529" in err:
                    yield f"event: error\ndata: {json.dumps({'message': 'Anthropic servers temporarily overloaded. Please try again.'})}\n\n"
                elif "rate" in err.lower() or "429" in err:
                    yield f"event: error\ndata: {json.dumps({'message': 'Rate limit exceeded. Please wait a moment.'})}\n\n"
                else:
                    yield f"event: error\ndata: {json.dumps({'message': f'An error occurred: {err}'})}\n\n"

            finally:
                # If the stream didn't complete normally (early exit from
                # _stream_agent due to is_disconnected), heal the checkpoint.
                if not stream_completed:
                    await _heal_checkpoint(graph, config, body.session_id)

        return StreamingResponse(event_generator(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})

    @app.get("/history", response_model=HistoryResponse, tags=["Memory"], summary="Get conversation history")
    async def get_history(session_id: str = Query(default="default", description="Session ID")):
        agent = get_agent()
        messages = [HistoryMessage(**m) for m in agent.get_history(session_id)]
        return HistoryResponse(session_id=session_id, messages=messages)

    @app.delete("/history", status_code=status.HTTP_204_NO_CONTENT, tags=["Memory"], summary="Clear conversation history")
    async def delete_history(session_id: str = Query(default="default", description="Session ID")):
        agent = get_agent()
        agent.clear_session(session_id)

    @app.delete("/collections", status_code=status.HTTP_204_NO_CONTENT, tags=["RAG"], summary="Wipe the vector store")
    async def delete_collection():
        store = get_vector_store()
        store.delete_collection()

    @app.delete("/collections/source", status_code=status.HTTP_204_NO_CONTENT, tags=["RAG"], summary="Delete all chunks for a specific source")
    async def delete_source(source: str = Query(description="Source filename to delete")):
        store = get_vector_store()
        deleted = await asyncio.get_running_loop().run_in_executor(None, store.delete_by_source, source)
        logger.info("Deleted %d chunks for source '%s'", deleted, source)

    @app.get("/collections/source/content", tags=["RAG"], summary="Get all chunks for a specific source")
    async def get_source_content(source: str = Query(description="Source filename to fetch chunks for")):
        store = get_vector_store()
        chunks = await asyncio.get_running_loop().run_in_executor(None, store.get_chunks_by_source, source)
        return {"source": source, "chunks": chunks}

    return app


async def _direct_rag(question: str, k: int, settings: Settings, chat_history: str = "") -> tuple[str, list[str], dict]:
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage
    from pydantic import SecretStr
    from app.agent.prompts import RAG_CONTEXT_TEMPLATE

    store = get_vector_store()
    results = await asyncio.get_running_loop().run_in_executor(None, store.similarity_search, question, k)

    if not results:
        context = "No relevant documentation found."
        sources: list[str] = []
    else:
        context_parts, sources = [], []
        for r in results:
            context_parts.append(f"[Source: {r.source}, chunk {r.chunk_index}]\n{r.content}")
            sources.append(f"{r.source} (chunk {r.chunk_index})")
        context = "\n\n---\n\n".join(context_parts)

    history_block = f"\n\nConversation so far:\n{chat_history}\n" if chat_history else ""
    prompt = RAG_CONTEXT_TEMPLATE.format(context=context, source="", chunk_index="", question=question) + history_block

    llm = ChatAnthropic(model=settings.claude_model, api_key=SecretStr(settings.anthropic_api_key),
        max_tokens=2048, temperature=0.0, timeout=60.0)
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    return str(response.content), sources, {}


app = create_app()

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")