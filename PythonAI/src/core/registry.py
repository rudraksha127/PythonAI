"""
PythonAI Core — Tool Registry
===============================
Inspired by Claude Code's tools.ts (getAllBaseTools, assembleToolPool).
Central registry for all tools with filtering and assembly logic.
"""

from __future__ import annotations

from typing import Any, cast

from .tool import PermissionDecision, Tool, ToolUseContext


class ToolRegistry:
    """Central registry for all PythonAI tools.

    Functions like Claude Code's tools.ts — register, filter, assemble tools.
    """

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._mcp_tools: dict[str, Tool] = {}

    # ── Registration ─────────────────────────────────────────

    def register(self, tool: Tool) -> None:
        """Register a built-in tool."""
        self._tools[tool.name] = tool
        for alias in tool.aliases:
            self._tools[alias] = tool

    def register_mcp(self, tool: Tool) -> None:
        """Register an MCP tool (external tool via MCP protocol).

        MCP tools are prefixed with 'mcp__' namespace to avoid
        collision with built-in tools.
        """
        self._mcp_tools[tool.name] = tool

    def register_mcp_server(self, connection: Any) -> int:
        """Register all tools from an MCP server connection.

        Args:
            connection: A ServerConnection object from mcp.client

        Returns:
            Number of MCP tools registered
        """
        from .mcp.tool_adapter import MCPToolAdapter
        adapter = MCPToolAdapter(connection)
        result = adapter.register_all(self)
        return cast(int, result)

    def unregister(self, name: str) -> None:
        """Unregister a tool by name."""
        self._tools.pop(name, None)
        self._mcp_tools.pop(name, None)

    def unregister_mcp_server(self, server_name: str) -> int:
        """Unregister all tools from an MCP server.

        Args:
            server_name: Name of the MCP server whose tools to remove

        Returns:
            Number of tools removed
        """
        prefix = f"mcp__{server_name}__"
        to_remove = [
            name for name in self._mcp_tools
            if name.startswith(prefix)
        ]
        for name in to_remove:
            self._mcp_tools.pop(name, None)
        return len(to_remove)

    def get(self, name: str) -> Tool | None:
        """Get a tool by name (built-in first, then MCP)."""
        return self._tools.get(name) or self._mcp_tools.get(name)

    def has_tool(self, name: str) -> bool:
        """Check if a tool exists."""
        return name in self._tools or name in self._mcp_tools

    # ── Listing ───────────────────────────────────────────────

    def list_tools(self) -> list[dict[str, Any]]:
        """List all registered tools with metadata."""
        tools = []
        for tool in self._tools.values():
            if tool.is_enabled():
                tools.append(tool.to_dict())
        for tool in self._mcp_tools.values():
            if tool.is_enabled():
                info = tool.to_dict()
                info["is_mcp"] = True
                tools.append(info)
        return tools

    def list_builtin(self) -> list[Tool]:
        """Get all enabled built-in tools."""
        return [t for t in self._tools.values() if t.is_enabled()]

    def list_mcp(self) -> list[Tool]:
        """Get all enabled MCP tools."""
        return [t for t in self._mcp_tools.values() if t.is_enabled()]

    def list_all(self) -> list[Tool]:
        """Get all enabled tools (built-in + MCP)."""
        return self.list_builtin() + self.list_mcp()

    # ── Filtering ─────────────────────────────────────────────

    def get_readonly(self) -> list[Tool]:
        """Get all read-only tools."""
        return [t for t in self.list_all() if t.is_readonly()]

    def get_writable(self) -> list[Tool]:
        """Get all writable tools."""
        return [t for t in self.list_all() if not t.is_readonly()]

    def get_concurrency_safe(self) -> list[Tool]:
        """Get all concurrency-safe tools."""
        return [t for t in self.list_all() if t.is_concurrency_safe()]

    def get_agent_tools(self) -> list[Tool]:
        """Get tools suitable for sub-agents (readonly + safe)."""
        return [t for t in self.list_all()
                if t.is_readonly() or t.is_concurrency_safe()]

    def filter_by_permissions(self, tools: list[Tool],
                              context: ToolUseContext) -> list[Tool]:
        """Filter tools by permission context."""
        allowed = []
        for tool in tools:
            result = tool.check_permissions({}, context)
            if result.behavior in (PermissionDecision.ALLOW,
                                   PermissionDecision.ALWAYS_ALLOW):
                allowed.append(tool)
        return allowed

    def assemble_pool(self, context: ToolUseContext | None = None,
                      include_mcp: bool = True) -> list[Tool]:
        """Assemble the full tool pool, sorted by name.

        Like Claude Code's assembleToolPool().
        """
        tools = self.list_builtin()
        if include_mcp:
            tools.extend(self.list_mcp())
        # Deduplicate by name, keep first occurrence
        seen: set[str] = set()
        deduped = []
        for tool in tools:
            if tool.name not in seen:
                seen.add(tool.name)
                deduped.append(tool)
        # Sort by name
        deduped.sort(key=lambda t: t.name)
        # Filter by permissions if context provided
        if context:
            deduped = self.filter_by_permissions(deduped, context)
        return deduped

    # ── Counts ────────────────────────────────────────────────

    @property
    def builtin_count(self) -> int:
        return len([t for t in self._tools.values() if t.is_enabled()])

    @property
    def mcp_count(self) -> int:
        return len([t for t in self._mcp_tools.values() if t.is_enabled()])

    @property
    def total_count(self) -> int:
        return self.builtin_count + self.mcp_count

    def __repr__(self) -> str:
        return f"ToolRegistry({self.builtin_count} built-in, {self.mcp_count} MCP)"


# ═══════════════════════════════════════
#  Global Registry (singleton pattern)
# ═══════════════════════════════════════

_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    """Get the global tool registry, creating it if needed."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def get_all_tools() -> list[Tool]:
    """Get all registered tools."""
    return get_registry().list_all()


def get_agent_tools() -> list[Tool]:
    """Get tools for sub-agents."""
    return get_registry().get_agent_tools()


def get_readonly_tools() -> list[Tool]:
    """Get read-only tools."""
    return get_registry().get_readonly()


def assemble_tool_pool(context: ToolUseContext | None = None,
                       include_mcp: bool = True) -> list[Tool]:
    """Assemble complete tool pool."""
    return get_registry().assemble_pool(context, include_mcp)
