"""Comprehensive unit tests for AgentOrchestrator — run pipeline, synthesis, and edge cases."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.agents.orchestrator import AgentOrchestrator, PlanStep
from src.core.agents.sub_agent import SubAgent, SubAgentResult
from src.core.registry import get_registry
from src.core.tools import register_all_tools

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def registry():
    reg = get_registry()
    register_all_tools(reg)
    return reg


@pytest.fixture
def orch(registry):
    """Create an orchestrator with recording stream."""
    # Ensure no MCP tools are in the registry for baseline tests
    # (MCP tools could be registered by other tests sharing the singleton)
    stream_log: list[str] = []
    def stream(msg: str) -> None:
        stream_log.append(msg)
    o = AgentOrchestrator(
        registry=registry,
        on_stream=stream,
        verbose=True,
    )
    return o, stream_log


@pytest.fixture
def clean_registry():
    """Create a completely fresh, isolated registry (no shared state)."""
    from src.core.registry import ToolRegistry
    from src.core.tools import register_all_tools as register
    fresh = ToolRegistry()
    register(fresh)
    return fresh


# ══════════════════════════════════════════════════════════════════════
# _init_default_agents
# ══════════════════════════════════════════════════════════════════════


class TestInitDefaultAgents:
    """Tests for _init_default_agents."""

    def test_default_agents_created(self, orch):
        """_init_default_agents should create coder, researcher, reviewer."""
        o, _ = orch
        agent_names = list(o._swarm.agents.keys())
        assert "coder" in agent_names
        assert "researcher" in agent_names
        assert "reviewer" in agent_names

    def test_default_agent_roles(self, orch):
        """Default agents should have correct roles."""
        o, _ = orch
        assert o._swarm.agents["coder"].role == "coding"
        assert o._swarm.agents["researcher"].role == "research"
        assert o._swarm.agents["reviewer"].role == "review"

    def test_mcp_agent_not_created_without_mcp_tools(self, clean_registry):
        """MCP agent should not be created when no MCP tools registered."""
        o = AgentOrchestrator(registry=clean_registry, on_stream=lambda m: None, verbose=True)
        assert clean_registry.list_mcp() == [], "Precondition: no MCP tools"
        assert "mcp-worker" not in o._swarm.agents

    def test_mcp_agent_created_with_mcp_tools(self):
        """MCP agent should be created when MCP tools are registered."""
        from src.core.registry import ToolRegistry
        from src.core.tool import Tool

        class MockMCPTool(Tool):
            def __init__(self):
                super().__init__(name="mcp__test__tool", description="MCP test tool")
            def input_schema(self):
                from src.core.tool import InputSchema
                return InputSchema()
            def call(self, input_data, context):
                from src.core.tool import ToolResult
                return ToolResult(data="ok")

        # Use a fresh registry to avoid polluting the shared singleton
        fresh_registry = ToolRegistry()
        from src.core.tools import register_all_tools
        register_all_tools(fresh_registry)
        fresh_registry.register_mcp(MockMCPTool())

        o, _ = AgentOrchestrator(registry=fresh_registry, on_stream=lambda m: None, verbose=True), []
        assert "mcp-worker" in o._swarm.agents
        assert o._swarm.agents["mcp-worker"].role == "mcp"


# ══════════════════════════════════════════════════════════════════════
# register_agent
# ══════════════════════════════════════════════════════════════════════


class TestRegisterAgent:
    """Tests for register_agent."""

    def test_register_custom_agent(self, orch):
        """register_agent should add a custom agent to the swarm."""
        o, _ = orch
        agent = SubAgent(
            name="custom_agent",
            role="custom",
            system_prompt="Custom prompt",
        )
        o.register_agent(agent)
        assert "custom_agent" in o._swarm.agents
        assert o._swarm.agents["custom_agent"] is agent

    def test_register_agent_overwrites(self, orch):
        """register_agent should overwrite existing agent with same name."""
        o, _ = orch
        original = o._swarm.agents["coder"]
        new_agent = SubAgent(
            name="coder",
            role="coding",
            system_prompt="Overwritten prompt",
        )
        o.register_agent(new_agent)
        assert o._swarm.agents["coder"] is new_agent
        assert o._swarm.agents["coder"] is not original


# ══════════════════════════════════════════════════════════════════════
# _synthesize_concat_fallback
# ══════════════════════════════════════════════════════════════════════


class TestSynthesizeConcatFallback:
    """Tests for _synthesize_concat_fallback."""

    def test_single_agent(self, orch):
        """Concat fallback with a single agent should include its output."""
        o, _ = orch
        successful = {
            "coder": SubAgentResult("coder", "coding", True, "Code written.", tool_calls_used=2),
        }
        result = o._synthesize_concat_fallback("Write a function", successful)
        assert "Write a function" in result
        assert "Code written." in result
        assert "Orchestrated across 1 agents" in result
        assert "2 total tool calls" in result

    def test_multiple_agents_in_priority_order(self, orch):
        """Concat fallback should order agents by priority: researcher, coder, mcp-worker, reviewer."""
        o, _ = orch
        successful = {
            "coder": SubAgentResult("coder", "coding", True, "Code done.", tool_calls_used=3),
            "researcher": SubAgentResult("researcher", "research", True, "Found info.", tool_calls_used=1),
            "reviewer": SubAgentResult("reviewer", "review", True, "Looks good.", tool_calls_used=0),
        }
        result = o._synthesize_concat_fallback("Build a feature", successful)

        # Find positions of each section in the output
        researcher_pos = result.index("Researcher")
        coder_pos = result.index("Coder")
        reviewer_pos = result.index("Reviewer")

        assert researcher_pos < coder_pos < reviewer_pos

    def test_orphaned_agent_name_formatted(self, orch):
        """Agent names should be formatted as title case headers."""
        o, _ = orch
        successful = {
            "mcp-worker": SubAgentResult("mcp-worker", "mcp", True, "DB connected.", tool_calls_used=1),
        }
        result = o._synthesize_concat_fallback("Query DB", successful)
        assert "Mcp Worker" in result  # title-cased
        assert "DB connected." in result
        assert "Orchestrated across 1 agents" in result

    def test_includes_original_request(self, orch):
        """Concat fallback should include the original user request."""
        o, _ = orch
        successful = {
            "coder": SubAgentResult("coder", "coding", True, "Done.", tool_calls_used=1),
        }
        result = o._synthesize_concat_fallback("This is my request", successful)
        assert "This is my request" in result

    def test_summary_footer_count(self, orch):
        """Summary footer should match actual tool call count."""
        o, _ = orch
        successful = {
            "coder": SubAgentResult("coder", "coding", True, "A", tool_calls_used=2),
            "researcher": SubAgentResult("researcher", "research", True, "B", tool_calls_used=3),
        }
        result = o._synthesize_concat_fallback("Request", successful)
        assert "5 total tool calls" in result


# ══════════════════════════════════════════════════════════════════════
# summary
# ══════════════════════════════════════════════════════════════════════


class TestSummary:
    """Tests for the summary method."""

    def test_summary_with_results(self, orch):
        """summary should include plan steps and their results."""
        o, _ = orch
        o.plan = [
            PlanStep(id="step_0", agent_name="coder", task="Write code", depends_on=[], priority=1),
        ]
        o.results = {
            "coder": SubAgentResult("coder", "coding", True, "Done.", tool_calls_used=2, rounds=3, elapsed=1.5),
        }
        # Mark step as done
        o.plan[0].status = "done"

        summary = o.summary()
        assert "coder" in summary
        assert "3 rounds" in summary
        assert "2 tools" in summary
        assert "1.5s" in summary

    def test_summary_with_no_result(self, orch):
        """summary should handle steps without results."""
        o, _ = orch
        o.plan = [
            PlanStep(id="step_0", agent_name="coder", task="Write code", depends_on=[], priority=1),
        ]
        o.plan[0].status = "pending"

        summary = o.summary()
        assert "coder" in summary
        assert "no result" in summary

    def test_summary_empty_plan(self, orch):
        """summary with empty plan should not crash."""
        o, _ = orch
        o.plan = []
        summary = o.summary()
        assert "Execution Summary" in summary

    def test_summary_with_failed_step(self, orch):
        """summary should show failed status."""
        o, _ = orch
        o.plan = [
            PlanStep(id="step_0", agent_name="coder", task="Write code", depends_on=[], priority=1),
        ]
        o.results = {
            "coder": SubAgentResult("coder", "coding", False, "", error="Something broke", tool_calls_used=0, rounds=1, elapsed=0.5),
        }
        o.plan[0].status = "failed"

        summary = o.summary()
        assert "[failed]" in summary or "[FAIL]" in summary.upper() or "[FAILED]" in summary


# ══════════════════════════════════════════════════════════════════════
# _on_agent_start / _on_agent_complete callbacks
# ══════════════════════════════════════════════════════════════════════


class TestOrchestratorCallbacks:
    """Tests for _on_agent_start and _on_agent_complete."""

    def test_on_agent_start_updates_plan_status(self, orch):
        """on_agent_start should set step status to 'running'."""
        o, _ = orch
        step = PlanStep(id="step_0", agent_name="coder", task="Task", depends_on=[])
        o.plan = [step]
        o._on_agent_start("coder")
        assert step.status == "running"

    def test_on_agent_start_streams_message(self, orch):
        """on_agent_start should stream a message."""
        o, log = orch
        o.plan = [PlanStep(id="step_0", agent_name="coder", task="Task", depends_on=[])]
        log.clear()
        o._on_agent_start("coder")
        assert any("Starting agent: coder" in msg for msg in log)

    def test_on_agent_complete_success_updates_status(self, orch):
        """on_agent_complete with success should set status to 'done'."""
        o, _ = orch
        step = PlanStep(id="step_0", agent_name="coder", task="Task", depends_on=[])
        o.plan = [step]
        result = SubAgentResult("coder", "coding", True, "Done", tool_calls_used=2, rounds=3, elapsed=1.0)
        o._on_agent_complete("coder", result)
        assert step.status == "done"

    def test_on_agent_complete_failure_updates_status(self, orch):
        """on_agent_complete with failure should set status to 'failed'."""
        o, _ = orch
        step = PlanStep(id="step_0", agent_name="coder", task="Task", depends_on=[])
        o.plan = [step]
        result = SubAgentResult("coder", "coding", False, "", error="Failed")
        o._on_agent_complete("coder", result)
        assert step.status == "failed"

    def test_on_agent_complete_streams_metrics(self, orch):
        """on_agent_complete should stream metrics."""
        o, log = orch
        o.plan = [PlanStep(id="step_0", agent_name="coder", task="Task", depends_on=[])]
        log.clear()
        result = SubAgentResult("coder", "coding", True, "Done", tool_calls_used=3, rounds=2, elapsed=1.5)
        o._on_agent_complete("coder", result)
        assert any("coder" in msg and "done" in msg for msg in log)
        assert any("3t" in msg for msg in log)  # tool calls
        assert any("2r" in msg for msg in log)  # rounds
        assert any("1.5s" in msg for msg in log)  # elapsed


# ══════════════════════════════════════════════════════════════════════
# run() full pipeline (mocked)
# ══════════════════════════════════════════════════════════════════════


class TestRunPipeline:
    """Tests for the full run() pipeline with mocked sub-agents."""

    def test_run_simple_task_returns_string(self, orch):
        """run() should return a string result for a simple task."""
        o, log = orch
        # Mock the sub-agent run to avoid LLM calls
        for agent in o._swarm.agents.values():
            agent.call_llm_fn = lambda m, t: {"content": "Mock result.", "tool_calls": []}

        result = o.run("say hello")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_run_calls_planning_first(self, orch):
        """run() should execute planning phase before execution."""
        o, log = orch
        for agent in o._swarm.agents.values():
            agent.call_llm_fn = lambda m, t: {"content": "Mock.", "tool_calls": []}

        o.run("write code")
        # Check that planning message was streamed
        assert any("Planning" in msg for msg in log)

    def test_run_shows_tool_count(self, orch):
        """run() should display registered tool count."""
        o, log = orch
        for agent in o._swarm.agents.values():
            agent.call_llm_fn = lambda m, t: {"content": "Mock.", "tool_calls": []}

        o.run("hello")
        assert any("registered" in msg for msg in log)

    def test_run_calls_cleanup_at_end(self, orch):
        """run() should call cleanup at the end, closing MCP connections."""
        o, log = orch
        for agent in o._swarm.agents.values():
            agent.call_llm_fn = lambda m, t: {"content": "Mock.", "tool_calls": []}

        # The cleanup should leave _mcp_client as None
        o.run("hello")
        assert o._mcp_client is None

    def test_run_completion_message(self, orch):
        """run() should stream a completion message with stats."""
        o, log = orch
        for agent in o._swarm.agents.values():
            agent.call_llm_fn = lambda m, t: {"content": "Mock.", "tool_calls": []}

        o.run("hello")
        assert any("Complete" in msg for msg in log)

    def test_run_synthesis_phase(self, orch):
        """run() should execute the synthesis phase after agents finish."""
        o, log = orch
        for agent in o._swarm.agents.values():
            agent.call_llm_fn = lambda m, t: {"content": "Mock.", "tool_calls": []}

        result = o.run("hello")
        # The synthesis phase should have been entered
        assert any("Synthesizing" in msg for msg in log)

    def test_non_streaming_mode_still_works(self, clean_registry):
        """run() should work without an on_stream callback."""
        o = AgentOrchestrator(registry=clean_registry, verbose=False)
        for agent in o._swarm.agents.values():
            agent.call_llm_fn = lambda m, t: {"content": "Mock result.", "tool_calls": []}

        result = o.run("hello")
        assert isinstance(result, str)
        assert len(result) > 0
        assert o._mcp_client is None  # Cleanup ran


# ══════════════════════════════════════════════════════════════════════
# Vector test: _plan_task_keyword_fallback detailed
# ══════════════════════════════════════════════════════════════════════


class TestKeywordFallbackDetailed:
    """Detailed tests for _plan_task_keyword_fallback."""

    def test_coding_keywords(self, orch):
        """Keywords like 'write', 'create', 'implement' should route to coder."""
        o, _ = orch
        o._call_planning_llm = MagicMock(return_value=None)
        for keyword in ["write", "create", "implement", "build", "fix", "refactor"]:
            plan = o._plan_task_keyword_fallback(f"Please {keyword} a function")
            agent_names = [s.agent_name for s in plan]
            assert "coder" in agent_names, f"Keyword '{keyword}' should trigger coder"

    def test_research_keywords(self, orch):
        """Keywords like 'find', 'search', 'lookup' should route to researcher."""
        o, _ = orch
        o._call_planning_llm = MagicMock(return_value=None)
        for keyword in ["find", "search", "lookup", "check", "examine"]:
            plan = o._plan_task_keyword_fallback(f"Please {keyword} the answer")
            agent_names = [s.agent_name for s in plan]
            assert "researcher" in agent_names, f"Keyword '{keyword}' should trigger researcher"

    def test_complex_task_triggers_reviewer(self, orch):
        """Keywords like 'complex', 'production', 'secure' should add reviewer."""
        o, _ = orch
        plan = o._plan_task_keyword_fallback("Build a complex production system")
        agent_names = [s.agent_name for s in plan]
        assert "coder" in agent_names
        assert "reviewer" in agent_names

    def test_default_fallback_to_coder(self, orch):
        """Plain requests with no matching keywords should fallback to coder."""
        o, _ = orch
        plan = o._plan_task_keyword_fallback("Hello world")
        assert len(plan) == 1
        assert plan[0].agent_name == "coder"

    def test_full_mixed_stack(self, orch):
        """A request with research + code + review should create all three."""
        o, _ = orch
        plan = o._plan_task_keyword_fallback("Find the bug and write a fix then validate it")
        agent_names = [s.agent_name for s in plan]
        assert "researcher" in agent_names
        assert "coder" in agent_names
        assert "reviewer" in agent_names

    def test_correct_dependencies(self, orch):
        """Dependencies between steps should be set correctly."""
        o, _ = orch
        plan = o._plan_task_keyword_fallback("Find issues and write code and then review")
        # Researcher (step_0) has no deps
        assert plan[0].depends_on == []
        # Coder (step_1) depends on researcher
        assert plan[1].depends_on == ["step_0"]
        # Reviewer (step_2) depends on both previous steps
        assert plan[2].depends_on == ["step_0", "step_1"]


# ══════════════════════════════════════════════════════════════════════
# Vector test: _plan_task_llm edge cases (error handling)
# ══════════════════════════════════════════════════════════════════════


class TestLLMPlanningEdgeCases:
    """Edge cases for _plan_task_llm."""

    def test_non_list_response(self, orch):
        """A non-list JSON response should trigger fallback."""
        o, _ = orch
        o._call_planning_llm = MagicMock(return_value='{"not": "a list"}')
        result = o._plan_task_llm("task")
        assert result is None

    def test_missing_id_field(self, orch):
        """A list item without 'id' should trigger fallback."""
        o, _ = orch
        o._call_planning_llm = MagicMock(return_value='[{"agent_name": "coder", "task": "test"}]')
        result = o._plan_task_llm("task")
        assert result is None

    def test_empty_list_returned(self, orch):
        """An empty list should return an empty plan."""
        o, _ = orch
        o._call_planning_llm = MagicMock(return_value='[]')
        result = o._plan_task_llm("task")
        assert result == []
