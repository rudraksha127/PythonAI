"""
PythonAI Tool — BashTool
=========================
Execute shell commands with timeout and security restrictions.
Inspired by Claude Code's BashTool.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any

from ..tool import (
    InputSchema,
    Parameter,
    ToolResult,
    ToolUseContext,
    ValidationResult,
    build_tool,
)


def _run_bash(command: str, timeout: int = 30,
              cwd: str | None = None,
              env: dict[str, str] | None = None) -> tuple[str, str, int]:
    """Run a bash command and return (stdout, stderr, returncode)."""
    # Security: block interactive commands
    dangerous_commands = ["sudo", "su", "passwd", "ssh", "scp", "sftp",
                          "vi", "vim", "nano", "emacs", "less", "more",
                          "top", "htop", "watch"]

    first_word = command.strip().split()[0].lower() if command.strip() else ""
    if first_word in dangerous_commands:
        return "", f"Blocked: '{first_word}' is not allowed for security reasons.", 1

    try:
        process = subprocess.Popen(
            command,
            shell=True,
            cwd=cwd or os.getcwd(),
            env=env or os.environ.copy(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            stdout, stderr = process.communicate(timeout=timeout)
            return stdout, stderr, process.returncode
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            return stdout, f"Command timed out after {timeout}s\n{stderr}", -1

    except Exception as e:
        return "", str(e), -1


# Tool definition
BashTool = build_tool(
    type("BashToolDef", (), {
        "name": "bash",
        "description": "Execute a shell command with timeout. Returns stdout, stderr, and exit code.",
        "search_hint": "run shell commands, terminal, CLI",
        "input_schema": InputSchema(
            command=Parameter(
                type="string",
                description="The shell command to execute",
                required=True,
            ),
            timeout=Parameter(
                type="integer",
                description="Timeout in seconds (default: 30, max: 300)",
                default=30,
            ),
            cwd=Parameter(
                type="string",
                description="Working directory (default: project root)",
            ),
        ),
        "is_destructive": True,
        "is_concurrency_safe": False,
        "max_result_size_chars": 50000,
        "call": lambda input_data, context: _bash_call(input_data, context),
        "validate_input": lambda input_data, context: _bash_validate(input_data, context),
        "get_tool_use_summary": lambda input_data: input_data.get("command", "")[:60] if input_data else None,
        "get_activity_description": lambda input_data: f"Running: {input_data.get('command', '')[:40]}..." if input_data else None,
    })
)


def _bash_validate(input_data: dict[str, Any],
                   context: ToolUseContext) -> ValidationResult:
    command = input_data.get("command", "")
    if not command or not command.strip():
        return ValidationResult(success=False, message="Command cannot be empty", error_code=1)
    if len(command) > 10000:
        return ValidationResult(success=False, message="Command too long (max 10000 chars)", error_code=2)
    return ValidationResult(success=True)


def _bash_call(input_data: dict[str, Any],
               context: ToolUseContext) -> ToolResult:
    command = input_data.get("command", "")
    timeout = min(input_data.get("timeout", 30), 300)
    cwd = input_data.get("cwd") or context.cwd or None

    stdout, stderr, returncode = _run_bash(command, timeout, cwd, context.env_vars)

    # Truncate if too long
    max_chars = 40000
    if len(stdout) > max_chars:
        stdout = stdout[:max_chars] + f"\n... (truncated, {len(stdout)} total chars)"

    result = {
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": returncode,
        "command": command,
    }

    if returncode != 0:
        result["error"] = f"Command exited with code {returncode}"

    return ToolResult(data=result, error=result.get("error"))
