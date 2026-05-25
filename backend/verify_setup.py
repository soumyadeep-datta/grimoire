#!/usr/bin/env python3
"""
Run after pip install to confirm all dependencies are correctly installed.

Usage:
    python verify_setup.py
"""

import sys

# (name, module, attribute_to_check)
REQUIRED = [
    ("FastAPI",               "fastapi",                         "FastAPI"),
    ("Pydantic v2",           "pydantic",                        "BaseModel"),
    ("Pydantic Settings",     "pydantic_settings",               "BaseSettings"),
    ("LangChain Core",        "langchain_core.documents",        "Document"),
    ("LangChain Text Split",  "langchain_text_splitters",        "RecursiveCharacterTextSplitter"),
    ("LangChain Anthropic",   "langchain_anthropic",             "ChatAnthropic"),
    ("LangChain Community",   "langchain_community.document_loaders", "TextLoader"),
    ("LangGraph",             "langgraph.prebuilt",              "create_react_agent"),
    ("LangGraph SQLite",      "langgraph.checkpoint.sqlite",     "SqliteSaver"),
    ("LangGraph Async SQLite","aiosqlite",                        None),
    ("Qdrant Client",         "qdrant_client",                   "QdrantClient"),
    ("BM25S",                 "bm25s",                           "BM25"),
    ("Sentence Transformers", "sentence_transformers",           "SentenceTransformer"),
    ("RestrictedPython",      "RestrictedPython",                "compile_restricted"),
    ("PyPDF",                 "pypdf",                           "PdfReader"),
    ("tree-sitter",           "tree_sitter",                     "Language"),
    ("tree-sitter-python",    "tree_sitter_python",              None),
    ("tree-sitter-javascript","tree_sitter_javascript",          None),
    ("tree-sitter-typescript","tree_sitter_typescript",          None),
    ("Uvicorn",               "uvicorn",                         None),
    ("httpx",                 "httpx",                           "AsyncClient"),
    ("pytest",                "pytest",                          None),
    ("numpy",                 "numpy",                           "ndarray"),
]

OPTIONAL = [
    ("Voyage AI",             "voyageai",                        "Client"),
    ("Cohere",                "cohere",                          "ClientV2"),
    ("Tavily",                "tavily",                          "TavilyClient"),
    ("DeepEval",              "deepeval",                        "evaluate"),
    ("OpenAI (eval only)",    "openai",                          None),
]

def check(checks: list, label: str) -> bool:
    print(f"\n{label}")
    print("-" * 50)
    all_ok = True
    for name, module, attr in checks:
        try:
            m = __import__(module, fromlist=[attr] if attr else [])
            if attr:
                getattr(m, attr)
            print(f"  ✓  {name}")
        except ImportError as e:
            print(f"  ✗  {name}: {e}")
            all_ok = False
        except AttributeError as e:
            print(f"  ⚠  {name}: installed but missing attribute — {e}")
            all_ok = False
    return all_ok


print("Grimoire — dependency verification")
print("=" * 50)

required_ok = check(REQUIRED, "Required dependencies")
check(OPTIONAL, "Optional dependencies (missing = degraded mode, not broken)")

print("\n" + "=" * 50)
if required_ok:
    print("✓ All required dependencies OK. Ready to run Grimoire.")
    print("\nOptional keys for full pipeline:")
    print("  VOYAGE_API_KEY  — Voyage-code-3.5 embeddings")
    print("  COHERE_API_KEY  — Cohere Rerank v4")
    print("  TAVILY_API_KEY  — Web search tool")
    sys.exit(0)
else:
    print("✗ Fix required dependency failures above before running.")
    sys.exit(1)