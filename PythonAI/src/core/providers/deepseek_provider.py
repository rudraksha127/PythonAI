"""
DeepSeek Provider — DeepSeek Models API Integration
====================================================
Implements DeepSeek API calls for chat and reasoning models.
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


def call_deepseek(
    messages: list[dict[str, str]],
    model: str = "deepseek-chat",
    base_url: str = "https://api.deepseek.com/v1",
    api_key: str = "",
    temperature: float = 0.0,
    max_tokens: int = 8192,
    stream: bool = False,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Call DeepSeek API.

    DeepSeek uses OpenAI-compatible API format.
    Supports deepseek-chat and deepseek-reasoner models.
    The reasoner model uses a different API structure with
    reasoning_content in the response.
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

        choice = body.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = message.get("content", "")

        # For deepseek-reasoner, extract reasoning content
        reasoning = message.get("reasoning_content", "")

        usage = body.get("usage", {})

        return {
            "content": content,
            "reasoning": reasoning,
            "tool_calls": message.get("tool_calls") or [],
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
                "prompt_tokens_details": usage.get("prompt_tokens_details", {}),
                "completion_tokens_details": usage.get("completion_tokens_details", {}),
            },
            "model": body.get("model", model),
            "elapsed_seconds": round(elapsed, 2),
            "finish_reason": choice.get("finish_reason", "stop"),
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
            "reasoning": "",
            "tool_calls": [],
            "error": f"DeepSeek API error: {e}",
            "error_detail": error_detail,
        }
    except (json.JSONDecodeError, OSError) as e:
        return {
            "content": "",
            "reasoning": "",
            "tool_calls": [],
            "error": f"DeepSeek request failed: {e}",
        }
