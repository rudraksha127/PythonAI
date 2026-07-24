"""
ForgeAI Ecosystem Integration Bridges
======================================

Connects PythonAI (Core Engine) to every other project in the ecosystem:

  ┌──────────────┐     ┌──────────────────┐     ┌──────────────┐
  │   PythonAI   │────▶│  hermes-agent    │────▶│  Skills/MCP  │
  │  (Core)      │     │  (Orchestrator)  │     │              │
  └──────┬───────┘     └──────────────────┘     └──────────────┘
         │
         ├────▶ Rudra-bots (Dashboard) ────▶ Real-time metrics
         ├────▶ Dashboard (Next.js) ──────▶ Training/SEAL UI
         ├────▶ open-claude (CLI) ────────▶ Terminal AI
         ├────▶ OpenJarvis (Agents) ──────▶ 40+ tools, 20+ agents
         └────▶ ~/.forgeai/ (Shared Config)

Usage:
    from src.integration.ecosystem_manager import EcosystemManager
    
    mgr = EcosystemManager()
    mgr.start_all()
    status = mgr.get_ecosystem_status()
"""

from __future__ import annotations

from .ecosystem_manager import EcosystemManager
from .openjarvis_bridge import (
    auto_register,
    build_oj_engine,
    build_oj_tool_adapters,
    create_oj_agent_callable,
    discover_oj_agents,
    discover_oj_tools,
    get_oj_agents,
    get_oj_status,
    is_openjarvis_available,
    register_oj_tools,
)

__all__ = [
    "EcosystemManager",
    "auto_register",
    "build_oj_engine",
    "build_oj_tool_adapters",
    "create_oj_agent_callable",
    "discover_oj_agents",
    "discover_oj_tools",
    "get_oj_agents",
    "get_oj_status",
    "is_openjarvis_available",
    "register_oj_tools",
]
