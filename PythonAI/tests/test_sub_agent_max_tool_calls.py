"""Unit tests for the max_tool_calls logic in SubAgent.

Tests cover:
  - Default max_tool_calls value (4)
  - Custom max_tool_calls value
  - Safety check triggers final synthesis at the limit
  - All 4 classmethods pass max_tool_calls through
  - System prompts contain stop-after-instructions
  - Edge cases: max_tool_calls=0 (no tools allowed), max_tool_calls=1
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.agents.sub_agent import SubAgent
from src.core.registry import get_registry
from src.core.tools import register_all_tools

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def registry():
    reg = get_registry()
    register_all_tools(reg)
    return reg


def make_mock_call_llm() -> MagicMock:
    """Create a mock call_llm_fn that returns a simple response."""
    mock = MagicMock()
    mock.return_value = {"content": "Task complete.", "tool_calls": []}
    return mock


# ── max_tool_calls default and customization ───────────────────────────


class TestMaxToolCallsDefault:
    """Default max_tool_calls should be 4."""

    def test_default_is_4(self, registry):
        """Creating a SubAgent without max_tool_calls should default to 4."""
        agent = SubAgent(
            name="test",
            role="coding",
            system_prompt="Test prompt",
            registry=registry,
            call_llm_fn=make_mock_call_llm(),
        )
        assert agent.max_tool_calls == 4

    def test_custom_max_tool_calls(self, registry):
        """Passing max_tool_calls should override the default."""
        agent = SubAgent(
            name="test",
            role="coding",
            system_prompt="Test prompt",
            max_tool_calls=7,
            registry=registry,
            call_llm_fn=make_mock_call_llm(),
        )
        assert agent.max_tool_calls == 7

    def test_max_tool_calls_zero(self, registry):
        """max_tool_calls=0 should mean no tool calls allowed."""
        agent = SubAgent(
            name="test",
            role="coding",
            system_prompt="Test prompt",
            max_tool_calls=0,
            registry=registry,
            call_llm_fn=make_mock_call_llm(),
        )
        assert agent.max_tool_calls == 0


# ── Safety check in run() loop ─────────────────────────────────────────


class TestSafetyCheck:
    """The safety check should trigger synthesis at the max_tool_calls limit."""

    def test_no_tool_calls_success(self, registry):
        """Agent with no tool calls should complete successfully."""
        mock_llm = MagicMock()
        mock_llm.return_value = {"content": "All done.", "tool_calls": []}

        agent = SubAgent(
            name="test", role="coding",
            system_prompt="Test",
            max_tool_calls=4,
            registry=registry,
            call_llm_fn=mock_llm,
        )
        result = agent.run("do something")
        assert result.success is True
        assert result.tool_calls_used == 0
        assert "All done." in result.output

    def test_safety_net_triggers_at_limit(self, registry):
        """When tool_calls >= max_tool_calls, safety net should force synthesis."""
        # Mock _call_llm: first call returns a tool call, second call returns content
        call_count = 0

        def mock_call_llm(messages, tools):
            nonlocal call_count
            call_count += 1
            if call_count <= 4:
                # Return a tool call
                return {
                    "content": "Using a tool...",
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": '{"command": "echo hello"}',
                        },
                    }],
                }
            else:
                # Final synthesis call (tools=[] empty)
                assert tools == [], \
                    f"Expected empty tools for final synthesis, got {len(tools)} tools"
                return {"content": "Final synthesis complete.", "tool_calls": []}

        agent = SubAgent(
            name="test", role="coding",
            system_prompt="Test",
            max_tool_calls=4,
            registry=registry,
            call_llm_fn=mock_call_llm,
            on_stream=lambda msg: None,
        )
        result = agent.run("do something")

        assert result.success is True
        assert result.tool_calls_used == 4
        assert "Final synthesis complete." in result.output

    def test_safety_net_rejects_excess_tools(self, registry):
        """Agent should NOT exceed max_tool_calls even if LLM keeps returning tools."""
        tool_count = 0

        def mock_llm(messages, tools):
            nonlocal tool_count
            tool_count += 1
            if tool_count <= 6:  # Try to keep making tool calls
                return {
                    "content": "More tools...",
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": '{"command": "echo hello"}',
                        },
                    }],
                }
            return {"content": "Done.", "tool_calls": []}

        agent = SubAgent(
            name="test", role="coding",
            system_prompt="Test",
            max_tool_calls=3,
            registry=registry,
            call_llm_fn=mock_llm,
            on_stream=lambda msg: None,
        )
        result = agent.run("do something")

        assert result.tool_calls_used == 3  # Should stop at 3, not 6
        assert result.success is True


    def test_safety_net_final_call_returns_none(self, registry):
        """When safety net's final LLM returns None, should fall through gracefully."""
        call_count = 0

        def mock_llm(messages, tools):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "content": "Using a tool...",
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": '{"command": "echo hello"}',
                        },
                    }],
                }
            # Safety net call: return None (LLM failure)
            return None

        agent = SubAgent(
            name="test", role="coding",
            system_prompt="Test",
            max_tool_calls=1,
            registry=registry,
            call_llm_fn=mock_llm,
            on_stream=lambda msg: None,
        )
        result = agent.run("do something")

        # Should still produce a result (falls through to final return)
        assert result.tool_calls_used == 1
        assert isinstance(result.output, str)

    def test_safety_net_final_call_empty_content(self, registry):
        """When safety net's final LLM has empty content, should fall through."""
        call_count = 0

        def mock_llm(messages, tools):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "content": "Using a tool...",
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": '{"command": "echo hello"}',
                        },
                    }],
                }
            # Safety net call: return empty content (no synthesis)
            return {"content": "", "tool_calls": []}

        agent = SubAgent(
            name="test", role="coding",
            system_prompt="Test",
            max_tool_calls=1,
            registry=registry,
            call_llm_fn=mock_llm,
            on_stream=lambda msg: None,
        )
        result = agent.run("do something")

        # Should still produce a result (falls through to final return)
        assert result.tool_calls_used == 1
        assert isinstance(result.output, str)


