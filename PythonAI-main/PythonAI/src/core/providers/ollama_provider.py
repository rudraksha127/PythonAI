"""
Ollama Provider — Local Ollama Models API Integration
=====================================================
Implements Ollama API calls through its OpenAI-compatible endpoint.
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


def call_ollama(
    messages: list[dict[str, str]],
    model: str = "qwen2.5-coder:14b",
    base_url: str = "http://localhost:11434/v1",
    temperature: float = 0.2,
    max_tokens: int = 8192,
    stream: bool = False,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Call Ollama API using its OpenAI-compatible endpoint.

    Ollama provides an OpenAI-compatible API at http://localhost:11434/v1
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
            "error": f"Ollama API error: {e}",
            "error_detail": error_detail or "Is Ollama running? Try 'ollama serve'",
        }
    except (json.JSONDecodeError, OSError) as e:
        return {
            "content": "",
            "tool_calls": [],
            "error": f"Ollama request failed: {e}",
        }


def call_ollama_native(
    messages: list[dict[str, str]],
    model: str = "qwen2.5-coder:14b",
    base_url: str = "http://localhost:11434",
    temperature: float = 0.2,
    max_tokens: int = 8192,
    stream: bool = False,
) -> dict[str, Any]:
    """
    Call Ollama using its native API (not OpenAI-compatible).

    Useful for models or features not available through the OpenAI-compatible endpoint.
    """
    url = f"{base_url.rstrip('/')}/api/chat"

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    headers = {"Content-Type": "application/json"}

    try:
        req = Request(url, method="POST", data=json.dumps(payload).encode())
        for key, value in headers.items():
            req.add_header(key, value)

        resp = urlopen(req, timeout=120)
        body = json.loads(resp.read().decode())

        return {
            "content": body.get("message", {}).get("content", ""),
            "tool_calls": [],
            "usage": {
                "prompt_tokens": body.get("prompt_eval_count", 0),
                "completion_tokens": body.get("eval_count", 0),
                "total_tokens": body.get("prompt_eval_count", 0) + body.get("eval_count", 0),
            },
            "model": model,
            "elapsed_seconds": body.get("total_duration", 0) / 1_000_000_000,
            "finish_reason": body.get("done_reason", "stop"),
        }

    except URLError as e:
        return {
            "content": "",
            "tool_calls": [],
            "error": f"Ollama native API error: {e}",
        }
    except (json.JSONDecodeError, OSError) as e:
        return {
            "content": "",
            "tool_calls": [],
            "error": f"Ollama native request failed: {e}",
        }
