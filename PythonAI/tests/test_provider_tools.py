"""
Unit tests for provider tools-parameter support across all 6 providers.
======================================================================

Verifies that each provider function:
  1. Accepts the tools parameter in its signature
  2. Includes tools + tool_choice in the API payload when tools are provided
  3. Omits tools from the payload when tools=None or tools=[]
  4. Correctly handles tool_calls in the API response
  5. Still handles errors gracefully with tools passed

NOTE: mock paths target each provider's module-level urlopen reference
because they use `from urllib.request import urlopen` (direct import).
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

SAMPLE_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for information",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from disk",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                },
                "required": ["path"],
            },
        },
    },
]

SAMPLE_MESSAGES: list[dict[str, str]] = [{"role": "user", "content": "Hello"}]

SAMPLE_MESSAGES_WITH_SYSTEM: list[dict[str, str]] = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello"},
]

SUCCESS_CONTENT = "Hello! I found the information you need."

SUCCESS_TOOL_CALLS_RESPONSE = {
    "choices": [
        {
            "message": {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_abc123",
                        "type": "function",
                        "function": {
                            "name": "web_search",
                            "arguments": '{"query": "Python programming"}',
                        },
                    }
                ],
            },
            "finish_reason": "tool_calls",
        }
    ],
    "usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60},
}

SUCCESS_RESPONSE = {
    "choices": [
        {
            "message": {"content": SUCCESS_CONTENT, "tool_calls": []},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}

ANTHROPIC_TOOL_CALLS_RESPONSE = {
    "content": [
        {"type": "text", "text": "Let me search for that."},
        {
            "type": "tool_use",
            "id": "toolu_abc123",
            "name": "web_search",
            "input": {"query": "Python programming"},
        },
    ],
    "usage": {"input_tokens": 50, "output_tokens": 20},
    "model": "claude-sonnet-4-20250514",
    "stop_reason": "tool_use",
    "stop_sequence": None,
}

ANTHROPIC_SUCCESS_RESPONSE = {
    "content": [{"type": "text", "text": "Python is a programming language."}],
    "usage": {"input_tokens": 15, "output_tokens": 10},
    "model": "claude-sonnet-4-20250514",
    "stop_reason": "end_turn",
    "stop_sequence": None,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_response(data: dict) -> MagicMock:
    """Create a mock urlopen response that returns the given dict as JSON."""
    mock = MagicMock()
    mock.read.return_value = json.dumps(data).encode("utf-8")
    return mock


def _capture_payload(mock_urlopen: MagicMock) -> dict[str, Any]:
    """Extract and decode the JSON payload from a mocked urlopen call."""
    request = mock_urlopen.call_args[0][0]
    return json.loads(request.data)


# ---------------------------------------------------------------------------
# OpenAI-Compatible Providers (same tools-in-payload pattern)
# ---------------------------------------------------------------------------

# Each provider imports urlopen directly: `from urllib.request import urlopen`
# So we must patch the provider's own module path, not urllib.request.
# (module_name, function_name, provider_kwargs, mock_path)
OPENAI_COMPATIBLE_PROVIDERS = [
    ("openai_provider", "call_openai", {"api_key": "sk-test"}, "src.core.providers.openai_provider.urlopen"),
    ("gemini_provider", "call_gemini", {"api_key": "test-key"}, "src.core.providers.gemini_provider.urlopen"),
    ("deepseek_provider", "call_deepseek", {"api_key": "sk-test"}, "src.core.providers.deepseek_provider.urlopen"),
    ("mistral_provider", "call_mistral", {"api_key": "test-key"}, "src.core.providers.mistral_provider.urlopen"),
    ("ollama_provider", "call_ollama", {}, "src.core.providers.ollama_provider.urlopen"),
]

# For error tests we need to raise URLError which is caught by provider try/except
from urllib.error import URLError  # noqa: E402  # noqa: E402


class TestOpenAICompatibleToolsParameter:
    """Tests for the tools parameter in OpenAI-compatible provider functions."""

    @pytest.mark.parametrize("module,func_name,provider_kwargs,mock_path", OPENAI_COMPATIBLE_PROVIDERS)
    def test_accepts_tools_parameter(self, module: str, func_name: str, provider_kwargs: dict, mock_path: str) -> None:
        """Function should accept tools parameter without crashing."""
        mod = __import__(f"src.core.providers.{module}", fromlist=[func_name])
        func = getattr(mod, func_name)

        with patch(mock_path, side_effect=URLError("No network")):
            result = func(
                messages=SAMPLE_MESSAGES,
                tools=SAMPLE_TOOLS,
                **provider_kwargs,
            )

        assert result is not None
        assert "error" in result

    @pytest.mark.parametrize("module,func_name,provider_kwargs,mock_path", OPENAI_COMPATIBLE_PROVIDERS)
    def test_tools_in_payload_when_provided(
        self, module: str, func_name: str, provider_kwargs: dict, mock_path: str
    ) -> None:
        """When tools are provided, payload should contain tools + tool_choice='auto'."""
        mod = __import__(f"src.core.providers.{module}", fromlist=[func_name])
        func = getattr(mod, func_name)

        with patch(mock_path) as mock_urlopen:
            mock_urlopen.return_value = _make_mock_response(SUCCESS_RESPONSE)
            func(
                messages=SAMPLE_MESSAGES,
                tools=SAMPLE_TOOLS,
                **provider_kwargs,
            )

        assert mock_urlopen.called
        payload = _capture_payload(mock_urlopen)

        assert "tools" in payload, f"{module}.{func_name}: tools missing from payload"
        assert payload["tools"] == SAMPLE_TOOLS, f"{module}.{func_name}: tool definitions changed"
        assert payload["tool_choice"] == "auto", f"{module}.{func_name}: tool_choice not 'auto'"

    @pytest.mark.parametrize("module,func_name,provider_kwargs,mock_path", OPENAI_COMPATIBLE_PROVIDERS)
    def test_tools_omitted_when_none(self, module: str, func_name: str, provider_kwargs: dict, mock_path: str) -> None:
        """When tools=None, payload should NOT contain tools or tool_choice."""
        mod = __import__(f"src.core.providers.{module}", fromlist=[func_name])
        func = getattr(mod, func_name)

        with patch(mock_path) as mock_urlopen:
            mock_urlopen.return_value = _make_mock_response(SUCCESS_RESPONSE)
            func(
                messages=SAMPLE_MESSAGES,
                tools=None,
                **provider_kwargs,
            )

        assert mock_urlopen.called
        payload = _capture_payload(mock_urlopen)

        assert "tools" not in payload, f"{module}.{func_name}: tools present despite None"
        assert "tool_choice" not in payload, f"{module}.{func_name}: tool_choice present despite None"

    @pytest.mark.parametrize("module,func_name,provider_kwargs,mock_path", OPENAI_COMPATIBLE_PROVIDERS)
    def test_tools_omitted_when_empty_list(
        self, module: str, func_name: str, provider_kwargs: dict, mock_path: str
    ) -> None:
        """When tools=[], payload should NOT contain tools (empty list is falsy)."""
        mod = __import__(f"src.core.providers.{module}", fromlist=[func_name])
        func = getattr(mod, func_name)

        with patch(mock_path) as mock_urlopen:
            mock_urlopen.return_value = _make_mock_response(SUCCESS_RESPONSE)
            func(
                messages=SAMPLE_MESSAGES,
                tools=[],
                **provider_kwargs,
            )

        assert mock_urlopen.called
        payload = _capture_payload(mock_urlopen)

        assert "tools" not in payload, f"{module}.{func_name}: tools present despite empty list"
        assert "tool_choice" not in payload, f"{module}.{func_name}: tool_choice present despite empty list"

    @pytest.mark.parametrize("module,func_name,provider_kwargs,mock_path", OPENAI_COMPATIBLE_PROVIDERS)
    def test_tool_calls_parsed_in_response(
        self, module: str, func_name: str, provider_kwargs: dict, mock_path: str
    ) -> None:
        """Tool calls in the API response should be parsed correctly."""
        mod = __import__(f"src.core.providers.{module}", fromlist=[func_name])
        func = getattr(mod, func_name)

        with patch(mock_path) as mock_urlopen:
            mock_urlopen.return_value = _make_mock_response(SUCCESS_TOOL_CALLS_RESPONSE)
            result = func(
                messages=SAMPLE_MESSAGES,
                tools=SAMPLE_TOOLS,
                **provider_kwargs,
            )

        assert len(result["tool_calls"]) == 1
        tc = result["tool_calls"][0]
        assert tc["function"]["name"] == "web_search"
        assert "Python programming" in tc["function"]["arguments"]
        assert tc["id"] == "call_abc123"

    @pytest.mark.parametrize("module,func_name,provider_kwargs,mock_path", OPENAI_COMPATIBLE_PROVIDERS)
    def test_tools_do_not_break_error_handling(
        self, module: str, func_name: str, provider_kwargs: dict, mock_path: str
    ) -> None:
        """Passing tools should not break error handling when network fails."""
        mod = __import__(f"src.core.providers.{module}", fromlist=[func_name])
        func = getattr(mod, func_name)

        with patch(mock_path, side_effect=URLError("Connection refused")):
            result = func(
                messages=SAMPLE_MESSAGES,
                tools=SAMPLE_TOOLS,
                **provider_kwargs,
            )

        assert result.get("error") is not None
        assert result["tool_calls"] == []

    @pytest.mark.parametrize("module,func_name,provider_kwargs,mock_path", OPENAI_COMPATIBLE_PROVIDERS)
    def test_tools_preserved_with_system_message(
        self, module: str, func_name: str, provider_kwargs: dict, mock_path: str
    ) -> None:
        """Tools should still work when the message list includes a system message."""
        mod = __import__(f"src.core.providers.{module}", fromlist=[func_name])
        func = getattr(mod, func_name)

        with patch(mock_path) as mock_urlopen:
            mock_urlopen.return_value = _make_mock_response(SUCCESS_RESPONSE)
            func(
                messages=SAMPLE_MESSAGES_WITH_SYSTEM,
                tools=SAMPLE_TOOLS,
                **provider_kwargs,
            )

        assert mock_urlopen.called
        payload = _capture_payload(mock_urlopen)
        assert "tools" in payload
        assert payload["tools"] == SAMPLE_TOOLS
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][1]["role"] == "user"

    @pytest.mark.parametrize("module,func_name,provider_kwargs,mock_path", OPENAI_COMPATIBLE_PROVIDERS)
    def test_tool_definition_preserves_all_fields(
        self, module: str, func_name: str, provider_kwargs: dict, mock_path: str
    ) -> None:
        """The full tool definition (name, description, parameters) should be preserved."""
        mod = __import__(f"src.core.providers.{module}", fromlist=[func_name])
        func = getattr(mod, func_name)

        detailed_tools = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read contents of a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Absolute path to the file",
                            },
                            "start_line": {
                                "type": "integer",
                                "description": "Optional starting line",
                            },
                        },
                        "required": ["path"],
                    },
                },
            }
        ]

        with patch(mock_path) as mock_urlopen:
            mock_urlopen.return_value = _make_mock_response(SUCCESS_RESPONSE)
            func(
                messages=SAMPLE_MESSAGES,
                tools=detailed_tools,
                **provider_kwargs,
            )

        assert mock_urlopen.called
        payload = _capture_payload(mock_urlopen)

        tool_in_payload = payload["tools"][0]
        fn = tool_in_payload["function"]
        assert fn["name"] == "read_file"
        assert "description" in fn
        assert "parameters" in fn
        assert "required" in fn["parameters"]
        assert "path" in fn["parameters"]["properties"]


# ---------------------------------------------------------------------------
# Anthropic Provider (different tool format)
# ---------------------------------------------------------------------------

ANTHROPIC_MOCK_PATH = "src.core.providers.anthropic_provider.urlopen"


class TestAnthropicToolsParameter:
    """Tests for the tools parameter in call_anthropic (different format)."""

    def test_accepts_tools_parameter(self) -> None:
        """call_anthropic should accept tools parameter without crashing."""
        from src.core.providers.anthropic_provider import call_anthropic

        with patch(ANTHROPIC_MOCK_PATH, side_effect=URLError("No network")):
            result = call_anthropic(
                messages=SAMPLE_MESSAGES,
                api_key="sk-ant-test",
                tools=SAMPLE_TOOLS,
            )

        assert result is not None
        assert "error" in result

    def test_tools_converted_to_anthropic_format(self) -> None:
        """OpenAI-format tools should be converted to Anthropic format in the payload."""
        from src.core.providers.anthropic_provider import call_anthropic

        with patch(ANTHROPIC_MOCK_PATH) as mock_urlopen:
            mock_urlopen.return_value = _make_mock_response(ANTHROPIC_SUCCESS_RESPONSE)
            call_anthropic(
                messages=SAMPLE_MESSAGES,
                api_key="sk-ant-test",
                tools=SAMPLE_TOOLS,
            )

        assert mock_urlopen.called
        payload = _capture_payload(mock_urlopen)

        assert "tools" in payload
        assert len(payload["tools"]) == 2

        tool1 = payload["tools"][0]
        assert tool1["name"] == "web_search"
        assert "description" in tool1
        assert tool1["input_schema"] == SAMPLE_TOOLS[0]["function"]["parameters"]

        tool2 = payload["tools"][1]
        assert tool2["name"] == "read_file"
        assert "description" in tool2
        assert tool2["input_schema"] == SAMPLE_TOOLS[1]["function"]["parameters"]

    def test_tools_omitted_when_none(self) -> None:
        """When tools=None, payload should not contain tools key."""
        from src.core.providers.anthropic_provider import call_anthropic

        with patch(ANTHROPIC_MOCK_PATH) as mock_urlopen:
            mock_urlopen.return_value = _make_mock_response(ANTHROPIC_SUCCESS_RESPONSE)
            call_anthropic(
                messages=SAMPLE_MESSAGES,
                api_key="sk-ant-test",
                tools=None,
            )

        assert mock_urlopen.called
        payload = _capture_payload(mock_urlopen)
        assert "tools" not in payload

    def test_tools_omitted_when_empty_list(self) -> None:
        """When tools=[], payload should not contain tools key."""
        from src.core.providers.anthropic_provider import call_anthropic

        with patch(ANTHROPIC_MOCK_PATH) as mock_urlopen:
            mock_urlopen.return_value = _make_mock_response(ANTHROPIC_SUCCESS_RESPONSE)
            call_anthropic(
                messages=SAMPLE_MESSAGES,
                api_key="sk-ant-test",
                tools=[],
            )

        assert mock_urlopen.called
        payload = _capture_payload(mock_urlopen)
        assert "tools" not in payload

    def test_tool_calls_parsed_in_response(self) -> None:
        """Anthropic tool calls should be parsed into OpenAI-compatible format."""
        from src.core.providers.anthropic_provider import call_anthropic

        with patch(ANTHROPIC_MOCK_PATH) as mock_urlopen:
            mock_urlopen.return_value = _make_mock_response(ANTHROPIC_TOOL_CALLS_RESPONSE)
            result = call_anthropic(
                messages=SAMPLE_MESSAGES,
                api_key="sk-ant-test",
                tools=SAMPLE_TOOLS,
            )

        assert "tool_calls" in result
        assert len(result["tool_calls"]) == 1
        tc = result["tool_calls"][0]
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "web_search"
        assert "Python programming" in tc["function"]["arguments"]
        assert tc["id"] == "toolu_abc123"

    def test_tool_calls_not_returned_when_no_tools(self) -> None:
        """When no tools are provided, the tool_calls list should be empty."""
        from src.core.providers.anthropic_provider import call_anthropic

        with patch(ANTHROPIC_MOCK_PATH) as mock_urlopen:
            mock_urlopen.return_value = _make_mock_response(ANTHROPIC_SUCCESS_RESPONSE)
            result = call_anthropic(
                messages=SAMPLE_MESSAGES,
                api_key="sk-ant-test",
                tools=None,
            )

        assert result["tool_calls"] == []
        assert "Python" in result["content"]

    def test_tools_with_system_prompt(self) -> None:
        """Tools should work alongside system prompt extraction."""
        from src.core.providers.anthropic_provider import call_anthropic

        with patch(ANTHROPIC_MOCK_PATH) as mock_urlopen:
            mock_urlopen.return_value = _make_mock_response(ANTHROPIC_SUCCESS_RESPONSE)
            call_anthropic(
                messages=SAMPLE_MESSAGES_WITH_SYSTEM,
                api_key="sk-ant-test",
                tools=SAMPLE_TOOLS,
            )

        assert mock_urlopen.called
        payload = _capture_payload(mock_urlopen)

        assert "system" in payload
        assert payload["system"] == [{"type": "text", "text": "You are a helpful assistant."}]
        assert "tools" in payload
        assert len(payload["tools"]) == 2

    def test_tools_do_not_break_error_handling(self) -> None:
        """Passing tools should not break error handling when network fails."""
        from src.core.providers.anthropic_provider import call_anthropic

        with patch(ANTHROPIC_MOCK_PATH, side_effect=URLError("Connection refused")):
            result = call_anthropic(
                messages=SAMPLE_MESSAGES,
                api_key="sk-ant-test",
                tools=SAMPLE_TOOLS,
            )

        assert result.get("error") is not None
        assert result["tool_calls"] == []

    def test_tool_definition_preserves_all_fields(self) -> None:
        """Anthropic conversion should preserve all fields from the tool definition."""
        from src.core.providers.anthropic_provider import call_anthropic

        detailed_tools = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read contents of a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "start_line": {"type": "integer"},
                        },
                        "required": ["path"],
                    },
                },
            }
        ]

        with patch(ANTHROPIC_MOCK_PATH) as mock_urlopen:
            mock_urlopen.return_value = _make_mock_response(ANTHROPIC_SUCCESS_RESPONSE)
            call_anthropic(
                messages=SAMPLE_MESSAGES,
                api_key="sk-ant-test",
                tools=detailed_tools,
            )

        assert mock_urlopen.called
        payload = _capture_payload(mock_urlopen)

        tool = payload["tools"][0]
        assert tool["name"] == "read_file"
        assert "description" in tool
        assert "input_schema" in tool
        assert "properties" in tool["input_schema"]
        assert "required" in tool["input_schema"]
