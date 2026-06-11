"""Unit tests for LLM-based planning and synthesis in AgentOrchestrator."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.core.agents.orchestrator import AgentOrchestrator
from src.core.agents.sub_agent import SubAgentResult
from src.core.registry import get_registry
from src.core.tools import register_all_tools


@pytest.fixture
def registry():
    """Create a fresh registry with all tools registered."""
    reg = get_registry()
    register_all_tools(reg)
    return reg


@pytest.fixture
def orch(registry):
    """Create an orchestrator with a fresh registry and recording stream."""
    stream_log: list[str] = []

    def stream(msg: str) -> None:
        stream_log.append(msg)

    o = AgentOrchestrator(
        registry=registry,
        on_stream=stream,
        verbose=True,
    )
    return o, stream_log


# ── TestCallPlanningLLM ─────────────────────────────────────────────────────────

class TestCallPlanningLLM:
    """Tests for _call_planning_llm wrapper."""

    def test_uses_injected_call_llm_fn(self, orch):
        o, _ = orch

        def mock_llm(messages, tools):
            assert tools == []
            return {"content": "Injected Response"}

        o.call_llm_fn = mock_llm

        result = o._call_planning_llm("System", "User")
        assert result == "Injected Response"

    def test_injected_call_llm_fn_failure(self, orch):
        o, _ = orch

        def mock_llm(messages, tools):
            raise RuntimeError("API failure")

        o.call_llm_fn = mock_llm

        result = o._call_planning_llm("System", "User")
        assert result is None

    @patch("src.core.providers.get_provider_api")
    @patch("src.core.providers.ProviderRouter")
    def test_fallback_to_provider_router(self, mock_router_cls, mock_get_api, orch):
        o, _ = orch
        # No call_llm_fn injected

        mock_router = MagicMock()
        mock_router_cls.return_value = mock_router
        mock_route = MagicMock()
        mock_route.error = None
        mock_route.provider = "openai"
        mock_route.model = "gpt-4"
        mock_route.base_url = "https://api.openai.com/v1"
        mock_route.api_key = "test_key"
        mock_router.route.return_value = mock_route

        mock_api_fn = MagicMock(return_value={"content": "Router Response"})
        mock_get_api.return_value = mock_api_fn

        result = o._call_planning_llm("System", "User", max_tokens=2048)
        assert result == "Router Response"

        mock_api_fn.assert_called_once()
        kwargs = mock_api_fn.call_args[1]
        assert kwargs["max_tokens"] == 2048
        assert kwargs["tools"] is None
        assert kwargs["model"] == "gpt-4"

    @patch("src.core.providers.ProviderRouter")
    def test_provider_router_failure_returns_none(self, mock_router_cls, orch):
        o, _ = orch

        mock_router = MagicMock()
        mock_router_cls.return_value = mock_router
        mock_route = MagicMock()
        mock_route.error = "No API keys"
        mock_router.route.return_value = mock_route
        mock_router.get_available_providers.return_value = []

        result = o._call_planning_llm("System", "User")
        assert result is None


# ── TestPlanTaskLLMBased ────────────────────────────────────────────────────────

class TestPlanTaskLLMBased:
    """Tests for LLM-powered plan_task."""

    def test_valid_json_returns_plan(self, orch):
        o, _ = orch

        def mock_llm(messages, tools):
            return {"content": """```json
[
  {
    "id": "step_0",
    "agent_name": "researcher",
    "task": "Do research",
    "depends_on": [],
    "priority": 1
  }
]
```"""}

        o.call_llm_fn = mock_llm

        plan = o.plan_task("research this")
        assert len(plan) == 1
        assert plan[0].id == "step_0"
        assert plan[0].agent_name == "researcher"
        assert plan[0].task == "Do research"
        assert plan[0].depends_on == []
        assert plan[0].priority == 1

    def test_multi_step_with_deps(self, orch):
        o, _ = orch

        def mock_llm(messages, tools):
            return {"content": json.dumps([
                {
                    "id": "step_0",
                    "agent_name": "researcher",
                    "task": "Research",
                    "depends_on": []
                },
                {
                    "id": "step_1",
                    "agent_name": "coder",
                    "task": "Implement",
                    "depends_on": ["step_0"]
                }
            ])}

        o.call_llm_fn = mock_llm

        plan = o.plan_task("research and implement")
        assert len(plan) == 2
        assert plan[1].agent_name == "coder"
        assert plan[1].depends_on == ["step_0"]

    def test_unknown_agent_fallback_to_coder(self, orch):
        o, _ = orch

        def mock_llm(messages, tools):
            return {"content": json.dumps([
                {
                    "id": "step_0",
                    "agent_name": "imaginary-agent",
                    "task": "Task",
                }
            ])}

        o.call_llm_fn = mock_llm

        plan = o.plan_task("task")
        assert len(plan) == 1
        assert plan[0].agent_name == "coder"

    def test_malformed_json_triggers_fallback(self, orch):
        o, _ = orch

        def mock_llm(messages, tools):
            return {"content": "This is not JSON"}

        o.call_llm_fn = mock_llm

        plan = o.plan_task("write code")
        # Should fallback to keyword based
        assert len(plan) == 1
        assert plan[0].agent_name == "coder"
        assert "Implement" in plan[0].task

    def test_llm_call_fails_triggers_fallback(self, orch):
        o, _ = orch

        def mock_llm(messages, tools):
            raise RuntimeError("API failure")

        o.call_llm_fn = mock_llm

        plan = o.plan_task("write code")
        assert len(plan) == 1
        assert plan[0].agent_name == "coder"

    def test_stream_output_shows_planning(self, orch):
        o, log = orch

        def mock_llm(messages, tools):
            return {"content": json.dumps([
                {
                    "id": "step_0",
                    "agent_name": "coder",
                    "task": "Task",
                }
            ])}

        o.call_llm_fn = mock_llm
        o.plan_task("task")

        assert any("[LLM] Planning" in msg for msg in log)

    def test_on_plan_callback_fires(self, orch):
        o, _ = orch

        def mock_llm(messages, tools):
            return {"content": json.dumps([
                {
                    "id": "step_0",
                    "agent_name": "coder",
                    "task": "Task",
                }
            ])}

        o.call_llm_fn = mock_llm

        plans_seen = []
        o.on_plan = lambda p: plans_seen.append(p)

        plan = o.plan_task("task")
        assert len(plans_seen) == 1
        assert plans_seen[0] == plan


# ── TestPlanTaskKeywordFallback ──────────────────────────────────────────────────

class TestPlanTaskKeywordFallback:
    """Tests for the keyword fallback in plan_task."""

    def test_keyword_coding(self, orch):
        o, _ = orch
        o._call_planning_llm = MagicMock(return_value=None)

        plan = o.plan_task("write some code")
        assert len(plan) == 1
        assert plan[0].agent_name == "coder"

    def test_keyword_research(self, orch):
        o, _ = orch
        o._call_planning_llm = MagicMock(return_value=None)

        plan = o.plan_task("find existing patterns")
        assert len(plan) == 1
        assert plan[0].agent_name == "researcher"

    def test_keyword_mixed(self, orch):
        o, _ = orch
        o._call_planning_llm = MagicMock(return_value=None)

        plan = o.plan_task("find patterns and write code and review it")
        assert len(plan) == 3
        agent_names = [s.agent_name for s in plan]
        assert "researcher" in agent_names
        assert "coder" in agent_names
        assert "reviewer" in agent_names


# ── TestSynthesizeLLMBased ──────────────────────────────────────────────────────

class TestSynthesizeLLMBased:
    """Tests for LLM-powered _synthesize."""

    def test_synthesize_success(self, orch):
        o, _ = orch

        def mock_llm(messages, tools):
            return {"content": "This is the combined output."}

        o.call_llm_fn = mock_llm
        o.results = {
            "coder": SubAgentResult("coder", "coding", True, "Code written.", tool_calls_used=2),
            "researcher": SubAgentResult("researcher", "research", True, "Found docs.", tool_calls_used=1),
        }

        synthesis = o._synthesize("Do stuff")
        assert "This is the combined output." in synthesis
        assert "Orchestrated across 2 agents" in synthesis
        assert "3 total tool calls" in synthesis

    def test_synthesize_handles_single_agent(self, orch):
        o, _ = orch

        def mock_llm(messages, tools):
            return {"content": "Single agent output."}

        o.call_llm_fn = mock_llm
        o.results = {
            "coder": SubAgentResult("coder", "coding", True, "Code written.", tool_calls_used=5),
        }

        synthesis = o._synthesize("Do stuff")
        assert "Single agent output." in synthesis
        assert "Orchestrated across 1 agents" in synthesis

    def test_all_failed_agents_returns_early(self, orch):
        o, _ = orch
        o._call_planning_llm = MagicMock()
        o.results = {
            "coder": SubAgentResult("coder", "coding", False, "", error="Failed"),
        }

        synthesis = o._synthesize("Do stuff")
        assert "All agents failed" in synthesis
        o._call_planning_llm.assert_not_called()

    def test_llm_call_fails_triggers_fallback(self, orch):
        o, _ = orch

        def mock_llm(messages, tools):
            raise RuntimeError("API failure")

        o.call_llm_fn = mock_llm
        o.results = {
            "coder": SubAgentResult("coder", "coding", True, "Code written.", tool_calls_used=2),
        }

        synthesis = o._synthesize("Do stuff")
        # Should fallback to concatenation
        assert "## Coder" in synthesis
        assert "Code written." in synthesis
        assert "Orchestrated across 1 agents" in synthesis

    def test_synthesis_prompt_includes_outputs_and_request(self, orch):
        o, _ = orch

        prompt_seen = ""
        def mock_llm(messages, tools):
            nonlocal prompt_seen
            for msg in messages:
                if msg["role"] == "user":
                    prompt_seen = msg["content"]
            return {"content": "Result"}

        o.call_llm_fn = mock_llm
        o.results = {
            "coder": SubAgentResult("coder", "coding", True, "Code from coder", tool_calls_used=2),
        }

        o._synthesize("Build a website")

        assert "Build a website" in prompt_seen
        assert "Code from coder" in prompt_seen
        assert "--- Agent: coder" in prompt_seen
