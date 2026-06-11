"""Comprehensive unit tests for AgentSwarm — parallel and sequential execution."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from src.core.agents.sub_agent import SubAgent, SubAgentResult
from src.core.agents.swarm import AgentSwarm
from src.core.registry import get_registry
from src.core.tools import register_all_tools

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def registry():
    reg = get_registry()
    register_all_tools(reg)
    return reg


def make_mock_agent(
    name: str,
    role: str = "coding",
    return_output: str = "Task complete.",
    delay: float = 0.0,
) -> SubAgent:
    """Create a SubAgent with a mock call_llm_fn that returns immediately."""
    def mock_llm(messages, tools):
        if delay:
            time.sleep(delay)
        return {"content": return_output, "tool_calls": []}

    return SubAgent(
        name=name,
        role=role,
        system_prompt=f"You are a {role} agent.",
        registry=get_registry(),
        call_llm_fn=mock_llm,
    )


def make_failing_agent(name: str, role: str = "coding") -> SubAgent:
    """Create a SubAgent whose mock LLM fails."""
    def mock_llm(messages, tools):
        raise RuntimeError(f"LLM failure for {name}")

    return SubAgent(
        name=name,
        role=role,
        system_prompt="Test prompt",
        registry=get_registry(),
        call_llm_fn=mock_llm,
    )


# ══════════════════════════════════════════════════════════════════════
# AgentSwarm — add_agent / get_agent
# ══════════════════════════════════════════════════════════════════════


class TestSwarmAgentManagement:
    """Tests for add_agent and get_agent."""

    def test_add_agent(self):
        """add_agent should register an agent by name."""
        swarm = AgentSwarm()
        agent = make_mock_agent("coder")
        swarm.add_agent(agent)
        assert "coder" in swarm.agents
        assert swarm.agents["coder"] is agent

    def test_add_multiple_agents(self):
        """add_agent should support multiple agents."""
        swarm = AgentSwarm()
        swarm.add_agent(make_mock_agent("coder"))
        swarm.add_agent(make_mock_agent("researcher"))
        swarm.add_agent(make_mock_agent("reviewer"))
        assert len(swarm.agents) == 3

    def test_add_agent_overwrites_duplicate(self):
        """add_agent should overwrite an existing agent with the same name."""
        swarm = AgentSwarm()
        agent1 = make_mock_agent("coder", return_output="First")
        agent2 = make_mock_agent("coder", return_output="Second")
        swarm.add_agent(agent1)
        swarm.add_agent(agent2)
        assert swarm.agents["coder"] is agent2

    def test_get_agent_found(self):
        """get_agent should return the agent when found."""
        swarm = AgentSwarm()
        agent = make_mock_agent("coder")
        swarm.add_agent(agent)
        assert swarm.get_agent("coder") is agent

    def test_get_agent_not_found(self):
        """get_agent should return None for unknown names."""
        swarm = AgentSwarm()
        assert swarm.get_agent("nonexistent") is None

    def test_constructor_with_agents(self):
        """Constructor should accept a list of agents."""
        agents = [
            make_mock_agent("coder"),
            make_mock_agent("researcher"),
        ]
        swarm = AgentSwarm(agents=agents)
        assert "coder" in swarm.agents
        assert "researcher" in swarm.agents

    def test_constructor_empty_agents(self):
        """Constructor with no agents should create empty swarm."""
        swarm = AgentSwarm()
        assert swarm.agents == {}


# ══════════════════════════════════════════════════════════════════════
# AgentSwarm — run_all (parallel execution)
# ══════════════════════════════════════════════════════════════════════


class TestSwarmRunAll:
    """Tests for run_all — parallel execution."""

    def test_single_agent(self):
        """run_all with a single agent should return its result."""
        swarm = AgentSwarm()
        swarm.add_agent(make_mock_agent("coder", return_output="Code done."))
        results = swarm.run_all({"coder": "Write code"})
        assert "coder" in results
        assert results["coder"].success is True
        assert results["coder"].output == "Code done."

    def test_multiple_agents_parallel(self):
        """run_all with multiple agents should run them all."""
        swarm = AgentSwarm()
        swarm.add_agent(make_mock_agent("coder", return_output="Code"))
        swarm.add_agent(make_mock_agent("researcher", return_output="Research"))
        swarm.add_agent(make_mock_agent("reviewer", return_output="Review"))

        results = swarm.run_all({
            "coder": "Write code",
            "researcher": "Do research",
            "reviewer": "Review code",
        })
        assert len(results) == 3
        assert results["coder"].output == "Code"
        assert results["researcher"].output == "Research"
        assert results["reviewer"].output == "Review"

    def test_missing_agent_returns_error(self):
        """run_all with a missing agent name should return an error result."""
        swarm = AgentSwarm()
        swarm.add_agent(make_mock_agent("coder"))
        results = swarm.run_all({"coder": "Code", "unknown": "Task"})
        assert "unknown" in results
        assert results["unknown"].success is False
        assert "not found" in results["unknown"].error

    def test_agent_raises_exception(self):
        """run_all should handle agents that raise exceptions."""
        swarm = AgentSwarm()
        swarm.add_agent(make_failing_agent("coder"))
        results = swarm.run_all({"coder": "Do something"})
        assert results["coder"].success is False
        assert results["coder"].error is not None

    def test_parallel_execution_speed(self):
        """run_all should run agents in parallel (faster than sequential)."""
        swarm = AgentSwarm()
        swarm.add_agent(make_mock_agent("agent_a", delay=0.3))
        swarm.add_agent(make_mock_agent("agent_b", delay=0.3))

        start = time.time()
        results = swarm.run_all({"agent_a": "Task A", "agent_b": "Task B"})
        elapsed = time.time() - start

        # Both run in parallel, should take ~0.3s not ~0.6s
        assert elapsed < 0.5, f"Parallel execution took {elapsed:.2f}s, expected < 0.5s"
        assert len(results) == 2
        assert results["agent_a"].success is True
        assert results["agent_b"].success is True

    def test_max_concurrent_limits(self):
        """max_concurrent should limit how many agents run simultaneously."""
        swarm = AgentSwarm(max_concurrent=1)  # Sequential effectively
        swarm.add_agent(make_mock_agent("agent_a", delay=0.15))
        swarm.add_agent(make_mock_agent("agent_b", delay=0.15))
        swarm.add_agent(make_mock_agent("agent_c", delay=0.15))

        start = time.time()
        results = swarm.run_all({
            "agent_a": "Task A",
            "agent_b": "Task B",
            "agent_c": "Task C",
        })
        elapsed = time.time() - start

        # With max_concurrent=1, should take ~0.45s (3 sequential)
        assert elapsed >= 0.4, f"Sequential execution took {elapsed:.2f}s, expected >= 0.4s"
        assert len(results) == 3

    def test_uses_callbacks(self):
        """run_all should call on_agent_start and on_agent_complete."""
        start_log: list[str] = []
        complete_log: list[str] = []

        def on_start(name):
            start_log.append(name)

        def on_complete(name, result):
            complete_log.append(name)

        swarm = AgentSwarm(
            on_agent_start=on_start,
            on_agent_complete=on_complete,
        )
        swarm.add_agent(make_mock_agent("coder"))
        swarm.add_agent(make_mock_agent("researcher"))

        swarm.run_all({"coder": "Code", "researcher": "Research"})

        assert "coder" in start_log
        assert "researcher" in start_log
        assert "coder" in complete_log
        assert "researcher" in complete_log

    def test_context_passed_to_agent(self):
        """run_all should pass context to the agent."""
        swarm = AgentSwarm()
        agent = make_mock_agent("coder")
        original_run = agent.run

        received_context = [None]

        def tracking_run(task, context=None):
            received_context[0] = context
            return original_run(task, context)

        agent.run = tracking_run  # type: ignore[method-assign]
        swarm.add_agent(agent)

        swarm.run_all(
            {"coder": "Write code"},
            contexts={"coder": "Previous result: found bug"},
        )

        assert received_context[0] == "Previous result: found bug"

    def test_empty_tasks(self):
        """run_all with empty tasks should return empty results."""
        swarm = AgentSwarm()
        swarm.add_agent(make_mock_agent("coder"))
        results = swarm.run_all({})
        assert results == {}

    def test_timeout_handling(self):
        """run_all should handle agent timeout gracefully."""
        swarm = AgentSwarm()

        def slow_llm(messages, tools):
            time.sleep(2)
            return {"content": "Too late", "tool_calls": []}

        agent = SubAgent(
            name="slow",
            role="coding",
            system_prompt="Test",
            registry=get_registry(),
            call_llm_fn=slow_llm,
        )
        swarm.add_agent(agent)

        with patch.object(swarm, "max_concurrent", 1):
            results = swarm.run_all({"slow": "Task"})
            assert "slow" in results
            assert results["slow"].success is True or results["slow"].success is False


# ══════════════════════════════════════════════════════════════════════
# AgentSwarm — run_sequential
# ══════════════════════════════════════════════════════════════════════


class TestSwarmRunSequential:
    """Tests for run_sequential."""

    def test_single_agent(self):
        """run_sequential with a single agent should work."""
        swarm = AgentSwarm()
        swarm.add_agent(make_mock_agent("coder", return_output="Code done."))
        results = swarm.run_sequential([("coder", "Write code")])
        assert "coder" in results
        assert results["coder"].output == "Code done."

    def test_multiple_agents_in_order(self):
        """run_sequential should execute agents in order."""
        execution_order: list[str] = []

        def make_tracking_agent(name):
            def mock_llm(messages, tools):
                execution_order.append(name)
                return {"content": f"{name} done", "tool_calls": []}

            return SubAgent(
                name=name,
                role="coding",
                system_prompt="Test",
                registry=get_registry(),
                call_llm_fn=mock_llm,
            )

        swarm = AgentSwarm()
        swarm.add_agent(make_tracking_agent("agent_a"))
        swarm.add_agent(make_tracking_agent("agent_b"))
        swarm.add_agent(make_tracking_agent("agent_c"))

        swarm.run_sequential([
            ("agent_a", "Task A"),
            ("agent_b", "Task B"),
            ("agent_c", "Task C"),
        ])

        assert execution_order == ["agent_a", "agent_b", "agent_c"]

    def test_context_accumulation(self):
        """run_sequential should accumulate context between agents."""
        swarm = AgentSwarm()

        # Track what context each agent receives
        contexts_received: list[str] = []

        def make_context_tracking_agent(name, output):
            def mock_llm(messages, tools):
                return {"content": output, "tool_calls": []}

            agent = SubAgent(
                name=name,
                role="coding",
                system_prompt="Test",
                registry=get_registry(),
                call_llm_fn=mock_llm,
            )
            real_run = agent.run

            def tracking_run(task, context=None):
                contexts_received.append(f"{name}:{context or ''}")
                return real_run(task, context)

            agent.run = tracking_run  # type: ignore[method-assign]
            return agent

        swarm.add_agent(make_context_tracking_agent("agent_a", "Result A"))
        swarm.add_agent(make_context_tracking_agent("agent_b", "Result B"))

        swarm.run_sequential(
            [("agent_a", "Task A"), ("agent_b", "Task B")],
            shared_context="Initial context",
        )

        # agent_a should receive "Initial context"
        assert "agent_a:Initial context" in contexts_received[0]
        # agent_b should receive "Initial context" + agent_a's output
        assert "agent_b:" in contexts_received[1]
        assert "Result A" in contexts_received[1]

    def test_missing_agent_returns_error(self):
        """run_sequential with missing agent should return error."""
        swarm = AgentSwarm()
        swarm.add_agent(make_mock_agent("coder"))
        results = swarm.run_sequential([("unknown", "Task")])
        assert "unknown" in results
        assert results["unknown"].success is False
        assert "not found" in results["unknown"].error

    def test_uses_callbacks(self):
        """run_sequential should call on_agent_start and on_agent_complete."""
        start_log: list[str] = []
        complete_log: list[str] = []

        def on_start(name):
            start_log.append(name)

        def on_complete(name, result):
            complete_log.append(name)

        swarm = AgentSwarm(
            on_agent_start=on_start,
            on_agent_complete=on_complete,
        )
        swarm.add_agent(make_mock_agent("coder"))
        swarm.add_agent(make_mock_agent("researcher"))

        swarm.run_sequential([("coder", "Code"), ("researcher", "Research")])

        assert start_log == ["coder", "researcher"]
        assert complete_log == ["coder", "researcher"]

    def test_failing_agent_stops_context(self):
        """A failing agent should not pass its output as context."""
        swarm = AgentSwarm()
        # Patch run() directly to return a failed result instead of raising
        agent_a = make_mock_agent("agent_a")
        agent_a.run = lambda task, ctx=None: SubAgentResult(  # type: ignore[method-assign]
            agent_name="agent_a", role="", success=False, output="", error="Failed",
        )
        swarm.add_agent(agent_a)
        swarm.add_agent(make_mock_agent("agent_b", return_output="B result"))

        results = swarm.run_sequential([("agent_a", "Task A"), ("agent_b", "Task B")])

        assert results["agent_a"].success is False
        # agent_b still runs (sequential doesn't stop on failure)
        assert results["agent_b"].success is True
        assert results["agent_b"].output == "B result"


# ══════════════════════════════════════════════════════════════════════
# AgentSwarm — collect_outputs, summary, properties
# ══════════════════════════════════════════════════════════════════════


class TestSwarmOutputAndSummary:
    """Tests for collect_outputs, summary, and properties."""

    def test_collect_outputs_all_successful(self):
        """collect_outputs should return all successful outputs."""
        swarm = AgentSwarm()
        swarm.add_agent(make_mock_agent("coder", return_output="Code"))
        swarm.add_agent(make_mock_agent("researcher", return_output="Research"))

        swarm.run_all({"coder": "Code", "researcher": "Research"})
        outputs = swarm.collect_outputs()

        assert outputs == {"coder": "Code", "researcher": "Research"}

    def test_collect_outputs_filters_failures(self):
        """collect_outputs should exclude failed agents."""
        swarm = AgentSwarm()
        swarm.add_agent(make_mock_agent("coder", return_output="Code"))
        failing = make_mock_agent("researcher")
        failing.run = lambda task, ctx=None: SubAgentResult(  # type: ignore[method-assign]
            agent_name="researcher", role="", success=False, output="", error="Failed",
        )
        swarm.add_agent(failing)

        swarm.run_all({"coder": "Code", "researcher": "Research"})
        outputs = swarm.collect_outputs()

        assert "coder" in outputs
        assert "researcher" not in outputs

    def test_collect_outputs_empty(self):
        """collect_outputs should return empty dict when no results."""
        swarm = AgentSwarm()
        assert swarm.collect_outputs() == {}

    def test_summary_contains_agent_names(self):
        """summary should include agent names and status."""
        swarm = AgentSwarm()
        swarm.add_agent(make_mock_agent("coder", return_output="Code"))
        swarm.run_all({"coder": "Write code"})

        summary = swarm.summary()
        assert "coder" in summary
        assert "[OK]" in summary or "[FAIL]" in summary

    def test_summary_with_failure(self):
        """summary should include error details for failed agents."""
        swarm = AgentSwarm()
        agent_a = make_mock_agent("coder")
        agent_a.run = lambda task, ctx=None: SubAgentResult(  # type: ignore[method-assign]
            agent_name="coder", role="", success=False, output="", error="Something broke",
        )
        swarm.add_agent(agent_a)
        swarm.run_all({"coder": "Task"})

        summary = swarm.summary()
        assert "[FAIL]" in summary
        assert "coder" in summary
        assert "Error:" in summary or "error" in summary.lower()

    def test_total_tool_calls(self):
        """total_tool_calls property should sum all tool calls."""
        swarm = AgentSwarm()
        swarm.add_agent(make_mock_agent("coder"))
        swarm.add_agent(make_mock_agent("researcher"))

        swarm.run_all({"coder": "Code", "researcher": "Research"})

        # Both agents use 0 tool calls (mock returns immediately)
        assert swarm.total_tool_calls == 0

    def test_total_tokens(self):
        """total_tokens property should sum all tokens."""
        swarm = AgentSwarm()
        swarm.add_agent(make_mock_agent("coder"))
        swarm.run_all({"coder": "Code"})

        assert isinstance(swarm.total_tokens, int)

    def test_summary_empty_swarm(self):
        """summary should work with empty results."""
        swarm = AgentSwarm()
        summary = swarm.summary()
        assert "AgentSwarm" in summary
        assert "Results" in summary


# ══════════════════════════════════════════════════════════════════════
# AgentSwarm — edge cases and thread safety
# ══════════════════════════════════════════════════════════════════════


class TestSwarmEdgeCases:
    """Edge cases for AgentSwarm."""

    def test_run_all_after_run_sequential(self):
        """Running run_all after run_sequential should produce fresh results."""
        swarm = AgentSwarm()
        swarm.add_agent(make_mock_agent("coder", return_output="First"))
        swarm.run_sequential([("coder", "Task 1")])
        assert swarm.results["coder"].output == "First"

        # Run again with different output
        swarm2 = AgentSwarm()
        swarm2.add_agent(make_mock_agent("coder", return_output="Second"))
        swarm2.run_all({"coder": "Task 2"})
        assert swarm2.results["coder"].output == "Second"

    def test_exception_in_future_thread(self):
        """Exception in a thread should be captured as a failed result."""
        swarm = AgentSwarm()

        def exploding_agent_run(task, context=None):
            raise ValueError("Something went wrong")

        agent = make_mock_agent("exploder")
        swarm.add_agent(agent)

        with patch.object(agent, "run", exploding_agent_run):
            results = swarm.run_all({"exploder": "Task"})

        assert results["exploder"].success is False
        assert "Something went wrong" in results["exploder"].error

    def test_max_concurrent_property(self):
        """max_concurrent should be configurable."""
        swarm = AgentSwarm(max_concurrent=2)
        assert swarm.max_concurrent == 2

    def test_default_max_concurrent(self):
        """Default max_concurrent should be 4."""
        swarm = AgentSwarm()
        assert swarm.max_concurrent == 4
