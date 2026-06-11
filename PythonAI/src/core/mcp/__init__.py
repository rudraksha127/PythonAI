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

from .client import (
    MCPClient,
    call_tool,
    connect_sse,
    connect_stdio,
    list_tools,
)
from .config import (
    MCPConfigManager,
    expand_env_vars,
    find_mcp_configs,
    parse_mcp_json,
)
from .discovery import (
    discover_mcp_servers,
    find_mcp_json_files,
)
from .server import (
    MCPServer,
    create_mcp_app,
    start_mcp_server,
)
from .tool_adapter import (
    MCPToolAdapter,
    wrap_mcp_tool,
)
from .types import (
    ConnectionState,
    HTTPConfig,
    MCPResourceInfo,
    MCPScope,
    MCPToolInfo,
    ServerConfig,
    ServerConnection,
    SSEConfig,
    StdioConfig,
    TransportType,
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
