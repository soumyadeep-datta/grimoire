"""
Tests for AST-aware code chunking via tree-sitter.

Entirely local — no API keys, no network, no mocking needed.
tree-sitter parses code in-process using compiled C bindings.
"""

from __future__ import annotations

import pytest
from langchain_core.documents import Document

from app.exceptions import IngestionError, UnsupportedFileTypeError


# ── Sample source code strings ─────────────────────────────────────────────────

PYTHON_WITH_CLASS = (
    "import os\n"
    "from pathlib import Path\n"
    "\n"
    "def standalone_function(x: int, y: int) -> int:\n"
    '    """Add two numbers."""\n'
    "    return x + y\n"
    "\n"
    "class MyClass:\n"
    "    def __init__(self, name: str):\n"
    "        self.name = name\n"
    "\n"
    "    def greet(self) -> str:\n"
    "        return f'Hello, {self.name}'\n"
)

PYTHON_SIMPLE = (
    "def add(a, b):\n"
    "    return a + b\n"
)

PYTHON_DECORATOR = (
    "from functools import wraps\n"
    "\n"
    "def my_decorator(func):\n"
    "    @wraps(func)\n"
    "    def wrapper(*args, **kwargs):\n"
    "        return func(*args, **kwargs)\n"
    "    return wrapper\n"
    "\n"
    "@my_decorator\n"
    "def decorated_function(x: int) -> int:\n"
    "    return x * 2\n"
)

SIMPLE_JS = (
    "function add(a, b) {\n"
    "    return a + b;\n"
    "}\n"
    "\n"
    "class Calculator {\n"
    "    constructor(value) {\n"
    "        this.value = value;\n"
    "    }\n"
    "    multiply(x) {\n"
    "        return this.value * x;\n"
    "    }\n"
    "}\n"
)

SIMPLE_TS = (
    "interface User {\n"
    "    name: string;\n"
    "    age: number;\n"
    "}\n"
    "\n"
    "function greet(user: User): string {\n"
    "    return `Hello ${user.name}`;\n"
    "}\n"
)

RUST_CODE = (
    "fn main() {\n"
    '    println!("Hello, Rust!");\n'
    "}\n"
)

IMPORTS_ONLY = "import os\nimport sys\n"

EMPTY_CODE = ""


# ── Python AST tests ───────────────────────────────────────────────────────────

