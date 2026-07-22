"""
PythonAI Core — Context Management
====================================
Re-exports ToolUseContext and provides additional context management
utilities for the tool execution pipeline.

The core ToolUseContext class is defined in src.core.tool and is the
primary context object passed to every tool call. This module provides
convenience re-exports and helpers for building/managing contexts.
"""

from __future__ import annotations

from typing import Any

from .tool import PermissionResult, ToolProgress, ToolUseContext


def make_context(
    cwd: str = ".",
    verbose: bool = False,
    debug: bool = False,
    **kwargs: Any,
) -> ToolUseContext:
    """Build a ToolUseContext with defaults for common use cases.

    Args:
        cwd: Working directory for tool execution.
        verbose: Enable verbose logging.
        debug: Enable debug mode.
        **kwargs: Additional ToolUseContext fields.

    Returns:
        A configured ToolUseContext instance.
    """
    return ToolUseContext(
        cwd=cwd,
        verbose=verbose,
        debug=debug,
        **kwargs,
    )


__all__ = [
    "ToolUseContext",
    "ToolProgress",
    "PermissionResult",
    "make_context",
]
