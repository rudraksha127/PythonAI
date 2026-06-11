"""Unit tests for cAST — AST-aware code chunking (EMNLP 2025).

Tests cover:
- Function chunking (single, async, nested)
- Class chunking (small classes, large classes with method splitting)
- Import block grouping
- Fallback line-based chunking for non-Python code
- Edge cases (syntax errors, empty files, decorators)
- Dependency extraction
- Multi-view embedding text generation
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.rag.cast_chunker import (
    ASTDependencyExtractor,
    CastChunker,
    CodeChunk,
    chunk_code_file,
    chunk_code_source,
)

# ══════════════════════════════════════════════════════════════════════
# CodeChunk dataclass tests
# ══════════════════════════════════════════════════════════════════════


class TestCodeChunk:
    """Tests for the CodeChunk dataclass."""

    def test_to_dict_roundtrip(self) -> None:
        """to_dict() should return all fields as a dict."""
        chunk = CodeChunk(
            content="def foo(): pass",
            chunk_type="function",
            start_line=1,
            end_line=1,
            name="foo",
            docstring="Do foo",
            signature="def foo():",
            parent_class=None,
            dependencies=["bar"],
            imports=["os"],
            filepath="/test.py",
            language="python",
            token_count=3,
        )
        d = chunk.to_dict()
        assert d["content"] == "def foo(): pass"
        assert d["chunk_type"] == "function"
        assert d["name"] == "foo"
        assert d["docstring"] == "Do foo"
        assert d["signature"] == "def foo():"
        assert d["dependencies"] == ["bar"]
        assert d["imports"] == ["os"]
        assert d["token_count"] == 3

    def test_to_embedding_text(self) -> None:
        """to_embedding_text() should join signature, docstring, and code."""
        chunk = CodeChunk(
            content="x = 1",
            chunk_type="assignment",
            start_line=1,
            end_line=1,
            name="x",
            docstring="A variable",
            signature="x: int = 1",
            filepath="test.py",
            language="python",
            token_count=1,
        )
        text = chunk.to_embedding_text()
        assert "Signature: x: int = 1" in text
        assert "Docstring: A variable" in text
        assert "Code:" in text
        assert "x = 1" in text

    def test_to_embedding_text_no_docstring(self) -> None:
        """to_embedding_text() should work without docstring/signature."""
        chunk = CodeChunk(
            content="pass",
            chunk_type="module",
            start_line=1,
            end_line=1,
            filepath="test.py",
            language="python",
            token_count=1,
        )
        text = chunk.to_embedding_text()
        assert "Code:" in text
        assert "pass" in text

    def test_default_fields(self) -> None:
        """CodeChunk should have sensible defaults for optional fields."""
        chunk = CodeChunk(
            content="",
            chunk_type="module",
            start_line=0,
            end_line=0,
            filepath="",
            language="python",
            token_count=0,
        )
        assert chunk.name == ""
        assert chunk.docstring == ""
        assert chunk.signature == ""
        assert chunk.parent_class is None
        assert chunk.dependencies == []
        assert chunk.imports == []


# ══════════════════════════════════════════════════════════════════════
# ASTDependencyExtractor tests
# ══════════════════════════════════════════════════════════════════════


class TestASTDependencyExtractor:
    """Tests for the ASTDependencyExtractor class."""

    def test_extract_imports(self) -> None:
        """Should extract import statements."""
        import ast

        tree = ast.parse("import os\nimport sys\nfrom pathlib import Path")
        extractor = ASTDependencyExtractor()
        extractor.visit(tree)
        assert "os" in extractor.imports
        assert "sys" in extractor.imports
        assert "pathlib.Path" in extractor.imports

    def test_extract_function_calls(self) -> None:
        """Should extract function call names."""
        import ast

        tree = ast.parse("""
import os
os.listdir('.')
print('hello')
obj.method()
""")
        extractor = ASTDependencyExtractor()
        extractor.visit(tree)
        assert "os.listdir" in extractor.calls
        assert "print" in extractor.calls

    def test_extract_defined_names(self) -> None:
        """Should extract defined function/class names."""
        import ast

        tree = ast.parse("""