class TestPythonAST:
    def test_returns_list_of_documents(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(PYTHON_WITH_CLASS, "test.py", "test.py")
        assert isinstance(chunks, list)
        assert len(chunks) > 0
        assert all(isinstance(c, Document) for c in chunks)

    def test_extracts_standalone_function(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(PYTHON_WITH_CLASS, "test.py", "test.py")
        contents = [c.page_content for c in chunks]
        assert any("standalone_function" in c for c in contents)

    def test_extracts_class(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(PYTHON_WITH_CLASS, "test.py", "test.py")
        contents = [c.page_content for c in chunks]
        assert any("MyClass" in c for c in contents)

    def test_extracts_methods_with_parent_class_context(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(PYTHON_WITH_CLASS, "test.py", "test.py")
        contents = [c.page_content for c in chunks]
        assert any("in class MyClass" in c for c in contents)

    def test_context_header_includes_source_name(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(PYTHON_WITH_CLASS, "test.py", "mymodule.py")
        assert all("mymodule.py" in c.page_content for c in chunks)

    def test_context_header_includes_imports(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(PYTHON_WITH_CLASS, "test.py", "test.py")
        assert any("import os" in c.page_content for c in chunks)

    def test_function_body_is_complete(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(PYTHON_WITH_CLASS, "test.py", "test.py")
        fn_chunks = [c for c in chunks
                     if "standalone_function" in c.page_content
                     and "# Function:" in c.page_content]
        assert len(fn_chunks) >= 1
        assert any("return x + y" in c.page_content for c in fn_chunks)

    def test_metadata_chunker_is_ast(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(PYTHON_SIMPLE, "test.py", "test.py")
        assert all(c.metadata.get("chunker") == "ast" for c in chunks)

    def test_metadata_source_name_stored(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(PYTHON_SIMPLE, "test.py", "my_module.py")
        assert all(c.metadata["source"] == "my_module.py" for c in chunks)

    def test_metadata_chunk_index_sequential(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(PYTHON_WITH_CLASS, "test.py", "test.py")
        indices = [c.metadata["chunk_index"] for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_metadata_total_chunks_correct(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(PYTHON_WITH_CLASS, "test.py", "test.py")
        n = len(chunks)
        assert all(c.metadata["total_chunks"] == n for c in chunks)

    def test_metadata_file_type_is_py(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(PYTHON_SIMPLE, "test.py", "test.py")
        assert all(c.metadata.get("file_type") == "py" for c in chunks)

    def test_simple_function_produces_chunk(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(PYTHON_SIMPLE, "test.py", "test.py")
        assert len(chunks) >= 1
        assert any("add" in c.page_content for c in chunks)

    def test_decorated_function_extracted(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(PYTHON_DECORATOR, "test.py", "test.py")
        contents = [c.page_content for c in chunks]
        assert any("decorated_function" in c for c in contents)

    def test_empty_source_returns_list(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(EMPTY_CODE, "test.py", "test.py")
        assert isinstance(chunks, list)

    def test_imports_only_returns_fallback(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(IMPORTS_ONLY, "test.py", "test.py")
        assert isinstance(chunks, list)
        # No top-level definitions → falls back to text splitter
        assert all(c.metadata.get("chunker") == "text" for c in chunks)


# ── JavaScript AST tests ───────────────────────────────────────────────────────

class TestJavaScriptAST:
    def test_returns_documents(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(SIMPLE_JS, "test.js", "test.js")
        assert len(chunks) > 0
        assert all(isinstance(c, Document) for c in chunks)

    def test_extracts_function(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(SIMPLE_JS, "test.js", "test.js")
        contents = [c.page_content for c in chunks]
        assert any("add" in c for c in contents)

    def test_extracts_class(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(SIMPLE_JS, "test.js", "test.js")
        contents = [c.page_content for c in chunks]
        assert any("Calculator" in c for c in contents)

    def test_chunker_marked_ast(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(SIMPLE_JS, "test.js", "test.js")
        assert all(c.metadata.get("chunker") == "ast" for c in chunks)


# ── TypeScript AST tests ───────────────────────────────────────────────────────

class TestTypeScriptAST:
    def test_returns_documents(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(SIMPLE_TS, "test.ts", "test.ts")
        assert len(chunks) > 0

    def test_extracts_interface(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(SIMPLE_TS, "test.ts", "test.ts")
        contents = [c.page_content for c in chunks]
        assert any("User" in c for c in contents)

    def test_extracts_function(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(SIMPLE_TS, "test.ts", "test.ts")
        contents = [c.page_content for c in chunks]
        assert any("greet" in c for c in contents)


# ── Fallback tests ─────────────────────────────────────────────────────────────

class TestFallback:
    def test_unsupported_extension_returns_text_chunks(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(RUST_CODE, "test.rs", "test.rs")
        assert isinstance(chunks, list)
        assert len(chunks) > 0
        assert all(c.metadata.get("chunker") == "text" for c in chunks)

    def test_fallback_chunks_have_chunk_index(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(RUST_CODE, "test.rs", "test.rs")
        assert all("chunk_index" in c.metadata for c in chunks)

    def test_fallback_chunks_have_total_chunks(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(RUST_CODE, "test.rs", "test.rs")
        assert all("total_chunks" in c.metadata for c in chunks)

    def test_markdown_uses_fallback(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file("# Title\n\nContent here.", "readme.md", "readme.md")
        assert isinstance(chunks, list)
        assert all(c.metadata.get("chunker") == "text" for c in chunks)


# ── Ingestion routing tests ────────────────────────────────────────────────────

class TestIngestionRouting:
    def test_python_file_uses_ast_chunker(self, tmp_path):
        from app.rag.ingestion import load_document
        py_file = tmp_path / "sample.py"
        py_file.write_text(PYTHON_WITH_CLASS)
        chunks = load_document(str(py_file))
        assert len(chunks) > 0
        assert any(c.metadata.get("chunker") == "ast" for c in chunks)

    def test_js_file_uses_ast_chunker(self, tmp_path):
        from app.rag.ingestion import load_document
        js_file = tmp_path / "app.js"
        js_file.write_text(SIMPLE_JS)
        chunks = load_document(str(js_file))
        assert len(chunks) > 0
        assert any(c.metadata.get("chunker") == "ast" for c in chunks)

    def test_markdown_does_not_use_ast_chunker(self, tmp_path):
        from app.rag.ingestion import load_document
        md_file = tmp_path / "readme.md"
        md_file.write_text("# Title\n\nSome content here.\n" * 5)
        chunks = load_document(str(md_file))
        assert len(chunks) > 0
        assert all(c.metadata.get("chunker") != "ast" for c in chunks)

    def test_txt_file_produces_chunks(self, tmp_path):
        from app.rag.ingestion import load_document
        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("Some plain text content. " * 20)
        chunks = load_document(str(txt_file))
        assert len(chunks) > 0

    def test_unsupported_extension_raises(self, tmp_path):
        from app.rag.ingestion import load_document
        bad_file = tmp_path / "file.xyz"
        bad_file.write_text("content")
        with pytest.raises(UnsupportedFileTypeError):
            load_document(str(bad_file))

    def test_load_text_empty_raises(self):
        from app.rag.ingestion import load_text
        with pytest.raises(IngestionError):
            load_text("   ")

    def test_load_text_produces_chunks(self):
        from app.rag.ingestion import load_text
        chunks = load_text("This is some content. " * 20, source_name="test.txt")
        assert len(chunks) > 0
        assert all(c.metadata["source"] == "test.txt" for c in chunks)

    def test_load_text_chunk_metadata(self):
        from app.rag.ingestion import load_text
        chunks = load_text("word " * 500, source_name="inline.txt")
        indices = [c.metadata["chunk_index"] for c in chunks]
        assert indices == list(range(len(chunks)))
        assert all(c.metadata["total_chunks"] == len(chunks) for c in chunks)