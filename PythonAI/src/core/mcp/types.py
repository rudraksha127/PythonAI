"""
PythonAI MCP — Type Definitions
================================
Transport configs, connection states, tool/resource types.
Inspired by Claude Code's services/mcp/types.ts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ═══════════════════════════════════════
#  Transport Types
# ═══════════════════════════════════════


class TransportType(str, Enum):
    """MCP transport protocol types."""

    STDIO = "stdio"
    SSE = "sse"
    HTTP = "http"
    WS = "ws"
    SDK = "sdk"


class MCPScope(str, Enum):
    """Configuration scope for MCP server definitions."""

    USER = "user"
    PROJECT = "project"
    LOCAL = "local"
    ENTERPRISE = "enterprise"
    DYNAMIC = "dynamic"


# ═══════════════════════════════════════
#  Server Configurations
# ═══════════════════════════════════════


@dataclass
class StdioConfig:
    """MCP server launched via stdio subprocess."""

    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None
    type: TransportType = TransportType.STDIO


@dataclass
class SSEConfig:
    """MCP server connected via Server-Sent Events."""

    url: str
    headers: dict[str, str] | None = None
    type: TransportType = TransportType.SSE


@dataclass
class HTTPConfig:
    """MCP server connected via Streamable HTTP."""

    url: str
    headers: dict[str, str] | None = None
    type: TransportType = TransportType.HTTP


@dataclass
class WSConfig:
    """MCP server connected via WebSocket."""

    url: str
    headers: dict[str, str] | None = None
    type: TransportType = TransportType.WS


ServerConfig = StdioConfig | SSEConfig | HTTPConfig | WSConfig


# ═══════════════════════════════════════
#  Connection States
# ═══════════════════════════════════════


class ConnectionState(str, Enum):
    """State of an MCP server connection."""

    CONNECTED = "connected"
    FAILED = "failed"
    PENDING = "pending"
    DISABLED = "disabled"
    DISCONNECTED = "disconnected"


@dataclass
class ServerConnection:
    """Represents a connection to an MCP server."""

    name: str
    state: ConnectionState
    config: ServerConfig
    capabilities: dict[str, Any] = field(default_factory=dict)
    server_info: dict[str, str] | None = None
    error: str | None = None
    tools: list[MCPToolInfo] = field(default_factory=list)
    resources: list[MCPResourceInfo] = field(default_factory=list)
    _transport: Any = None  # Internal transport reference
    _client: Any = None  # Internal client reference


# ═══════════════════════════════════════
#  Tool & Resource Info
# ═══════════════════════════════════════


@dataclass
class MCPToolInfo:
    """Information about an MCP tool from a server."""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    server_name: str = ""
    annotations: dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPResourceInfo:
    """Information about an MCP resource from a server."""

    uri: str
    name: str = ""
    description: str = ""
    mime_type: str = ""
    server_name: str = ""


# ═══════════════════════════════════════
#  JSON-RPC Message Types
# ═══════════════════════════════════════


@dataclass
class JSONRPCRequest:
    """JSON-RPC 2.0 request."""

    jsonrpc: str = "2.0"
    method: str = ""
    params: dict[str, Any] | None = None
    id: str | int | None = None


@dataclass
class JSONRPCResponse:
    """JSON-RPC 2.0 response."""

    jsonrpc: str = "2.0"
    id: str | int | None = None
    result: Any = None
    error: dict[str, Any] | None = None


@dataclass
class JSONRPCNotification:
    """JSON-RPC 2.0 notification (no id)."""

    jsonrpc: str = "2.0"
    method: str = ""
    params: dict[str, Any] | None = None


# ═══════════════════════════════════════
#  Tool Result Types
# ═══════════════════════════════════════


@dataclass
class MCPToolResult:
    """Result from calling an MCP tool."""

    content: list[dict[str, Any]] = field(default_factory=list)
    is_error: bool = False
    _meta: dict[str, Any] | None = None
