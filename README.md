# Grimoire — Agentic Developer Knowledge Assistant

> A production-grade RAG system for querying developer documentation and codebases. Combines hybrid retrieval, LangGraph-orchestrated agents, and evaluated answer generation — deployable with a single API key.

---

## Evaluation Results

Evaluated on 20 questions using DeepEval with GPT-4o-mini as judge, Claude Sonnet 4.6 for generation.

| Metric | Score |
|---|---|
| Faithfulness | **0.9143** |
| Contextual Recall | **0.8794** |
| Answer Relevancy | **0.9126** |
| Contextual Precision | **0.9377** |

Reproduce: `python -m app.eval.evaluate --dataset eval_dataset_v2.json --output eval_report_v2.json`

---

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

**AST-aware chunking:** Code files (`.py`, `.js`, `.ts`) are parsed via tree-sitter and split at semantic boundaries — functions, classes, methods — rather than arbitrary character limits. Each chunk includes a contextual header (file name, imports, parent class) following Anthropic's Contextual Retrieval pattern.

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

---

## Quick Start

### Requirements
- Python 3.12+
- `ANTHROPIC_API_KEY` (required — everything else is optional)

### Setup

```bash
git clone https://github.com/your-username/grimoire.git
cd grimoire/backend

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Fill in ANTHROPIC_API_KEY (required) and optional keys
```

### Run

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

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
```

---

## API Keys

Only `ANTHROPIC_API_KEY` is required. Additional keys unlock better retrieval quality:

| Key | Provider | Effect if missing |
|---|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) | **Required** |
| `VOYAGE_API_KEY` | [dash.voyageai.com](https://dash.voyageai.com) — free 200M tokens | Falls back to `all-MiniLM-L6-v2` (local) |
| `COHERE_API_KEY` | [dashboard.cohere.com](https://dashboard.cohere.com) — free 1K/month | Skips reranking, uses RRF order |
| `TAVILY_API_KEY` | [app.tavily.com](https://app.tavily.com) — free 1K/month | Web search tool excluded from agent |
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com) | Only needed for DeepEval evaluation |

> **Note:** Switching embedding providers (Voyage ↔ local) requires wiping the vector store (`DELETE /collections`) and re-ingesting documents, since embedding dimensions differ (1024 vs 384).

---

## Project Structure

```
grimoire/
├── backend/
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
│   ├── data/docs/               # Sample documents
│   ├── eval_dataset_v2.json     # 20 evaluation questions
│   ├── eval_report_v2.json      # Evaluation results
│   └── .env.example             # Environment variable template
└── README.md
```

---

## Tech Stack

| Component | Technology |
|---|---|
| LLM | Claude Sonnet 4.6 |
| Embeddings | Voyage-code-3.5 (1024-dim) / all-MiniLM-L6-v2 fallback |
| Vector store | Qdrant (local persistent) |
| Sparse search | BM25S (in-memory, built at startup) |
| Reranking | Cohere Rerank v4 (`rerank-v4.0-fast`) |
| Fusion | Reciprocal Rank Fusion (k=60) |
| AST parsing | tree-sitter 0.25.x (Python, JS, TS) |
| Agent framework | LangGraph 1.2 + SqliteSaver checkpointing |
| Backend | FastAPI + Pydantic v2 |
| Web search | Tavily |
| Evaluation | DeepEval 4.x, GPT-4o-mini judge |
| Observability | LangSmith |

---

## Running Evaluation

```bash
# Generate evaluation dataset from ingested docs
python -m app.eval.dataset --output eval_dataset_v2.json --n-questions 20

# Run DeepEval scoring
python -m app.eval.evaluate --dataset eval_dataset_v2.json --output eval_report_v2.json
```

---

## Running Tests

```bash
cd backend
pytest tests/ -v --cov=app --cov-report=term-missing
```

83 tests, 75% coverage. Tests run without any API keys — all external services are mocked.

---

## Supported File Types

| Type | Extensions | Chunker |
|---|---|---|
| Code | `.py` `.js` `.ts` `.jsx` `.tsx` | AST (tree-sitter) |
| PDF | `.pdf` | PyPDFLoader |
| Text | `.md` `.txt` `.html` `.rst` | RecursiveCharacterTextSplitter |
| Config | `.yaml` `.json` `.toml` | RecursiveCharacterTextSplitter |
| More | `.go` `.rs` `.java` `.cpp` `.c` | RecursiveCharacterTextSplitter |