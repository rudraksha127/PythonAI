"""
Anthropic Provider — Anthropic Claude Models API Integration
=============================================================
Implements Anthropic API calls for Claude 3 and Claude 4 models.
Anthropic uses a different API format than OpenAI-compatible providers:

  - API endpoint: https://api.anthropic.com/v1/messages
  - Requires anthropic-version header
  - Uses content blocks (list of dicts) instead of simple messages
  - Tool use is via content blocks, not function calling
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


def call_anthropic(
    messages: list[dict[str, Any]],
    model: str = "claude-sonnet-4-20250514",
    base_url: str = "https://api.anthropic.com/v1",
    api_key: str = "",
    temperature: float = 0.0,
    max_tokens: int = 8192,
    stream: bool = False,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Call Anthropic API.

    Anthropic uses a distinct API format from OpenAI-compatible providers:
    - Messages use content blocks (list of dicts with "type" and "text")
    - Tools are specified via the "tools" parameter
    - Tool results are returned as content blocks with type "tool_result"
    - Requires anthropic-version header (default: 2023-06-01)

    Args:
        messages: List of message dicts (converted from OpenAI format).
        model: Claude model ID (e.g. claude-sonnet-4-20250514).
        base_url: API base URL (default: https://api.anthropic.com/v1).
        api_key: Anthropic API key.
        temperature: Sampling temperature (0.0-1.0).
        max_tokens: Maximum tokens in response.
        stream: Enable streaming (not yet supported).

    Returns:
        Dict with keys: content, tool_calls, usage, model, error, etc.
    """
    url = f"{base_url.rstrip('/')}/messages"

    # Convert messages from OpenAI format to Anthropic format
    # Extract system prompt separately (Anthropic uses top-level "system" field)
    system_prompt = ""
    converted_messages: list[dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") == "system":
            system_prompt = msg.get("content", "")
        else:
            converted_messages.append(msg)
    anthropic_messages = _convert_messages(converted_messages)

    payload: dict[str, Any] = {
        "model": model,
        "messages": anthropic_messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": stream,
    }

    # Attach system prompt at top level if present
    if system_prompt:
        payload["system"] = [{"type": "text", "text": system_prompt}]

    # Convert tools to Anthropic format and attach
    if tools:
        anthropic_tools = []
        for tool in tools:
            fn = tool.get("function", tool)
            anthropic_tools.append(
                {
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", {}),
                }
            )
        payload["tools"] = anthropic_tools

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    try:
        req = Request(url, method="POST", data=json.dumps(payload).encode())
        for key, value in headers.items():
            req.add_header(key, value)

        start = time.time()
        resp = urlopen(req, timeout=120)
        elapsed = time.time() - start

        body = json.loads(resp.read().decode())

        content = ""
        tool_calls: list[dict[str, Any]] = []

        # Parse content blocks from Anthropic response
        for block in body.get("content", []):
            block_type = block.get("type", "")
            if block_type == "text":
                content += block.get("text", "")
            elif block_type == "tool_use":
                tool_calls.append(
                    {
                        "id": block.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": json.dumps(block.get("input", {})),
                        },
                    }
                )

        usage = body.get("usage", {})

        return {
            "content": content,
            "tool_calls": tool_calls,
            "usage": {
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            },
            "model": body.get("model", model),
            "elapsed_seconds": round(elapsed, 2),
            "finish_reason": body.get("stop_reason", "end_turn"),
            "stop_sequence": body.get("stop_sequence"),
        }

    except URLError as e:
        error_detail = ""
        if hasattr(e, "read"):
            try:
                error_detail = e.read().decode()[:500]
            except Exception:
                pass
        return {
            "content": "",
            "tool_calls": [],
            "error": f"Anthropic API error: {e}",
            "error_detail": error_detail,
        }
    except (json.JSONDecodeError, OSError) as e:
        return {
            "content": "",
            "tool_calls": [],
            "error": f"Anthropic request failed: {e}",
        }


def _convert_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert OpenAI-format messages to Anthropic-format messages.

    OpenAI format uses 'role' and 'content' (string).
    Anthropic format uses 'role' and 'content' (list of content blocks).

    Handles:
    - System messages (extracted as system prompt, not in messages array)
    - Tool result messages (converted to tool_result content blocks)
    - Assistant messages with tool calls (converted to content blocks)
    """
    anthropic_messages: list[dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "system":
            # Anthropic puts system prompt at the top level, not in messages
            continue

        if role == "tool":
            # Convert tool results to Anthropic tool_result blocks
            tool_call_id = msg.get("tool_call_id", "")
            msg.get("name", "")
            anthropic_messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_call_id,
                            "content": content if isinstance(content, str) else json.dumps(content),
                        }
                    ],
                }
            )

        elif role == "assistant":
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                # Assistant message with tool calls
                blocks: list[dict[str, Any]] = []
                if content:
                    blocks.append({"type": "text", "text": content})
                for tc in tool_calls:
                    fn_info = tc.get("function", tc)
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.get("id", "tool_unknown"),
                            "name": fn_info.get("name", ""),
                            "input": json.loads(fn_info.get("arguments", "{}"))
                            if isinstance(fn_info.get("arguments"), str)
                            else fn_info.get("arguments", {}),
                        }
                    )
                anthropic_messages.append(
                    {
                        "role": "assistant",
                        "content": blocks,
                    }
                )
            else:
                # Plain text assistant message
                anthropic_messages.append(
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": content}],
                    }
                )

        else:
            # User message
            anthropic_messages.append(
                {
                    "role": "user",
                    "content": [{"type": "text", "text": content}],
                }
            )

    return anthropic_messages
