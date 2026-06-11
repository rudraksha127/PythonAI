"""
PythonAI Tool — GlobTool
==========================
Search for files matching glob patterns.
Inspired by Claude Code's GlobTool.
"""

from __future__ import annotations

import glob as glob_module
import os
from typing import Any

from ..tool import (
    InputSchema,
    Parameter,
    ToolResult,
    ToolUseContext,
    ValidationResult,
    build_tool,
)

GlobTool = build_tool(
    type("GlobToolDef", (), {
        "name": "glob",
        "description": "Search for files and directories matching a glob pattern.",
        "search_hint": "find files, search paths, file search",
        "input_schema": InputSchema(
            pattern=Parameter(
                type="string",
                description="Glob pattern to match (e.g., '**/*.py', 'src/**/*.ts')",
                required=True,
            ),
            cwd=Parameter(
                type="string",
                description="Working directory to search from (default: project root)",
            ),
            max_results=Parameter(
                type="integer",
                description="Maximum number of results to return (default: 100)",
                default=100,
            ),
        ),
        "is_readonly": True,
        "is_concurrency_safe": True,
        "max_result_size_chars": 10000,
        "call": lambda input_data, context: _glob_call(input_data, context),
        "validate_input": lambda input_data, context: _glob_validate(input_data, context),
        "get_tool_use_summary": lambda input_data: input_data.get("pattern", "") if input_data else None,
        "get_activity_description": lambda input_data: f"Searching {input_data.get('pattern', '')}" if input_data else None,
    })
)


def _glob_validate(input_data: dict[str, Any],
                   context: ToolUseContext) -> ValidationResult:
    pattern = input_data.get("pattern", "")
    if not pattern:
        return ValidationResult(success=False, message="pattern is required", error_code=1)
    return ValidationResult(success=True)


def _glob_call(input_data: dict[str, Any],
               context: ToolUseContext) -> ToolResult:
    pattern = input_data.get("pattern", "")
    cwd = input_data.get("cwd") or context.cwd or os.getcwd()
    max_results = min(input_data.get("max_results", 100), 500)

    cwd = os.path.normpath(os.path.expanduser(str(cwd)))

    # Handle both forward and backward slashes
    pattern = pattern.replace("\\", "/")

    # If pattern is absolute, use it directly; otherwise join with cwd
    if os.path.isabs(pattern):
        search_path = pattern
    else:
        search_path = os.path.join(cwd, pattern)

    search_path = search_path.replace("\\", "/")

    try:
        results = glob_module.glob(search_path, recursive=True)

        # Sort by modification time (most recent first)
        def get_mtime(p):
            try:
                return os.path.getmtime(p)
            except OSError:
                return 0

        results.sort(key=get_mtime, reverse=True)

        # Limit and format
        total = len(results)
        results = results[:max_results]

        # Categorize
        files = []
        dirs = []
        for r in results:
            if os.path.isdir(r):
                dirs.append(r)
            else:
                size = os.path.getsize(r) if os.path.exists(r) else 0
                files.append({"path": r, "size": size})

        return ToolResult(data={
            "pattern": pattern,
            "total_matches": total,
            "returned": len(results),
            "files": files,
            "directories": dirs,
            "cwd": cwd,
            "message": f"Found {total} matches, showing {len(results)}",
        })

    except Exception as e:
        return ToolResult(data={"error": f"Glob failed: {e}", "pattern": pattern},
                          error=f"Glob failed: {e}")
