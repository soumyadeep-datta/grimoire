"""
Document ingestion pipeline.

Loads PDFs, markdown, plain text, code files, and HTML.
Splits them into overlapping chunks with enriched metadata.

Chunking strategy:
    Code files (.py, .js, .ts, .jsx, .tsx):
        AST-aware chunking via tree-sitter — extracts complete semantic units
        (functions, classes, methods) rather than character-bounded fragments.
        Each chunk has a contextual header prepended (file, imports, node type).

    Text/markdown/config files:
        RecursiveCharacterTextSplitter with language-aware separators.

    PDF:
        PyPDFLoader → RecursiveCharacterTextSplitter.
"""

from __future__ import annotations

import logging
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
)
from langchain_core.documents import Document

from app.config import get_settings
from app.exceptions import IngestionError, UnsupportedFileTypeError

logger = logging.getLogger(__name__)

# Extensions handled by AST chunker
_AST_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx"}

# Registry: adding a new format is one line
_LOADER_REGISTRY: dict[str, type] = {
    ".pdf": PyPDFLoader,

    # Raw text for RAG — NOT Unstructured (which reorders and strips structure)
    ".md": TextLoader,
    ".markdown": TextLoader,
    ".txt": TextLoader,
    ".html": TextLoader,
    ".htm": TextLoader,

    # Code & config files
    ".py": TextLoader,  ".js": TextLoader,  ".ts": TextLoader,
    ".jsx": TextLoader, ".tsx": TextLoader, ".go": TextLoader,
    ".rs": TextLoader,  ".java": TextLoader, ".cpp": TextLoader,
    ".c": TextLoader,   ".yaml": TextLoader, ".yml": TextLoader,
    ".json": TextLoader, ".toml": TextLoader, ".rst": TextLoader,
}

# Code files split on language boundaries before whitespace
_CODE_SEPARATORS = ["\nclass ", "\ndef ", "\n\n", "\n", " ", ""]
_CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".go", ".rs", ".java", ".cpp", ".c"
}


def _build_splitter(ext: str) -> RecursiveCharacterTextSplitter:
    s = get_settings()
    kwargs = dict(
        chunk_size=s.chunk_size,
        chunk_overlap=s.chunk_overlap,
        length_function=len,
        add_start_index=True,
    )
    if ext in _CODE_EXTENSIONS:
        kwargs["separators"] = _CODE_SEPARATORS
    return RecursiveCharacterTextSplitter(**kwargs)


def _load_as_text(path: Path) -> list[Document]:
    """Load a file as raw text, handling encoding gracefully."""
    loader = TextLoader(str(path), encoding="utf-8", autodetect_encoding=True)
    return loader.load()


def load_document(file_path: str | Path) -> list[Document]:
    """
    Load and chunk a document file.

    Code files use AST-aware chunking via tree-sitter.
    All other supported formats use RecursiveCharacterTextSplitter.
    """
    path = Path(file_path).resolve()
    ext = path.suffix.lower()

    if ext not in _LOADER_REGISTRY:
        raise UnsupportedFileTypeError(
            f"Extension '{ext}' not supported. Supported: {sorted(_LOADER_REGISTRY.keys())}"
        )

    logger.info("Loading %s | ext=%s | chunker=%s",
                path.name, ext, "ast" if ext in _AST_EXTENSIONS else "text")

    try:
        raw_docs = _load_as_text(path) if _LOADER_REGISTRY[ext] is TextLoader else \
                   _LOADER_REGISTRY[ext](str(path)).load()
    except Exception as exc:
        raise IngestionError(f"Failed to load '{path.name}': {exc}") from exc

    if not raw_docs:
        return []

    # Route to AST chunker for code files
    if ext in _AST_EXTENSIONS:
        from app.rag.ast_chunker import ast_chunk_file
        s = get_settings()
        source_code = "\n".join(doc.page_content for doc in raw_docs)
        chunks = ast_chunk_file(
            source_code=source_code,
            file_path=str(path),
            source_name=path.name,
            chunk_size=s.chunk_size,
            chunk_overlap=s.chunk_overlap,
        )
    else:
        chunks = _build_splitter(ext).split_documents(raw_docs)
        for i, chunk in enumerate(chunks):
            chunk.metadata.update({
                "source": path.name,
                "source_path": str(path),
                "file_type": ext.lstrip("."),
                "chunk_index": i,
                "total_chunks": len(chunks),
            })

    logger.info("Produced %d chunks from %s | chunker=%s",
                len(chunks), path.name, "ast" if ext in _AST_EXTENSIONS else "text")
    return chunks


def load_text(text: str, source_name: str = "inline") -> list[Document]:
    """Ingest raw text content — always uses text splitter."""
    if not text.strip():
        raise IngestionError("Cannot ingest empty text.")

    s = get_settings()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=s.chunk_size,
        chunk_overlap=s.chunk_overlap,
        add_start_index=True,
    )

    doc = Document(
        page_content=text,
        metadata={"source": source_name, "file_type": "text"},
    )

    chunks = splitter.split_documents([doc])

    for i, chunk in enumerate(chunks):
        chunk.metadata.update({
            "chunk_index": i,
            "total_chunks": len(chunks),
        })

    return chunks
