"""
PythonAI Agentic System — Phase 6
===================================
Multi-step agentic reasoning with MCP + built-in tools.

Architecture:
  Orchestrator → plans → delegates sub-tasks → synthesizes
    ├── SubAgent (coding)    — writes/edits files, runs commands
    ├── SubAgent (research)  — reads files, searches web, fetches URLs
    ├── SubAgent (mcp)       — uses MCP server tools
    └── SubAgent (review)    — reviews and validates results

Each SubAgent runs an independent LLM+tool loop (ToolCallingEngine)
with its own tool pool and context window.
"""

from .sub_agent import SubAgent, SubAgentResult
from .swarm import AgentSwarm
from .orchestrator import AgentOrchestrator, PlanStep

__all__ = [
    "SubAgent",
    "SubAgentResult",
    "AgentSwarm",
    "AgentOrchestrator",
    "PlanStep",
]
