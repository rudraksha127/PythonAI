"""
PythonAI Tool — GrepTool
==========================
Search file contents using regex patterns.
Inspired by Claude Code's GrepTool.
"""

from __future__ import annotations

import os
import re
from typing import Any

from ..tool import (
    Tool,
    ToolResult,
    ToolUseContext,
    InputSchema,
    Parameter,
    ValidationResult,
    build_tool,
)


GrepTool = build_tool(
    type("GrepToolDef", (), {
        "name": "grep",
        "description": "Search file contents using regular expressions. Returns matching lines with context.",
        "search_hint": "search code, find patterns, regex search",
        "input_schema": InputSchema(
            pattern=Parameter(
                type="string",
                description="Regular expression pattern to search for",
                required=True,
            ),
            include=Parameter(
                type="string",
                description="Glob pattern for files to include (e.g., '*.py', '*.{ts,js}')",
                default="*",
            ),
            cwd=Parameter(
                type="string",
                description="Directory to search in (default: project root)",
            ),
            max_results=Parameter(
                type="integer",
                description="Maximum results to return (default: 50)",
                default=50,
            ),
            context_lines=Parameter(
                type="integer",
                description="Number of context lines before/after match (default: 0)",
                default=0,
            ),
            ignore_case=Parameter(
                type="boolean",
                description="Case insensitive search",
                default=False,
            ),
        ),
        "is_readonly": True,
        "is_concurrency_safe": True,
        "max_result_size_chars": 50000,
        "call": lambda input_data, context: _grep_call(input_data, context),
        "validate_input": lambda input_data, context: _grep_validate(input_data, context),
        "get_tool_use_summary": lambda input_data: f"/{input_data.get('pattern', '')}/" if input_data else None,
        "get_activity_description": lambda input_data: f"Searching for {input_data.get('pattern', '')}" if input_data else None,
    })
)


def _grep_validate(input_data: dict[str, Any],
                   context: ToolUseContext) -> ValidationResult:
    pattern = input_data.get("pattern", "")
    if not pattern:
        return ValidationResult(success=False, message="pattern is required", error_code=1)
    try:
        re.compile(pattern)
    except re.error as e:
        return ValidationResult(success=False, message=f"Invalid regex: {e}", error_code=2)
    return ValidationResult(success=True)


def _grep_call(input_data: dict[str, Any],
               context: ToolUseContext) -> ToolResult:
    pattern_str = input_data.get("pattern", "")
    include = input_data.get("include", "*")
    cwd = input_data.get("cwd") or context.cwd or os.getcwd()
    max_results = min(input_data.get("max_results", 50), 200)
    context_lines = input_data.get("context_lines", 0)
    ignore_case = input_data.get("ignore_case", False)

    cwd = os.path.normpath(os.path.expanduser(str(cwd)))

    # Compile regex
    flags = re.IGNORECASE if ignore_case else 0
    try:
        regex = re.compile(pattern_str, flags)
    except re.error as e:
        return ToolResult(data={"error": f"Invalid regex: {e}"}, error=f"Invalid regex: {e}")

    # Convert include glob to a simple extension filter
    # e.g., "*.py" -> ".py", "*.{ts,js}" -> [".ts", ".js"]
    include_extensions = set()
    if include and include != "*":
        for part in include.replace("{", "").replace("}", "").split(","):
            part = part.strip().replace("*", "")
            if part.startswith("."):
                include_extensions.add(part)

    matches: list[dict[str, Any]] = []
    total_files_searched = 0

    try:
        for root, dirs, files in os.walk(cwd):
            # Skip hidden directories and common non-code dirs
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in
                       {"node_modules", "__pycache__", ".git", ".venv", "venv",
                        "dist", "build", ".tox", "eggs"}]

            for file in files:
                if len(matches) >= max_results:
                    break

                # Filter by extension
                if include_extensions:
                    ext = os.path.splitext(file)[1].lower()
                    if ext not in include_extensions:
                        continue

                filepath = os.path.join(root, file)

                # Skip binary files by extension
                binary_exts = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
                              ".woff", ".woff2", ".ttf", ".eot", ".o", ".pyc",
                              ".pyd", ".so", ".dll", ".dylib", ".exe"}
                if os.path.splitext(file)[1].lower() in binary_exts:
                    continue

                total_files_searched += 1

                try:
                    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()
                except Exception:
                    continue

                for i, line in enumerate(lines):
                    if regex.search(line):
                        context_start = max(0, i - context_lines)
                        context_end = min(len(lines), i + context_lines + 1)
                        context_section = "".join(lines[context_start:context_end])
                        rel_path = os.path.relpath(filepath, cwd)

                        matches.append({
                            "file": rel_path,
                            "line_number": i + 1,
                            "line": line.rstrip("\n\r"),
                            "context": context_section.rstrip(),
                        })

                        if len(matches) >= max_results:
                            break

            if len(matches) >= max_results:
                break

        return ToolResult(data={
            "pattern": pattern_str,
            "total_matches": len(matches),
            "total_files_searched": total_files_searched,
            "matches": matches,
            "cwd": cwd,
            "message": f"Found {len(matches)} matches in {total_files_searched} files",
        })

    except Exception as e:
        return ToolResult(data={"error": f"Grep failed: {e}"}, error=f"Grep failed: {e}")
