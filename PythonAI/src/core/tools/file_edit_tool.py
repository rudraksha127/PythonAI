"""
PythonAI Tool — FileEditTool
==============================
Make targeted string replacements in files.
Inspired by Claude Code's FileEditTool.
"""

from __future__ import annotations

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

FileEditTool = build_tool(
    type(
        "FileEditToolDef",
        (),
        {
            "name": "edit",
            "description": "Make a targeted string replacement in an existing file. Use exact string matching.",
            "search_hint": "modify files, replace text, patch",
            "input_schema": InputSchema(
                file_path=Parameter(
                    type="string",
                    description="Path to the file to edit (absolute or relative)",
                    required=True,
                ),
                old_string=Parameter(
                    type="string",
                    description="The exact text to find and replace (must match exactly)",
                    required=True,
                ),
                new_string=Parameter(
                    type="string",
                    description="The new text to replace with",
                    required=True,
                ),
            ),
            "is_destructive": True,
            "is_concurrency_safe": False,
            "max_result_size_chars": 2000,
            "call": lambda input_data, context: _edit_call(input_data, context),
            "validate_input": lambda input_data, context: _edit_validate(input_data, context),
            "get_tool_use_summary": lambda input_data: input_data.get("file_path", "") if input_data else None,
            "get_activity_description": lambda input_data: (
                f"Editing {input_data.get('file_path', '')}" if input_data else None
            ),
        },
    )
)


def _edit_validate(input_data: dict[str, Any], context: ToolUseContext) -> ValidationResult:
    file_path = input_data.get("file_path", "")
    if not file_path:
        return ValidationResult(success=False, message="file_path is required", error_code=1)

    if not os.path.exists(file_path):
        return ValidationResult(success=False, message=f"File not found: {file_path}", error_code=2)

    if os.path.isdir(file_path):
        return ValidationResult(success=False, message=f"'{file_path}' is a directory", error_code=3)

    old_string = input_data.get("old_string", "")
    if not old_string:
        return ValidationResult(success=False, message="old_string is required", error_code=4)

    return ValidationResult(success=True)


def _edit_call(input_data: dict[str, Any], context: ToolUseContext) -> ToolResult:
    file_path = input_data.get("file_path", "")
    old_string = input_data.get("old_string", "")
    new_string = input_data.get("new_string", "")

    # Resolve path
    if not os.path.isabs(file_path):
        file_path = os.path.join(context.cwd or os.getcwd(), file_path)
    file_path = os.path.normpath(os.path.expanduser(file_path))

    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        if old_string not in content:
            return ToolResult(
                data={
                    "error": f"Could not find old_string in {file_path}",
                    "hint": "Make sure the old_string matches the file content exactly, including whitespace.",
                },
                error="old_string not found in file",
            )

        new_content = content.replace(old_string, new_string, 1)
        if new_content == content:
            return ToolResult(
                data={"error": "No changes made (old_string == new_string or both empty)"},
                error="No changes made",
            )

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return ToolResult(
            data={
                "file_path": file_path,
                "old_size_chars": len(old_string),
                "new_size_chars": len(new_string),
                "diff": f"-{len(old_string)} chars, +{len(new_string)} chars",
                "message": f"Applied edit to {file_path}",
            }
        )

    except FileNotFoundError:
        return ToolResult(data={"error": f"File not found: {file_path}"}, error=f"File not found: {file_path}")
    except Exception as e:
        return ToolResult(data={"error": f"Edit failed: {e}"}, error=f"Edit failed: {e}")
