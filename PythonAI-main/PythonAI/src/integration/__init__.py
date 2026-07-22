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
         └────▶ ~/.forgeai/ (Shared Config)

Usage:
    from src.integration.ecosystem_manager import EcosystemManager
    
    mgr = EcosystemManager()
    mgr.start_all()
    status = mgr.get_ecosystem_status()
"""

from __future__ import annotations

from .ecosystem_manager import EcosystemManager

__all__ = ["EcosystemManager"]