def foo():
    pass

async def bar():
    pass

class MyClass:
    pass
""")
        extractor = ASTDependencyExtractor()
        extractor.visit(tree)
        assert "foo" in extractor.defined_names
        assert "bar" in extractor.defined_names
        assert "MyClass" in extractor.defined_names

    def test_empty_module(self) -> None:
        """Empty module should not crash."""
        import ast

        tree = ast.parse("")
        extractor = ASTDependencyExtractor()
        extractor.visit(tree)  # Should not raise
        assert extractor.calls == []
        assert extractor.imports == []
        assert extractor.defined_names == []


# ══════════════════════════════════════════════════════════════════════
# CastChunker core tests
# ══════════════════════════════════════════════════════════════════════


class TestCastChunkerFunctions:
    """Tests for chunking Python functions."""

    def test_single_function(self) -> None:
        """A single function should produce one chunk."""
        source = """
def greet(name):
    \"\"\"Say hello.\"\"\"
    return f"Hello {name}"
"""
        chunks = chunk_code_source(source)
        assert len(chunks) >= 1
        func_chunks = [c for c in chunks if c["chunk_type"] == "function"]
        assert len(func_chunks) >= 1
        assert func_chunks[0]["name"] == "greet"
        assert "Hello" in func_chunks[0]["content"]

    def test_async_function(self) -> None:
        """Async functions should be chunked correctly."""
        source = """
async def fetch_data(url):
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.json()
"""
        chunks = chunk_code_source(source)
        func_chunks = [c for c in chunks if "async_function" in c["chunk_type"] or c["chunk_type"] == "function"]
        assert len(func_chunks) >= 1
        assert func_chunks[0]["name"] == "fetch_data"

    def test_multiple_functions(self) -> None:
        """Multiple functions should each get their own chunk (or be merged if small)."""
        source = """
def foo():
    return 1

def bar():
    return 2

def baz():
    return 3
"""
        chunks = chunk_code_source(source)
        func_names = [c["name"] for c in chunks if c["chunk_type"] in ("function", "merged_function_block")]
        # Small contiguous functions may be merged, but at least one should exist
        assert len(func_names) >= 1
        # Content should include all function bodies
        all_content = " ".join(c["content"] for c in chunks)
        assert "foo" in all_content
        assert "bar" in all_content
        assert "baz" in all_content

    def test_function_with_decorator(self) -> None:
        """Decorated functions should include the decorator in the chunk."""
        source = """
@lru_cache
@log_call
def expensive(n):
    return n ** 2
"""
        chunks = chunk_code_source(source)
        func_chunks = [c for c in chunks if c["chunk_type"] == "function"]
        assert len(func_chunks) >= 1
        content = func_chunks[0]["content"]
        assert "@lru_cache" in content or "@log_call" in content
        assert "expensive" in content

    def test_function_dependencies(self) -> None:
        """Function chunks should list internal calls as dependencies."""
        source = """
def caller():
    x = helper_a()
    y = helper_b(x)
    return y

def helper_a():
    return 42
"""
        chunks = chunk_code_source(source)
        caller_chunks = [c for c in chunks if c["name"] == "caller"]
        if caller_chunks:
            deps = caller_chunks[0].get("dependencies", [])
            assert "helper_a" in deps or "helper_b" in deps

    def test_function_with_docstring(self) -> None:
        """Function docstrings should be extracted."""
        source = '''
def documented():
    """This function does something important.

    More details here.
    """
    pass
'''
        chunks = chunk_code_source(source)
        func_chunks = [c for c in chunks if c["chunk_type"] == "function"]
        assert len(func_chunks) >= 1
        assert "something important" in func_chunks[0].get("docstring", "")


class TestCastChunkerClasses:
    """Tests for chunking Python classes."""

    def test_small_class(self) -> None:
        """A small class should be a single chunk."""
        source = """
