"""
PythonAI MCP — Transport Module (Backward Compatibility)
=========================================================
Re-exports transport-related types from .types for backward
compatibility after a refactoring consolidated all types into
a single module.

New code should import directly from .types instead.
"""

from __future__ import annotations

from .types import (
    ConnectionState,
    HTTPConfig,
    MCPScope,
    ServerConfig,
    ServerConnection,
    SSEConfig,
    StdioConfig,
    TransportType,
)

__all__ = [
    "TransportType",
    "ServerConfig",
    "StdioConfig",
    "SSEConfig",
    "HTTPConfig",
    "ConnectionState",
    "ServerConnection",
    "MCPScope",
]
