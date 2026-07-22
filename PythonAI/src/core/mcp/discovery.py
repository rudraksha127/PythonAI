"""
PythonAI MCP — Server Discovery
=================================
Find and connect to MCP servers from local configuration.
Inspired by Claude Code's services/mcp/config.ts discovery patterns.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from .client import MCPClient
from .config import MCPConfigManager, parse_mcp_json
from .types import (
    ConnectionState,
    ServerConfig,
    ServerConnection,
    StdioConfig,
)

logger = logging.getLogger("pythonai.mcp.discovery")


# ═══════════════════════════════════════
#  File Discovery
# ═══════════════════════════════════════


def find_mcp_json_files(start_dir: str | None = None) -> list[Path]:
    """Find all .mcp.json files walking up from start_dir."""
    start = Path(start_dir or os.getcwd())
    found: list[Path] = []

    current = start
    while current != current.parent:
        mcp_json = current / ".mcp.json"
        if mcp_json.exists():
            found.append(mcp_json)
        current = current.parent

    # Also check standard config dirs
    for d in [
        Path.home() / ".config" / "pythonai",
        Path.home() / ".pythonai",
    ]:
        mcp_json = d / "mcp.json"
        if mcp_json.exists():
            found.append(mcp_json)

    return found


def discover_mcp_servers(
    project_dir: str | None = None,
    enable_auto_discovery: bool = True,
) -> dict[str, ServerConnection]:
    """Discover and connect to all configured MCP servers.

    Returns dict of server_name -> ServerConnection (some may be FAILED).
    """

    config_mgr = MCPConfigManager(project_dir)
    servers = config_mgr.get_servers()
    connections: dict[str, ServerConnection] = {}

    client = MCPClient()

    for name, config in servers.items():
        logger.info(f"Connecting to MCP server: {name} ({type(config).__name__})")
        connection = client.connect(config, name=name)
        connections[name] = connection

        if connection.state == ConnectionState.CONNECTED:
            logger.info(
                f"  Connected to '{name}': {len(connection.tools)} tools, {len(connection.resources)} resources"
            )
        else:
            logger.warning(f"  Failed to connect '{name}': {connection.error}")

    return connections


# ═══════════════════════════════════════
#  Ollama MCP Discovery
# ═══════════════════════════════════════


def discover_ollama_mcp() -> dict[str, ServerConfig] | None:
    """Check if Ollama is running and expose it as an MCP server.

    Returns a config dict or None if Ollama is not available.
    This is experimental — Ollama natively uses OpenAI-compatible API,
    but some MCP clients need an MCP protocol bridge.
    """
    try:
        import httpx

        resp = httpx.get("http://127.0.0.1:11434/api/tags", timeout=2.0)
        if resp.status_code != 200:
            return None

        models = resp.json().get("models", [])
        if not models:
            return None

        # Return the first model as an MCP-compatible server config
        # (actual Ollama MCP bridge needed is external)
        return {}
    except Exception:
        return None


# ═══════════════════════════════════════
#  Environment-based Discovery
# ═══════════════════════════════════════


def discover_from_env() -> dict[str, ServerConfig]:
    """Discover MCP servers from environment variables.

    Supports:
      PYTHONAI_MCP_SERVERS — JSON string of {name: config}
      PYTHONAI_MCP_<NAME>_COMMAND, PYTHONAI_MCP_<NAME>_ARGS
    """
    servers: dict[str, ServerConfig] = {}

    # JSON config from env
    env_json = os.environ.get("PYTHONAI_MCP_SERVERS")
    if env_json:
        try:
            data = json.loads(env_json)
            parsed = parse_mcp_json({"mcpServers": data})
            servers.update(parsed)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to parse PYTHONAI_MCP_SERVERS: {e}")

    # Per-server env vars: PYTHONAI_MCP_<NAME>_COMMAND
    for key, value in os.environ.items():
        if key.startswith("PYTHONAI_MCP_") and key.endswith("_COMMAND"):
            name = key[len("PYTHONAI_MCP_") : -len("_COMMAND")].lower()
            if name in servers:
                continue

            args_str = os.environ.get(f"PYTHONAI_MCP_{name.upper()}_ARGS", "")
            args = [a.strip() for a in args_str.split(",") if a.strip()] if args_str else []

            servers[name] = StdioConfig(command=value, args=args)

    return servers
