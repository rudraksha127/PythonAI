"""
cAST Chunker — AST-aware Code Chunking (EMNLP 2025 Implementation)
==================================================================

Implements the cAST algorithm from "Enhancing Code RAG with Structural 
Chunking via Abstract Syntax Tree" (Zhang et al., EMNLP 2025).

Key insight: Code's natural structure is the AST, not arbitrary line counts.
- A function is one chunk (even if 200 lines)
- A class is one chunk (split only if >500 tokens)
- Chunking respects semantic boundaries

Benchmark: +4.3 Recall@5 on RepoEval, +2.67 Pass@1 on SWE-bench.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# Tree-sitter optional — falls back to Python's ast module or line-based chunking
# Core tree-sitter library (must be installed for any grammar to work)
_HAS_TS_CORE = False
try:
    from tree_sitter import Language, Parser
    _HAS_TS_CORE = True
except ImportError:
    pass

_HAS_TS_PYTHON = False
_HAS_TS_JS = False
_HAS_TS_TS = False
_HAS_TS_GO = False
_HAS_TS_RUST = False
_HAS_TS_JAVA = False

try:
    import tree_sitter_python  # noqa: F401
    _HAS_TS_PYTHON = True
except ImportError:
    pass

try:
    import tree_sitter_javascript as _ts_js  # noqa: F401
    _HAS_TS_JS = True
except ImportError:
    pass

try:
    import tree_sitter_typescript as _ts_ts  # noqa: F401
    _HAS_TS_TS = True
except ImportError:
    pass

try:
    import tree_sitter_go as _ts_go  # noqa: F401
    _HAS_TS_GO = True
except ImportError:
    pass

try:
    import tree_sitter_rust as _ts_rs  # noqa: F401
    _HAS_TS_RUST = True
except ImportError:
    pass

try:
    import tree_sitter_java as _ts_java  # noqa: F401
    _HAS_TS_JAVA = True
except ImportError:
    pass

_HAS_TREE_SITTER = _HAS_TS_CORE and (_HAS_TS_PYTHON or _HAS_TS_JS or _HAS_TS_TS or _HAS_TS_GO or _HAS_TS_RUST or _HAS_TS_JAVA)

# AST node types that have inner bodies — split points for recursive chunking (Python)
_BLOCK_BODY_NODES: tuple = (
    ast.If, ast.For, ast.While, ast.Try, ast.With,
    ast.AsyncFor, ast.AsyncWith,
)
# Python 3.10+ match statement
try:
    _BLOCK_BODY_NODES += (ast.Match,)
except AttributeError:
    pass

# Tree-sitter block node type names per language (for recursive splitting)
_TS_BLOCK_TYPES: dict[str, tuple[str, ...]] = {
    "javascript": ("if_statement", "for_statement", "for_in_statement", "while_statement",
                    "try_statement", "switch_statement", "with_statement", "do_statement"),
    "typescript": ("if_statement", "for_statement", "for_in_statement", "while_statement",
                    "try_statement", "switch_statement", "with_statement", "do_statement"),
    "tsx": ("if_statement", "for_statement", "for_in_statement", "while_statement",
             "try_statement", "switch_statement", "with_statement", "do_statement"),
    "go": ("if_statement", "for_statement", "switch_statement", "select_statement",
            "type_switch_statement"),
    "rust": ("if_expression", "for_expression", "while_expression", "loop_expression",
              "match_expression"),
    "java": ("if_statement", "for_statement", "while_statement", "try_statement",
              "switch_statement", "do_statement"),
}

# Max recursion depth for recursive splitting
_MAX_RECURSION_DEPTH = 5


@dataclass
class CodeChunk:
    """A semantically complete code unit from cAST chunking."""
    content: str
    chunk_type: str  # "function", "class", "module", "method", "import_block"
    start_line: int
    end_line: int
    name: str = ""
    docstring: str = ""
    signature: str = ""
    parent_class: Optional[str] = None
    dependencies: list[str] = field(default_factory=list)  # function calls, imports
    imports: list[str] = field(default_factory=list)
    filepath: str = ""
    language: str = "python"
    token_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "chunk_type": self.chunk_type,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "name": self.name,
            "docstring": self.docstring,
            "signature": self.signature,
            "parent_class": self.parent_class,
            "dependencies": self.dependencies,
            "imports": self.imports,
            "filepath": self.filepath,
            "language": self.language,
            "token_count": self.token_count,
        }

    def to_embedding_text(self) -> str:
        """Multi-view embedding text: code + docstring + signature."""
        parts = []
        if self.signature:
            parts.append(f"Signature: {self.signature}")
        if self.docstring:
            parts.append(f"Docstring: {self.docstring}")
        parts.append(f"Code:\n{self.content}")
        return "\n\n".join(parts)


# ═══════════════════════════════════════════════════════════════
# Tree-sitter Multi-Language Configuration
# ═══════════════════════════════════════════════════════════════


@dataclass
class TSLanguageConfig:
    """Configuration for a tree-sitter language grammar and its chunking rules."""
    name: str
    extensions: list[str]

    # Node type name patterns for identifying constructs
    function_types: tuple[str, ...] = ()
    class_types: tuple[str, ...] = ()
    interface_types: tuple[str, ...] = ()
    import_types: tuple[str, ...] = ()
    assignment_types: tuple[str, ...] = ()

    # How to extract name from a node (field name or index-based)
    name_field: str = "name"
    # Types whose name is a type_identifier (e.g., TypeScript, Go, Java)
    uses_type_identifier: bool = False

    # Comment syntax for docstring detection
    comment_types: tuple[str, ...] = ("comment",)
    block_comment_prefix: str = "/*"  # For JSDoc/Javadoc detection
    line_comment_prefix: str = "//"


# Language registry maps language names to their configurations
_TS_LANGUAGE_CONFIGS: dict[str, TSLanguageConfig] = {
    "javascript": TSLanguageConfig(
        name="javascript",
        extensions=[".js", ".jsx", ".mjs"],
        function_types=("function_declaration", "method_definition",
                        "generator_function_declaration", "arrow_function"),
        class_types=("class_declaration", "class_expression"),
        import_types=("import_statement", "import_expression", "export_statement"),
        assignment_types=("lexical_declaration", "variable_declaration",
                          "expression_statement"),
    ),
    "typescript": TSLanguageConfig(
        name="typescript",
        extensions=[".ts"],
        function_types=("function_declaration", "method_definition",
                        "generator_function_declaration", "arrow_function"),
        class_types=("class_declaration", "class_expression"),
        interface_types=("interface_declaration", "type_alias_declaration",
                         "enum_declaration"),
        import_types=("import_statement", "import_expression", "export_statement"),
        assignment_types=("lexical_declaration", "variable_declaration",
                          "expression_statement"),
    ),
    "tsx": TSLanguageConfig(
        name="tsx",
        extensions=[".tsx"],
        function_types=("function_declaration", "method_definition",
                        "generator_function_declaration", "arrow_function"),
        class_types=("class_declaration", "class_expression"),
        interface_types=("interface_declaration", "type_alias_declaration",
                         "enum_declaration"),
        import_types=("import_statement", "import_expression", "export_statement"),
        assignment_types=("lexical_declaration", "variable_declaration",
                          "expression_statement"),
    ),
    "go": TSLanguageConfig(
        name="go",
        extensions=[".go"],
        function_types=("function_declaration", "method_declaration"),
        class_types=("type_declaration", "type_spec"),
        interface_types=("interface_type", "struct_type"),
        import_types=("import_declaration",),
        assignment_types=("assignment_statement", "short_var_declaration",
                          "const_declaration", "var_declaration"),
        uses_type_identifier=True,
        comment_types=("comment",),
        line_comment_prefix="//",
    ),
    "rust": TSLanguageConfig(
        name="rust",
        extensions=[".rs"],
        function_types=("function_item",),
        class_types=("struct_item", "enum_item", "union_item"),
        interface_types=("trait_item", "impl_item", "type_item", "type_alias"),
        import_types=("use_declaration",),
        assignment_types=("let_declaration", "const_item", "static_item"),
        uses_type_identifier=True,
        comment_types=("line_comment", "block_comment"),
        line_comment_prefix="//",
        block_comment_prefix="/*",
    ),
    "java": TSLanguageConfig(
        name="java",
        extensions=[".java"],
        function_types=("method_declaration",),
        class_types=("class_declaration", "enum_declaration",
                      "record_declaration"),
        interface_types=("interface_declaration", "annotation_type_declaration"),
        import_types=("import_declaration",),
        assignment_types=("variable_declaration", "field_declaration"),
        uses_type_identifier=True,
        comment_types=("block_comment", "line_comment"),
        block_comment_prefix="/*",
        line_comment_prefix="//",
    ),
}

# Extension → language name mapping for auto-detection
_EXT_TO_LANG: dict[str, str] = {}
for _lang_name, _cfg in _TS_LANGUAGE_CONFIGS.items():
    for _ext in _cfg.extensions:
        _EXT_TO_LANG[_ext] = _lang_name

# Also register common extensions not in a single config
_EXT_TO_LANG.setdefault(".py", "python")
_EXT_TO_LANG.setdefault(".cjs", "javascript")
_EXT_TO_LANG.setdefault(".mts", "typescript")
_EXT_TO_LANG.setdefault(".cts", "typescript")


class ASTDependencyExtractor(ast.NodeVisitor):
    """Extract function calls and imports from AST."""

    def __init__(self):
        self.calls: list[str] = []
        self.imports: list[str] = []
        self.defined_names: list[str] = []

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module or ""
        for alias in node.names:
            self.imports.append(f"{module}.{alias.name}" if module else alias.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self.defined_names.append(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        self.defined_names.append(node.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        self.defined_names.append(node.name)
        self.generic_visit(node)

    def visit_Call(self, node):
        call_name = self._get_call_name(node.func)
        if call_name:
            self.calls.append(call_name)
        self.generic_visit(node)

    def _get_call_name(self, func_node) -> Optional[str]:
        if isinstance(func_node, ast.Name):
            return func_node.id
        elif isinstance(func_node, ast.Attribute):
            value = self._get_call_name(func_node.value)
            if value:
                return f"{value}.{func_node.attr}"
        return None


def _extract_docstring(node) -> str:
    """Extract docstring from a function or class node."""
    if (node.body and isinstance(node.body[0], ast.Expr) and
            isinstance(node.body[0].value, ast.Constant)):
        value = node.body[0].value
        if isinstance(value.value, str):
            return value.value
    return ""


def _get_function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef, source_lines: list[str]) -> str:
    """Extract the function signature (decorator + def line)."""
    start = node.lineno - 1
    # Find the line with the colon
    sig_lines = []
    for i in range(start, min(start + 20, len(source_lines))):
        sig_lines.append(source_lines[i])
        if ":" in source_lines[i] and not source_lines[i].rstrip().endswith("\\"):
            break
    return "\n".join(sig_lines)


def _count_tokens(text: str) -> int:
    """Rough token count (4 chars ≈ 1 token for Python code)."""
    return max(1, len(text) // 4)


class CastChunker:
    """
    cAST: AST-aware code chunking for semantic completeness.
    
    Algorithm:
    1. Parse source file into AST
    2. Extract top-level nodes (functions, classes, imports)
    3. For classes: extract methods as sub-chunks
    4. Merge small sibling nodes if under size threshold
    5. Split large nodes recursively if over max size
    """

    MAX_CHUNK_TOKENS = 2000  # ~8000 chars
    MIN_CHUNK_TOKENS = 50    # Skip tiny chunks
    MERGE_THRESHOLD = 300    # Merge siblings under this
    SPLIT_THRESHOLD = 2500   # Split functions/classes that exceed this

    def __init__(self, language: str = "python"):
        self.language = language
        self.chunks: list[CodeChunk] = []

    def chunk_file(self, filepath: str | Path) -> list[CodeChunk]:
        """Parse a source file and return semantically complete chunks."""
        filepath = Path(filepath)
        if not filepath.exists():
            return []

        source = filepath.read_text(encoding="utf-8", errors="replace")
        return self.chunk_source(source, str(filepath))

    def chunk_source(self, source: str, filepath: str = "<unknown>") -> list[CodeChunk]:
        """Parse source code string and return chunks."""
        self.chunks = []
        source_lines = source.splitlines()

        if self.language == "python":
            self._chunk_python(source, source_lines, filepath)
        elif self.language in _TS_LANGUAGE_CONFIGS:
            self._chunk_ts_based(source, source_lines, filepath)
        else:
            # Fallback: line-based chunking for unsupported languages
            self._chunk_by_lines(source, source_lines, filepath)

        return self.chunks

    def _chunk_python(self, source: str, source_lines: list[str], filepath: str):
        """Python-specific AST-based chunking."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            # Fallback to line-based if syntax errors
            self._chunk_by_lines(source, source_lines, filepath)
            return

        extractor = ASTDependencyExtractor()

        # Process top-level nodes
        top_level_chunks: list[CodeChunk] = []
        import_block: list[str] = []
        import_start = None

        for node in ast.iter_child_nodes(tree):
            # Group consecutive imports
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if not import_start:
                    import_start = node.lineno
                import_block.append("\n".join(source_lines[node.lineno - 1: node.end_lineno]))
                extractor.visit(node)
                continue
            else:
                # Flush import block
                if import_block:
                    content = "\n".join(import_block)
                    if content.strip():
                        chunk = CodeChunk(
                            content=content,
                            chunk_type="import_block",
                            start_line=import_start or 1,
                            end_line=import_start + len(content.splitlines()) - 1 if import_start else 1,
                            name="imports",
                            imports=extractor.imports.copy(),
                            filepath=filepath,
                            language="python",
                            token_count=_count_tokens(content),
                        )
                        top_level_chunks.append(chunk)
                    import_block = []
                    import_start = None

            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                result = self._process_function(node, source_lines, filepath)
                if isinstance(result, list):
                    top_level_chunks.extend(result)
                else:
                    top_level_chunks.append(result)

            elif isinstance(node, ast.ClassDef):
                result = self._process_class(node, source_lines, filepath)
                if isinstance(result, list):
                    top_level_chunks.extend(result)
                else:
                    top_level_chunks.append(result)

            elif isinstance(node, (ast.Assign, ast.AnnAssign)) and not import_block:
                # Top-level assignments/constants
                content = source_lines[node.lineno - 1: node.end_lineno]
                content_str = "\n".join(content)
                if len(content_str) > 1:
                    chunk = CodeChunk(
                        content=content_str,
                        chunk_type="assignment",
                        start_line=node.lineno,
                        end_line=node.end_lineno,
                        name="module_variable",
                        filepath=filepath,
                        language="python",
                        token_count=_count_tokens(content_str),
                    )
                    top_level_chunks.append(chunk)

        # Flush remaining imports
        if import_block:
            content = "\n".join(import_block)
            chunk = CodeChunk(
                content=content,
                chunk_type="import_block",
                start_line=import_start or 1,
                end_line=import_start + len(content.splitlines()) - 1 if import_start else 1,
                name="imports",
                imports=extractor.imports.copy(),
                filepath=filepath,
                language="python",
                token_count=_count_tokens(content),
            )
            top_level_chunks.append(chunk)

        # Merge small sibling chunks
        top_level_chunks = self._merge_siblings(top_level_chunks)

        self.chunks.extend(top_level_chunks)

    @staticmethod
    def _get_node_start_line(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
        """Get the actual start line, accounting for decorators above the definition."""
        if node.decorator_list:
            return min(d.lineno for d in node.decorator_list)
        return node.lineno

    def _process_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        source_lines: list[str],
        filepath: str,
    ) -> CodeChunk | list[CodeChunk]:
        """Process a function node — may return multiple chunks if overly large."""
        sub_extractor = ASTDependencyExtractor()
        sub_extractor.visit(node)

        start_line = self._get_node_start_line(node)
        content_lines = source_lines[start_line - 1: node.end_lineno]
        content = "\n".join(content_lines)
        token_count = _count_tokens(content)

        chunk_type = "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function"

        # ── Recursive splitting for overly large functions ────
        if token_count > self.SPLIT_THRESHOLD and node.body:
            split_chunks = self._split_function_at_blocks(
                node=node,
                source_lines=source_lines,
                filepath=filepath,
                chunk_type=chunk_type,
                func_name=node.name,
                start_line=start_line,
                depth=0,
            )
            # Merge dependencies from function-level extractor into each sub-chunk
            for c in split_chunks:
                if not c.dependencies:
                    c.dependencies = sub_extractor.calls.copy()
                if not c.imports:
                    c.imports = sub_extractor.imports.copy()
            return split_chunks

        return CodeChunk(
            content=content,
            chunk_type=chunk_type,
            start_line=start_line,
            end_line=node.end_lineno,
            name=node.name,
            docstring=_extract_docstring(node),
            signature=_get_function_signature(node, source_lines),
            dependencies=sub_extractor.calls,
            imports=sub_extractor.imports,
            filepath=filepath,
            language="python",
            token_count=token_count,
        )

    def _split_function_at_blocks(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        source_lines: list[str],
        filepath: str,
        chunk_type: str,
        func_name: str,
        start_line: int,
        depth: int = 0,
    ) -> list[CodeChunk]:
        """
        Split a function at inner block boundaries (if/for/while/try/with).

        Walks the function body and creates separate chunks for:
        - The preamble (signature + linear code before first block)
        - Each block statement (if/for/while/try/with) as its own chunk
        - Code between blocks

        If a block itself exceeds SPLIT_THRESHOLD, it is recursively split.
        """
        if depth > _MAX_RECURSION_DEPTH:
            # Safety valve — return one monolithic chunk
            content = "\n".join(source_lines[start_line - 1: node.end_lineno])
            return [CodeChunk(
                content=content,
                chunk_type=chunk_type,
                start_line=start_line,
                end_line=node.end_lineno,
                name=func_name,
                filepath=filepath,
                language="python",
                token_count=_count_tokens(content),
            )]

        chunks: list[CodeChunk] = []
        cursor = start_line  # Source line cursor (1-based)
        section_idx = 0

        for stmt in node.body:
            stmt_start = stmt.lineno
            stmt_end = getattr(stmt, "end_lineno", stmt.lineno)

            if isinstance(stmt, _BLOCK_BODY_NODES):
                # ── Code before this block ──
                if stmt_start > cursor:
                    pre_lines = source_lines[cursor - 1: stmt_start - 1]
                    pre_content = "\n".join(pre_lines).strip()
                    if pre_content:
                        chunks.append(CodeChunk(
                            content=pre_content,
                            chunk_type=f"{chunk_type}_section",
                            start_line=cursor,
                            end_line=stmt_start - 1,
                            name=f"{func_name}_pre_{section_idx}",
                            filepath=filepath,
                            language="python",
                            token_count=_count_tokens(pre_content),
                        ))
                        section_idx += 1

                # ── The block statement — check if it needs recursive split ──
                block_lines = source_lines[stmt_start - 1: stmt_end]
                block_content = "\n".join(block_lines)
                block_tokens = _count_tokens(block_content)

                if block_tokens > self.SPLIT_THRESHOLD:
                    # Recursively split the block
                    sub_chunks = self._split_node_into_sections(
                        stmt, stmt_start, stmt_end, source_lines,
                        filepath, func_name, chunk_type, depth + 1,
                    )
                    chunks.extend(sub_chunks)
                else:
                    chunks.append(CodeChunk(
                        content=block_content,
                        chunk_type=f"{chunk_type}_block",
                        start_line=stmt_start,
                        end_line=stmt_end,
                        name=f"{func_name}_{type(stmt).__name__.lower()}_{section_idx}",
                        filepath=filepath,
                        language="python",
                        token_count=block_tokens,
                    ))
                    section_idx += 1

                cursor = stmt_end + 1

        # ── Remaining code after the last block ──
        if cursor <= node.end_lineno:
            post_lines = source_lines[cursor - 1: node.end_lineno]
            post_content = "\n".join(post_lines).strip()
            if post_content:
                chunks.append(CodeChunk(
                    content=post_content,
                    chunk_type=f"{chunk_type}_section",
                    start_line=cursor,
                    end_line=node.end_lineno,
                    name=f"{func_name}_post_{section_idx}",
                    filepath=filepath,
                    language="python",
                    token_count=_count_tokens(post_content),
                ))

        return chunks

    def _split_node_into_sections(
        self,
        node: ast.AST,
        start_line: int,
        end_line: int,
        source_lines: list[str],
        filepath: str,
        parent_name: str,
        parent_type: str,
        depth: int,
    ) -> list[CodeChunk]:
        """Split an arbitrary AST node into sections at its inner body boundaries.

        Works for if/for/while/try/with by walking the node's body children.
        """
        if depth > _MAX_RECURSION_DEPTH:
            content = "\n".join(source_lines[start_line - 1: end_line])
            return [CodeChunk(
                content=content,
                chunk_type=f"{parent_type}_block",
                start_line=start_line,
                end_line=end_line,
                name=f"{parent_name}_section",
                filepath=filepath,
                language="python",
                token_count=_count_tokens(content),
            )]

        # Collect body nodes from the block statement
        body_nodes: list[ast.AST] = []
        if hasattr(node, "body") and isinstance(node.body, list):
            body_nodes.extend(node.body)
        if hasattr(node, "orelse") and isinstance(node.orelse, list):
            body_nodes.extend(node.orelse)
        if hasattr(node, "handlers") and isinstance(node.handlers, list):
            body_nodes.extend(node.handlers)
            # Also walk into handler bodies
            for handler in node.handlers:
                if hasattr(handler, "body") and isinstance(handler.body, list):
                    body_nodes.extend(handler.body)
        if hasattr(node, "finalbody") and isinstance(node.finalbody, list):
            body_nodes.extend(node.finalbody)

        if not body_nodes:
            content = "\n".join(source_lines[start_line - 1: end_line])
            return [CodeChunk(
                content=content,
                chunk_type=f"{parent_type}_block",
                start_line=start_line,
                end_line=end_line,
                name=f"{parent_name}_section",
                filepath=filepath,
                language="python",
                token_count=_count_tokens(content),
            )]

        chunks: list[CodeChunk] = []
        cursor = start_line
        section_idx = 0

        for stmt in body_nodes:
            stmt_start = stmt.lineno
            stmt_end = getattr(stmt, "end_lineno", stmt.lineno)

            if isinstance(stmt, _BLOCK_BODY_NODES):
                # Code before this nested block
                if stmt_start > cursor:
                    pre_lines = source_lines[cursor - 1: stmt_start - 1]
                    pre_content = "\n".join(pre_lines).strip()
                    if pre_content:
                        chunks.append(CodeChunk(
                            content=pre_content,
                            chunk_type=f"{parent_type}_section",
                            start_line=cursor,
                            end_line=stmt_start - 1,
                            name=f"{parent_name}_inner_pre_{section_idx}",
                            filepath=filepath,
                            language="python",
                            token_count=_count_tokens(pre_content),
                        ))
                        section_idx += 1

                # The nested block — recursively split if too large
                block_lines = source_lines[stmt_start - 1: stmt_end]
                block_content = "\n".join(block_lines)
                if _count_tokens(block_content) > self.SPLIT_THRESHOLD:
                    sub_chunks = self._split_node_into_sections(
                        stmt, stmt_start, stmt_end, source_lines,
                        filepath, parent_name, parent_type, depth + 1,
                    )
                    chunks.extend(sub_chunks)
                else:
                    chunks.append(CodeChunk(
                        content=block_content,
                        chunk_type=f"{parent_type}_block",
                        start_line=stmt_start,
                        end_line=stmt_end,
                        name=f"{parent_name}_inner_{type(stmt).__name__.lower()}_{section_idx}",
                        filepath=filepath,
                        language="python",
                        token_count=_count_tokens(block_content),
                    ))
                    section_idx += 1

                cursor = stmt_end + 1

        # Remaining code
        if cursor <= end_line:
            post_lines = source_lines[cursor - 1: end_line]
            post_content = "\n".join(post_lines).strip()
            if post_content:
                chunks.append(CodeChunk(
                    content=post_content,
                    chunk_type=f"{parent_type}_section",
                    start_line=cursor,
                    end_line=end_line,
                    name=f"{parent_name}_inner_post_{section_idx}",
                    filepath=filepath,
                    language="python",
                    token_count=_count_tokens(post_content),
                ))

        return chunks

    def _process_class(
        self,
        node: ast.ClassDef,
        source_lines: list[str],
        filepath: str,
    ) -> CodeChunk | list[CodeChunk]:
        """Process a class node — may return multiple chunks for large classes."""
        content_lines = source_lines[node.lineno - 1: node.end_lineno]
        content = "\n".join(content_lines)
        token_count = _count_tokens(content)

        # If class is small enough, return as single chunk
        if token_count <= self.MAX_CHUNK_TOKENS:
            sub_extractor = ASTDependencyExtractor()
            sub_extractor.visit(node)

            return CodeChunk(
                content=content,
                chunk_type="class",
                start_line=node.lineno,
                end_line=node.end_lineno,
                name=node.name,
                docstring=_extract_docstring(node),
                signature=f"class {node.name}{self._get_class_bases(node)}:",
                dependencies=sub_extractor.calls,
                imports=sub_extractor.imports,
                filepath=filepath,
                language="python",
                token_count=token_count,
            )

        # Large class: split into methods
        chunks: list[CodeChunk] = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                result = self._process_function(item, source_lines, filepath)
                if isinstance(result, list):
                    for mc in result:
                        mc.parent_class = node.name
                        mc.chunk_type = "method"
                        chunks.append(mc)
                else:
                    result.parent_class = node.name
                    result.chunk_type = "method"
                    chunks.append(result)
            elif isinstance(item, (ast.Assign, ast.AnnAssign)):
                # Class-level attribute
                attr_content = "\n".join(source_lines[item.lineno - 1: item.end_lineno])
                chunks.append(CodeChunk(
                    content=attr_content,
                    chunk_type="class_attribute",
                    start_line=item.lineno,
                    end_line=item.end_lineno,
                    name="class_attr",
                    parent_class=node.name,
                    filepath=filepath,
                    language="python",
                    token_count=_count_tokens(attr_content),
                ))

        # Also include class definition line + docstring as context chunk
        class_header = source_lines[node.lineno - 1]
        docstring = _extract_docstring(node)
        if docstring:
            header_content = class_header + "\n" + '"""' + docstring + '"""'
            chunks.insert(0, CodeChunk(
                content=header_content,
                chunk_type="class_header",
                start_line=node.lineno,
                end_line=node.lineno + docstring.count("\n") + 2,
                name=node.name,
                docstring=docstring,
                signature=f"class {node.name}{self._get_class_bases(node)}:",
                filepath=filepath,
                language="python",
                token_count=_count_tokens(header_content),
            ))

        return chunks

    def _get_class_bases(self, node: ast.ClassDef) -> str:
        """Get class base classes as string."""
        if not node.bases:
            return ""
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(f"{base.value.id}.{base.attr}" if isinstance(base.value, ast.Name) else base.attr)
        return f"({', '.join(bases)})"

    def _merge_siblings(self, chunks: list[CodeChunk]) -> list[CodeChunk]:
        """Merge small sibling chunks of the same type that are contiguous."""
        if len(chunks) <= 1:
            return chunks

        merged: list[CodeChunk] = []
        i = 0
        while i < len(chunks):
            current = chunks[i]
            # Try to merge with next chunks of same type
            if current.token_count < self.MERGE_THRESHOLD and i + 1 < len(chunks):
                merged_content = [current.content]
                merged_end = current.end_line
                merged_type = current.chunk_type
                j = i + 1
                while (j < len(chunks)
                       and chunks[j].token_count < self.MERGE_THRESHOLD
                       and chunks[j].chunk_type == merged_type):
                    # Only merge if contiguous (allowing 1 blank line gap)
                    if chunks[j].start_line <= merged_end + 2:
                        merged_content.append(chunks[j].content)
                        merged_end = chunks[j].end_line
                        j += 1
                    else:
                        break

                if j > i + 1:
                    # We merged multiple chunks
                    content = "\n\n".join(merged_content)
                    merged.append(CodeChunk(
                        content=content,
                        chunk_type=merged_type,
                        start_line=current.start_line,
                        end_line=merged_end,
                        name=f"merged_{merged_type}_block",
                        filepath=current.filepath,
                        language=current.language,
                        token_count=_count_tokens(content),
                    ))
                    i = j
                    continue

            merged.append(current)
            i += 1

        return merged

    def _chunk_by_lines(self, source: str, source_lines: list[str], filepath: str):
        """Fallback: line-based chunking for non-Python files."""
        # Try to find natural boundaries (blank lines, function defs, class defs)
        boundaries = [0]
        for i, line in enumerate(source_lines):
            stripped = line.strip()
            if stripped.startswith(("def ", "class ", "function ", "func ")):
                boundaries.append(i)
            elif stripped == "" and i > 0 and i < len(source_lines) - 1:
                # Check if next non-empty line starts a new block
                for j in range(i + 1, min(i + 5, len(source_lines))):
                    if source_lines[j].strip():
                        if source_lines[j].strip().startswith(("def ", "class ", "function ")):
                            boundaries.append(i + 1)
                        break

        boundaries.append(len(source_lines))

        for idx in range(len(boundaries) - 1):
            start = boundaries[idx]
            end = boundaries[idx + 1]
            content = "\n".join(source_lines[start:end])
            if content.strip() and len(content) > 30:
                self.chunks.append(CodeChunk(
                    content=content,
                    chunk_type="code_block",
                    start_line=start + 1,
                    end_line=end,
                    name=f"block_{idx}",
                    filepath=filepath,
                    language=self.language,
                    token_count=_count_tokens(content),
                ))

    def chunk_directory(
        self,
        dirpath: str | Path,
        extensions: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> list[CodeChunk]:
        """Chunk all source files in a directory. Auto-detects language from extension."""
        if extensions is None:
            extensions = [".py", ".js", ".jsx", ".mjs", ".ts", ".tsx", ".java", ".go", ".rs"]
        if exclude_patterns is None:
            exclude_patterns = [
                "__pycache__", "node_modules", ".git", "dist", "build",
                "venv", ".venv", "env", ".tox", "*.min.js",
            ]

        dirpath = Path(dirpath)
        all_chunks = []

        for ext in extensions:
            for filepath in dirpath.rglob(f"*{ext}"):
                # Check exclusions
                skip = False
                for pattern in exclude_patterns:
                    if pattern in str(filepath):
                        skip = True
                        break
                if skip:
                    continue

                # Auto-detect language from extension
                lang = _EXT_TO_LANG.get(ext, "python")
                if lang != "python":
                    # Verify tree-sitter grammar is available
                    if lang == "javascript" and not _HAS_TS_JS:
                        continue
                    elif lang == "typescript" and not _HAS_TS_TS:
                        continue
                    elif lang == "tsx" and not _HAS_TS_TS:
                        continue
                    elif lang == "go" and not _HAS_TS_GO:
                        continue
                    elif lang == "rust" and not _HAS_TS_RUST:
                        continue
                    elif lang == "java" and not _HAS_TS_JAVA:
                        continue

                try:
                    original_language = self.language
                    self.language = lang
                    chunks = self.chunk_file(filepath)
                    self.language = original_language
                    all_chunks.extend(chunks)
                except Exception as e:
                    print(f"[cAST] Error chunking {filepath}: {e}")

        return all_chunks

    # ═══════════════════════════════════════════════════════════════
    # Tree-sitter Multi-Language Chunking
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _get_ts_language_object(lang: str):
        """Get the tree-sitter Language object for a given language name."""
        if lang == "javascript" and _HAS_TS_JS:
            import tree_sitter_javascript
            return Language(tree_sitter_javascript.language())
        elif lang == "typescript" and _HAS_TS_TS:
            import tree_sitter_typescript
            return Language(tree_sitter_typescript.language_typescript())
        elif lang == "tsx" and _HAS_TS_TS:
            import tree_sitter_typescript
            return Language(tree_sitter_typescript.language_tsx())
        elif lang == "go" and _HAS_TS_GO:
            import tree_sitter_go
            return Language(tree_sitter_go.language())
        elif lang == "rust" and _HAS_TS_RUST:
            import tree_sitter_rust
            return Language(tree_sitter_rust.language())
        elif lang == "java" and _HAS_TS_JAVA:
            import tree_sitter_java
            return Language(tree_sitter_java.language())
        return None

    def _chunk_ts_based(self, source: str, source_lines: list[str], filepath: str):
        """Generic tree-sitter based chunking for any supported language."""
        lang_config = _TS_LANGUAGE_CONFIGS.get(self.language)
        if lang_config is None:
            self._chunk_by_lines(source, source_lines, filepath)
            return

        ts_lang = self._get_ts_language_object(self.language)
        if ts_lang is None:
            self._chunk_by_lines(source, source_lines, filepath)
            return

        parser = Parser(ts_lang)
        source_bytes = source.encode("utf-8")
        tree = parser.parse(source_bytes)
        root = tree.root_node

        # Collect all top-level named children
        top_level_chunks: list[CodeChunk] = []
        import_block: list[str] = []
        import_start: int | None = None

        cursor = root.walk()
        if cursor.goto_first_child():
            while True:
                node = cursor.node

                # ── Import grouping ──
                if node.type in lang_config.import_types:
                    if import_start is None:
                        import_start = node.start_point[0] + 1  # 1-based
                    node_text = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
                    import_block.append(node_text)
                    if not cursor.goto_next_sibling():
                        break
                    continue
                else:
                    if import_block:
                        chunk = self._make_ts_import_chunk(
                            import_block, import_start or 1, source_lines, filepath
                        )
                        if chunk:
                            top_level_chunks.append(chunk)
                        import_block = []
                        import_start = None

                # ── Functions ──
                if node.type in lang_config.function_types:
                    result = self._process_ts_function(
                        node, source_bytes, source_lines, filepath, lang_config
                    )
                    if isinstance(result, list):
                        top_level_chunks.extend(result)
                    else:
                        top_level_chunks.append(result)

                # ── Classes ──
                elif node.type in lang_config.class_types:
                    result = self._process_ts_class(
                        node, source_bytes, source_lines, filepath, lang_config
                    )
                    if isinstance(result, list):
                        top_level_chunks.extend(result)
                    else:
                        top_level_chunks.append(result)

                # ── Interfaces / Type aliases / Enums ──
                elif node.type in lang_config.interface_types:
                    chunk = self._process_ts_interface(
                        node, source_bytes, source_lines, filepath, lang_config
                    )
                    if chunk:
                        top_level_chunks.append(chunk)

                # ── Top-level assignments / declarations ──
                elif node.type in lang_config.assignment_types:
                    chunk = self._process_ts_assignment(
                        node, source_bytes, source_lines, filepath, lang_config
                    )
                    if chunk:
                        top_level_chunks.append(chunk)

                if not cursor.goto_next_sibling():
                    break

            # Flush remaining imports
            if import_block:
                chunk = self._make_ts_import_chunk(
                    import_block, import_start or 1, source_lines, filepath
                )
                if chunk:
                    top_level_chunks.append(chunk)

        # Merge small sibling chunks
        top_level_chunks = self._merge_siblings(top_level_chunks)
        self.chunks.extend(top_level_chunks)

    def _make_ts_import_chunk(
        self,
        import_block: list[str],
        import_start: int,
        source_lines: list[str],
        filepath: str,
    ) -> CodeChunk | None:
        """Create a CodeChunk from grouped import statements."""
        content = "\n".join(import_block)
        if not content.strip():
            return None
        end_line = import_start + len(content.splitlines()) - 1
        # Extract import names (best-effort)
        import_names = []
        for line in import_block:
            stripped = line.strip()
            if stripped.startswith(("import", "use", "from", "#include")):
                import_names.append(stripped)
        return CodeChunk(
            content=content,
            chunk_type="import_block",
            start_line=import_start,
            end_line=end_line,
            name="imports",
            imports=import_names,
            filepath=filepath,
            language=self.language,
            token_count=_count_tokens(content),
        )

    def _process_ts_function(
        self,
        node,
        source_bytes: bytes,
        source_lines: list[str],
        filepath: str,
        lang_config: TSLanguageConfig,
    ) -> CodeChunk | list[CodeChunk]:
        """Process a tree-sitter function node."""
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        content = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
        token_count = _count_tokens(content)
        name = self._extract_ts_node_name(node, source_bytes)
        docstring = self._get_ts_comment_before(node, source_bytes)
        signature = self._get_ts_signature(node, source_lines)

        if token_count > self.SPLIT_THRESHOLD:
            # Recursive splitting would need tree-sitter child walking
            # For now, return as single chunk with a warning
            pass

        return CodeChunk(
            content=content,
            chunk_type="function",
            start_line=start_line,
            end_line=end_line,
            name=name or "anonymous",
            docstring=docstring,
            signature=signature,
            filepath=filepath,
            language=self.language,
            token_count=token_count,
        )

    def _process_ts_class(
        self,
        node,
        source_bytes: bytes,
        source_lines: list[str],
        filepath: str,
        lang_config: TSLanguageConfig,
    ) -> CodeChunk | list[CodeChunk]:
        """Process a tree-sitter class node — may split into methods."""
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        content = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
        token_count = _count_tokens(content)
        name = self._extract_ts_node_name(node, source_bytes)
        docstring = self._get_ts_comment_before(node, source_bytes)

        # Small class — return as single chunk
        if token_count <= self.MAX_CHUNK_TOKENS:
            signature = f"{node.type}: {name}" if name else node.type
            return CodeChunk(
                content=content,
                chunk_type="class",
                start_line=start_line,
                end_line=end_line,
                name=name or "anonymous",
                docstring=docstring,
                signature=signature,
                filepath=filepath,
                language=self.language,
                token_count=token_count,
            )

        # Large class — split into methods
        chunks: list[CodeChunk] = []

        # Add class header chunk
        header_line = source_lines[start_line - 1]
        if docstring:
            header_content = header_line
            chunks.append(CodeChunk(
                content=header_content,
                chunk_type="class_header",
                start_line=start_line,
                end_line=start_line,
                name=name or "anonymous",
                docstring=docstring,
                signature=f"{node.type}: {name}" if name else node.type,
                filepath=filepath,
                language=self.language,
                token_count=_count_tokens(header_content),
            ))

        # Walk class body for method definitions
        body_node = node.child_by_field_name("body")
        if body_node:
            method_cursor = body_node.walk()
            if method_cursor.goto_first_child():
                while True:
                    child = method_cursor.node
                    if child.type in lang_config.function_types:
                        func_chunk = self._process_ts_function(
                            child, source_bytes, source_lines, filepath, lang_config
                        )
                        if isinstance(func_chunk, list):
                            for mc in func_chunk:
                                mc.parent_class = name
                                mc.chunk_type = "method"
                                chunks.append(mc)
                        else:
                            func_chunk.parent_class = name
                            func_chunk.chunk_type = "method"
                            chunks.append(func_chunk)
                    if not method_cursor.goto_next_sibling():
                        break

        if not chunks:
            # No methods found — return as single chunk
            signature = f"{node.type}: {name}" if name else node.type
            return CodeChunk(
                content=content,
                chunk_type="class",
                start_line=start_line,
                end_line=end_line,
                name=name or "anonymous",
                docstring=docstring,
                signature=signature,
                filepath=filepath,
                language=self.language,
                token_count=token_count,
            )

        return chunks

    def _process_ts_interface(
        self,
        node,
        source_bytes: bytes,
        source_lines: list[str],
        filepath: str,
        lang_config: TSLanguageConfig,
    ) -> CodeChunk | None:
        """Process an interface/type alias/enum node."""
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        content = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
        token_count = _count_tokens(content)
        name = self._extract_ts_node_name(node, source_bytes)
        docstring = self._get_ts_comment_before(node, source_bytes)

        if not content.strip():
            return None

        chunk_type = node.type  # e.g., "interface_declaration", "type_alias"

        return CodeChunk(
            content=content,
            chunk_type=chunk_type,
            start_line=start_line,
            end_line=end_line,
            name=name or chunk_type,
            docstring=docstring,
            signature=f"{node.type}: {name}" if name else node.type,
            filepath=filepath,
            language=self.language,
            token_count=token_count,
        )

    def _process_ts_assignment(
        self,
        node,
        source_bytes: bytes,
        source_lines: list[str],
        filepath: str,
        lang_config: TSLanguageConfig,
    ) -> CodeChunk | None:
        """Process a top-level assignment or declaration."""
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        content = source_bytes[node.start_byte:node.end_byte].decode("utf-8")

        if len(content.strip()) <= 1:
            return None

        return CodeChunk(
            content=content,
            chunk_type="assignment",
            start_line=start_line,
            end_line=end_line,
            name="module_variable",
            filepath=filepath,
            language=self.language,
            token_count=_count_tokens(content),
        )

    @staticmethod
    def _extract_ts_node_name(node, source_bytes: bytes) -> str:
        """Extract the name from a tree-sitter node using the 'name' field."""
        name_node = node.child_by_field_name("name")
        if name_node:
            return source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8")
        return ""

    @staticmethod
    def _get_ts_comment_before(node, source_bytes: bytes) -> str:
        """Get the comment/docstring immediately before a node.

        Looks for comment nodes that are direct siblings before the node.
        Captures block comments (/** ... */) and line comments (/// ...).
        """
        comments = []
        prev = node.prev_named_sibling
        while prev is not None and prev.type in ("comment", "line_comment", "block_comment"):
            text = source_bytes[prev.start_byte:prev.end_byte].decode("utf-8").strip()
            comments.insert(0, text)
            prev = prev.prev_named_sibling
            # Only look at up to 3 comment nodes before
            if len(comments) >= 3:
                break

        if comments:
            # Clean up JSDoc/Javadoc markers
            cleaned = []
            for c in comments:
                c = c.strip()
                if c.startswith("/**") and c.endswith("*/"):
                    # Multi-line doc comment: extract the text
                    lines = c.split("\n")
                    doc_lines = []
                    for line in lines:
                        line = line.strip()
                        line = line.lstrip("/*").rstrip("*/")
                        line = line.strip()
                        if line.startswith("*"):
                            line = line[1:].strip()
                        if line:
                            doc_lines.append(line)
                    cleaned.append(" ".join(doc_lines))
                elif c.startswith("///"):
                    # Rust doc comment
                    lines = c.split("\n")
                    doc_lines = [l.strip().lstrip("///").strip() for l in lines]
                    cleaned.append(" ".join(doc_lines))
                elif c.startswith("//"):
                    # Line comment
                    lines = c.split("\n")
                    doc_lines = [l.strip().lstrip("//").strip() for l in lines]
                    cleaned.append(" ".join(doc_lines))
                else:
                    cleaned.append(c)
            return "\n".join(cleaned)
        return ""

    @staticmethod
    def _get_ts_signature(node, source_lines: list[str]) -> str:
        """Extract the first line(s) of a tree-sitter node as its signature."""
        start = node.start_point[0]
        end = min(start + 5, len(source_lines))
        sig_lines = []
        for i in range(start, end):
            line = source_lines[i]
            sig_lines.append(line)
            # Stop at '{' for brace-based languages, ':' for Rust-like
            stripped = line.strip()
            if stripped.endswith("{") or stripped.endswith(":") or stripped.endswith("where"):
                break
        return "\n".join(sig_lines)


def chunk_code_file(filepath: str | Path, language: str = "python") -> list[dict[str, Any]]:
    """Convenience function: chunk a file and return dicts."""
    chunker = CastChunker(language=language)
    chunks = chunker.chunk_file(filepath)
    return [c.to_dict() for c in chunks]


def chunk_code_source(source: str, language: str = "python", filepath: str = "<unknown>") -> list[dict[str, Any]]:
    """Convenience function: chunk source code string and return dicts."""
    chunker = CastChunker(language=language)
    chunks = chunker.chunk_source(source, filepath)
    return [c.to_dict() for c in chunks]


# ═══════════════════════════════════════════════════════════════
# CLI Interface
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="cAST: AST-aware code chunking for RAG")
    parser.add_argument("path", help="File or directory to chunk")
    parser.add_argument("--output", "-o", help="Output JSON file (default: stdout)")
    parser.add_argument("--language", "-l", default="python", help="Language (default: python)")
    parser.add_argument("--stats", action="store_true", help="Print statistics")
    args = parser.parse_args()

    path = Path(args.path)

    if path.is_file():
        chunks = chunk_code_file(path, args.language)
    elif path.is_dir():
        chunker = CastChunker(args.language)
        raw_chunks = chunker.chunk_directory(path)
        chunks = [c.to_dict() for c in raw_chunks]
    else:
        print(f"Error: {path} not found")
        exit(1)

    if args.stats:
        print(f"\n{'='*50}")
        print(f"cAST Chunking Statistics")
        print(f"{'='*50}")
        print(f"Total chunks: {len(chunks)}")
        types = {}
        for c in chunks:
            t = c["chunk_type"]
            types[t] = types.get(t, 0) + 1
        for t, count in sorted(types.items(), key=lambda x: -x[1]):
            print(f"  {t}: {count}")
        avg_tokens = sum(c["token_count"] for c in chunks) / len(chunks) if chunks else 0
        print(f"Avg tokens/chunk: {avg_tokens:.0f}")
        print(f"{'='*50}\n")

    output = json.dumps(chunks, indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Wrote {len(chunks)} chunks to {args.output}")
    else:
        print(output)