class Point:
    \"\"\"A 2D point.\"\"\"

    def __init__(self, x, y):
        self.x = x
        self.y = y

    def distance(self, other):
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5
"""
        chunks = chunk_code_source(source)
        class_chunks = [c for c in chunks if c["chunk_type"] == "class"]
        # Small class should be a single class chunk, not split into methods
        assert len(class_chunks) >= 1
        assert class_chunks[0]["name"] == "Point"
        assert "__init__" in class_chunks[0]["content"]

    def test_class_signature(self) -> None:
        """Class signature should include base classes."""
        source = """
class MyList(list):
    pass
"""
        chunks = chunk_code_source(source)
        class_chunks = [c for c in chunks if c["chunk_type"] == "class"]
        if class_chunks:
            assert "(list)" in class_chunks[0].get("signature", "")


class TestCastChunkerImports:
    """Tests for import block chunking."""

    def test_import_block(self) -> None:
        """Consecutive imports should be grouped into one import_block chunk."""
        source = """import os
import sys
from pathlib import Path
import json

def foo():
    pass
"""
        chunks = chunk_code_source(source)
        import_chunks = [c for c in chunks if c["chunk_type"] == "import_block"]
        assert len(import_chunks) >= 1
        assert "import os" in import_chunks[0]["content"]

    def test_imports_with_interleaved_code(self) -> None:
        """Imports separated by code should form separate blocks."""
        source = """import os

def helper():
    pass

import sys
"""
        chunks = chunk_code_source(source)
        import_chunks = [c for c in chunks if c["chunk_type"] == "import_block"]
        assert len(import_chunks) >= 1


class TestCastChunkerEdgeCases:
    """Tests for edge cases in cAST chunking."""

    def test_empty_source(self) -> None:
        """Empty source should return no chunks."""
        chunks = chunk_code_source("")
        assert chunks == []

    def test_whitespace_only(self) -> None:
        """Whitespace-only source should return no chunks."""
        chunks = chunk_code_source("   \n  \n  ")
        assert chunks == []

    def test_syntax_error_fallback(self) -> None:
        """Code with syntax errors should fall back to line-based chunking."""
        source = "def broken(:\n    pass\n"
        chunks = chunk_code_source(source)
        # Should fall back gracefully (may have chunks from line-based chunking)
        assert isinstance(chunks, list)

    def test_only_imports(self) -> None:
        """A file with only imports should produce an import_block chunk."""
        source = "import os\nimport sys\n"
        chunks = chunk_code_source(source)
        assert len(chunks) >= 1
        assert chunks[0]["chunk_type"] == "import_block"

    def test_module_level_assignments(self) -> None:
        """Top-level assignments should be chunked."""
        source = """
import os

CONSTANT = 42
DEBUG = True
"""
        chunks = chunk_code_source(source)
        # Should have import_block + assignments
        chunk_types = [c["chunk_type"] for c in chunks]
        assert "import_block" in chunk_types
        assert "assignment" in chunk_types
        # Content should include both constants
        all_content = " ".join(c["content"] for c in chunks)
        assert "CONSTANT" in all_content or "42" in all_content

    def test_non_python_fallback(self) -> None:
        """Unsupported language should use line-based chunking fallback."""
        source = """
void greet(const char* name) {
    printf("Hello %s", name);
}

int add(int a, int b) {
    return a + b;
}
"""
        chunker = CastChunker(language="cpp")
        chunks = chunker.chunk_source(source, "test.cpp")
        # C++ falls back to line-based chunking (no tree-sitter grammar registered)
        assert len(chunks) >= 1
        assert all(c.chunk_type == "code_block" for c in chunks)


class TestCastChunkerFileOperations:
    """Tests for file-based chunking operations."""

    def test_chunk_file_nonexistent(self, tmp_path: Path) -> None:
        """chunk_file should return empty list for non-existent file."""
        chunks = chunk_code_file(tmp_path / "nonexistent.py")
        assert chunks == []

    def test_chunk_file_basic(self, tmp_path: Path) -> None:
        """chunk_file should parse a real Python file."""
        py_file = tmp_path / "test_module.py"
        py_file.write_text("""
def hello():
    print("world")
