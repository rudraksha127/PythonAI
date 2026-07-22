"""
Token Budget — Auto-Continuation Detection
===========================================
Inspired by Claude Code's query/tokenBudget.ts.

When the model is still producing useful output:
- Track tokens per turn
- If < 90% of budget and still producing > 500 tokens delta → continue
- If 3+ continuations with diminishing returns (< 500 tokens each) → stop
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

COMPLETION_THRESHOLD = 0.90  # Continue if under 90% of budget
DIMINISHING_THRESHOLD = 500  # Stop if delta < 500 tokens for 2+ rounds
MAX_CONTINUATIONS = 10  # Absolute max continuations


@dataclass
class BudgetTracker:
    """Tracks token budget across model turns."""

    continuation_count: int = 0
    last_delta_tokens: int = 0
    last_global_turn_tokens: int = 0
    started_at: float = field(default_factory=time.time)

    def reset(self) -> None:
        self.continuation_count = 0
        self.last_delta_tokens = 0
        self.last_global_turn_tokens = 0
        self.started_at = time.time()


@dataclass
class ContinueDecision:
    action: str = "continue"  # "continue" or "stop"
    nudge_message: str = ""
    continuation_count: int = 0
    pct: float = 0.0
    turn_tokens: int = 0
    budget: int = 0
    reason: str = ""


def check_token_budget(
    tracker: BudgetTracker,
    agent_id: str | None,
    budget: int | None,
    global_turn_tokens: int,
) -> ContinueDecision:
    """
    Check if the model should continue or stop based on token budget.

    Args:
        tracker: Budget tracker with continuation state
        agent_id: If set, subagents don't use budget
        budget: Token budget for this turn (None = unlimited)
        global_turn_tokens: Total tokens used so far

    Returns:
        ContinueDecision with action "continue" or "stop"
    """
    if agent_id or budget is None or budget <= 0:
        return ContinueDecision(action="stop", reason="no_budget")

    turn_tokens = global_turn_tokens
    pct = round((turn_tokens / budget) * 100, 1)
    delta_since_last = global_turn_tokens - tracker.last_global_turn_tokens

    # Check diminishing returns
    is_diminishing = (
        tracker.continuation_count >= 3
        and delta_since_last < DIMINISHING_THRESHOLD
        and tracker.last_delta_tokens < DIMINISHING_THRESHOLD
    )

    # Check max continuations
    if tracker.continuation_count >= MAX_CONTINUATIONS:
        return ContinueDecision(
            action="stop",
            reason="max_continuations",
            continuation_count=tracker.continuation_count,
            pct=pct,
            turn_tokens=turn_tokens,
            budget=budget,
        )

    if not is_diminishing and turn_tokens < budget * COMPLETION_THRESHOLD:
        tracker.continuation_count += 1
        tracker.last_delta_tokens = delta_since_last
        tracker.last_global_turn_tokens = global_turn_tokens

        nudge = _get_budget_nudge_message(pct, turn_tokens, budget)

        return ContinueDecision(
            action="continue",
            nudge_message=nudge,
            continuation_count=tracker.continuation_count,
            pct=pct,
            turn_tokens=turn_tokens,
            budget=budget,
            reason="has_budget",
        )

    if is_diminishing:
        return ContinueDecision(
            action="stop",
            reason="diminishing_returns",
            continuation_count=tracker.continuation_count,
            pct=pct,
            turn_tokens=turn_tokens,
            budget=budget,
        )

    return ContinueDecision(
        action="stop",
        reason="budget_exhausted",
        continuation_count=tracker.continuation_count,
        pct=pct,
        turn_tokens=turn_tokens,
        budget=budget,
    )


def _get_budget_nudge_message(pct: float, turn_tokens: int, budget: int) -> str:
    """Get the nudge message for auto-continuation."""
    remaining = budget - turn_tokens
    if remaining > 100_000:
        return (
            f"[You have plenty of budget remaining ({remaining:,} tokens / {pct}% used). "
            "Continue your response naturally.]"
        )
    elif remaining > 50_000:
        return f"[You have {remaining:,} tokens remaining ({pct}% used). Continue your response.]"
    elif remaining > 10_000:
        return f"[You have {remaining:,} tokens remaining ({pct}% used). Be concise but complete your response.]"
    else:
        return f"[Budget nearly exhausted ({remaining:,} tokens left, {pct}% used). Wrap up your response.]"