# ── Edge cases ─────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases for max_tool_calls."""

    def test_max_tool_calls_zero_immediate_synthesis(self, registry):
        """max_tool_calls=0 should skip tools and return immediately."""
        mock_llm = MagicMock()
        mock_llm.return_value = {"content": "No tools needed.", "tool_calls": []}

        agent = SubAgent(
            name="test", role="coding",
            system_prompt="Test",
            max_tool_calls=0,
            registry=registry,
            call_llm_fn=mock_llm,
        )
        result = agent.run("do something")
        assert result.success is True
        assert result.tool_calls_used == 0

    def test_max_tool_calls_one_stops_after_one(self, registry):
        """max_tool_calls=1 should stop after exactly 1 tool call."""
        call_count = 0

        def mock_llm(messages, tools):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "content": "Using a tool...",
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": '{"command": "echo hello"}',
                        },
                    }],
                }
            return {"content": "Synthesis.", "tool_calls": []}

        agent = SubAgent(
            name="test", role="coding",
            system_prompt="Test",
            max_tool_calls=1,
            registry=registry,
            call_llm_fn=mock_llm,
            on_stream=lambda msg: None,
        )
        result = agent.run("do something")
        assert result.tool_calls_used == 1
        assert result.success is True

    def test_max_tool_calls_large_value(self, registry):
        """max_tool_calls=10 should allow up to 10 tool calls."""
        call_count = 0

        def mock_llm(messages, tools):
            nonlocal call_count
            call_count += 1
            if call_count <= 6:
                return {
                    "content": "Tool call...",
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": '{"command": "echo hello"}',
                        },
                    }],
                }
            return {"content": "Done.", "tool_calls": []}

        agent = SubAgent(
            name="test", role="coding",
            system_prompt="Test",
            max_tool_calls=10,
            registry=registry,
            call_llm_fn=mock_llm,
            on_stream=lambda msg: None,
        )
        result = agent.run("do something")
        assert result.tool_calls_used == 6  # All 6 tool calls used
        assert result.success is True

    def test_mixed_tool_and_no_tool_calls(self, registry):
        """Agent should handle mixed rounds (tools + no tools) correctly."""
        call_count = 0

        def mock_llm(messages, tools):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "content": "Tool call...",
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": '{"command": "echo hello"}',
                        },
                    }],
                }
            # Round 2: no tool calls -> success
            return {"content": "Final result.", "tool_calls": []}

        agent = SubAgent(
            name="test", role="coding",
            system_prompt="Test",
            max_tool_calls=4,
            registry=registry,
            call_llm_fn=mock_llm,
        )
        result = agent.run("do something")
        assert result.tool_calls_used == 1  # Only 1 tool call
        assert result.success is True
        assert "Final result." in result.output