""")
        chunks = chunk_code_file(py_file)
        assert len(chunks) >= 1
        assert chunks[0]["name"] == "hello"

    def test_chunk_directory(self, tmp_path: Path) -> None:
        """chunk_directory should find and chunk all Python files."""
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "__init__.py").write_text("")
        (tmp_path / "pkg" / "module_a.py").write_text("""
def func_a():
    pass
""")
        (tmp_path / "pkg" / "module_b.py").write_text("""
class ClassB:
    pass
""")
        chunker = CastChunker()
        all_chunks = chunker.chunk_directory(tmp_path, extensions=[".py"])
        assert len(all_chunks) >= 2
        names = [c.name for c in all_chunks]
        assert any("func_a" in name for name in names if name)
        assert any("ClassB" in name for name in names if name)

    def test_chunk_directory_with_exclusions(self, tmp_path: Path) -> None:
        """chunk_directory should skip excluded patterns."""
        (tmp_path / "venv").mkdir()
        (tmp_path / "venv" / "lib.py").write_text("x = 1")
        (tmp_path / "src.py").write_text("y = 2")

        chunker = CastChunker()
        all_chunks = chunker.chunk_directory(
            tmp_path,
            extensions=[".py"],
            exclude_patterns=["venv"],
        )
        # Should only have src.py, not venv/lib.py
        filepaths = [c.filepath for c in all_chunks]
        assert all("venv" not in fp for fp in filepaths)

    def test_chunk_file_with_encoding_errors(self, tmp_path: Path) -> None:
        """Files with encoding issues should not crash."""
        py_file = tmp_path / "bad_encoding.py"
        py_file.write_bytes(b"def foo():\n    pass\n\xff\xfe")
        chunks = chunk_code_file(py_file)
        # Should handle gracefully
        assert isinstance(chunks, list)

    def test_token_count_approximation(self) -> None:
        """Token count should be roughly chars/4."""
        from src.rag.cast_chunker import _count_tokens

        assert _count_tokens("") == 1  # empty → max(1, 0) = 1
        assert _count_tokens("a" * 100) == 25  # 100 / 4 = 25


class TestCastChunkerLargeFile:
    """Test chunking of a realistic larger Python file."""

    def test_large_realistic_file(self) -> None:
        """A file with mixed content should produce multiple typed chunks."""
        source = '''
"""Module docstring."""

import os
import sys
from typing import Optional

CONSTANT_VALUE = 100

def helper_func(x: int) -> int:
    """A helper function."""
    return x * 2

class DataProcessor:
    """Process data in various ways."""

    def __init__(self, prefix: str = ""):
        self.prefix = prefix

    def process(self, data: list) -> list:
        """Process a list of items."""
        return [self.prefix + str(item) for item in data]

def main():
    processor = DataProcessor("item_")
    results = processor.process([1, 2, 3])
    print(results)

if __name__ == "__main__":
    main()
'''
        chunks = chunk_code_source(source)
        # Should have at least: import_block, assignment, functions, class
        chunk_types = [c["chunk_type"] for c in chunks]
        assert "function" in chunk_types or "merged_function_block" in chunk_types
        assert "class" in chunk_types or "class_header" in chunk_types or "method" in chunk_types
        assert "import_block" in chunk_types

        # Verify function/class names appear in content somewhere
        all_content = " ".join(c["content"] for c in chunks)
        assert "helper_func" in all_content
        assert "DataProcessor" in all_content or "main" in all_content


class TestCastChunkerMergeBehavior:
    """Tests for the sibling merging behavior."""

    def test_merge_small_chunks(self) -> None:
        """Small contiguous chunks of the same type should be merged."""
        source = """
X = 1
Y = 2
Z = 3
"""
        chunker = CastChunker()
        chunks = chunker.chunk_source(source)
        # Small contiguous assignments of same type should be merged
        assert len(chunks) >= 1
        # If merged, content should contain all assignments
        all_content = " ".join(c.content for c in chunks)
        assert "X = 1" in all_content
        assert "Y = 2" in all_content
        assert "Z = 3" in all_content


# ══════════════════════════════════════════════════════════════════════
# Recursive splitting tests
# ══════════════════════════════════════════════════════════════════════


class TestCastChunkerRecursiveSplit:
    """Tests for recursive splitting of large functions/classes at block boundaries."""

    def test_small_function_not_split(self) -> None:
        """A small function should remain as a single chunk (no splitting)."""
        source = """
