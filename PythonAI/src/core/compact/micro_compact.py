"""
Micro-Compaction — Pre-Request Tool Result Cleanup
===================================================
Inspired by Claude Code's microCompact.ts.

Two triggers:
1. Time-based: If gap since last assistant > threshold, clear old tool results
2. Count-based: If tool results > threshold, summarize or clear old ones

Runs BEFORE the API call — no token cost for compaction itself.
"""

from __future__ import annotations

import json
import time
from typing import Any

# Tools eligible for micro-compaction
COMPACTABLE_TOOLS = {
    "bash", "read", "file_read", "grep", "glob",
    "web_search", "web_fetch", "file_edit", "file_write",
}

TIME_BASED_CLEARED_MESSAGE = "[Previous tool result content cleared for context efficiency]"

# Default thresholds
DEFAULT_TIME_GAP_MINUTES = 30   # Clear old results after 30 min gap
DEFAULT_COUNT_KEEP_RECENT = 10   # Keep last 10 tool results
DEFAULT_COUNT_TRIGGER = 25       # Start compacting at 25 tool results


def estimate_tool_result_tokens(content: str | list | dict) -> int:
    """Rough token estimate for tool result content."""
    if isinstance(content, str):
        return len(content) // 4
    if isinstance(content, list):
        return sum(estimate_tool_result_tokens(item) for item in content)
    if isinstance(content, dict):
        return estimate_tool_result_tokens(json.dumps(content))
    return 0


def collect_compactable_tool_ids(messages: list[dict[str, Any]]) -> list[str]:
    """Collect tool_use IDs whose tool names are in COMPACTABLE_TOOLS."""
    ids = []
    for msg in messages:
        if msg.get("role") == "assistant" and "tool_calls" in msg:
            for tc in msg["tool_calls"]:
                fn = tc.get("function", tc)
                name = fn.get("name", "")
                if name in COMPACTABLE_TOOLS:
                    ids.append(tc.get("id", name))
    return ids


def microcompact_messages(
    messages: list[dict[str, Any]],
    time_gap_minutes: int = DEFAULT_TIME_GAP_MINUTES,
    count_keep_recent: int = DEFAULT_COUNT_KEEP_RECENT,
    count_trigger: int = DEFAULT_COUNT_TRIGGER,
) -> dict[str, Any]:
    """
    Run micro-compaction on messages.

    Returns:
        dict with:
        - messages: Compacted messages
        - compacted: bool — whether compaction happened
        - tokens_saved: int
        - reason: str — why compaction triggered
    """
    if not messages:
        return {"messages": messages, "compacted": False, "tokens_saved": 0, "reason": "empty"}

    # Collect all compactable tool IDs
    compactable_ids = collect_compactable_tool_ids(messages)

    # Count total tool results
    total_results = len(compactable_ids)

    if total_results == 0:
        return {"messages": messages, "compacted": False, "tokens_saved": 0, "reason": "no_tools"}

    # Check time-based trigger
    last_assistant_time = _find_last_assistant_time(messages)
    time_triggered = False
    if last_assistant_time is not None:
        gap_minutes = (time.time() - last_assistant_time) / 60
        time_triggered = gap_minutes >= time_gap_minutes

    # Check count-based trigger
    count_triggered = total_results >= count_trigger

    if not time_triggered and not count_triggered:
        return {"messages": messages, "compacted": False, "tokens_saved": 0, "reason": "no_trigger"}

    reason = "time_based" if time_triggered else "count_based"
    if time_triggered and count_triggered:
        reason = "both"

    # Determine which IDs to clear
    keep_recent = max(1, count_keep_recent)
    keep_ids = set(compactable_ids[-keep_recent:])
    clear_ids = set(compactable_ids) - keep_ids

    if not clear_ids:
        return {"messages": messages, "compacted": False, "tokens_saved": 0, "reason": "all_recent"}

    # Clear old tool results
    tokens_saved = 0
    result_messages = []

    for msg in messages:
        if msg.get("role") != "tool":
            result_messages.append(msg)
            continue

        tool_call_id = msg.get("tool_call_id", "")
        if tool_call_id in clear_ids:
            content = msg.get("content", "")
            if isinstance(content, str):
                tokens_saved += estimate_tool_result_tokens(content)
            # Replace with cleared message
            result_messages.append({
                "role": "tool",
                "content": TIME_BASED_CLEARED_MESSAGE,
                "tool_call_id": tool_call_id,
                "name": msg.get("name", ""),
            })
        else:
            result_messages.append(msg)

    return {
        "messages": result_messages,
        "compacted": True,
        "tokens_saved": tokens_saved,
        "reason": reason,
        "cleared_count": len(clear_ids),
        "kept_count": len(keep_ids),
    }


def _find_last_assistant_time(messages: list[dict[str, Any]]) -> float | None:
    """Find the timestamp of the last assistant message."""
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            ts = msg.get("timestamp")
            if ts:
                try:
                    return float(ts)
                except (ValueError, TypeError):
                    return None
    return None


class MicroCompactStats:
    """Tracks micro-compaction statistics."""

    def __init__(self):
        self.total_compactions = 0
        self.total_tokens_saved = 0
        self.time_based_count = 0
        self.count_based_count = 0

    def record(self, result: dict[str, Any]) -> None:
        if result.get("compacted"):
            self.total_compactions += 1
            self.total_tokens_saved += result.get("tokens_saved", 0)
            reason = result.get("reason", "")
            if "time" in reason:
                self.time_based_count += 1
            if "count" in reason:
                self.count_based_count += 1

    def report(self) -> dict[str, Any]:
        return {
            "total_compactions": self.total_compactions,
            "total_tokens_saved": self.total_tokens_saved,
            "time_based": self.time_based_count,
            "count_based": self.count_based_count,
        }