# ── Classmethod threading ──────────────────────────────────────────────


class TestClassmethodThreading:
    """All 4 classmethods should accept and pass max_tool_calls."""

    def test_coding_agent_passes_max_tool_calls(self, registry):
        """coding_agent should accept custom max_tool_calls."""
        agent = SubAgent.coding_agent(
            registry=registry,
            call_llm_fn=make_mock_call_llm(),
            max_tool_calls=7,
        )
        assert agent.max_tool_calls == 7

    def test_research_agent_passes_max_tool_calls(self, registry):
        """research_agent should accept custom max_tool_calls."""
        agent = SubAgent.research_agent(
            registry=registry,
            call_llm_fn=make_mock_call_llm(),
            max_tool_calls=2,
        )
        assert agent.max_tool_calls == 2

    def test_mcp_agent_passes_max_tool_calls(self, registry):
        """mcp_agent should accept custom max_tool_calls."""
        agent = SubAgent.mcp_agent(
            registry=registry,
            call_llm_fn=make_mock_call_llm(),
            max_tool_calls=5,
        )
        assert agent.max_tool_calls == 5

    def test_review_agent_passes_max_tool_calls(self, registry):
        """review_agent should accept custom max_tool_calls."""
        agent = SubAgent.review_agent(
            registry=registry,
            call_llm_fn=make_mock_call_llm(),
            max_tool_calls=3,
        )
        assert agent.max_tool_calls == 3

    def test_all_classmethods_default_to_4(self, registry):
        """All classmethods should default max_tool_calls to 4."""
        mock = make_mock_call_llm()
        assert SubAgent.coding_agent(registry=registry, call_llm_fn=mock).max_tool_calls == 4
        assert SubAgent.research_agent(registry=registry, call_llm_fn=mock).max_tool_calls == 4
        assert SubAgent.mcp_agent(registry=registry, call_llm_fn=mock).max_tool_calls == 4
        assert SubAgent.review_agent(registry=registry, call_llm_fn=mock).max_tool_calls == 4


# ── System prompts ─────────────────────────────────────────────────────


class TestSystemPrompts:
    """System prompts should contain the stop-after-instructions."""

    STOP_PHRASE = "After 2-3 tool calls"

    def test_coding_system_prompt_has_stop_instruction(self):
        """Coding agent's system prompt should tell the LLM to stop after 2-3 calls."""
        agent = SubAgent.coding_agent()
        assert self.STOP_PHRASE in agent.system_prompt

    def test_research_system_prompt_has_stop_instruction(self):
        """Research agent's system prompt should tell the LLM to stop."""
        agent = SubAgent.research_agent()
        assert self.STOP_PHRASE in agent.system_prompt

    def test_mcp_system_prompt_has_stop_instruction(self):
        """MCP agent's system prompt should tell the LLM to stop."""
        agent = SubAgent.mcp_agent()
        assert self.STOP_PHRASE in agent.system_prompt

    def test_review_system_prompt_has_stop_instruction(self):
        """Review agent's system prompt should tell the LLM to stop."""
        agent = SubAgent.review_agent()
        # Review agent uses "After 1-2 read tool calls" instead
        assert "After 1-2" in agent.system_prompt
        assert "tool calls" in agent.system_prompt

    def test_build_system_prompt_includes_workflow(self, registry):
        """_build_system_prompt should include WORKFLOW section."""
        agent = SubAgent(
            name="test", role="coding",
            system_prompt="Test prompt",
            registry=registry,
            call_llm_fn=make_mock_call_llm(),
        )
        prompt = agent._build_system_prompt("test task", None)
        assert "WORKFLOW" in prompt
        assert "1-3 tools" in prompt
        assert "STOP making tool calls" in prompt


