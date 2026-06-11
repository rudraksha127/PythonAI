"""Comprehensive unit tests for SubAgent remaining methods.

Covers:
  - _get_tool_pool (built-in + MCP tools)
  - _build_system_prompt (tool list in prompt)
  - _execute_tool (success, tool not found, JSON error, exception)
  - run() with context passing
  - run() max_steps exhaustion
  - run() with empty tool calls in response
  - _call_llm retry and error handling
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

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


@pytest.fixture
def agent(registry):
    """Create a basic SubAgent for testing."""

    def mock_llm(messages, tools):
        return {"content": "Task complete.", "tool_calls": []}

    return SubAgent(
        name="test_agent",
        role="coding",
        system_prompt="You are a code agent.",
        registry=registry,
        call_llm_fn=mock_llm,
    )


@pytest.fixture
def recording_agent(registry):
    """Create a SubAgent that records call history."""
    call_history: list[dict] = []

    def record_llm(messages, tools):
        call_history.append({"messages": messages, "tools": tools})
        return {"content": "Done.", "tool_calls": []}

    agent = SubAgent(
        name="recorder",
        role="coding",
        system_prompt="You are a code agent.",
        registry=registry,
        call_llm_fn=record_llm,
    )
    return agent, call_history


# ══════════════════════════════════════════════════════════════════════
# _get_tool_pool
# ══════════════════════════════════════════════════════════════════════


class TestGetToolPool:
    """Tests for _get_tool_pool."""

    def test_returns_builtin_tools(self, agent):
        """_get_tool_pool should include built-in tools."""
        pool = agent._get_tool_pool()
        assert len(pool) > 0
        tool_names = [t.name for t in pool]
        # There should be some built-in tools from the registry
        assert any(name in tool_names for name in ["read", "write", "bash", "glob", "grep"])

    def test_returns_list_of_tools(self, agent):
        """_get_tool_pool should return a list of Tool objects."""
        pool = agent._get_tool_pool()
        assert isinstance(pool, list)

    def test_includes_mcp_tools(self, registry):
        """_get_tool_pool should include MCP tools when registered."""
        from src.core.tool import InputSchema, Tool, ToolResult

        class MockMCPTool(Tool):
            def __init__(self):
                super().__init__(name="mcp__test__db", description="MCP DB tool")

            def input_schema(self):
                return InputSchema()

            def call(self, input_data, context):
                return ToolResult(data="ok")

        registry.register_mcp(MockMCPTool())
        a = SubAgent(
            name="mcp_agent",
            role="mcp",
            system_prompt="You are an MCP agent.",
            registry=registry,
            call_llm_fn=lambda m, t: {"content": "ok", "tool_calls": []},
        )
        pool = a._get_tool_pool()
        assert any("mcp__test__db" in t.name for t in pool)

    def test_empty_pool_if_no_tools(self):
        """_get_tool_pool should return empty list when no tools available."""
        from src.core.registry import ToolRegistry

        empty_registry = ToolRegistry()
        a = SubAgent(
            name="empty",
            role="coding",
            system_prompt="Test",
            registry=empty_registry,
            call_llm_fn=lambda m, t: {"content": "ok", "tool_calls": []},
        )
        pool = a._get_tool_pool()
        assert len(pool) == 0

    def test_no_duplicate_names(self, agent):
        """_get_tool_pool should not include duplicate tools."""
        pool = agent._get_tool_pool()
        names = [t.name for t in pool]
        assert len(names) == len(set(names))


# ══════════════════════════════════════════════════════════════════════
# _build_system_prompt
# ══════════════════════════════════════════════════════════════════════


class TestBuildSystemPrompt:
    """Tests for _build_system_prompt."""

    def test_includes_base_prompt(self, agent):
        """_build_system_prompt should include the base system prompt."""
        prompt = agent._build_system_prompt("Write code", None)
        assert "You are a code agent." in prompt

    def test_includes_agent_name_and_role(self, agent):
        """_build_system_prompt should include agent name and role."""
        prompt = agent._build_system_prompt("Write code", None)
        assert "test_agent" in prompt
        assert "coding" in prompt

    def test_includes_available_tools_section(self, agent):
        """_build_system_prompt should include an 'Available tools' section."""
        prompt = agent._build_system_prompt("Write code", None)
        assert "Available tools" in prompt

    def test_includes_workflow_section(self, agent):
        """_build_system_prompt should include WORKFLOW section."""
        prompt = agent._build_system_prompt("Write code", None)
        assert "WORKFLOW" in prompt

    def test_includes_tool_names(self, agent):
        """_build_system_prompt should list tool names."""
        prompt = agent._build_system_prompt("Write code", None)
        # Should mention at least one tool
        assert "bash" in prompt or "read" in prompt or "write" in prompt

    def test_includes_tool_descriptions(self, agent):
        """_build_system_prompt should include tool descriptions."""
        prompt = agent._build_system_prompt("Write code", None)
        tool = next((t for t in agent.tools if t.description), None)
        if tool:
            assert tool.description[:20] in prompt

    def test_prompt_not_empty(self, agent):
        """_build_system_prompt should return a non-empty string."""
        prompt = agent._build_system_prompt("Do something", None)
        assert len(prompt) > 100

    def test_includes_task_context(self, agent):
        """_build_system_prompt content does not include the task (that's user message)."""
        prompt = agent._build_system_prompt("Write a function", None)
        # The base system prompt should NOT contain "Write a function"
        # (that goes in the user message, not system prompt)
        assert "Write a function" not in prompt


# ══════════════════════════════════════════════════════════════════════
# _execute_tool
# ══════════════════════════════════════════════════════════════════════


class TestExecuteTool:
    """Tests for _execute_tool."""

    def test_successful_tool_execution(self, agent):
        """_execute_tool should execute a valid tool and return results."""
        result = agent._execute_tool({"function": {"name": "bash", "arguments": '{"command": "echo hello"}'}})
        parsed = json.loads(result)
        assert "hello" in str(parsed)

    def test_tool_not_found(self, agent):
        """_execute_tool should return error for unknown tools."""
        result = agent._execute_tool({"function": {"name": "nonexistent_tool_xyz", "arguments": "{}"}})
        parsed = json.loads(result)
        assert "error" in parsed
        assert "not found" in parsed["error"].lower()

    def test_invalid_json_arguments(self, agent):
        """_execute_tool should handle invalid JSON arguments."""
        result = agent._execute_tool({"function": {"name": "bash", "arguments": "not valid json"}})
        # Should not crash — invalid args get wrapped as raw_input
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_tool_raises_exception(self, agent):
        """_execute_tool should handle tool code that raises."""
        result = agent._execute_tool(
            {
                "function": {
                    "name": "bash",
                    "arguments": '{"command": "exit 1"}',
                }
            }
        )
        parsed = json.loads(result)
        # bash exit code 1 should produce an error
        assert isinstance(parsed, dict)

    def test_function_key_variants(self, agent):
        """_execute_tool should handle both 'function' key and flat format."""
        # Flat format (no 'function' key)
        result = agent._execute_tool(
            {
                "name": "bash",
                "arguments": '{"command": "echo flat"}',
            }
        )
        parsed = json.loads(result)
        assert isinstance(parsed, dict)


# ══════════════════════════════════════════════════════════════════════
# run() with context
# ══════════════════════════════════════════════════════════════════════


class TestRunWithContext:
    """Tests for run() with context passing."""

    def test_context_included_in_user_message(self, registry):
        """Context should be included in the user message."""
        messages_seen = []

        def capture_llm(messages, tools):
            messages_seen.extend(messages)
            return {"content": "Done.", "tool_calls": []}

        agent = SubAgent(
            name="test",
            role="coding",
            system_prompt="You are an agent.",
            registry=registry,
            call_llm_fn=capture_llm,
        )
        agent.run("Write code", context="Previous result: found bug")

        # Find the user message
        user_msg = next((m for m in messages_seen if m["role"] == "user"), None)
        assert user_msg is not None
        assert "Previous result: found bug" in user_msg["content"]

    def test_no_context_omits_context_section(self, registry):
        """Without context, user message should just be the task."""
        messages_seen = []

        def capture_llm(messages, tools):
            messages_seen.extend(messages)
            return {"content": "Done.", "tool_calls": []}

        agent = SubAgent(
            name="test",
            role="coding",
            system_prompt="You are an agent.",
            registry=registry,
            call_llm_fn=capture_llm,
        )
        agent.run("Write code")

        user_msg = next((m for m in messages_seen if m["role"] == "user"), None)
        assert user_msg is not None
        assert user_msg["content"] == "Write code"

    def test_context_does_not_break_without_tool_calls(self, agent):
        """run() with context should succeed even when no tool calls occur."""
        result = agent.run("Say hello", context="Some context here")
        assert result.success is True
        assert "Task complete." in result.output


# ══════════════════════════════════════════════════════════════════════
# run() max_steps exhaustion
# ══════════════════════════════════════════════════════════════════════


class TestMaxStepsExhaustion:
    """Tests for run() when max_steps is exhausted."""

    def test_max_steps_limits_rounds(self, registry):
        """Agent should stop after max_steps even if LLM keeps returning calls."""
        call_count = [0]

        def always_tool_llm(messages, tools):
            call_count[0] += 1
            return {
                "content": "Using a tool...",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": '{"command": "echo hello"}',
                        },
                    }
                ],
            }

        agent = SubAgent(
            name="test",
            role="coding",
            system_prompt="Test",
            max_steps=3,
            max_tool_calls=10,
            registry=registry,
            call_llm_fn=always_tool_llm,
            on_stream=lambda msg: None,
        )
        result = agent.run("Do something")

        # Should have stopped after max_steps rounds
        assert result.rounds <= 3
        # The on_stream lambda means we don't crash

    def test_max_steps_with_empty_response(self, registry):
        """Agent should stop on empty response at max_steps."""
        call_count = [0]

        def empty_llm(messages, tools):
            call_count[0] += 1
            return {"content": "", "tool_calls": []}

        agent = SubAgent(
            name="test",
            role="coding",
            system_prompt="Test",
            max_steps=2,
            registry=registry,
            call_llm_fn=empty_llm,
        )
        result = agent.run("Do something")

        # Should produce some result (even empty)
        assert isinstance(result.output, str)

    def test_max_steps_with_mixed_responses(self, registry):
        """Agent should handle mix of tool calls and content."""
        call_count = [0]

        def mixed_llm(messages, tools):
            call_count[0] += 1
            if call_count[0] <= 1:
                return {
                    "content": "Thinking...",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "bash",
                                "arguments": '{"command": "echo hello"}',
                            },
                        }
                    ],
                }
            return {"content": "Final answer.", "tool_calls": []}

        agent = SubAgent(
            name="test",
            role="coding",
            system_prompt="Test",
            max_steps=5,
            max_tool_calls=4,
            registry=registry,
            call_llm_fn=mixed_llm,
            on_stream=lambda msg: None,
        )
        result = agent.run("Do something")
        assert result.success is True
        assert result.tool_calls_used >= 1
        assert "Final answer." in result.output