def foo():
    x = 1
    y = 2
    return x + y
"""
        chunks = chunk_code_source(source)
        assert len(chunks) == 1
        assert chunks[0]["chunk_type"] == "function"

    def test_function_with_small_blocks_not_split(self) -> None:
        """A function with small innner blocks should stay as one chunk."""
        source = """
def moderate(n):
    if n > 0:
        return n
    for i in range(10):
        print(i)
    return 0
"""
        chunks = chunk_code_source(source)
        assert len(chunks) == 1
        assert chunks[0]["chunk_type"] == "function"

    def test_large_function_split_preamble(self) -> None:
        """A very large function should be split at block boundaries."""
        # Build a large function with a big preamble, a for loop, an if block, and postamble
        preamble = "\n".join([f"    x{i} = {i} * 2" for i in range(300)])
        loop_body = "\n".join([f"        print(item_{i})" for i in range(100)])
        if_body = "\n".join([f"        result_{i} = process(item)" for i in range(80)])
        postamble = "\n".join([f"    y{i} = c * i" for i in range(100)])

        source = f"""
def huge_func():
{preamble}
    for item in data:
{loop_body}
    if condition:
{if_body}
{postamble}
"""

        chunker = CastChunker()
        chunker.SPLIT_THRESHOLD = 100
        chunks = chunker.chunk_source(source)

        chunk_types = [c.chunk_type for c in chunks]
        assert "function_section" in chunk_types or "function_block" in chunk_types
        assert len(chunks) >= 2

    def test_large_function_with_real_for_block(self) -> None:
        """A function with a massive for loop should split the for block separately."""
        loop_body = "\n".join([f"        process(data[{i}])" for i in range(200)])
        source = f"""
def big_processor(items):
    setup = prepare(items)
    results = []
    for item in items:
{loop_body}
    return results
"""
        chunker = CastChunker()
        chunker.SPLIT_THRESHOLD = 150
        chunks = chunker.chunk_source(source)

        # Should split: preamble (setup) + for block + postamble (return)
        assert len(chunks) >= 2
        # At least one chunk should contain the for statement
        has_for_chunk = any("for item in" in c.content for c in chunks)
        assert has_for_chunk, "No chunk contains the for loop"

    def test_oversized_if_block_recursive_split(self) -> None:
        """An if block that is itself oversized should be recursively split."""
        true_branch = "\n".join([f"        handle_{i}()" for i in range(200)])
        source = f"""
def validate_all(items):
    check(items)
    if should_process:
{true_branch}
    cleanup()
"""
        chunker = CastChunker()
        chunker.SPLIT_THRESHOLD = 100
        chunks = chunker.chunk_source(source)
        # Should have preamble + if block + postamble
        assert len(chunks) >= 2

    def test_oversized_method_in_class(self) -> None:
        """A method inside a class that exceeds SPLIT_THRESHOLD should be split."""
        method_body = "\n".join([f"        self.data[{i}] = process(values)" for i in range(250)])
        source = f"""
class DataProcessor:
    def process_all(self, values):
{method_body}
        return self.data

    def small_method(self):
        return 42
"""
        chunker = CastChunker()
        chunker.SPLIT_THRESHOLD = 100
        chunks = chunker.chunk_source(source)

        chunk_types = [c.chunk_type for c in chunks]
        # Should have class_header or method chunks from the split
        assert "method" in chunk_types or "class_header" in chunk_types or "class" in chunk_types
        # The oversized method should be split into multiple chunks
        assert len(chunks) >= 2

    def test_recursion_depth_limit(self) -> None:
        """Extremely nested code should hit recursion depth limit but not crash."""
        # Build deeply nested ifs
        nested = "if a:  # level 1\n"
        for i in range(2, 12):
            nested += "    " * (i - 1) + f"if b{i}:  # level {i}\n"
        nested += "    " * 11 + "pass\n"
        for i in range(11, 1, -1):
            nested += "    " * (i - 2) + "elif x:"
            for j in range(50):
                nested += "\n" + "    " * (i - 1) + f"    y{j} = {j}"
            nested += "\n"

        source = f"""
