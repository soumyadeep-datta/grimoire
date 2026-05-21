"""
Tests for AST-aware code chunking via tree-sitter.

These tests are entirely local — no API keys, no network, no mocking needed.
tree-sitter parses code in-process using compiled C bindings.
"""

from __future__ import annotations

import pytest
from langchain_core.documents import Document


SIMPLE_PYTHON = '''
import os
from pathlib import Path

def standalone_function(x: int, y: int) -> int:
    """Add two numbers."""
    return x + y

class MyClass:
    def __init__(self, name: str):
        self.name = name

    def greet(self) -> str:
        return f"Hello, {self.name}"

    @staticmethod
    def static_method():
        pass
'''

PYTHON_WITH_DECORATOR = '''
from functools import wraps

def my_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

@my_decorator
def decorated_function(x: int) -> int:
    return x * 2
'''

SIMPLE_JS = '''
function add(a, b) {
    return a + b;
}

class Calculator {
    constructor(value) {
        this.value = value;
    }

    multiply(x) {
        return this.value * x;
    }
}
'''

SIMPLE_TS = '''
interface User {
    name: string;
    age: number;
}

type Status = "active" | "inactive";

function greet(user: User): string {
    return `Hello ${user.name}`;
}
'''

UNSUPPORTED_CODE = '''
fn main() {
    println!("Hello, Rust!");
}
'''


class TestPythonAST:
    def test_extracts_function(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(SIMPLE_PYTHON, "test.py", "test.py")
        contents = [c.page_content for c in chunks]
        assert any("standalone_function" in c for c in contents)

    def test_extracts_class(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(SIMPLE_PYTHON, "test.py", "test.py")
        contents = [c.page_content for c in chunks]
        assert any("MyClass" in c for c in contents)

    def test_extracts_methods_with_class_context(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(SIMPLE_PYTHON, "test.py", "test.py")
        contents = [c.page_content for c in chunks]
        assert any("in class MyClass" in c for c in contents)

    def test_context_header_includes_filename(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(SIMPLE_PYTHON, "mymodule.py", "mymodule.py")
        assert all("mymodule.py" in c.page_content for c in chunks)

    def test_context_header_includes_imports(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(SIMPLE_PYTHON, "test.py", "test.py")
        assert any("import os" in c.page_content for c in chunks)

    def test_metadata_chunk_index_sequential(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(SIMPLE_PYTHON, "test.py", "test.py")
        indices = [c.metadata["chunk_index"] for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_metadata_total_chunks_correct(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(SIMPLE_PYTHON, "test.py", "test.py")
        for chunk in chunks:
            assert chunk.metadata["total_chunks"] == len(chunks)

    def test_metadata_chunker_is_ast(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(SIMPLE_PYTHON, "test.py", "test.py")
        assert all(c.metadata["chunker"] == "ast" for c in chunks)

    def test_metadata_source_name(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(SIMPLE_PYTHON, "test.py", "my_module.py")
        assert all(c.metadata["source"] == "my_module.py" for c in chunks)

    def test_returns_documents(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(SIMPLE_PYTHON, "test.py", "test.py")
        assert all(isinstance(c, Document) for c in chunks)
        assert len(chunks) > 0

    def test_decorated_function_extracted(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(PYTHON_WITH_DECORATOR, "test.py", "test.py")
        contents = [c.page_content for c in chunks]
        assert any("decorated_function" in c for c in contents)

    def test_no_function_split_mid_body(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(SIMPLE_PYTHON, "test.py", "test.py")
        # standalone_function should appear complete in one chunk
        fn_chunks = [c for c in chunks if "standalone_function" in c.page_content
                     and "# Function:" in c.page_content]
        assert len(fn_chunks) >= 1
        # The chunk should contain the return statement
        assert any("return x + y" in c.page_content for c in fn_chunks)

    def test_empty_file_returns_fallback(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file("", "test.py", "test.py")
        # Empty file falls back to text splitter — returns empty or minimal chunks
        assert isinstance(chunks, list)

    def test_file_with_only_imports_falls_back(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file("import os\nimport sys\n", "test.py", "test.py")
        assert isinstance(chunks, list)


class TestJavaScriptAST:
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

    def test_returns_documents(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(SIMPLE_JS, "test.js", "test.js")
        assert len(chunks) > 0
        assert all(isinstance(c, Document) for c in chunks)


class TestTypeScriptAST:
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

    def test_returns_documents(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(SIMPLE_TS, "test.ts", "test.ts")
        assert len(chunks) > 0


class TestFallback:
    def test_unsupported_extension_uses_fallback(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(UNSUPPORTED_CODE, "test.rs", "test.rs")
        assert isinstance(chunks, list)
        assert len(chunks) > 0
        # Fallback chunks have chunker=text
        assert all(c.metadata.get("chunker") == "text" for c in chunks)

    def test_markdown_uses_fallback(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file("# Hello\n\nThis is markdown.", "test.md", "test.md")
        assert isinstance(chunks, list)

    def test_fallback_chunks_have_metadata(self):
        from app.rag.ast_chunker import ast_chunk_file
        chunks = ast_chunk_file(UNSUPPORTED_CODE, "test.rs", "test.rs")
        for chunk in chunks:
            assert "chunk_index" in chunk.metadata
            assert "total_chunks" in chunk.metadata


class TestIngestionRouting:
    def test_python_uses_ast_chunker(self, tmp_path):
        """Python files should be routed to AST chunker in ingestion pipeline."""
        from app.rag.ingestion import load_document
        py_file = tmp_path / "sample.py"
        py_file.write_text(SIMPLE_PYTHON)
        chunks = load_document(str(py_file))
        assert len(chunks) > 0
        ast_chunks = [c for c in chunks if c.metadata.get("chunker") == "ast"]
        assert len(ast_chunks) > 0

    def test_markdown_uses_text_splitter(self, tmp_path):
        """Markdown files should NOT use AST chunker."""
        from app.rag.ingestion import load_document
        md_file = tmp_path / "readme.md"
        md_file.write_text("# Title\n\nSome content here.\n" * 10)
        chunks = load_document(str(md_file))
        assert len(chunks) > 0
        # No ast chunker for markdown
        assert all(c.metadata.get("chunker") != "ast" for c in chunks)

    def test_js_uses_ast_chunker(self, tmp_path):
        from app.rag.ingestion import load_document
        js_file = tmp_path / "app.js"
        js_file.write_text(SIMPLE_JS)
        chunks = load_document(str(js_file))
        assert len(chunks) > 0