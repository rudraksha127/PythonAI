"""
Time-Decay Learning Signal
===========================
Original Research Contribution #3 from ForgeAI Antigravity Prompt.

weight(example, age) = e^(-λ × age_weeks) where λ = 0.1

Recent accepts: weight 1.0
6 months ago: weight 0.14
12 months ago: weight 0.02

Prevents model from overcommitting to conventions that have been superseded.
Without time decay, old conventions compete equally with new ones.
"""

from __future__ import annotations

import math
import time
from typing import Any


class TimeDecaySignal:
    """Decay training signal weight based on age.

    Older signals get lower weight, preventing the model from
    overfitting to stale conventions.

    Usage:
        decay = TimeDecaySignal(lambda_val=0.1)
        weight = decay.compute_weight(timestamp)
        weighted_examples = decay.apply(examples)
    """

    def __init__(self, lambda_val: float = 0.1, min_weight: float = 0.01):
        """
        Args:
            lambda_val: Decay rate (default 0.1).
                Higher values = faster decay.
                0.1 → 90% decay in ~23 weeks
                0.05 → 90% decay in ~46 weeks
                0.2 → 90% decay in ~11.5 weeks
            min_weight: Minimum weight floor (default 0.01)
        """
        self.lambda_val = lambda_val
        self.min_weight = min_weight

    def compute_weight(self, timestamp: float, now: float | None = None) -> float:
        """Compute decay weight for a signal with given timestamp.

        Args:
            timestamp: Unix timestamp of the signal
            now: Current time (default: time.time())

        Returns:
            Weight between min_weight and 1.0
        """
        if now is None:
            now = time.time()

        age_seconds = max(0, now - timestamp)
        age_weeks = age_seconds / (7 * 24 * 3600)
        weight = math.exp(-self.lambda_val * age_weeks)
        return max(self.min_weight, min(1.0, weight))

    def apply(
        self,
        examples: list[dict[str, Any]],
        timestamp_field: str = "timestamp",
        now: float | None = None,
    ) -> list[dict[str, Any]]:
        """Apply time decay weights to a list of examples.

        Args:
            examples: List of signal/example dicts with timestamp_field
            timestamp_field: Field name containing Unix timestamp
            now: Current time override

        Returns:
            Examples with added `decay_weight` field
        """
        if now is None:
            now = time.time()

        weighted = []
        for ex in examples:
            ts = ex.get(timestamp_field, now)
            decay_weight = self.compute_weight(ts, now)
            ex_copy = dict(ex)
            ex_copy["decay_weight"] = round(decay_weight, 4)
            ex_copy["age_weeks"] = round(
                max(0, now - ts) / (7 * 24 * 3600), 1
            )
            weighted.append(ex_copy)

        return weighted

    def get_half_life_weeks(self) -> float:
        """Get the half-life of the decay signal."""
        return math.log(2) / self.lambda_val if self.lambda_val > 0 else float("inf")

    def describe(self) -> dict[str, Any]:
        """Return description of the decay scheme."""
        return {
            "method": "Time-Decay Learning Signal",
            "lambda": self.lambda_val,
            "half_life_weeks": round(self.get_half_life_weeks(), 1),
            "min_weight": self.min_weight,
            "weight_at_1_week": round(math.exp(-self.lambda_val * 1), 4),
            "weight_at_1_month": round(math.exp(-self.lambda_val * 4), 4),
            "weight_at_6_months": round(math.exp(-self.lambda_val * 26), 4),
            "weight_at_12_months": round(math.exp(-self.lambda_val * 52), 4),
            "reference": "ForgeAI Original Research #3",
        }
