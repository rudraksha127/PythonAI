"""
Enhanced Code Parser — Extract and Analyze Code Blocks
======================================================

Advanced parser for extracting code blocks, inline code, and
AST-based semantic structures from text/markdown.

Features:
- Multi-language code block extraction
- Inline code extraction
- Python AST-based parsing for functions, classes, and imports
- Error-tolerant processing
- Metadata generation (line counts, languages, etc.)

Usage:
    from src.utils.code_parser import extract_code_blocks, parse_python_ast

    blocks = extract_code_blocks("Some text with ```python\nprint(1)```")
    print(blocks[0].language)  # "python"
    
    ast_info = parse_python_ast("import os\n\ndef foo(): pass")
    print(ast_info["functions"])  # ["foo"]
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class CodeBlock:
    """Represents an extracted code block with metadata."""

    code: str
    language: str = ""
    start_idx: int = -1
    end_idx: int = -1
    line_count: int = 0
    is_inline: bool = False

    def __post_init__(self):
        self.line_count = len(self.code.splitlines())


def extract_code_blocks(text: str) -> list[CodeBlock]:
    """
    Extract fenced code blocks and inline code from markdown text.

    Returns:
        List of CodeBlock objects.
    """
    if not text:
        return []

    blocks: list[CodeBlock] = []

    # 1. Extract fenced code blocks: ```language\n code \n```
    fenced_pattern = re.compile(r"```([a-zA-Z0-9_+\-#]*)\n(.*?)```", re.DOTALL)
    for match in fenced_pattern.finditer(text):
        language = match.group(1).strip().lower()
        code = match.group(2).strip()

        if code:
            blocks.append(
                CodeBlock(
                    code=code,
                    language=language,
                    start_idx=match.start(),
                    end_idx=match.end(),
                    is_inline=False,
                )
            )

    # 2. Extract inline code: `code`
    # Ensure it's not part of a larger fenced block by checking boundaries
    inline_pattern = re.compile(r"(?<!`)`([^`\n]{1,100})`(?!`)")
    for match in inline_pattern.finditer(text):
        code = match.group(1).strip()
        start, end = match.span()

        # Skip if this inline match falls inside any fenced block
        inside_fenced = False
        for fb in blocks:
            if not fb.is_inline and fb.start_idx <= start <= fb.end_idx:
                inside_fenced = True
                break

        if not inside_fenced and code:
            blocks.append(
                CodeBlock(
                    code=code,
                    language="",
                    start_idx=start,
                    end_idx=end,
                    is_inline=True,
                )
            )

    # Sort by appearance in text
    blocks.sort(key=lambda x: x.start_idx)
    return blocks


def parse_python_ast(code: str) -> dict[str, Any]:
    """
    Parse Python code into AST to extract structural information.

    Tolerates SyntaxErrors by returning partial/empty info gracefully.

    Returns:
        Dict with 'imports', 'functions', 'classes', 'is_valid', 'error'
    """
    result = {
        "imports": [],
        "functions": [],
        "classes": [],
        "is_valid": False,
        "error": None,
    }

    if not code or not code.strip():
        return result

    try:
        tree = ast.parse(code)
        result["is_valid"] = True

        for node in ast.walk(tree):
            # Extract standard imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    result["imports"].append(alias.name)

            # Extract from ... import ...
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    result["imports"].append(f"{module}.{alias.name}")

            # Extract top-level and nested functions
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                result["functions"].append(node.name)

            # Extract classes
            elif isinstance(node, ast.ClassDef):
                result["classes"].append(node.name)

        # Deduplicate while preserving order (using dict)
        result["imports"] = list(dict.fromkeys(result["imports"]))

    except SyntaxError as e:
        result["error"] = str(e)
    except Exception as e:
        result["error"] = f"Unexpected AST error: {e}"

    return result


def extract_and_analyze(text: str) -> dict[str, Any]:
    """
    Extract code blocks from text and run AST analysis on Python blocks.

    Returns:
        Dict with detailed metadata for each block.
    """
    blocks = extract_code_blocks(text)
    analyzed_blocks = []

    for idx, block in enumerate(blocks):
        block_info = {
            "id": idx,
            "code": block.code,
            "language": block.language,
            "is_inline": block.is_inline,
            "line_count": block.line_count,
        }

        # Auto-detect language if missing but syntax looks like Python
        is_python_like = block.language in ("python", "py", "") and not block.is_inline

        if is_python_like:
            ast_info = parse_python_ast(block.code)
            # If it was explicitly marked as python, or if it parses validly
            if block.language in ("python", "py") or ast_info["is_valid"]:
                block_info["language"] = "python"
                block_info["ast"] = ast_info

        analyzed_blocks.append(block_info)

    return {
        "total_blocks": len(blocks),
        "fenced_blocks": sum(1 for b in blocks if not b.is_inline),
        "inline_blocks": sum(1 for b in blocks if b.is_inline),
        "blocks": analyzed_blocks,
    }
