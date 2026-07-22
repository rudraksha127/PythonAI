"""
Gemini Provider — Google Gemini Models API Integration
======================================================
Implements Google Gemini API calls through OpenAI-compatible endpoint
or native Gemini API.
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


def call_gemini(
    messages: list[dict[str, str]],
    model: str = "gemini-2.5-flash",
    base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai",
    api_key: str = "",
    temperature: float = 0.3,
    max_tokens: int = 8192,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Call Google Gemini API using OpenAI-compatible endpoint.

    Uses Gemini's OpenAI compatibility layer:
    https://generativelanguage.googleapis.com/v1beta/openai/
    """
    url = f"{base_url.rstrip('/')}/chat/completions"

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
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

        usage = body.get("usage", {})

        return {
            "content": content,
            "tool_calls": message.get("tool_calls", []),
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
        error_detail = ""
        if hasattr(e, "read"):
            try:
                error_detail = e.read().decode()[:300]
            except Exception:
                pass
        return {
            "content": "",
            "tool_calls": [],
            "error": f"Gemini API error: {e}",
            "error_detail": error_detail,
        }
    except (json.JSONDecodeError, OSError) as e:
        return {
            "content": "",
            "tool_calls": [],
            "error": f"Gemini request failed: {e}",
        }
