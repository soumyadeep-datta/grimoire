#!/usr/bin/env python3
"""Run after pip install to confirm all imports work correctly."""

import sys

CHECKS = [
    ("FastAPI",               "fastapi",                        "FastAPI"),
    ("Pydantic v2",           "pydantic",                       "BaseModel"),
    ("Pydantic Settings",     "pydantic_settings",              "BaseSettings"),
    ("LangChain core",        "langchain_core.documents",       "Document"),
    ("LangChain splitter",    "langchain.text_splitter",        "RecursiveCharacterTextSplitter"),
    ("LangChain Anthropic",   "langchain_anthropic",            "ChatAnthropic"),
    ("LangChain Community",   "langchain_community.embeddings", "HuggingFaceEmbeddings"),
    ("LangChain Chroma",      "langchain_chroma",               "Chroma"),
    ("ChromaDB",              "chromadb",                       "PersistentClient"),
    ("Sentence Transformers", "sentence_transformers",          "SentenceTransformer"),
    ("Tavily",                "tavily",                         "TavilyClient"),
    ("RAGAS",                 "ragas",                          "evaluate"),
    ("HuggingFace Datasets",  "datasets",                       "Dataset"),
    ("RestrictedPython",      "RestrictedPython",               "compile_restricted"),
    ("PyPDF",                 "pypdf",                          "PdfReader"),
    ("Uvicorn",               "uvicorn",                        None),
    ("pytest",                "pytest",                         None),
    ("httpx",                 "httpx",                          "AsyncClient"),
]

print("Grimoire — dependency verification")
print("=" * 50)

all_ok = True
for name, module, attr in CHECKS:
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

print("=" * 50)
if all_ok:
    print("All dependencies OK. Ready to build. ✓")
    sys.exit(0)
else:
    print("Fix failures above before continuing.")
    sys.exit(1)
