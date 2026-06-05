"""
PythonAI Tool — FileReadTool
==============================
Read files with line numbers, offset/limit, and token budgeting.
Inspired by Claude Code's FileReadTool.
"""

from __future__ import annotations

import os
import traceback
from typing import Any

from ..tool import (
    Tool,
    ToolResult,
    ToolUseContext,
    InputSchema,
    Parameter,
    ValidationResult,
    PermissionResult,
    PermissionDecision,
    build_tool,
)

# Extensions we can read as text
TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".json", ".xml",
    ".yaml", ".yml", ".md", ".txt", ".cfg", ".ini", ".conf", ".env",
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd",
    ".c", ".cpp", ".h", ".hpp", ".java", ".go", ".rs", ".rb", ".php",
    ".swift", ".kt", ".kts", ".scala", ".clj", ".cljs", ".ex", ".exs",
    ".sql", ".r", ".m", ".mm", ".dart", ".lua", ".pl", ".pm", ".t",
    ".vue", ".svelte", ".astro", ".ejs", ".hbs", ".mustache",
    ".toml", ".lock", ".gitignore", ".dockerignore",
    ".csv", ".tsv", ".log",
    ".gradle", ".properties", ".plist",
}


def _is_text_file(filepath: str) -> bool:
    """Check if a file is likely a text file based on extension."""
    ext = os.path.splitext(filepath)[1].lower()
    return ext in TEXT_EXTENSIONS or not ext  # No extension = try to read


def _read_file_lines(filepath: str, offset: int = 1, limit: int | None = None,
                     max_size: int = 5 * 1024 * 1024) -> tuple[list[str], int, int]:
    """Read lines from a file with offset and limit.

    Returns: (lines, total_lines, total_bytes)
    """
    total_bytes = os.path.getsize(filepath)
    if total_bytes > max_size:
        raise ValueError(
            f"File too large ({total_bytes / 1024 / 1024:.1f} MB). "
            f"Maximum: {max_size / 1024 / 1024:.1f} MB. "
            f"Use offset/limit to read portions, or use bash with tools like head/tail."
        )

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()

    total_lines = len(all_lines)

    # Adjust offset (1-indexed to 0-indexed)
    start = max(0, offset - 1)
    if limit is not None:
        end = min(start + limit, total_lines)
    else:
        end = total_lines

    lines = all_lines[start:end]

    return lines, total_lines, total_bytes


FileReadTool = build_tool(
    type("FileReadToolDef", (), {
        "name": "read",
        "description": "Read a file with line numbers. Use offset/limit for large files.",
        "search_hint": "read files, view source code",
        "input_schema": InputSchema(
            file_path=Parameter(
                type="string",
                description="Absolute or relative path to the file to read",
                required=True,
            ),
            offset=Parameter(
                type="integer",
                description="Line number to start reading from (1-indexed, default: 1)",
                default=1,
            ),
            limit=Parameter(
                type="integer",
                description="Number of lines to read (default: read entire file)",
            ),
        ),
        "is_readonly": True,
        "is_concurrency_safe": True,
        "max_result_size_chars": 50000,
        "call": lambda input_data, context: _read_call(input_data, context),
        "validate_input": lambda input_data, context: _read_validate(input_data, context),
        "get_tool_use_summary": lambda input_data: input_data.get("file_path", "") if input_data else None,
        "get_activity_description": lambda input_data: f"Reading {input_data.get('file_path', '')}" if input_data else None,
    })
)


def _read_validate(input_data: dict[str, Any],
                   context: ToolUseContext) -> ValidationResult:
    file_path = input_data.get("file_path", "")
    if not file_path:
        return ValidationResult(success=False, message="file_path is required", error_code=1)

    if not os.path.exists(file_path):
        return ValidationResult(success=False, message=f"File not found: {file_path}", error_code=2)

    if os.path.isdir(file_path):
        return ValidationResult(success=False, message=f"'{file_path}' is a directory, not a file", error_code=3)

    return ValidationResult(success=True)


def _read_call(input_data: dict[str, Any],
               context: ToolUseContext) -> ToolResult:
    file_path = input_data.get("file_path", "")
    offset = input_data.get("offset", 1)
    limit = input_data.get("limit")

    # Resolve path
    if not os.path.isabs(file_path):
        file_path = os.path.join(context.cwd or os.getcwd(), file_path)
    file_path = os.path.normpath(os.path.expanduser(file_path))

    max_size = (context.file_reading_limits.get("max_size_bytes", 5 * 1024 * 1024))

    try:
        lines, total_lines, total_bytes = _read_file_lines(
            file_path, offset, limit, max_size
        )

        # Format with line numbers
        num_width = len(str(total_lines))
        content_lines = []
        for i, line in enumerate(lines):
            line_num = offset + i
            content_lines.append(f"{line_num:>{num_width}} |{line}")

        content = "".join(content_lines)

        result = {
            "file_path": file_path,
            "content": content,
            "num_lines": len(lines),
            "start_line": offset,
            "total_lines": total_lines,
            "size_bytes": total_bytes,
        }

        return ToolResult(data=result)

    except FileNotFoundError:
        return ToolResult(data={"error": f"File not found: {file_path}"},
                          error=f"File not found: {file_path}")
    except IsADirectoryError:
        return ToolResult(data={"error": f"'{file_path}' is a directory"},
                          error=f"'{file_path}' is a directory")
    except ValueError as e:
        return ToolResult(data={"error": str(e)}, error=str(e))
    except Exception as e:
        return ToolResult(data={"error": f"Error reading file: {e}"},
                          error=f"Error reading file: {e}")
