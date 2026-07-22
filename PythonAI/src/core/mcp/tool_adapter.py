"""
PythonAI MCP — Tool Adapter
=============================
Wrap external MCP tools as PythonAI Tool objects.
Handles tool discovery, name normalization, and call delegation.
Inspired by Claude Code's MCPTool in services/mcp/client.ts.
"""

from __future__ import annotations

import logging
from typing import Any

from .client import call_tool
from .types import ConnectionState, MCPToolInfo, ServerConnection

logger = logging.getLogger("pythonai.mcp.tool_adapter")


# ═══════════════════════════════════════
#  MCP Tool Adapter
# ═══════════════════════════════════════


def normalize_mcp_name(name: str) -> str:
    """Normalize a name for use as a tool name (lowercase, underscores)."""
    result = ""
    for ch in name:
        if ch.isalnum() or ch == "_":
            result += ch
        elif ch in ("-", " ", "."):
            result += "_"
        else:
            result += "_"
    return result.lower().strip("_")


def build_qualified_name(server_name: str, tool_name: str) -> str:
    """Build the fully-qualified MCP tool name.

    E.g.: server "filesystem", tool "read" → "mcp__filesystem__read"
    """
    ns = normalize_mcp_name(server_name)
    tn = normalize_mcp_name(tool_name)
    return f"mcp__{ns}__{tn}"


def wrap_mcp_tool(
    connection: ServerConnection,
    tool_info: MCPToolInfo,
) -> dict[str, Any]:
    """Wrap an MCP tool as a PythonAI-compatible tool definition.

    Returns a ToolDef-like dict that can be passed to build_tool().
    """
    qualified_name = build_qualified_name(connection.name, tool_info.name)

    def call_fn(input_data: dict[str, Any], context: Any) -> Any:
        """Call the MCP tool with input data."""
        from ..tool import ToolResult

        result = call_tool(connection, tool_info.name, input_data)

        if result.is_error:
            error_text = ""
            for block in result.content:
                if block.get("type") == "text":
                    error_text += block.get("text", "")
            return ToolResult(
                data={"content": result.content},
                error=error_text or "Tool call failed",
            )

        # Format content into a readable result
        text_parts = []
        for block in result.content:
            block_type = block.get("type", "text")
            if block_type == "text":
                text_parts.append(block.get("text", ""))
            elif block_type == "resource":
                resource = block.get("resource", {})
                if "text" in resource:
                    text_parts.append(resource["text"])
                elif "blob" in resource:
                    text_parts.append(f"[Binary resource: {resource.get('mimeType', 'unknown')}]")

        return ToolResult(
            data={
                "content": result.content,
                "text": "\n".join(text_parts),
            },
        )

    schema = tool_info.input_schema or {"type": "object", "properties": {}}

    return {
        "name": qualified_name,
        "description": tool_info.description or f"MCP tool: {tool_info.name} (via {connection.name})",
        "input_schema": schema,
        "call": call_fn,
        "is_readonly": tool_info.annotations.get("readOnlyHint", False),
        "is_concurrency_safe": tool_info.annotations.get("readOnlyHint", False),
        "is_destructive": tool_info.annotations.get("destructiveHint", False),
        "search_hint": f"mcp {connection.name} {tool_info.name}",
    }


class MCPToolAdapter:
    """Manages MCP tool wrapping and registration for a connected server."""

    def __init__(self, connection: ServerConnection):
        self.connection = connection
        self._wrapped_tools: list[dict[str, Any]] = []

    def get_wrapped_tools(self) -> list[dict[str, Any]]:
        """Get all tools from this server wrapped as PythonAI tool defs."""
        if self.connection.state != ConnectionState.CONNECTED:
            return []

        if not self._wrapped_tools:
            self._wrapped_tools = [wrap_mcp_tool(self.connection, tool) for tool in self.connection.tools]

        return self._wrapped_tools

    def register_all(self, registry: Any) -> int:
        """Register all MCP tools into a PythonAI ToolRegistry."""
        from ..registry import get_registry

        target = registry or get_registry()
        tools = self.get_wrapped_tools()
        count = 0

        from ..tool import build_tool

        for tool_def in tools:
            tool = build_tool(type("McpToolDef", (), tool_def)())
            target.register_mcp(tool)
            count += 1

        return count
