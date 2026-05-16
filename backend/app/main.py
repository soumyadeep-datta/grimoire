"""
FastAPI application entry point.

Routes:
    POST /query          — ReAct agent or direct RAG answer
    POST /ingest         — upload and index a document
    POST /ingest/text    — index raw text directly
    GET  /history        — conversation history for a session
    DELETE /history      — clear a session
    GET  /collections    — vector store stats
    GET  /health         — liveness check
    DELETE /collections  — wipe the vector store
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agent.orchestrator import get_agent
from app.config import Settings, get_settings
from app.exceptions import (
    AgentTimeoutError, CollectionNotFoundError, GrimoireError, UnsupportedFileTypeError,
)
from app.memory.conversation import add_exchange, clear_session, get_history_list, get_history_string
from app.models import (
    CollectionStatsResponse, ErrorResponse, HealthResponse,
    HistoryMessage, HistoryResponse, IngestResponse, IngestTextRequest,
    QueryRequest, QueryResponse, ToolTrace,
)
from app.rag.ingestion import load_document, load_text
from app.rag.retriever import get_vector_store

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the embedding model on startup so the first request isn't slow."""
    settings = get_settings()
    logger.info("Grimoire starting | env=%s", settings.environment)
    try:
        from app.rag.embeddings import get_embeddings
        get_embeddings()
        logger.info("Embedding model warmed up.")
    except Exception as exc:
        logger.error("Embedding model warm-up failed: %s", exc)
    yield
    logger.info("Grimoire shutting down.")


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = get_settings()

    app = FastAPI(
        title="Grimoire API",
        description="Agentic Developer Knowledge Assistant — RAG + multi-agent QA over your docs.",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.backend_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(CollectionNotFoundError)
    async def _(req, exc: CollectionNotFoundError):
        return JSONResponse(status_code=404, content=ErrorResponse(error="Not Found", detail=exc.message).model_dump())

    @app.exception_handler(UnsupportedFileTypeError)
    async def _(req, exc: UnsupportedFileTypeError):
        return JSONResponse(status_code=415, content=ErrorResponse(error="Unsupported Media Type", detail=exc.message).model_dump())

    @app.exception_handler(AgentTimeoutError)
    async def _(req, exc: AgentTimeoutError):
        return JSONResponse(status_code=504, content=ErrorResponse(error="Agent Timeout", detail=exc.message).model_dump())

    @app.exception_handler(GrimoireError)
    async def _(req, exc: GrimoireError):
        return JSONResponse(status_code=500, content=ErrorResponse(error="Internal Error", detail=exc.message).model_dump())

    @app.get("/health", response_model=HealthResponse, tags=["System"])
    async def health_check():
        return HealthResponse(
            status="ok", environment=settings.environment,
            vector_store=get_vector_store().collection_stats(),
        )

    @app.get("/collections", response_model=CollectionStatsResponse, tags=["RAG"])
    async def collection_stats():
        return CollectionStatsResponse(**get_vector_store().collection_stats())

    @app.post("/ingest", response_model=IngestResponse, status_code=201, tags=["RAG"])
    async def ingest_file(
        file: Annotated[UploadFile, File()],
        settings: Settings = Depends(get_settings),
    ):
        import asyncio, tempfile
        from pathlib import Path as P
        if not file.filename:
            raise HTTPException(status_code=400, detail="File must have a filename.")
        content = await file.read()
        with tempfile.NamedTemporaryFile(suffix=P(file.filename).suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            chunks = await asyncio.get_event_loop().run_in_executor(None, load_document, tmp_path)
            for chunk in chunks:
                chunk.metadata["source"] = file.filename
            store = get_vector_store()
            added = await asyncio.get_event_loop().run_in_executor(None, store.add_documents, chunks)
        finally:
            P(tmp_path).unlink(missing_ok=True)
        return IngestResponse(message=f"Indexed '{file.filename}'.", chunks_added=added, source=file.filename)

    @app.post("/ingest/text", response_model=IngestResponse, status_code=201, tags=["RAG"])
    async def ingest_text_endpoint(body: IngestTextRequest):
        import asyncio
        chunks = await asyncio.get_event_loop().run_in_executor(None, load_text, body.content, body.source_name)
        store = get_vector_store()
        added = await asyncio.get_event_loop().run_in_executor(None, store.add_documents, chunks)
        return IngestResponse(message=f"Indexed '{body.source_name}'.", chunks_added=added, source=body.source_name)

    @app.post("/query", response_model=QueryResponse, tags=["Agent"])
    async def query(body: QueryRequest):
        import asyncio
        start = time.monotonic()
        chat_history = get_history_string(body.session_id)

        if body.use_agent:
            resp = await get_agent().arun(question=body.question, chat_history=chat_history)
            answer = resp.answer
            tools_used = [ToolTrace(**t) for t in resp.tools_used]
            sources, token_usage = resp.sources, resp.token_usage
        else:
            answer, sources, token_usage = await _direct_rag(body.question, body.retrieval_k, settings)
            tools_used = [ToolTrace(tool="rag_retrieval", input=body.question, output_preview="")]

        add_exchange(body.session_id, body.question, answer)
        latency_ms = (time.monotonic() - start) * 1000
        return QueryResponse(
            question=body.question, answer=answer, session_id=body.session_id,
            tools_used=tools_used, sources=sources, token_usage=token_usage,
            latency_ms=round(latency_ms, 2),
        )

    @app.get("/history", response_model=HistoryResponse, tags=["Memory"])
    async def get_history(session_id: str = Query(default="default")):
        return HistoryResponse(session_id=session_id, messages=[HistoryMessage(**m) for m in get_history_list(session_id)])

    @app.delete("/history", status_code=204, tags=["Memory"])
    async def delete_history(session_id: str = Query(default="default")):
        clear_session(session_id)

    @app.delete("/collections", status_code=204, tags=["RAG"])
    async def delete_collection():
        get_vector_store().delete_collection()

    return app


async def _direct_rag(question: str, k: int, settings: Settings) -> tuple[str, list[str], dict]:
    import asyncio
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage
    from app.agent.prompts import RAG_CONTEXT_TEMPLATE

    store = get_vector_store()
    results = await asyncio.get_event_loop().run_in_executor(None, store.similarity_search, question, k)

    if not results:
        context, sources = "No relevant documentation found.", []
    else:
        parts, sources = [], []
        for r in results:
            meta = r.document.metadata
            src, idx = meta.get("source", "unknown"), meta.get("chunk_index", "?")
            parts.append(f"[Source: {src}, chunk {idx}]\n{r.content}")
            sources.append(f"{src} (chunk {idx})")
        context = "\n\n---\n\n".join(parts)

    prompt = RAG_CONTEXT_TEMPLATE.format(context=context, source="", chunk_index="", question=question)
    llm = ChatAnthropic(model=settings.claude_model, api_key=settings.anthropic_api_key, max_tokens=2048, temperature=0.0)
    response = await asyncio.get_event_loop().run_in_executor(None, lambda: llm.invoke([HumanMessage(content=prompt)]))
    return response.content, sources, {}


app = create_app()

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
