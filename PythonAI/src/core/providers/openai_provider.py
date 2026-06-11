"""
OpenAI Provider — GPT Models API Integration
============================================
Implements OpenAI-compatible API calls for GPT models.
Works with any OpenAI-compatible endpoint (OpenAI, Groq, Together, etc.).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


def call_openai(
    messages: list[dict[str, str]],
    model: str = "gpt-4o",
    base_url: str = "https://api.openai.com/v1",
    api_key: str = "",
    temperature: float = 0.3,
    max_tokens: int = 4096,
    stream: bool = False,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Call an OpenAI-compatible chat completions API.

    Args:
        messages: List of message dicts with role and content.
        model: Model ID to use.
        base_url: API base URL (e.g., https://api.openai.com/v1).
        api_key: API key.
        temperature: Sampling temperature.
        max_tokens: Maximum tokens to generate.
        stream: Whether to stream the response.
        tools: Optional list of tool definitions.

    Returns:
        Response dict with content, tool_calls, usage, etc.
    """
    url = f"{base_url.rstrip('/')}/chat/completions"

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        req = Request(url, method="POST", data=json.dumps(payload).encode())
        for key, value in headers.items():
            req.add_header(key, value)

        start = time.time()
        resp = urlopen(req, timeout=120)
        elapsed = time.time() - start

        body = json.loads(resp.read().decode())

        # Extract content
        choice = body.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = message.get("content", "")
        tool_calls_raw = message.get("tool_calls") or []

        # Format tool calls
        tool_calls = []
        for tc in tool_calls_raw:
            tool_calls.append(
                {
                    "id": tc.get("id", ""),
                    "type": tc.get("type", "function"),
                    "function": {
                        "name": tc.get("function", {}).get("name", ""),
                        "arguments": tc.get("function", {}).get("arguments", "{}"),
                    },
                }
            )

        usage = body.get("usage", {})

        return {
            "content": content,
            "tool_calls": tool_calls,
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            "model": model,
            "elapsed_seconds": round(elapsed, 2),
            "finish_reason": choice.get("finish_reason", "stop"),
        }

    except URLError as e:
        error_body = ""
        if hasattr(e, "read"):
            try:
                error_body = e.read().decode()
            except Exception:
                pass
        return {
            "content": "",
            "tool_calls": [],
            "error": f"API request failed: {e}",
            "error_detail": error_body[:500] if error_body else "",
        }
    except (json.JSONDecodeError, OSError) as e:
        return {
            "content": "",
            "tool_calls": [],
            "error": f"Request failed: {e}",
        }


def call_openai_stream(
    messages: list[dict[str, str]],
    model: str = "gpt-4o",
    base_url: str = "https://api.openai.com/v1",
    api_key: str = "",
    temperature: float = 0.3,
    max_tokens: int = 4096,
    on_token: Callable[[str], None] | None = None,
) -> str:
    """
    Call an OpenAI-compatible API with streaming.

    Args:
        messages: List of message dicts.
        model: Model ID.
        base_url: API base URL.
        api_key: API key.
        temperature: Sampling temperature.
        max_tokens: Max tokens.
        on_token: Callback for each token received.

    Returns:
        Full response text.
    """
    url = f"{base_url.rstrip('/')}/chat/completions"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        import http.client

        parsed_url = url.replace("https://", "").replace("http://", "")
        host = parsed_url.split("/")[0]
        path = "/" + "/".join(parsed_url.split("/")[1:]) if "/" in parsed_url else "/"

        if url.startswith("https"):
            conn: http.client.HTTPSConnection | http.client.HTTPConnection = http.client.HTTPSConnection(
                host, timeout=120
            )
        else:
            conn = http.client.HTTPConnection(host, timeout=120)

        conn.request(
            "POST",
            path,
            body=json.dumps(payload),
            headers=headers,
        )

        response = conn.getresponse()
        full_text = ""

        while True:
            line = response.readline()
            if not line:
                break
            line_str = line.decode("utf-8", errors="replace").strip()

            if line_str.startswith("data: "):
                data_str = line_str[6:]
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    token = delta.get("content", "")
                    if token:
                        full_text += token
                        if on_token is not None:
                            on_token(token)
                except json.JSONDecodeError:
                    pass

        conn.close()
        return full_text

    except Exception as e:
        return f"[Stream error: {e}]"
