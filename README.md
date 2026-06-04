# Grimoire — Agentic Developer Knowledge Assistant

> A production-grade RAG system for querying developer documentation and codebases. Combines hybrid retrieval, LangGraph-orchestrated agents, and evaluated answer generation — deployable with a single API key.

![Grimoire UI](docs/screenshot.png)

-----

## Quick Start (Docker — Recommended)

```bash
git clone https://github.com/soumyadeep-datta/grimoire.git
cd grimoire

cp .env.example .env
# Edit .env: add ANTHROPIC_API_KEY (required)

docker compose up
```

Open <http://localhost:3000> — the full stack is running.

First build takes ~10 minutes (downloading Python + Node images, installing deps, building Next.js bundle). Subsequent runs start in ~5 seconds.

To stop: `docker compose down`. To wipe ingested data and start fresh: `docker compose down -v`.

-----

## Evaluation Results

Evaluated on 20 questions using DeepEval with GPT-4o-mini as judge, Claude Sonnet 4.6 for generation.

|Metric              |Score     |
|--------------------|----------|
|Faithfulness        |**0.9143**|
|Contextual Recall   |**0.8794**|
|Answer Relevancy    |**0.9126**|
|Contextual Precision|**0.9377**|

Reproduce: `python -m app.eval.evaluate --dataset eval_dataset_v2.json --output eval_report_v2.json`

-----

## Architecture

### Retrieval Pipeline (4 stages)

```
Query
  │
  ├── 1. Dense search   ── Voyage-code-3.5 embeddings → Qdrant
  ├── 2. Sparse search  ── BM25S lexical index (in-memory, built at startup)
  │
  ├── 3. RRF fusion     ── Reciprocal Rank Fusion (k=60) merges both ranked lists
  │
  └── 4. Reranking      ── Cohere Rerank v4 cross-encoder → top-k results
```

**Why hybrid?** Pure dense search misses exact tokens (function names, error codes, API identifiers). Pure BM25 misses semantic similarity. RRF fusion eliminates both failure modes. Cohere Rerank adds cross-encoder precision as a second stage.

**AST-aware chunking:** Code files (`.py`, `.js`, `.ts`) are parsed via tree-sitter and split at semantic boundaries — functions, classes, methods — rather than arbitrary character limits. Each chunk includes a contextual header (file name, imports, parent class) following Anthropic’s Contextual Retrieval pattern.

### Agent Architecture

```
User Query
    │
    ▼
LangGraph ReAct Agent (Claude Sonnet 4.6)
    │
    ├── Tool 1: rag_retrieval    — 4-stage hybrid pipeline over ingested docs
    ├── Tool 2: web_search       — Tavily (optional, excluded if no key)
    ├── Tool 3: database_query   — NL→SQL over SQLite knowledge base
    └── Tool 4: code_executor    — RestrictedPython sandbox
    │
    ▼
LangGraph SQLite Checkpointer (unified memory)
    │
    ▼
Answer with citations
```

**Unified memory:** Both agent mode and direct RAG mode write to the same LangGraph SQLite checkpoint store, keyed by `session_id`. History persists across server restarts and is consistent regardless of which query mode was used.

### Frontend

Next.js 16 + TypeScript. Streaming chat UI featuring an auto-expanding live execution timeline showing real-time agent reasoning steps, sub-query execution logs, latencies, and cross-encoder retrieval scores. Features direct source citation modals, session persistence via local caching, offline detection, and a warm, minimal monochromatic dark aesthetic. Connects to the backend via the standard REST API documented at `/docs`.

-----

## Design Decisions

### Tool-Level Exception Handling

LangGraph checkpoints state after each node transition. If a tool raises an unhandled exception, the checkpoint contains an `AIMessage` with `tool_calls` but no corresponding `ToolMessage` — leaving the graph in an irrecoverable `INVALID_CHAT_HISTORY` state that corrupts the session permanently.

**Decision:** All tools catch exceptions internally and return error strings instead of raising. This ensures LangGraph always receives a valid `ToolMessage`, keeping the checkpoint intact regardless of upstream API failures (Voyage rate limits, Tavily timeouts, SQLite errors).

