"""
Reactive Compaction — Post-413 Error Recovery
==============================================
Inspired by Claude Code's reactiveCompact.ts.

When the API returns a 413 / prompt-too-long error:
1. Compact messages (summarize older ones)
2. Retry the request with compacted context
3. If still fails, fall back to user-facing error

Acts as the last-resort escape hatch when proactive
compaction didn't catch the issue.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

MAX_REACTIVE_RETRIES = 2


def is_prompt_too_long_error(response: dict[str, Any]) -> bool:
    """Check if response indicates prompt-too-long / 413 error."""
    error = response.get("error", "")
    if isinstance(error, str):
        error_lower = error.lower()
        if "prompt too long" in error_lower or "context too long" in error_lower:
            return True
        if "413" in error or "payload too large" in error_lower:
            return True
        if "maximum context length" in error_lower:
            return True
    return False


def reactive_compact_if_needed(
    response: dict[str, Any],
    messages: list[dict[str, Any]],
    compact_fn: Callable[..., Any] | None = None,
    retry_count: int = 0,
    max_retries: int = MAX_REACTIVE_RETRIES,
) -> dict[str, Any]:
    """
    Handle prompt-too-long error by compacting and retrying.

    Args:
        response: The API response that may contain a PTL error
        messages: Current message list
        compact_fn: Function to compact messages
        retry_count: Current retry attempt number
        max_retries: Maximum retry attempts

    Returns:
        dict with:
        - should_retry: bool
        - compacted_messages: list or None
        - error: str or None
        - retry_count: updated count
    """
    if not is_prompt_too_long_error(response):
        return {
            "should_retry": False,
            "compacted_messages": None,
            "error": None,
            "retry_count": retry_count,
        }

    if retry_count >= max_retries:
        return {
            "should_retry": False,
            "compacted_messages": None,
            "error": "Prompt too long after max retries. Try /compact or reducing context.",
            "retry_count": retry_count,
        }

    # Compact messages
    if compact_fn:
        try:
            result = compact_fn(messages)
            compacted = result.get("messages", messages)
            return {
                "should_retry": True,
                "compacted_messages": compacted,
                "error": None,
                "retry_count": retry_count + 1,
                "tokens_saved": result.get("compacted_result", {}).get("tokens_saved", 0),
            }
        except Exception as e:
            return {
                "should_retry": False,
                "compacted_messages": None,
                "error": f"Compaction failed: {e}",
                "retry_count": retry_count + 1,
            }

    # Default: drop oldest non-system messages
    if len(messages) <= 3:
        return {
            "should_retry": False,
            "compacted_messages": None,
            "error": "Not enough messages to compact.",
            "retry_count": retry_count,
        }

    # Find first non-system message and drop it
    drop_idx = None
    for i, msg in enumerate(messages):
        if msg.get("role") != "system":
            drop_idx = i
            break

    if drop_idx is None or drop_idx >= len(messages) - 1:
        return {
            "should_retry": False,
            "compacted_messages": None,
            "error": "Cannot compact further.",
            "retry_count": retry_count,
        }

    compacted = messages[:drop_idx] + messages[drop_idx + 1 :]

    return {
        "should_retry": True,
        "compacted_messages": compacted,
        "error": None,
        "retry_count": retry_count + 1,
        "dropped_count": 1,
    }
