"""
PythonAI Tool — FileWriteTool
===============================
Write content to files. Creates directories if needed.
Inspired by Claude Code's FileWriteTool.
"""

from __future__ import annotations

import os
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


def _write_file(file_path: str, content: str, create_dirs: bool = True) -> str:
    """Write content to a file. Returns the absolute path written."""
    file_path = os.path.normpath(os.path.expanduser(file_path))

    if not os.path.isabs(file_path):
        file_path = os.path.abspath(file_path)

    if create_dirs:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return file_path


FileWriteTool = build_tool(
    type("FileWriteToolDef", (), {
        "name": "write",
        "description": "Write content to a file. Creates parent directories automatically.",
        "search_hint": "create files, save content",
        "input_schema": InputSchema(
            file_path=Parameter(
                type="string",
                description="Path to write the file to (absolute or relative)",
                required=True,
            ),
            content=Parameter(
                type="string",
                description="Content to write to the file",
                required=True,
            ),
        ),
        "is_destructive": True,
        "is_concurrency_safe": False,
        "max_result_size_chars": 1000,
        "call": lambda input_data, context: _write_call(input_data, context),
        "validate_input": lambda input_data, context: _write_validate(input_data, context),
        "get_tool_use_summary": lambda input_data: input_data.get("file_path", "") if input_data else None,
        "get_activity_description": lambda input_data: f"Writing {input_data.get('file_path', '')}" if input_data else None,
    })
)


def _write_validate(input_data: dict[str, Any],
                    context: ToolUseContext) -> ValidationResult:
    file_path = input_data.get("file_path", "")
    if not file_path:
        return ValidationResult(success=False, message="file_path is required", error_code=1)

    content = input_data.get("content", "")
    if len(content) > 1000000:  # 1MB limit
        return ValidationResult(success=False, message="Content too large (max 1MB)", error_code=2)

    return ValidationResult(success=True)


def _write_call(input_data: dict[str, Any],
                context: ToolUseContext) -> ToolResult:
    file_path = input_data.get("file_path", "")
    content = input_data.get("content", "")

    try:
        path = _write_file(file_path, content)
        return ToolResult(data={
            "file_path": path,
            "size_bytes": len(content.encode("utf-8")),
            "message": f"Successfully wrote {len(content)} chars to {path}",
        })
    except Exception as e:
        return ToolResult(data={"error": f"Failed to write file: {e}"},
                          error=f"Failed to write file: {e}")
