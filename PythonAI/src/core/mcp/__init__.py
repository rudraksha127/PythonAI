"""
PythonAI MCP Protocol Integration
==================================
Model Context Protocol (MCP) support for external tool connectivity.
Inspired by Claude Code's services/mcp/ architecture.

Provides:
  - MCP client: connect to external MCP servers (stdio, SSE, HTTP)
  - MCP server: expose PythonAI tools via MCP protocol
  - Tool adapter: wrap MCP tools as PythonAI Tool objects
  - Config management: .mcp.json, scopes, env expansion
  - CLI commands: list, add, remove, discover MCP servers
"""

from .types import (
    TransportType,
    ServerConfig,
    StdioConfig,
    SSEConfig,
    HTTPConfig,
    ConnectionState,
    ServerConnection,
    MCPToolInfo,
    MCPResourceInfo,
    MCPScope,
)
from .client import (
    MCPClient,
    connect_stdio,
    connect_sse,
    call_tool,
    list_tools,
)
from .config import (
    MCPConfigManager,
    find_mcp_configs,
    parse_mcp_json,
    expand_env_vars,
)
from .tool_adapter import (
    MCPToolAdapter,
    wrap_mcp_tool,
)
from .server import (
    MCPServer,
    create_mcp_app,
    start_mcp_server,
)
from .discovery import (
    discover_mcp_servers,
    find_mcp_json_files,
)


__all__ = [
    # Types
    "TransportType",
    "ServerConfig",
    "StdioConfig",
    "SSEConfig",
    "HTTPConfig",
    "ConnectionState",
    "ServerConnection",
    "MCPToolInfo",
    "MCPResourceInfo",
    "MCPScope",
    # Client
    "MCPClient",
    "connect_stdio",
    "connect_sse",
    "call_tool",
    "list_tools",
    # Config
    "MCPConfigManager",
    "find_mcp_configs",
    "parse_mcp_json",
    "expand_env_vars",
    # Tool adapter
    "MCPToolAdapter",
    "wrap_mcp_tool",
    # Server
    "MCPServer",
    "create_mcp_app",
    "start_mcp_server",
    # Discovery
    "discover_mcp_servers",
    "find_mcp_json_files",
]