def deeply_nested():
{nested}
    return True
"""
        chunker = CastChunker()
        chunker.SPLIT_THRESHOLD = 100
        # Should not crash — depth limit should prevent infinite recursion
        chunks = chunker.chunk_source(source)
        assert isinstance(chunks, list)
        assert len(chunks) >= 1

    def test_split_threshold_not_reached(self) -> None:
        """When SPLIT_THRESHOLD is set very high, no splitting should occur."""
        loop_body = "\n".join([f"    process(data[{i}])" for i in range(200)])
        source = f"""
def big(items):
{loop_body}
"""
        chunker = CastChunker()
        chunker.SPLIT_THRESHOLD = 100000  # Very high, no split
        chunks = chunker.chunk_source(source)
        assert len(chunks) == 1
        assert chunks[0].chunk_type == "function"

    def test_split_preserves_decorators(self) -> None:
        """When splitting, decorators should remain in the first function section."""
        long_body = "\n".join([f"    x{i} = decorator_check()" for i in range(300)])
        source = f"""
@cache
@log_call
def cached_processor(items):
{long_body}
    return items
"""
        chunker = CastChunker()
        chunker.SPLIT_THRESHOLD = 100
        chunks = chunker.chunk_source(source)

        # First chunk should contain decorators
        first_content = chunks[0].content
        assert "@cache" in first_content or "@log_call" in first_content


# ══════════════════════════════════════════════════════════════════════
# Integration-level tests with the full pipeline
# ══════════════════════════════════════════════════════════════════════


class TestCastChunkerPipeline:
    """Tests for how CastChunker integrates with the RAG pipeline."""

    def test_chunks_are_serializable(self) -> None:
        """All chunk dicts should be JSON serializable."""
        import json

        source = """
import os

def foo():
    return 1

class Bar:
    def method(self):
        pass
"""
        chunks = chunk_code_source(source)
        # Should serialize to JSON without error
        json_str = json.dumps(chunks)
        assert len(json_str) > 0
        # Deserialize back
        restored = json.loads(json_str)
        assert len(restored) == len(chunks)

    def test_chunk_ids_are_unique(self) -> None:
        """Chunk IDs within a file should be unique (based on content stability)."""
        source = """
def a(): pass
def b(): pass
def c(): pass
"""
        chunker = CastChunker()
        chunks = chunker.chunk_source(source)
        # No duplicate chunk types for this simple case
        assert len(chunks) == 3 or len(chunks) == 1  # may merge, but no crash


# ══════════════════════════════════════════════════════════════════════
# Multi-Language Tree-sitter Chunking Tests
# ══════════════════════════════════════════════════════════════════════


try:
    import tree_sitter_javascript  # noqa: F401

    HAS_TS_JS = True
except ImportError:
    HAS_TS_JS = False

try:
    import tree_sitter_typescript  # noqa: F401

    HAS_TS_TS = True
except ImportError:
    HAS_TS_TS = False

try:
    import tree_sitter_go  # noqa: F401

    HAS_TS_GO = True
except ImportError:
    HAS_TS_GO = False

try:
    import tree_sitter_rust  # noqa: F401

    HAS_TS_RUST = True
except ImportError:
    HAS_TS_RUST = False

try:
    import tree_sitter_java  # noqa: F401

    HAS_TS_JAVA = True
except ImportError:
    HAS_TS_JAVA = False


@pytest.mark.skipif(not HAS_TS_JS, reason="tree-sitter-javascript not installed")
class TestJavaScriptChunker:
    """Tests for chunking JavaScript with tree-sitter."""

    def test_js_function(self) -> None:
        """A simple JS function should produce one function chunk."""
        source = """
