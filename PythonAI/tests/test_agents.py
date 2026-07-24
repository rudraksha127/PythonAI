"""Tests for the agent system."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest


class TestAgentImports:
    """Test that agents module imports correctly."""

    def test_all_agents_import(self) -> None:
        """Verify all agents can be imported."""
        from src.agents import ALL_AGENTS

        assert "orchestrator" in ALL_AGENTS
        assert "code" in ALL_AGENTS
        assert "debug" in ALL_AGENTS
        assert "docs" in ALL_AGENTS
        assert "teacher" in ALL_AGENTS
        assert "performance" in ALL_AGENTS
        assert "retrieval" in ALL_AGENTS

    def test_agent_count(self) -> None:
        """Verify expected number of agents."""
        from src.agents import ALL_AGENTS

        assert len(ALL_AGENTS) == 7

    def test_individual_agent_imports(self) -> None:
        """Verify each agent module imports correctly."""
        from src.agents.code import run_code_agent
        from src.agents.debug import run_debug_agent
        from src.agents.docs import run_docs_agent
        from src.agents.orchestrator import run_orchestrator_agent
        from src.agents.performance import run_performance_agent
        from src.agents.retrieval import run_retrieval_agent
        from src.agents.teacher import run_teacher_agent

        assert callable(run_code_agent)
        assert callable(run_debug_agent)
        assert callable(run_docs_agent)
        assert callable(run_orchestrator_agent)
        assert callable(run_performance_agent)
        assert callable(run_retrieval_agent)
        assert callable(run_teacher_agent)


class TestAgentSwarm:
    """Test the agent swarm system."""

    def test_agent_swarm_module_exists(self) -> None:
        """Verify AgentSwarm module can be imported (if available)."""
        try:
            from src.utils import swarm  # noqa: F811
            assert hasattr(swarm, "AgentSwarm")
            assert hasattr(swarm, "execute_agents")
        except ImportError:
            pytest.skip("AgentSwarm module not available (optional dependency)")
