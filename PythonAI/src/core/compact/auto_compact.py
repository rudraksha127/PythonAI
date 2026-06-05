"""
Auto-Compaction — Token Threshold Compaction
=============================================
Inspired by Claude Code's autoCompact.ts.

When token count exceeds threshold (default: 90% of context window):
1. Fork agent to summarize older messages
2. Replace old messages with compact summary
3. Circuit breaker after N consecutive failures

Also integrates session memory compaction as first attempt.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable

# Default thresholds
DEFAULT_CONTEXT_WINDOW = 128_000    # Default model context window
DEFAULT_COMPACT_THRESHOLD_PCT = 0.90  # Compact at 90% of context
DEFAULT_RESERVE_TOKENS = 20_000    # Reserve for output during compaction
AUTOCOMPACT_BUFFER_TOKENS = 13_000  # Buffer before threshold
MAX_CONSECUTIVE_FAILURES = 3       # Circuit breaker limit


def get_effective_context_window(
    model_context_window: int = DEFAULT_CONTEXT_WINDOW,
    reserve_tokens: int = DEFAULT_RESERVE_TOKENS,
) -> int:
    """Get effective context window (minus reserve for compaction output)."""
    return model_context_window - reserve_tokens


def get_auto_compact_threshold(
    model_context_window: int = DEFAULT_CONTEXT_WINDOW,
) -> int:
    """Get auto-compact threshold (context window - buffer)."""
    effective = get_effective_context_window(model_context_window)
    return effective - AUTOCOMPACT_BUFFER_TOKENS


def estimate_token_count(messages: list[dict[str, Any]]) -> int:
    """Rough token estimation for messages."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += len(content) // 4  # ~4 chars per token
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    total += len(item["text"]) // 4
        # Add overhead per message
        total += 10  # Role + metadata overhead
    return total


def should_auto_compact(
    messages: list[dict[str, Any]],
    model_context_window: int = DEFAULT_CONTEXT_WINDOW,
) -> bool:
    """Check if auto-compaction should trigger."""
    token_count = estimate_token_count(messages)
    threshold = get_auto_compact_threshold(model_context_window)
    return token_count >= threshold


def auto_compact_if_needed(
    messages: list[dict[str, Any]],
    model_context_window: int = DEFAULT_CONTEXT_WINDOW,
    compact_fn: Callable | None = None,
    consecutive_failures: int = 0,
) -> dict[str, Any]:
    """
    Auto-compact messages if token count exceeds threshold.

    Args:
        messages: Current message list
        model_context_window: Context window for the model
        compact_fn: Optional function to call for actual compaction (e.g., LLM summarization)
        consecutive_failures: Previous consecutive failure count

    Returns:
        dict with:
        - messages: Possibly compacted messages
        - was_compacted: bool
        - compacted_result: dict or None
        - consecutive_failures: updated failure count
    """
    # Circuit breaker
    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
        return {
            "messages": messages,
            "was_compacted": False,
            "compacted_result": None,
            "consecutive_failures": consecutive_failures,
            "reason": "circuit_breaker",
        }

    if not should_auto_compact(messages, model_context_window):
        return {
            "messages": messages,
            "was_compacted": False,
            "compacted_result": None,
            "consecutive_failures": 0,
            "reason": "below_threshold",
        }

    # Perform compaction
    if compact_fn:
        try:
            result = compact_fn(messages)
            return {
                "messages": result.get("messages", messages),
                "was_compacted": True,
                "compacted_result": result,
                "consecutive_failures": 0,
                "reason": "compacted",
            }
        except Exception:
            return {
                "messages": messages,
                "was_compacted": False,
                "compacted_result": None,
                "consecutive_failures": consecutive_failures + 1,
                "reason": "compaction_failed",
            }

    # Default compaction: simple truncation
    return _simple_compact(messages)


def _simple_compact(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Simple compaction: keep system prompt + last N messages,
    summarize older ones into a compact summary.
    """
    if len(messages) <= 6:
        return {
            "messages": messages,
            "was_compacted": False,
            "compacted_result": None,
            "reason": "too_few_messages",
        }

    # Keep: system (first 1-2 msgs) + last 4 messages + tool results
    keep_prefix = []
    idx = 0
    while idx < len(messages) and messages[idx].get("role") == "system":
        keep_prefix.append(messages[idx])
        idx += 1

    # Keep last 4 non-system messages
    non_system = [m for m in messages if m.get("role") != "system"]
    keep_suffix = non_system[-4:] if len(non_system) >= 4 else non_system

    # Messages to compact
    to_compact = messages[len(keep_prefix):-len(keep_suffix)] if keep_suffix else messages[len(keep_prefix):]

    if not to_compact:
        return {
            "messages": messages,
            "was_compacted": False,
            "compacted_result": None,
            "reason": "nothing_to_compact",
        }

    # Create compact summary
    compact_summary = _create_compact_summary(to_compact)
    compact_msg = {
        "role": "system",
        "content": f"[Compacted conversation history: {compact_summary}]",
        "is_compact_summary": True,
        "timestamp": time.time(),
    }

    result = keep_prefix + [compact_msg] + keep_suffix

    return {
        "messages": result,
        "was_compacted": True,
        "compacted_result": {
            "messages_compacted": len(to_compact),
            "tokens_saved": estimate_token_count(to_compact),
            "summary": compact_summary,
        },
        "reason": "simple_compact",
    }


def _create_compact_summary(messages: list[dict[str, Any]]) -> str:
    """Create a text summary of messages being compacted."""
    parts = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, str) and len(content) > 100:
            content = content[:100] + "..."
        parts.append(f"[{role}]: {content[:80]}")
    return " | ".join(parts)


class AutoCompactStats:
    """Tracks auto-compaction statistics."""

    def __init__(self):
        self.total_compactions = 0
        self.total_messages_compacted = 0
        self.total_tokens_saved = 0
        self.circuit_breaker_triggers = 0
        self.failures = 0

    def record(self, result: dict[str, Any]) -> None:
        if result.get("was_compacted"):
            self.total_compactions += 1
            cr = result.get("compacted_result", {})
            if cr:
                self.total_messages_compacted += cr.get("messages_compacted", 0)
                self.total_tokens_saved += cr.get("tokens_saved", 0)
        if result.get("reason") == "circuit_breaker":
            self.circuit_breaker_triggers += 1
        if result.get("reason") == "compaction_failed":
            self.failures += 1

    def report(self) -> dict[str, Any]:
        return {
            "total_compactions": self.total_compactions,
            "total_messages_compacted": self.total_messages_compacted,
            "total_tokens_saved": self.total_tokens_saved,
            "circuit_breaker_triggers": self.circuit_breaker_triggers,
            "failures": self.failures,
        }