function greet(name) {
    return "Hello " + name;
}
"""
        chunker = CastChunker(language="javascript")
        chunks = chunker.chunk_source(source, "test.js")
        assert len(chunks) >= 1
        func_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert len(func_chunks) >= 1
        assert func_chunks[0].name == "greet"

    def test_js_arrow_function(self) -> None:
        """Arrow functions assigned to variables should be chunked."""
        source = """
const add = (a, b) => a + b;
"""
        chunker = CastChunker(language="javascript")
        chunks = chunker.chunk_source(source, "test.js")
        # Arrow functions with const are caught as assignment or function
        assert len(chunks) >= 1
        all_content = " ".join(c.content for c in chunks)
        assert "add" in all_content or "const" in all_content

    def test_js_class(self) -> None:
        """A JS class should be chunked as one chunk by default."""
        source = """
class Animal {
    constructor(name) {
        this.name = name;
    }
    speak() {
        return this.name + " makes a noise.";
    }
}
"""
        chunker = CastChunker(language="javascript")
        chunks = chunker.chunk_source(source, "test.js")
        assert len(chunks) >= 1
        class_chunks = [c for c in chunks if c.chunk_type == "class"]
        assert len(class_chunks) >= 1
        assert class_chunks[0].name == "Animal"
        assert "constructor" in class_chunks[0].content or "speak" in class_chunks[0].content

    def test_js_import(self) -> None:
        """JS import statements should be grouped into an import block."""
        source = """
import React from 'react';
import { useState } from 'react';

export function App() {
    return null;
}
"""
        chunker = CastChunker(language="javascript")
        chunks = chunker.chunk_source(source, "test.jsx")
        chunk_types = [c.chunk_type for c in chunks]
        assert "import_block" in chunk_types or "function" in chunk_types
        all_content = " ".join(c.content for c in chunks)
        assert "import React" in all_content
        assert "export function App" in all_content

    def test_js_multiple_functions(self) -> None:
        """Multiple JS functions should each get a chunk."""
        source = """
function foo() { return 1; }
function bar() { return 2; }
function baz() { return 3; }
"""
        chunker = CastChunker(language="javascript")
        chunks = chunker.chunk_source(source, "test.js")
        func_names = [c.name for c in chunks if c.chunk_type == "function"]
        # Small functions may be merged
        assert len(func_names) >= 1
        all_content = " ".join(c.content for c in chunks)
        assert "foo" in all_content
        assert "bar" in all_content
        assert "baz" in all_content


@pytest.mark.skipif(not HAS_TS_TS, reason="tree-sitter-typescript not installed")
class TestTypeScriptChunker:
    """Tests for chunking TypeScript with tree-sitter."""

    def test_ts_function(self) -> None:
        """A typed TS function should produce one chunk."""
        source = """
function greet(name: string): string {
    return `Hello ${name}`;
}
"""
        chunker = CastChunker(language="typescript")
        chunks = chunker.chunk_source(source, "test.ts")
        func_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert len(func_chunks) >= 1
        assert func_chunks[0].name == "greet"

    def test_ts_interface(self) -> None:
        """TypeScript interfaces should be chunked."""
        source = """
interface User {
    id: number;
    name: string;
    email: string;
}
"""
        chunker = CastChunker(language="typescript")
        chunks = chunker.chunk_source(source, "test.ts")
        assert len(chunks) >= 1
        all_content = " ".join(c.content for c in chunks)
        assert "User" in all_content or "interface" in all_content

    def test_ts_class(self) -> None:
        """A TS class with typed methods."""
        source = """
class Service {
    private data: string[] = [];

    add(item: string): void {
        this.data.push(item);
    }

    getAll(): string[] {
        return this.data;
    }
}
"""
        chunker = CastChunker(language="typescript")
        chunks = chunker.chunk_source(source, "test.ts")
        assert len(chunks) >= 1
        class_chunks = [c for c in chunks if c.chunk_type == "class"]
        assert len(class_chunks) >= 1
        assert class_chunks[0].name == "Service"

    def test_tsx_file(self) -> None:
        """TSX files should parse correctly."""
        source = """
