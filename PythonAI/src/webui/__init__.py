"""
PythonAI Web UI — Streamlit Frontend
=====================================
Phase 5 upgrade: Multi-page dashboard with tool execution visualization,
provider routing display, and MCP server status.

Pages:
  - RAG Chat            — Original RAG Q&A assistant
  - Dataset Generation  — Dataset generator
  - Dashboard Home      — Overview of all systems
  - Tool System         — Tool execution visualization
  - Provider Routing    — Provider status & routing
  - MCP Servers         - MCP connection dashboard
"""

from __future__ import annotations

from .views.dashboard_home import render as render_home
from .views.tools_dashboard import render as render_tools
from .views.providers_dashboard import render as render_providers
from .views.mcp_dashboard import render as render_mcp
from .views.agent_workspace import render as render_agent_workspace

__all__ = [
    "render_home",
    "render_tools",
    "render_providers",
    "render_mcp",
    "render_agent_workspace",
]
