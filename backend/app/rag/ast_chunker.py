"""
AST-aware code chunking via tree-sitter.

Replaces naive character-based splitting for code files. Instead of splitting
at arbitrary character boundaries (which cuts functions in half), this module
parses source files into a concrete syntax tree and extracts complete semantic
units — functions, classes, methods — as individual chunks.

Each chunk includes contextual metadata (parent class, file path, imports)
prepended before the content, following the Contextual Retrieval pattern
(Anthropic, 2024) which reduces retrieval failures by 35%.

Supported languages:
    .py  — Python  (function_definition, class_definition, decorated_definition)
    .js  — JavaScript  (function_declaration, class_declaration, method_definition)
    .ts  — TypeScript  (same as JS + interface_declaration, type_alias_declaration)
    .tsx — TypeScript/JSX

For unsupported languages, falls back to RecursiveCharacterTextSplitter.

Reference: cAST paper (arXiv 2506.15655) — +4.3 Recall@5 on RepoEval vs naive splitting.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Generator

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import get_settings

logger = logging.getLogger(__name__)

# Node types to extract as top-level chunks per language
_PYTHON_CHUNK_TYPES = {
    "function_definition",
    "class_definition",
    "decorated_definition",  # @decorator + def/class
}

_JS_CHUNK_TYPES = {
    "function_declaration",
    "function_expression",
    "arrow_function",
    "class_declaration",
    "class_expression",
    "method_definition",
    "lexical_declaration",   # const fn = () => {}
}

_TS_CHUNK_TYPES = _JS_CHUNK_TYPES | {
    "interface_declaration",
    "type_alias_declaration",
    "abstract_class_declaration",
}

_EXTENSION_TO_TYPES: dict[str, set[str]] = {
    ".py": _PYTHON_CHUNK_TYPES,
    ".js": _JS_CHUNK_TYPES,
    ".jsx": _JS_CHUNK_TYPES,
    ".ts": _TS_CHUNK_TYPES,
    ".tsx": _TS_CHUNK_TYPES,
}


def _get_parser(ext: str):
    """
    Return a (parser, chunk_types) tuple for the given file extension.
    Returns (None, None) for unsupported extensions.
    """
    from tree_sitter import Language, Parser

    try:
        if ext == ".py":
            import tree_sitter_python as tsp
            lang = Language(tsp.language())
        elif ext in {".js", ".jsx"}:
            import tree_sitter_javascript as tsj
            lang = Language(tsj.language())
        elif ext in {".ts", ".tsx"}:
            import tree_sitter_typescript as tst
            # TypeScript grammar has separate language() for tsx
            lang = Language(tst.language_tsx() if ext == ".tsx" else tst.language_typescript())
        else:
            return None, None

        parser = Parser(lang)
        return parser, _EXTENSION_TO_TYPES[ext]

    except Exception as exc:
        logger.warning("Could not load tree-sitter parser for %s: %s", ext, exc)
        return None, None


def _extract_imports(source: bytes, root_node) -> str:
    """Extract import statements from the root node for context prepending."""
    imports = []
    for child in root_node.children:
        if child.type in {"import_statement", "import_from_statement",
                          "import_declaration", "lexical_declaration"}:
            text = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
            imports.append(text)
        if len(imports) >= 5:  # cap at 5 imports for context
            break
    return "\n".join(imports)


def _get_node_name(node, source: bytes) -> str:
    """Extract the name of a function or class node."""
    name_node = node.child_by_field_name("name")
    if name_node:
        return source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
    return "anonymous"


def _walk_chunks(
    node,
    source: bytes,
    chunk_types: set[str],
    parent_class: str = "",
) -> Generator[tuple[str, str], None, None]:
    """
    Walk the AST and yield (context_prefix, chunk_text) pairs.

    Extracts complete semantic units at the top level and within class bodies.
    Does not recurse into function bodies to avoid nested function explosion.
    """
    for child in node.children:
        if child.type in chunk_types:
            name = _get_node_name(child, source)
            text = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")

            # Build context prefix — what is this chunk?
            if parent_class:
                context = f"# Method: {name} (in class {parent_class})"
            elif child.type == "class_definition":
                context = f"# Class: {name}"
            elif child.type == "decorated_definition":
                context = f"# Decorated definition: {name}"
            else:
                context = f"# Function: {name}"

            yield context, text

            # Recurse into class bodies to extract methods
            if child.type in {"class_definition", "class_declaration",
                               "abstract_class_declaration"}:
                body = child.child_by_field_name("body")
                if body:
                    yield from _walk_chunks(body, source, chunk_types, parent_class=name)

        elif child.type == "decorated_definition":
            # Handle @decorator + def/class in Python
            yield from _walk_chunks(child, source, chunk_types, parent_class)


def ast_chunk_file(
    source_code: str,
    file_path: str,
    source_name: str = "unknown",
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> list[Document]:
    """
    Parse source code with tree-sitter and extract semantic chunks.

    Each chunk is a complete syntactic unit (function/class/method) with
    a contextual prefix prepended — following Anthropic's Contextual Retrieval
    pattern for improved retrieval recall.

    Falls back to RecursiveCharacterTextSplitter for unsupported extensions
    or parse failures.

    Args:
        source_code: Raw source code string.
        file_path:   File path used to determine language.
        source_name: Source identifier stored in chunk metadata.
        chunk_size:  Max characters per chunk (for oversized nodes).
        chunk_overlap: Overlap for fallback splitter.

    Returns:
        List of Document objects with enriched metadata.
    """
    ext = Path(file_path).suffix.lower()
    parser, chunk_types = _get_parser(ext)

    if parser is None:
        # Fallback for unsupported languages
        logger.debug("No AST parser for %s — falling back to text splitter", ext)
        return _fallback_split(source_code, source_name, chunk_size, chunk_overlap)

    source_bytes = source_code.encode("utf-8")

    try:
        tree = parser.parse(source_bytes)
    except Exception as exc:
        logger.warning("tree-sitter parse failed for %s: %s — falling back", file_path, exc)
        return _fallback_split(source_code, source_name, chunk_size, chunk_overlap)

    root = tree.root_node

    # Extract top-level imports for context
    imports_context = _extract_imports(source_bytes, root)

    chunks: list[Document] = []

    # Check for parse errors — if >20% of nodes are errors, fall back
    error_count = sum(1 for child in root.children if child.is_error)
    if error_count > len(root.children) * 0.2:
        logger.warning("High parse error rate for %s — falling back to text splitter", file_path)
        return _fallback_split(source_code, source_name, chunk_size, chunk_overlap)

    for context_prefix, chunk_text in _walk_chunks(root, source_bytes, chunk_types):
        # Prepend context: imports + what this chunk is
        header_parts = []
        if imports_context:
            header_parts.append(f"# File: {source_name}\n{imports_context}")
        header_parts.append(context_prefix)
        full_content = "\n".join(header_parts) + "\n\n" + chunk_text

        # If a single node exceeds chunk_size, split it further
        if len(full_content) > chunk_size * 2:
            sub_chunks = _fallback_split(
                full_content, source_name, chunk_size, chunk_overlap
            )
            chunks.extend(sub_chunks)
        else:
            chunks.append(Document(
                page_content=full_content,
                metadata={"source": source_name, "file_type": ext.lstrip(".")},
            ))

    if not chunks:
        # File had no extractable top-level definitions — fall back
        logger.debug("No AST chunks extracted from %s — falling back", file_path)
        return _fallback_split(source_code, source_name, chunk_size, chunk_overlap)

    # Add chunk_index and total_chunks metadata
    for i, chunk in enumerate(chunks):
        chunk.metadata.update({
            "chunk_index": i,
            "total_chunks": len(chunks),
            "chunker": "ast",
        })

    logger.info(
        "AST chunked %s | %d chunks | language=%s",
        source_name, len(chunks), ext.lstrip(".")
    )
    return chunks


def _fallback_split(
    text: str,
    source_name: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Document]:
    """Fallback to RecursiveCharacterTextSplitter for unsupported/error cases."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        add_start_index=True,
    )
    doc = Document(
        page_content=text,
        metadata={"source": source_name, "chunker": "text"},
    )
    chunks = splitter.split_documents([doc])
    for i, chunk in enumerate(chunks):
        chunk.metadata.update({
            "chunk_index": i,
            "total_chunks": len(chunks),
        })
    return chunks
