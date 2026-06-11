"""
Unit tests for src.core.providers.anthropic_provider — Claude API Integration.
"""

from __future__ import annotations


class TestConvertMessages:
    """Tests for the _convert_messages helper function."""

    def test_user_message_conversion(self) -> None:
        """A plain user message should be converted to Anthropic content block format."""
        from src.core.providers.anthropic_provider import _convert_messages

        result = _convert_messages([{"role": "user", "content": "Hello"}])

        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert result[0]["content"] == [{"type": "text", "text": "Hello"}]

    def test_system_message_skipped(self) -> None:
        """System messages should be skipped (handled at top level)."""
        from src.core.providers.anthropic_provider import _convert_messages

        result = _convert_messages([
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hi"},
        ])

        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_assistant_plain_text(self) -> None:
        """A plain text assistant message should use text content block."""
        from src.core.providers.anthropic_provider import _convert_messages

        result = _convert_messages([{"role": "assistant", "content": "Sure thing!"}])

        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == [{"type": "text", "text": "Sure thing!"}]

    def test_assistant_with_tool_calls(self) -> None:
        """Assistant messages with tool_calls should include tool_use blocks."""
        from src.core.providers.anthropic_provider import _convert_messages

        result = _convert_messages([{
            "role": "assistant",
            "content": "Let me search for that.",
            "tool_calls": [{
                "id": "call_123",
                "type": "function",
                "function": {
                    "name": "web_search",
                    "arguments": '{"query": "Python"}',
                },
            }],
        }])

        assert len(result) == 1
        content = result[0]["content"]
        # Should have text block + tool_use block
        text_blocks = [b for b in content if b["type"] == "text"]
        tool_blocks = [b for b in content if b["type"] == "tool_use"]
        assert len(text_blocks) >= 1
        assert len(tool_blocks) >= 1
        assert tool_blocks[0]["name"] == "web_search"
        assert tool_blocks[0]["id"] == "call_123"
        assert tool_blocks[0]["input"] == {"query": "Python"}

    def test_tool_result_conversion(self) -> None:
        """Tool result messages should become tool_result content blocks."""
        from src.core.providers.anthropic_provider import _convert_messages

        result = _convert_messages([{
            "role": "tool",
            "content": '{"results": ["doc1"]}',
            "tool_call_id": "call_123",
            "name": "web_search",
        }])

        assert len(result) == 1
        assert result[0]["role"] == "user"
        content = result[0]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "tool_result"
        assert content[0]["tool_use_id"] == "call_123"

    def test_mixed_conversation(self) -> None:
        """A full conversation with multiple turns should convert correctly."""
        from src.core.providers.anthropic_provider import _convert_messages

        messages = [
            {"role": "user", "content": "Search for Python"},
            {"role": "assistant", "content": "", "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": "search", "arguments": '{"q": "Python"}'},
            }]},
            {"role": "tool", "content": '["result"]', "tool_call_id": "call_1", "name": "search"},
        ]

        result = _convert_messages(messages)
        assert len(result) == 3
        # User -> user with text block
        assert result[0]["role"] == "user"
        # Assistant with tool -> assistant with tool_use block
        assert result[1]["role"] == "assistant"
        assert any(b["type"] == "tool_use" for b in result[1]["content"])
        # Tool result -> user with tool_result block
        assert result[2]["role"] == "user"
        assert result[2]["content"][0]["type"] == "tool_result"

    def test_empty_messages(self) -> None:
        """Empty message list should return empty list."""
        from src.core.providers.anthropic_provider import _convert_messages
        assert _convert_messages([]) == []


class TestCallAnthropic:
    """Tests for the call_anthropic function (no network calls)."""

    def test_importable(self) -> None:
        """call_anthropic should be importable."""
        from src.core.providers.anthropic_provider import call_anthropic
        assert call_anthropic is not None

    def test_no_api_key_returns_error(self) -> None:
        """Calling with no API key should return an error, not crash."""
        from src.core.providers.anthropic_provider import call_anthropic

        result = call_anthropic(
            messages=[{"role": "user", "content": "Hello"}],
            api_key="",
        )

        assert result.get("error") is not None
        assert "Anthropic" in result["error"]

    def test_invalid_key_returns_error(self) -> None:
        """Calling with an invalid API key should return an error, not crash."""
        from src.core.providers.anthropic_provider import call_anthropic

        result = call_anthropic(
            messages=[{"role": "user", "content": "Hello"}],
            api_key="sk-invalid-key",
        )

        assert result.get("error") is not None

    def test_system_prompt_extracted(self) -> None:
        """System prompt should be extracted and not passed in messages."""
        from src.core.providers.anthropic_provider import call_anthropic

        result = call_anthropic(
            messages=[
                {"role": "system", "content": "You are Claude."},
                {"role": "user", "content": "Hi"},
            ],
            api_key="",
        )

        # Should still return error (no API key) but not crash
        assert result is not None

    def test_result_structure_on_error(self) -> None:
        """Error result should have expected keys."""
        from src.core.providers.anthropic_provider import call_anthropic

        result = call_anthropic(
            messages=[{"role": "user", "content": "Hello"}],
            api_key="",
        )

        # Error result should still have content and tool_calls keys
        assert "content" in result
        assert "tool_calls" in result
        assert result["tool_calls"] == []


class TestCallAnthropicWithTools:
    """Tests for call_anthropic with tools parameter."""

    def test_tools_parameter_accepted(self) -> None:
        """call_anthropic should accept a tools parameter without crashing."""
        from src.core.providers.anthropic_provider import call_anthropic

        result = call_anthropic(
            messages=[{"role": "user", "content": "Search for Python"}],
            api_key="",
            tools=[{
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
            }],
        )

        # Should return error (no API key), not crash
        assert result.get("error") is not None
        assert result["tool_calls"] == []

    def test_tools_converted_to_anthropic_format(self) -> None:
        """Tools should be converted from OpenAI to Anthropic format."""
        from src.core.providers.anthropic_provider import call_anthropic

        openai_tools = [{
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        }]

        result = call_anthropic(
            messages=[{"role": "user", "content": "Search"}],
            api_key="",
            tools=openai_tools,
        )

        # Should still fail gracefully (no API key)
        assert result is not None
