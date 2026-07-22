"""
Hormetic Training — Boundary Robustness
========================================
Original Research Contribution #8 from ForgeAI Antigravity Prompt.

Include 5-10% rejected examples in positive training set at weight 0.1-0.2.
Forces model to learn rejection boundary, not just acceptance region.
Improves boundary robustness and generalization to edge cases.

Inspired by hormesis: low-dose stress strengthens the system.
"""

from __future__ import annotations

import numpy as np
from typing import Any


class HormeticTrainer:
    """Mix rejected/negative examples into training set at low weight.

    The standard approach trains only on positive examples (accepts, PR merges).
    This creates a problem: the model learns what to DO but not what to AVOID.

    Hormetic training includes a small percentage of rejected examples
    at reduced weight, teaching the model the acceptance boundary.

    Usage:
        hormetic = HormeticTrainer(reject_ratio=0.08, reject_weight=0.15)
        training_set = hormetic.prepare(accepts, rejects)
    """

    def __init__(
        self,
        reject_ratio: float = 0.08,
        reject_weight: float = 0.15,
        min_rejects: int = 5,
    ):
        """
        Args:
            reject_ratio: Fraction of rejects to include (default 0.08 = 8%)
            reject_weight: Weight multiplier for rejected examples (0.1-0.2)
            min_rejects: Minimum rejected examples needed
        """
        self.reject_ratio = max(0.01, min(0.20, reject_ratio))
        self.reject_weight = max(0.05, min(0.50, reject_weight))
        self.min_rejects = min_rejects

    def prepare(
        self,
        positive_examples: list[dict[str, Any]],
        rejected_examples: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Merge positive examples with a hormetic dose of rejected ones.

        Args:
            positive_examples: List of accepted/merged examples (weight=1.0)
            rejected_examples: List of rejected examples (weight=reject_weight)

        Returns:
            Combined dataset with appropriate weights
        """
        # Weight all positive examples at 1.0
        weighted_positives = []
        for ex in positive_examples:
            ex_copy = dict(ex)
            ex_copy["weight"] = 1.0
            ex_copy["hormetic"] = False
            weighted_positives.append(ex_copy)

        # Add hormetic dose of rejected examples
        if rejected_examples and len(rejected_examples) >= self.min_rejects:
            # Sample the specified ratio of rejects
            n_rejects_to_include = max(
                self.min_rejects,
                int(len(positive_examples) * self.reject_ratio),
            )
            n_rejects_to_include = min(n_rejects_to_include, len(rejected_examples))

            sampled_rejects = np.random.choice(
                len(rejected_examples),
                size=n_rejects_to_include,
                replace=False,
            )

            for idx in sampled_rejects:
                ex = rejected_examples[idx]
                ex_copy = dict(ex)
                ex_copy["weight"] = self.reject_weight
                ex_copy["hormetic"] = True
                weighted_positives.append(ex_copy)

        # Shuffle for randomness
        np.random.shuffle(weighted_positives)

        return weighted_positives

    def prepare_from_signals(
        self,
        signals: list[dict[str, Any]],
        accept_types: tuple[str, ...] = ("accept", "edit", "pr_merge"),
        reject_types: tuple[str, ...] = ("reject",),
    ) -> list[dict[str, Any]]:
        """Prepare hormetic training set directly from signal data.

        Args:
            signals: List of signal dicts with signal_type field
            accept_types: Signal types considered positive
            reject_types: Signal types considered negative

        Returns:
            Hormetically balanced training set
        """
        positives = [s for s in signals if s.get("signal_type") in accept_types]
        rejects = [s for s in signals if s.get("signal_type") in reject_types]

        return self.prepare(positives, rejects)

    def describe(self) -> dict[str, Any]:
        """Return description of the hormetic training scheme."""
        return {
            "method": "Hormetic Training",
            "rationale": (
                "Include 5-10% rejected examples at weight 0.1-0.2. "
                "Forces model to learn rejection boundary, not just acceptance region."
            ),
            "reject_ratio": self.reject_ratio,
            "reject_weight": self.reject_weight,
            "min_rejects": self.min_rejects,
            "reference": "ForgeAI Original Research #8",
        }