See: [LangGraph INVALID_CHAT_HISTORY troubleshooting](https://langchain-ai.github.io/langgraph/troubleshooting/errors/INVALID_CHAT_HISTORY/)

### Backend State Healing on Disconnection

When a user switches conversations or closes the browser mid-stream, the frontend’s `AbortController` severs the SSE connection. The backend catches this via `request.is_disconnected()` and `asyncio.CancelledError`. It isolates the interruption cleanly to prevent event loop blockages, then inspects the graph state for dangling `tool_calls`. If found, synthetic `ToolMessage` objects are injected via non-blocking `await graph.aupdate_state(config, {"messages": ...}, as_node="tools")` and `await graph.aget_state(config)` calls to safely restore valid state machine transitions.

**Result:** Users can abort, switch, or refresh at any point during a stream without corrupting the conversation checkpoint. The session remains fully resumable.

### State Architecture & Telemetry Separation

Grimoire implements a strict separation between volatile runtime telemetry and immutable conversation history:

- **Live sessions** stream real-time execution metadata via Server-Sent Events — agent reasoning traces, tool search queries, step latencies, reranker similarity scores, and chunk counts. This data exists only in the frontend’s React state during the active session.
- **Historical sessions** are persisted as text via LangGraph’s SQLite checkpoint store. Intermediate vector coordinates, execution metrics, and reasoning traces are deliberately excluded post-stream to keep storage writes decoupled from analytical telemetry footprints.

This mirrors industry practice: ChatGPT and Claude both serialize historical conversations as text, reserving structured telemetry for live observability pipelines (LangSmith, Prometheus) rather than transactional user databases.

### Single-Collection, Mode-Locked at Startup

The embedding model (Voyage-code-3.5 at 1024 dimensions, or local all-MiniLM-L6-v2 at 384 dimensions) is locked at server startup based on available API keys. All documents are stored in a single Qdrant collection with a fixed vector dimension.

**Why not runtime fallback:** Switching embedding models at runtime would produce query vectors with mismatched dimensions (384 vs 1024). Qdrant rejects dimension mismatches at the query level — there is no graceful degradation path. A dual-collection architecture was evaluated and rejected due to the complexity of maintaining parallel indices and merging results across incompatible vector spaces.

### In-Memory BM25S with Qdrant Sparse Vector Migration Path

Lexical search uses BM25S loaded into application memory at startup. This provides a zero-dependency, self-contained hybrid retrieval pipeline that works without external tokenizer services.

**Trade-off:** The BM25S vocabulary scales linearly with corpus size — **O(N)** memory at startup. For production-scale deployments managing large document collections, the migration path is routing sparse token weights natively into Qdrant’s [named sparse vectors](https://qdrant.tech/documentation/concepts/vectors/#named-vectors), shifting token indexing from application memory to the database engine for **O(1)** startup overhead and horizontal scalability via Qdrant cluster sharding with server-side Reciprocal Rank Fusion.

### Unified Checkpoint-Based Conversation Memory

Both the agent mode (LangGraph ReAct loop) and direct RAG mode share the same SQLite checkpoint store, keyed by `session_id`. This means conversation history is consistent regardless of which query path was used — a user can start with direct RAG for fast answers and switch to agent mode for complex queries without losing context.

The checkpoint store also provides automatic persistence across server restarts via Docker volume mounts (`CHECKPOINT_DB_PATH`), eliminating the need for a separate session management database.

-----

## Tech Stack

|Component      |Technology                                            |
|---------------|------------------------------------------------------|
|LLM            |Claude Sonnet 4.6                                     |
|Embeddings     |Voyage-code-3.5 (1024-dim) / all-MiniLM-L6-v2 fallback|
|Vector store   |Qdrant (local persistent)                             |
|Sparse search  |BM25S (in-memory, built at startup)                   |
|Reranking      |Cohere Rerank v4 (`rerank-v4.0-fast`)                 |
|Fusion         |Reciprocal Rank Fusion (k=60)                         |
|AST parsing    |tree-sitter 0.25.x (Python, JS, TS)                   |
|Agent framework|LangGraph 1.2 + SqliteSaver checkpointing             |
|Backend        |FastAPI + Pydantic v2                                 |
|Frontend       |Next.js 16 + TypeScript                               |
|Web search     |Tavily                                                |
|Evaluation     |DeepEval 4.x, GPT-4o-mini judge                       |
|Observability  |LangSmith                                             |
|Deployment     |Docker Compose                                        |

-----

## Project Structure

```
grimoire/
├── docker-compose.yml           # Two services: backend + frontend
├── .env.example                 # Environment variable template
├── backend/
│   ├── Dockerfile               # Python 3.12 multi-stage build
│   ├── requirements.txt
│   ├── verify_setup.py
│   ├── app/
│   │   ├── main.py              # FastAPI routes + lifespan (eager init)
│   │   ├── config.py            # Pydantic settings with optional key handling
│   │   ├── agent/
│   │   │   ├── orchestrator.py  # LangGraph ReAct agent + SQLite checkpointer
│   │   │   ├── tools.py         # rag_retrieval, web_search, database_query, code_executor
│   │   │   └── prompts.py       # System prompt + RAG context template
│   │   ├── rag/
│   │   │   ├── retriever.py     # Hybrid pipeline: BM25S + dense + RRF + Cohere Rerank
│   │   │   ├── embeddings.py    # Voyage-code-3.5 with local fallback
│   │   │   ├── ingestion.py     # Document loading with AST routing
│   │   │   └── ast_chunker.py   # tree-sitter AST chunking for code files
│   │   └── eval/
│   │       ├── dataset.py       # QA pair generation from ingested docs
│   │       └── evaluate.py      # DeepEval scoring pipeline
│   ├── tests/                   # 83 tests, 75% coverage
│   └── eval_dataset_v2.json     # 20 evaluation questions
└── frontend/
    ├── Dockerfile               # Node 20 multi-stage build
    ├── next.config.ts
    └── src/
        ├── app/                 # Next.js App Router
        ├── components/          # Chat UI, sidebar, modals
        ├── hooks/               # useChat (streaming, retry, sessions)
        └── lib/                 # API client, connection context, toast
```

-----

## Manual Setup (without Docker)

For development or environments where Docker isn’t available.

### Requirements

- Python 3.12+
- Node.js 20+
- `ANTHROPIC_API_KEY` (required — everything else is optional)

### Backend

```bash
cd grimoire/backend

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Verify all dependencies installed correctly
python verify_setup.py

cp ../.env.example ../.env
# Fill in ANTHROPIC_API_KEY (required) and optional keys

uvicorn app.main:app --reload --port 8000
```

API docs: <http://localhost:8000/docs>

### Frontend

```bash
cd grimoire/frontend
npm install
npm run dev
```

UI: <http://localhost:3000>

-----

## API Reference

The full interactive API explorer is at <http://localhost:8000/docs> (Swagger UI) once the backend is running. Common operations:

### Ingest documents

```bash
# Ingest a file
curl -X POST http://localhost:8000/ingest \
  -F "file=@your_doc.md"

# Ingest raw text
curl -X POST http://localhost:8000/ingest/text \
  -H "Content-Type: application/json" \
  -d '{"content": "Your content here", "source_name": "my_doc.txt"}'
```

### Query

```bash
# Direct RAG (fast, ~4s)
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How does X work?", "session_id": "my-session", "use_agent": false}'

# Agent mode (full tool orchestration, ~15-30s)
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How does X work?", "session_id": "my-session", "use_agent": true}'

# Streaming (Server-Sent Events, used by the frontend)
curl -X POST http://localhost:8000/query/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "How does X work?", "session_id": "my-session"}'
```

-----

## API Keys

Only `ANTHROPIC_API_KEY` is required. Additional keys unlock better retrieval quality:

|Key                |Provider                                                            |Effect if missing                       |
|-------------------|--------------------------------------------------------------------|----------------------------------------|
|`ANTHROPIC_API_KEY`|[console.anthropic.com](https://console.anthropic.com)              |**Required**                            |
|`VOYAGE_API_KEY`   |[dash.voyageai.com](https://dash.voyageai.com) — free 200M tokens   |Falls back to `all-MiniLM-L6-v2` (local)|
|`COHERE_API_KEY`   |[dashboard.cohere.com](https://dashboard.cohere.com) — free 1K/month|Skips reranking, uses RRF order         |
|`TAVILY_API_KEY`   |[app.tavily.com](https://app.tavily.com) — free 1K/month            |Web search tool excluded from agent     |
|`OPENAI_API_KEY`   |[platform.openai.com](https://platform.openai.com)                  |Only needed for DeepEval evaluation     |


> **Note:** Switching embedding providers (Voyage ↔ local) requires wiping the vector store (`DELETE /collections`) and re-ingesting documents, since embedding dimensions differ (1024 vs 384).

-----

## Running Evaluation

```bash
cd backend

# Generate evaluation dataset from ingested docs
python -m app.eval.dataset --output eval_dataset_v2.json --n-questions 20

# Run DeepEval scoring
python -m app.eval.evaluate --dataset eval_dataset_v2.json --output eval_report_v2.json
```

-----

## Running Tests

```bash
cd backend
pytest tests/ -v --cov=app --cov-report=term-missing
```

83 tests, 75% coverage. Tests run without any API keys — all external services are mocked.

-----

## Supported File Types

|Type       |Extensions                             |Chunker                          |
|-----------|---------------------------------------|---------------------------------|
|Code (AST) |`.py` `.js` `.ts` `.jsx` `.tsx`        |tree-sitter (semantic boundaries)|
|Code (text)|`.go` `.rs` `.java` `.cpp` `.c`        |RecursiveCharacterTextSplitter   |
|PDF        |`.pdf`                                 |PyPDFLoader                      |
|Markup     |`.md` `.markdown` `.html` `.htm` `.rst`|RecursiveCharacterTextSplitter   |
|Plain text |`.txt`                                 |RecursiveCharacterTextSplitter   |
|Config     |`.yaml` `.yml` `.json` `.toml`         |RecursiveCharacterTextSplitter   |

-----

## Error Handling

Grimoire returns typed HTTP status codes — no generic 500s for upstream issues:

|HTTP Status              |When                                                                  |
|-------------------------|----------------------------------------------------------------------|
|`404 Not Found`          |No documents ingested yet                                             |
|`409 Conflict`           |Embedding dimension mismatch (switched providers without re-ingesting)|
|`415 Unsupported Media`  |Unsupported file type                                                 |
|`429 Too Many Requests`  |Anthropic, Voyage, or Cohere rate limit hit                           |
|`503 Service Unavailable`|Anthropic temporarily overloaded                                      |
|`502 Bad Gateway`        |Voyage or Cohere returned an unexpected error                         |
|`504 Gateway Timeout`    |Agent exceeded execution time limit                                   |

Corrupted LangGraph checkpoints (from mid-request server crashes) are automatically detected and cleared on the next request — no user action required.

-----

## Future Work

**Agent Capabilities**

- **Self-Corrective Retrieval** — CRAG-style retrieval grader that classifies results as relevant / ambiguous / incorrect and triggers query rewriting or web-search fallback on low confidence scores.
- **Model Context Protocol (MCP)** — Expose Grimoire as a native MCP server so external developer tools (e.g., Claude Desktop, Cursor) can programmatically leverage its hybrid context index.

**Ingestion Scaling**

- **URL Ingestion** — Scrape and extract content dynamically from online reference documentation.
- **Batch Pipeline Ingestion** — Stream real-time file extraction progress for large multi-gigabyte repository ingestion.

**Observability & UI Extension**

- **LangSmith Core Tracing** — Deep trace inspection for granular step execution latency profiling across backend workers.
- **Dynamic Context Chips** — Generate empty-state suggestion cues derived from the structural vocabulary density of ingested knowledge domains.
- **Light Mode** — Complementary high-contrast workspace palette to mirror the primary monochromatic system layout.