# ── max_retries: retry mechanism ──────────────────────────────────────


class TestMaxRetries:
    """max_retries should allow retrying failed LLM calls."""

    def test_max_retries_default_is_2(self):
        """Default max_retries should be 2 (from MAX_LLM_RETRIES constant)."""
        agent = SubAgent(
            name="test", role="coding",
            system_prompt="Test",
            call_llm_fn=MagicMock(),
        )
        assert agent.max_retries == 2

    def test_custom_max_retries(self):
        """Custom max_retries should override the default."""
        agent = SubAgent(
            name="test", role="coding",
            system_prompt="Test",
            max_retries=5,
            call_llm_fn=MagicMock(),
        )
        assert agent.max_retries == 5

    def test_max_retries_zero(self):
        """max_retries=0 should mean no retries (single attempt)."""
        agent = SubAgent(
            name="test", role="coding",
            system_prompt="Test",
            max_retries=0,
            call_llm_fn=MagicMock(),
        )
        assert agent.max_retries == 0

    def test_classmethods_pass_max_retries(self, registry):
        """Classmethods should accept custom max_retries."""
        mock = MagicMock()
        assert SubAgent.coding_agent(registry=registry, call_llm_fn=mock, max_retries=3).max_retries == 3
        assert SubAgent.research_agent(registry=registry, call_llm_fn=mock, max_retries=3).max_retries == 3
        assert SubAgent.review_agent(registry=registry, call_llm_fn=mock, max_retries=3).max_retries == 3
        assert SubAgent.mcp_agent(registry=registry, call_llm_fn=mock, max_retries=3).max_retries == 3

    def test_classmethods_default_max_retries(self, registry):
        """Classmethods should default max_retries to 2."""
        mock = MagicMock()
        assert SubAgent.coding_agent(registry=registry, call_llm_fn=mock).max_retries == 2
        assert SubAgent.research_agent(registry=registry, call_llm_fn=mock).max_retries == 2
        assert SubAgent.review_agent(registry=registry, call_llm_fn=mock).max_retries == 2
        assert SubAgent.mcp_agent(registry=registry, call_llm_fn=mock).max_retries == 2


# ── Integration with ToolCallingEngine ─────────────────────────────────


class TestSafetyNetMessage:
    """The safety net should stream a message when triggered."""

    def test_safety_net_streams_message(self, registry):
        """When max_tool_calls is hit, a 'Max tools reached' message should stream."""
        stream_log: list[str] = []
        call_count = 0

        def mock_llm(messages, tools):
            nonlocal call_count
            call_count += 1
            if call_count <= 4:
                return {
                    "content": "Tool...",
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": '{"command": "echo hello"}',
                        },
                    }],
                }
            return {"content": "Synthesis.", "tool_calls": []}

        agent = SubAgent(
            name="test", role="coding",
            system_prompt="Test",
            max_tool_calls=4,
            registry=registry,
            call_llm_fn=mock_llm,
            on_stream=lambda msg: stream_log.append(msg),
        )
        result = agent.run("do something")

        assert result.success is True
        # Check that "Max tools reached" was streamed
        assert any("Max tools reached" in msg for msg in stream_log)