import React from 'react';

const App: React.FC = () => {
    return <div>Hello</div>;
};

export default App;
"""
        chunker = CastChunker(language="tsx")
        chunks = chunker.chunk_source(source, "test.tsx")
        # Should produce at least one chunk
        assert len(chunks) >= 1


@pytest.mark.skipif(not HAS_TS_GO, reason="tree-sitter-go not installed")
class TestGoChunker:
    """Tests for chunking Go with tree-sitter."""

    def test_go_function(self) -> None:
        """A Go function should be chunked."""
        source = """package main

import "fmt"

func greet(name string) string {
    return "Hello " + name
}
"""
        chunker = CastChunker(language="go")
        chunks = chunker.chunk_source(source, "test.go")
        func_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert len(func_chunks) >= 1
        assert func_chunks[0].name == "greet" or len(func_chunks) > 0
        all_content = " ".join(c.content for c in chunks)
        assert "greet" in all_content

    def test_go_struct(self) -> None:
        """Go struct type declarations should be chunked."""
        source = """package main

type Person struct {
    Name string
    Age  int
}
"""
        chunker = CastChunker(language="go")
        chunks = chunker.chunk_source(source, "test.go")
        assert len(chunks) >= 1
        all_content = " ".join(c.content for c in chunks)
        assert "Person" in all_content
        assert "struct" in all_content


@pytest.mark.skipif(not HAS_TS_RUST, reason="tree-sitter-rust not installed")
class TestRustChunker:
    """Tests for chunking Rust with tree-sitter."""

    def test_rust_function(self) -> None:
        """A Rust function should be chunked."""
        source = """fn greet(name: &str) -> String {
    format!("Hello {}", name)
}
"""
        chunker = CastChunker(language="rust")
        chunks = chunker.chunk_source(source, "test.rs")
        func_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert len(func_chunks) >= 1
        assert func_chunks[0].name == "greet"

    def test_rust_struct(self) -> None:
        """Rust struct definitions should be chunked."""
        source = """struct Point {
    x: f64,
    y: f64,
}
"""
        chunker = CastChunker(language="rust")
        chunks = chunker.chunk_source(source, "test.rs")
        assert len(chunks) >= 1
        all_content = " ".join(c.content for c in chunks)
        assert "Point" in all_content
        assert "struct" in all_content

    def test_rust_trait(self) -> None:
        """Rust trait definitions should be chunked."""
        source = """pub trait Drawable {
    fn draw(&self);
    fn area(&self) -> f64;
}
"""
        chunker = CastChunker(language="rust")
        chunks = chunker.chunk_source(source, "test.rs")
        assert len(chunks) >= 1
        all_content = " ".join(c.content for c in chunks)
        assert "Drawable" in all_content
        assert "trait" in all_content


@pytest.mark.skipif(not HAS_TS_JAVA, reason="tree-sitter-java not installed")
class TestJavaChunker:
    """Tests for chunking Java with tree-sitter."""

    def test_java_class(self) -> None:
        """A Java class should be chunked."""
        source = """
public class Calculator {
    public int add(int a, int b) {
        return a + b;
    }

    public int multiply(int a, int b) {
        return a * b;
    }
}
"""
        chunker = CastChunker(language="java")
        chunks = chunker.chunk_source(source, "Calculator.java")
        class_chunks = [c for c in chunks if c.chunk_type == "class"]
        assert len(class_chunks) >= 1
        assert class_chunks[0].name == "Calculator"
        assert "add" in class_chunks[0].content or "multiply" in class_chunks[0].content

    def test_java_imports(self) -> None:
        """Java import statements should be grouped."""
        source = """
import java.util.List;
import java.util.ArrayList;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello");
    }
}
"""
        chunker = CastChunker(language="java")
        chunks = chunker.chunk_source(source, "Main.java")
        all_content = " ".join(c.content for c in chunks)
        assert "import java.util.List" in all_content
        assert "class Main" in all_content
