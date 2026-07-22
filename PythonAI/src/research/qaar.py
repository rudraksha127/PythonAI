"""
QAAR — Quality-Adjusted Acceptance Rate
========================================
Original Research Contribution #1 from ForgeAI Antigravity Prompt.

QAAR = RAR × 0.3 + EDA × 0.25 + TPR × 0.25 + CSR × 0.20

Where:
- RAR (Raw Acceptance Rate): Basic accept/reject ratio
- EDA (Edit Distance Adjustment): How much the accepted code differs
- TPR (Test Pass Rate): Verifiable correctness signal
- CSR (Code Survival Rate): How long accepted code survives in repo

This corrects for the problem with raw acceptance rate:
>45% may indicate uncritical acceptance, not quality.
QAAR corrects this with post-hoc verifiable signals.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Any


@dataclass
class QAARComponents:
    """Individual components that make up the QAAR score."""

    raw_acceptance_rate: float = 0.0
    edit_distance_adjustment: float = 0.0
    test_pass_rate: float = 0.0
    code_survival_rate: float = 0.0

    @property
    def qaar(self) -> float:
        """Compute Quality-Adjusted Acceptance Rate."""
        return (
            self.raw_acceptance_rate * 0.30
            + self.edit_distance_adjustment * 0.25
            + self.test_pass_rate * 0.25
            + self.code_survival_rate * 0.20
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "raw_acceptance_rate": round(self.raw_acceptance_rate, 2),
            "edit_distance_adjustment": round(self.edit_distance_adjustment, 2),
            "test_pass_rate": round(self.test_pass_rate, 2),
            "code_survival_rate": round(self.code_survival_rate, 2),
            "qaar": round(self.qaar, 2),
        }


class QAARMetric:
    """Computes Quality-Adjusted Acceptance Rate from capture engine signals.

    Usage:
        qaar = QAARMetric()
        result = qaar.compute(capture_engine)
    """

    def __init__(self, window_days: int = 30, min_signals: int = 50):
        self.window_days = window_days
        self.min_signals = min_signals

    def compute(self, signals: list[dict[str, Any]]) -> QAARComponents:
        """Compute QAAR from a list of signal dictionaries.

        Each signal dict should have:
            signal_type: 'accept' | 'reject' | 'edit'
            edit_distance: float (0.0-1.0)
            test_passed: bool | None
            timestamp: float
        """
        if len(signals) < self.min_signals:
            return QAARComponents()  # Not enough data

        # 1. Raw Acceptance Rate (RAR)
        total_suggestions = len(signals)
        accepts = sum(1 for s in signals if s.get("signal_type") in ("accept", "pr_merge"))
        rejects = sum(1 for s in signals if s.get("signal_type") == "reject")
        edits = sum(1 for s in signals if s.get("signal_type") == "edit")

        total_decisions = accepts + rejects
        raw_acceptance_rate = accepts / total_decisions if total_decisions > 0 else 0.0

        # 2. Edit Distance Adjustment (EDA)
        # Higher edit distance = developer is critically reviewing
        # Formula: 1 - avg(edit_distance) → lower edits = higher confidence
        edit_distances = [
            s.get("edit_distance", 0.0)
            for s in signals
            if s.get("signal_type") in ("accept", "edit")
        ]
        avg_edit_distance = np.mean(edit_distances) if edit_distances else 0.0
        # Invert so lower edit distance = higher score
        edit_distance_adjustment = 1.0 - min(avg_edit_distance, 1.0)

        # 3. Test Pass Rate (TPR)
        tested_signals = [s for s in signals if s.get("test_passed") is not None]
        if tested_signals:
            test_pass_rate = sum(
                1 for s in tested_signals if s.get("test_passed") is True
            ) / len(tested_signals)
        else:
            test_pass_rate = raw_acceptance_rate  # Fallback

        # 4. Code Survival Rate (CSR) - proxy: PR merges / total accepts
        # PR merges = code that survived review
        pr_merges = sum(1 for s in signals if s.get("signal_type") == "pr_merge")
        total_positive = accepts + pr_merges
        code_survival_rate = pr_merges / total_positive if total_positive > 0 else raw_acceptance_rate * 0.5

        return QAARComponents(
            raw_acceptance_rate=raw_acceptance_rate,
            edit_distance_adjustment=edit_distance_adjustment,
            test_pass_rate=test_pass_rate,
            code_survival_rate=code_survival_rate,
        )

    def trend(self, signals_by_week: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
        """Compute QAAR trend over weekly windows."""
        results = []
        for week_num, week_signals in enumerate(signals_by_week, 1):
            if len(week_signals) < 10:
                continue
            components = self.compute(week_signals)
            results.append({
                "week": week_num,
                "signal_count": len(week_signals),
                **components.to_dict(),
            })
        return results


def compute_qaar(
    signals: list[dict[str, Any]],
    window_days: int = 30,
    min_signals: int = 50,
) -> dict[str, Any]:
    """Convenience function to compute QAAR from signals.

    Args:
        signals: List of signal dicts (should be pre-sorted by timestamp).
        window_days: Lookback window for relevant signals.
        min_signals: Minimum signals needed for meaningful QAAR.

    Returns:
        Dict with QAAR components: raw_acceptance_rate, edit_distance_adjustment,
        test_pass_rate, code_survival_rate, and composite qaar score.
    """
    metric = QAARMetric(window_days=window_days, min_signals=min_signals)
    components = metric.compute(signals)
    return components.to_dict()