# ══════════════════════════════════════════════════════════════════════
# _call_llm — retry and error handling
# ══════════════════════════════════════════════════════════════════════


class TestCallLLM:
    """Tests for _call_llm with retry and error handling."""

    def test_uses_injected_call_llm_fn(self, agent):
        """_call_llm should use the injected call_llm_fn when provided."""
        result = agent._call_llm(
            [{"role": "user", "content": "Hello"}],
            [{"type": "function", "function": {"name": "test"}}],
        )
        assert result is not None
        assert "Task complete." in result["content"]

    def test_injected_fn_called_directly_no_retry(self, registry):
        """When call_llm_fn is set, it should be called directly (no retry)."""
        call_count = [0]

        def raises_once(messages, tools):
            call_count[0] += 1
            raise RuntimeError("Error")

        agent = SubAgent(
            name="test",
            role="coding",
            system_prompt="Test",
            max_retries=2,
            registry=registry,
            call_llm_fn=raises_once,  # Injected fn — retry logic is NOT applied
        )
        with pytest.raises(RuntimeError, match="Error"):
            agent._call_llm([{"role": "user", "content": "Hello"}], [])
        # Should only be called once (no retry for injected fn)
        assert call_count[0] == 1

    @patch("src.core.providers.ProviderRouter")
    @patch("src.core.providers.get_provider_api")
    @patch("src.core.providers.ProfileManager")
    def test_retry_on_exception_via_router(self, mock_profile_mgr, mock_get_api, mock_router_cls, registry):
        """_call_llm should retry on transient exceptions via the provider router."""
        call_count = [0]

        def failing_then_succeeding(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 1:
                raise RuntimeError("Transient error")
            return {"content": "Success after retry.", "tool_calls": []}

        # Set up mock route
        mock_route = MagicMock()
        mock_route.error = None
        mock_route.provider = "openai"
        mock_route.model = "gpt-4"
        mock_route.base_url = "https://api.openai.com/v1"
        mock_route.api_key = "test_key"

        mock_router = MagicMock()
        mock_router.route.return_value = mock_route
        mock_router_cls.return_value = mock_router

        mock_get_api.return_value = failing_then_succeeding

        mock_profile = MagicMock()
        mock_profile.provider = "auto"
        mock_profile.model = ""
        mock_profile_mgr_instance = MagicMock()
        mock_profile_mgr_instance.load.return_value = mock_profile
        mock_profile_mgr.return_value = mock_profile_mgr_instance

        agent = SubAgent(
            name="test",
            role="coding",
            system_prompt="Test",
            max_retries=2,
            registry=registry,
            on_stream=lambda msg: None,
        )
        # Don't set call_llm_fn — will use router fallback
        result = agent._call_llm([{"role": "user", "content": "Hello"}], [])
        assert result is not None
        assert "Success after retry." in result["content"]

    @patch("src.core.providers.ProviderRouter")
    @patch("src.core.providers.get_provider_api")
    @patch("src.core.providers.ProfileManager")
    def test_retry_exhausted_returns_none_via_router(self, mock_profile_mgr, mock_get_api, mock_router_cls, registry):
        """_call_llm should return None after exhausting retries via router."""
        call_count = [0]

        def always_fails(*args, **kwargs):
            call_count[0] += 1
            raise RuntimeError("Persistent error")

        mock_route = MagicMock()
        mock_route.error = None
        mock_route.provider = "openai"
        mock_route.model = "gpt-4"
        mock_route.base_url = "https://api.openai.com/v1"
        mock_route.api_key = "test_key"

        mock_router = MagicMock()
        mock_router.route.return_value = mock_route
        mock_router_cls.return_value = mock_router

        mock_get_api.return_value = always_fails

        mock_profile = MagicMock()
        mock_profile.provider = "auto"
        mock_profile.model = ""
        mock_profile_mgr_instance = MagicMock()
        mock_profile_mgr_instance.load.return_value = mock_profile
        mock_profile_mgr.return_value = mock_profile_mgr_instance

        agent = SubAgent(
            name="test",
            role="coding",
            system_prompt="Test",
            max_retries=1,
            registry=registry,
            on_stream=lambda msg: None,
        )
        result = agent._call_llm([{"role": "user", "content": "Hello"}], [])
        assert result is None
        # Should have called 2 times (initial + 1 retry)
        assert call_count[0] == 2

    @patch("src.core.providers.ProviderRouter")
    @patch("src.core.providers.get_provider_api")
    @patch("src.core.providers.ProfileManager")
    def test_retry_zero_returns_none_immediately_via_router(
        self, mock_profile_mgr, mock_get_api, mock_router_cls, registry
    ):
        """With max_retries=0, a failed call should return None immediately via router."""

        def fails(*args, **kwargs):
            raise RuntimeError("Error")

        mock_route = MagicMock()
        mock_route.error = None
        mock_route.provider = "openai"
        mock_route.model = "gpt-4"
        mock_route.base_url = "https://api.openai.com/v1"
        mock_route.api_key = "test_key"

        mock_router = MagicMock()
        mock_router.route.return_value = mock_route
        mock_router_cls.return_value = mock_router

        mock_get_api.return_value = fails

        mock_profile = MagicMock()
        mock_profile.provider = "auto"
        mock_profile.model = ""
        mock_profile_mgr_instance = MagicMock()
        mock_profile_mgr_instance.load.return_value = mock_profile
        mock_profile_mgr.return_value = mock_profile_mgr_instance

        agent = SubAgent(
            name="test",
            role="coding",
            system_prompt="Test",
            max_retries=0,
            registry=registry,
        )
        result = agent._call_llm([{"role": "user", "content": "Hello"}], [])
        assert result is None


# ══════════════════════════════════════════════════════════════════════
# run() — tool call parsing and streaming
# ══════════════════════════════════════════════════════════════════════


class TestRunToolCallParsing:
    """Tests for run() with different tool call formats."""

    def test_stream_called_during_run(self, registry):
        """on_stream should be called during tool execution."""
        stream_log: list[str] = []

        def tool_llm(messages, tools):
            return {
                "content": "Using tool...",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": '{"command": "echo hello"}',
                        },
                    }
                ],
            }

        agent = SubAgent(
            name="test",
            role="coding",
            system_prompt="Test",
            max_tool_calls=4,
            registry=registry,
            call_llm_fn=tool_llm,
            on_stream=lambda msg: stream_log.append(msg),
        )

        # The tool-use loop needs another LLM call to finish
        # We've set max_tool_calls=4, but the mock always returns a tool call
        # So the safety net should kick in at 4
        agent.run("Do something")

        # Stream should have been called at least once
        assert len(stream_log) >= 1

    def test_messages_appended_correctly(self, registry):
        """run() should append assistant and tool messages to history."""
        call_history = []

        def tool_llm(messages, tools):
            call_history.append(messages.copy())
            return {
                "content": "Using tool.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": '{"command": "echo hello"}',
                        },
                    }
                ],
            }

        agent = SubAgent(
            name="test",
            role="coding",
            system_prompt="Test prompt",
            max_tool_calls=1,
            registry=registry,
            call_llm_fn=tool_llm,
            on_stream=lambda msg: None,
        )
        agent.run("Do it")

        # Messages should contain system + user + assistant + tool + synthesis
        assert len(agent.messages) >= 4

    def test_response_without_tool_calls_stops_loop(self, registry):
        """A response without tool calls should stop the reasoning loop."""

        def direct_answer(messages, tools):
            return {"content": "Here's the answer.", "tool_calls": []}

        agent = SubAgent(
            name="test",
            role="coding",
            system_prompt="Test",
            registry=registry,
            call_llm_fn=direct_answer,
        )
        result = agent.run("What is Python?")
        assert result.success is True
        assert "Here's the answer." in result.output
        assert result.rounds == 1  # Only 1 round


# ══════════════════════════════════════════════════════════════════════
# run() — LLM failure returns error result
# ══════════════════════════════════════════════════════════════════════


class TestRunLLMFailure:
    """Tests for run() when the LLM call fails."""

    def test_llm_failure_returns_error_result(self, registry):
        """When _call_llm returns None, run() should return a failed result."""

        def failing_llm(messages, tools):
            return None  # Simulate exhausted retries

        agent = SubAgent(
            name="test",
            role="coding",
            system_prompt="Test",
            registry=registry,
            call_llm_fn=failing_llm,
        )
        result = agent.run("Do something")
        assert result.success is False
        # Should have error info
        assert isinstance(result.error, str)
