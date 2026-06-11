"""
PythonAI MCP — Configuration Management
========================================
Multi-scope MCP server configuration management.
Inspired by Claude Code's services/mcp/config.ts.

Manages MCP servers defined in:
  - .mcp.json (per-project)
  - User config (~/.config/pythonai/mcp.json)
  - Environment variables
  - Enterprise/managed configs
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from .types import (
    HTTPConfig,
    MCPScope,
    ServerConfig,
    SSEConfig,
    StdioConfig,
    WSConfig,
)

logger = logging.getLogger("pythonai.mcp.config")


# ═══════════════════════════════════════
#  Environment Variable Expansion
# ═══════════════════════════════════════

ENV_VAR_PATTERN = re.compile(r'\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)')


def expand_env_vars(value: str) -> tuple[str, list[str]]:
    """Expand ${VAR} and $VAR environment variable references.

    Returns (expanded_string, missing_vars_list).
    """
    missing: list[str] = []

    def replacer(match: re.Match[str]) -> str:
        var_name = match.group(1) or match.group(2)
        env_val: str | None = os.environ.get(var_name)
        if env_val is None:
            if var_name not in missing:
                missing.append(var_name)
            return match.group(0)  # Preserve original
        return env_val

    expanded = ENV_VAR_PATTERN.sub(replacer, value)
    return expanded, missing


def expand_config_env(config: ServerConfig) -> tuple[ServerConfig, list[str]]:
    """Expand env vars in all fields of a server config."""
    all_missing: list[str] = []

    if isinstance(config, StdioConfig):
        cmd, m1 = expand_env_vars(config.command)
        args = []
        for a in config.args:
            ea, m = expand_env_vars(a)
            args.append(ea)
            all_missing.extend(m)
        env = None
        if config.env:
            env = {}
            for k, v in config.env.items():
                ev, m = expand_env_vars(v)
                env[k] = ev
                all_missing.extend(m)
        all_missing.extend(m1)
        return StdioConfig(command=cmd, args=args, env=env), all_missing

    elif isinstance(config, SSEConfig):
        url, m1 = expand_env_vars(config.url)
        headers = _expand_headers(config.headers, all_missing)
        all_missing.extend(m1)
        return SSEConfig(url=url, headers=headers), all_missing

    elif isinstance(config, HTTPConfig):
        url, m1 = expand_env_vars(config.url)
        headers = _expand_headers(config.headers, all_missing)
        all_missing.extend(m1)
        return HTTPConfig(url=url, headers=headers), all_missing

    elif isinstance(config, WSConfig):
        url, m1 = expand_env_vars(config.url)
        headers = _expand_headers(config.headers, all_missing)
        all_missing.extend(m1)
        return WSConfig(url=url, headers=headers), all_missing

    return config, all_missing


def _expand_headers(
    headers: dict[str, str] | None,
    missing: list[str],
) -> dict[str, str] | None:
    if not headers:
        return headers
    expanded: dict[str, str] = {}
    for k, v in headers.items():
        ev, m = expand_env_vars(v)
        expanded[k] = ev
        missing.extend(m)
    return expanded


# ═══════════════════════════════════════
#  MCP JSON Config Parser
# ═══════════════════════════════════════

def parse_mcp_json(data: dict[str, Any]) -> dict[str, ServerConfig]:
    """Parse an .mcp.json style configuration.

    Expects format:
    {
      "mcpServers": {
        "server-name": {
          "command": "npx",
          "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]
        }
      }
    }
    """
    servers: dict[str, ServerConfig] = {}
    raw_servers = data.get("mcpServers", {})

    for name, cfg in raw_servers.items():
        server_cfg = _parse_single_server(cfg)
        if server_cfg:
            servers[name] = server_cfg

    return servers


def _parse_single_server(cfg: dict[str, Any]) -> ServerConfig | None:
    """Parse a single server config entry."""
    transport_type = cfg.get("type", "stdio")

    if transport_type in ("stdio", None, ""):
        return StdioConfig(
            command=cfg.get("command", ""),
            args=cfg.get("args", []),
            env=cfg.get("env"),
        )
    elif transport_type == "sse":
        return SSEConfig(
            url=cfg.get("url", ""),
            headers=cfg.get("headers"),
        )
    elif transport_type == "http":
        return HTTPConfig(
            url=cfg.get("url", ""),
            headers=cfg.get("headers"),
        )
    elif transport_type == "ws":
        return WSConfig(
            url=cfg.get("url", ""),
            headers=cfg.get("headers"),
        )

    logger.warning(f"Unsupported MCP transport type: {transport_type}")
    return None


# ═══════════════════════════════════════
#  Config Manager
# ═══════════════════════════════════════

DEFAULT_MCP_DIRS = [
    Path.home() / ".config" / "pythonai",
    Path.home() / ".pythonai",
]


class MCPConfigManager:
    """Manages MCP server configurations across multiple scopes.

    Configuration precedence (highest to lowest):
      1. Local (project-specific)
      2. Project (.mcp.json in project dir or ancestors)
      3. User (global config)
      4. Enterprise (managed)
    """

    def __init__(self, project_dir: str | None = None):
        self.project_dir = Path(project_dir or os.getcwd())
        self._servers: dict[str, tuple[ServerConfig, MCPScope]] = {}
        self._load_all()

    # ── Loading ─────────────────────────────────────────────────

    def _load_all(self) -> None:
        """Load servers from all scopes with proper precedence."""
        self._servers = {}

        # 1. Enterprise (lowest priority)
        for d in DEFAULT_MCP_DIRS:
            ep_path = d / "managed-mcp.json"
            if ep_path.exists():
                self._load_file(ep_path, MCPScope.ENTERPRISE)

        # 2. User config
        for d in DEFAULT_MCP_DIRS:
            user_path = d / "mcp.json"
            if user_path.exists():
                self._load_file(user_path, MCPScope.USER)

        # 3. Project .mcp.json (walk up from project dir)
        self._load_project_configs()

        # 4. Local (project-specific, highest priority)
        local_path = self.project_dir / ".pythonai" / "mcp.json"
        if local_path.exists():
            self._load_file(local_path, MCPScope.LOCAL)

    def _load_project_configs(self) -> None:
        """Walk up from project dir to find .mcp.json files."""
        current = self.project_dir

        while current != current.parent:
            mcp_json = current / ".mcp.json"
            if mcp_json.exists():
                self._load_file(mcp_json, MCPScope.PROJECT)
            current = current.parent

    def _load_file(self, path: Path, scope: MCPScope) -> None:
        """Load and parse an MCP config file."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            servers = parse_mcp_json(data)

            for name, config in servers.items():
                expanded, missing = expand_config_env(config)
                if missing:
                    logger.warning(
                        f"MCP server '{name}' has unset env vars: {missing}"
                    )
                # Higher precedence scopes overwrite lower ones
                self._servers[name] = (expanded, scope)

        except json.JSONDecodeError as e:
            logger.error(f"Invalid MCP config in {path}: {e}")
        except Exception as e:
            logger.error(f"Failed to load MCP config {path}: {e}")

    # ── Accessors ───────────────────────────────────────────────

    def get_all(self) -> dict[str, tuple[ServerConfig, MCPScope]]:
        """Get all configured MCP servers with their scope."""
        return dict(self._servers)

    def get_servers(self) -> dict[str, ServerConfig]:
        """Get all server configs (without scope info)."""
        return {name: cfg for name, (cfg, _) in self._servers.items()}

    def get_by_scope(self, scope: MCPScope) -> dict[str, ServerConfig]:
        """Get servers from a specific scope."""
        return {
            name: cfg
            for name, (cfg, s) in self._servers.items()
            if s == scope
        }

    def get(self, name: str) -> ServerConfig | None:
        """Get a specific server config by name."""
        entry = self._servers.get(name)
        return entry[0] if entry else None

    def add(self, name: str, config: ServerConfig, scope: MCPScope = MCPScope.LOCAL) -> None:
        """Add or update an MCP server configuration."""
        self._servers[name] = (config, scope)

        # Persist to appropriate scope file
        if scope == MCPScope.LOCAL:
            self._save_local(name, config)
        elif scope == MCPScope.PROJECT:
            self._save_project(name, config)
        elif scope == MCPScope.USER:
            self._save_user(name, config)

    def remove(self, name: str) -> bool:
        """Remove an MCP server configuration."""
        if name not in self._servers:
            return False

        config, scope = self._servers.pop(name)

        # Remove from the appropriate scope file
        if scope == MCPScope.LOCAL:
            self._remove_local(name)
        elif scope == MCPScope.PROJECT:
            self._remove_project(name)
        elif scope == MCPScope.USER:
            self._remove_user(name)

        return True

    # ── Persistence ─────────────────────────────────────────────

    def _save_local(self, name: str, config: ServerConfig) -> None:
        path = self.project_dir / ".pythonai" / "mcp.json"
        self._save_entry(path, name, config)

    def _save_project(self, name: str, config: ServerConfig) -> None:
        path = self.project_dir / ".mcp.json"
        self._save_entry(path, name, config)

    def _save_user(self, name: str, config: ServerConfig) -> None:
        path = DEFAULT_MCP_DIRS[0] / "mcp.json"
        self._save_entry(path, name, config)

    def _save_entry(self, path: Path, name: str, config: ServerConfig) -> None:
        """Save a single server entry to a config file."""
        path.parent.mkdir(parents=True, exist_ok=True)

        existing = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass

        mcp_servers = existing.get("mcpServers", {})

        if isinstance(config, StdioConfig):
            mcp_servers[name] = {
                "command": config.command,
                "args": config.args,
            }
            if config.env:
                mcp_servers[name]["env"] = config.env
        elif isinstance(config, SSEConfig):
            mcp_servers[name] = {
                "type": "sse",
                "url": config.url,
            }
            if config.headers:
                mcp_servers[name]["headers"] = config.headers
        elif isinstance(config, HTTPConfig):
            mcp_servers[name] = {
                "type": "http",
                "url": config.url,
            }
            if config.headers:
                mcp_servers[name]["headers"] = config.headers

        existing["mcpServers"] = mcp_servers
        path.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    def _remove_local(self, name: str) -> None:
        path = self.project_dir / ".pythonai" / "mcp.json"
        self._remove_entry(path, name)

    def _remove_project(self, name: str) -> None:
        path = self.project_dir / ".mcp.json"
        self._remove_entry(path, name)

    def _remove_user(self, name: str) -> None:
        path = DEFAULT_MCP_DIRS[0] / "mcp.json"
        self._remove_entry(path, name)

    def _remove_entry(self, path: Path, name: str) -> None:
        """Remove a server entry from a config file."""
        if not path.exists():
            return

        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            mcp_servers = existing.get("mcpServers", {})
            mcp_servers.pop(name, None)
            existing["mcpServers"] = mcp_servers
            path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to remove '{name}' from {path}: {e}")

    # ── Summary ─────────────────────────────────────────────────

    def summary(self) -> dict[str, Any]:
        """Get a summary of all configured servers."""
        by_scope: dict[str, list[str]] = {}
        for name, (cfg, scope) in self._servers.items():
            key = scope.value
            if key not in by_scope:
                by_scope[key] = []
            by_scope[key].append(name)

        return {
            "total": len(self._servers),
            "by_scope": by_scope,
            "servers": [
                {
                    "name": name,
                    "type": self._get_type_name(cfg),
                    "scope": scope.value,
                }
                for name, (cfg, scope) in self._servers.items()
            ],
        }

    def _get_type_name(self, config: ServerConfig) -> str:
        if isinstance(config, StdioConfig):
            return f"stdio ({config.command})"
        elif isinstance(config, SSEConfig):
            return "sse"
        elif isinstance(config, HTTPConfig):
            return "http"
        elif isinstance(config, WSConfig):
            return "ws"
        return "unknown"


# ═══════════════════════════════════════
#  Convenience Functions
# ═══════════════════════════════════════

def find_mcp_configs(project_dir: str | None = None) -> dict[str, ServerConfig]:
    """Quick-find all MCP server configs for a project."""
    mgr = MCPConfigManager(project_dir)
    return mgr.get_servers()
