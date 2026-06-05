"""
PythonAI Core — Tool System & Execution Engine
================================================
Inspired by Claude Code's Tool.ts architecture.
Provides typed tools, permission system, tool-calling loop, and multi-provider routing.
"""

from .tool import (
    Tool,
    ToolResult,
    ToolUseContext,
    PermissionResult,
    ValidationResult,
    ToolProgress,
    build_tool,
    TOOL_DEFAULTS,
)
from .registry import (
    ToolRegistry,
    get_all_tools,
    get_agent_tools,
    get_readonly_tools,
    assemble_tool_pool,
)
from .engine import ToolCallingEngine

__all__ = [
    "Tool",
    "ToolResult",
    "ToolUseContext",
    "PermissionResult",
    "ValidationResult",
    "ToolProgress",
    "build_tool",
    "TOOL_DEFAULTS",
    "ToolRegistry",
    "get_all_tools",
    "get_agent_tools",
    "get_readonly_tools",
    "assemble_tool_pool",
    "ToolCallingEngine",
]
