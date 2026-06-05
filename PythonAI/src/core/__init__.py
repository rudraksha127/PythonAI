"""
PythonAI Core — Tool System, Provider Router & Execution Engine
===============================================================
Inspired by Claude Code's Tool.ts + OpenClaude's provider routing.
Provides typed tools, permission system, tool-calling loop,
multi-provider routing, and 3-tier message compaction.

Phases:
  Phase 1 — Tool System (Tool, Tools, Engine)
  Phase 2 — Provider Router (15+ providers)
  Phase 3 — Advanced Engine (parallel tools, compaction, token budget)
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
from .executor import ToolCallingEngine, QueryConfig, QueryDeps, parse_tool_calls, partition_tool_calls

# Provider System (Phase 2)
from .providers import (
    ModelRegistry,
    ModelCapabilities,
    ModelDescriptor,
    ProviderDescriptor,
    ProviderRouter,
    RouteResult,
    RouteStrategy,
    ProviderProfile,
    ProfileManager,
    ProviderDiscovery,
    get_model_info,
    find_models_by_capability,
    get_registry as get_provider_registry,
)

# Compact System (Phase 3)
from .compact import (
    microcompact_messages,
    auto_compact_if_needed,
    get_auto_compact_threshold,
    reactive_compact_if_needed,
)

# MCP Protocol (Phase 4)
from .mcp import (
    MCPClient,
    MCPConfigManager,
    MCPServer,
    MCPToolAdapter,
    MCPToolInfo,
    ServerConnection,
    ConnectionState,
    ServerConfig,
    StdioConfig,
    SSEConfig,
    HTTPConfig,
    TransportType,
    MCPScope,
    connect_stdio,
    connect_sse,
    call_tool,
    list_tools,
    find_mcp_configs,
    discover_mcp_servers,
    find_mcp_json_files,
    create_mcp_app,
    start_mcp_server,
    wrap_mcp_tool,
)

# Token Budget (Phase 3)
from .engine.token_budget import (
    BudgetTracker,
    check_token_budget,
    ContinueDecision,
)

# Agentic System (Phase 6)
from .agents import (
    SubAgent,
    SubAgentResult,
    AgentSwarm,
    AgentOrchestrator,
    PlanStep,
)

# MCP convenience singletons
_mcp_config_manager: MCPConfigManager | None = None


def get_mcp_config_manager() -> MCPConfigManager:
    global _mcp_config_manager
    if _mcp_config_manager is None:
        _mcp_config_manager = MCPConfigManager()
    return _mcp_config_manager


def connect_all_mcp_servers() -> dict[str, ServerConnection]:
    """Discover and connect to all configured MCP servers."""
    return discover_mcp_servers()

# Convenience singletons
_provider_router: ProviderRouter | None = None
_profile_manager: ProfileManager | None = None


def get_router() -> ProviderRouter:
    global _provider_router
    if _provider_router is None:
        _provider_router = ProviderRouter()
    return _provider_router


def get_profile_manager() -> ProfileManager:
    global _profile_manager
    if _profile_manager is None:
        _profile_manager = ProfileManager()
    return _profile_manager


__all__ = [
    # Tool System
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
    # Engine (Phase 3)
    "ToolCallingEngine",
    "QueryConfig",
    "QueryDeps",
    "parse_tool_calls",
    "partition_tool_calls",
    # MCP Protocol
    "MCPClient",
    "MCPConfigManager",
    "MCPServer",
    "MCPToolAdapter",
    "MCPToolInfo",
    "ServerConnection",
    "ConnectionState",
    "ServerConfig",
    "StdioConfig",
    "SSEConfig",
    "HTTPConfig",
    "TransportType",
    "MCPScope",
    "connect_stdio",
    "connect_sse",
    "call_tool",
    "list_tools",
    "find_mcp_configs",
    "discover_mcp_servers",
    "find_mcp_json_files",
    "create_mcp_app",
    "start_mcp_server",
    "wrap_mcp_tool",
    "get_mcp_config_manager",
    "connect_all_mcp_servers",
    # Provider System
    "ModelRegistry",
    "ModelCapabilities",
    "ModelDescriptor",
    "ProviderDescriptor",
    "ProviderRouter",
    "RouteResult",
    "RouteStrategy",
    "ProviderProfile",
    "ProfileManager",
    "ProviderDiscovery",
    "get_model_info",
    "find_models_by_capability",
    "get_provider_registry",
    "get_router",
    "get_profile_manager",
    # Compact System (Phase 3)
    "microcompact_messages",
    "auto_compact_if_needed",
    "get_auto_compact_threshold",
    "reactive_compact_if_needed",
    # Agentic System (Phase 6)
    "SubAgent",
    "SubAgentResult",
    "AgentSwarm",
    "AgentOrchestrator",
    "PlanStep",
    # Token Budget
    "BudgetTracker",
    "check_token_budget",
    "ContinueDecision",
]
