# Grimoire — Agentic Developer Knowledge Assistant

> A production-grade RAG + multi-agent system that lets developers query their own documentation, codebases, and reference materials using autonomous agents that plan, retrieve, reason, and respond with citations.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         React Frontend                               │
│   ChatWindow · ToolTrace · CitationCard · FeedbackButtons           │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ HTTP (REST)
┌──────────────────────────────▼──────────────────────────────────────┐
│                       FastAPI Backend                                │
│  POST /query   POST /ingest   GET /history   GET /health            │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                    LangChain ReAct Agent                             │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────┐  │
│  │ Tool 1: RAG  │  │Tool 2: Web   │  │Tool 3: SQLite│  │Tool 4: │  │
│  │ ChromaDB     │  │Search Tavily │  │NL→SQL Query  │  │Python  │  │
│  │ Retrieval    │  │              │  │              │  │Executor│  │
│  └──────────────┘  └──────────────┘  └──────────────┘  └────────┘  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│               RAG Pipeline                                           │
│  Ingest → Chunk → Embed (all-MiniLM-L6-v2) → ChromaDB              │
│  Query → Embed → Cosine Similarity → Top-K → Context Injection      │
└─────────────────────────────────────────────────────────────────────┘
                  │                           │
       ┌──────────▼──────────┐    ┌───────────▼──────────┐
       │  ChromaDB (local)   │    │  Claude Sonnet 4 API  │
       │  Persistent vectors │    │  LangSmith Tracing    │
       └─────────────────────┘    └──────────────────────┘
```

## RAGAS Evaluation Scores

| Metric              | Score  |
|---------------------|--------|
| Context Precision   | TBD    |
| Context Recall      | TBD    |
| Faithfulness        | TBD    |
| Answer Relevancy    | TBD    |

*(Updated after MVP evaluation run — see `backend/app/eval/` for dataset and scripts)*

## Quick Start

```bash
cp .env.example .env
# Fill in API keys

docker-compose up --build
# Frontend: http://localhost:3000
# Backend:  http://localhost:8000
# API docs: http://localhost:8000/docs
```

## Manual Setup (Development)

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install && npm run dev
```

## Features

- **Domain-agnostic RAG** — ingest any PDFs, markdown, code files, or URLs
- **ReAct multi-agent** — agent plans and chains tool calls autonomously
- **Tool transparency** — UI shows every tool the agent invoked and why
- **Source citations** — every answer links back to exact document chunks
- **Conversation memory** — 10-turn sliding window context
- **RAGAS evaluation** — quantified retrieval quality with reproducible scores
- **LangSmith tracing** — full agent decision traces, latency, token usage
- **Docker deployment** — single `docker-compose up` to run everything

## Project Structure

```
grimoire/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI routes
│   │   ├── config.py        # Pydantic settings
│   │   ├── agent/           # ReAct orchestrator + tools
│   │   ├── rag/             # Ingestion, embeddings, retrieval
│   │   ├── memory/          # Conversation buffer
│   │   └── eval/            # RAGAS pipeline
│   ├── tests/               # pytest suite
│   └── data/docs/           # Sample docs for testing
├── frontend/src/
│   ├── components/          # Chat UI, tool traces, citations
│   └── api/                 # API client
└── docker-compose.yml
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM | Claude Sonnet 4 (`claude-sonnet-4-20250514`) |
| Embeddings | `all-MiniLM-L6-v2` (local, HuggingFace) |
| Vector DB | ChromaDB (persistent local storage) |
| Agent Framework | LangChain + LangGraph |
| Backend | FastAPI + Pydantic v2 |
| Frontend | React 18 + Tailwind CSS |
| Web Search | Tavily API |
| Evaluation | RAGAS |
| Observability | LangSmith |
| Infrastructure | Docker, docker-compose |
