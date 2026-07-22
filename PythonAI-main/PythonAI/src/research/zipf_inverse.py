"""
Zipf-Inverse Training Weights
==============================
Original Research Contribution #2 from ForgeAI Antigravity Prompt.

weight(example) = 1 / frequency(primary_pattern) × normalization

Rare patterns (security, edge cases) get upweighted.
Common patterns (standard imports) get downweighted.
Result: model learns full convention distribution, not just the head.

Reference: Zipf's law for code tokens — top 20% patterns = 80% of code.
Generic models overtrain on head, undertrain on tail.
Zipf-inverse corrects this by weighting tail patterns higher.
"""

from __future__ import annotations

import numpy as np
from collections import Counter
from typing import Any


class ZipfInverseWeighting:
    """Assigns training weights inversely proportional to pattern frequency.

    Usage:
        weight = ZipfInverseWeighting()
        weighted_examples = weight.apply(examples)
        # Each example gets a `weight` field
    """

    def __init__(self, min_weight: float = 0.1, max_weight: float = 5.0):
        self.min_weight = min_weight
        self.max_weight = max_weight

    def compute_weights(
        self,
        patterns: list[str],
        normalize: bool = True,
    ) -> dict[str, float]:
        """Compute Zipf-inverse weights for each unique pattern.

        Args:
            patterns: List of pattern strings (e.g., function names, APIs used)
            normalize: If True, rescale weights to [min_weight, max_weight]

        Returns:
            Dict mapping pattern -> weight
        """
        if not patterns:
            return {}

        counter = Counter(patterns)
        total = sum(counter.values())

        # Compute inverse frequency
        weights: dict[str, float] = {}
        for pattern, count in counter.items():
            freq = count / total
            weight = 1.0 / max(freq, 1e-10)  # Inverse frequency
            weights[pattern] = weight

        if normalize and weights:
            w_min = min(weights.values())
            w_max = max(weights.values())
            w_range = w_max - w_min
            if w_range > 0:
                for pattern in weights:
                    normalized = (weights[pattern] - w_min) / w_range
                    # Scale to [min_weight, max_weight]
                    weights[pattern] = (
                        self.min_weight + normalized * (self.max_weight - self.min_weight)
                    )
                weights[pattern] = max(self.min_weight, min(self.max_weight, weights[pattern]))

        return weights

    def extract_patterns(self, example: dict[str, Any]) -> list[str]:
        """Extract patterns from a training example.

        Override this method for custom pattern extraction logic.

        Returns:
            List of pattern strings found in the example
        """
        patterns = []
        text = example.get("output", "") or example.get("text", "") or ""

        # Extract function calls
        import re
        func_calls = re.findall(r"(\w+)\s*\(", text)
        patterns.extend(func_calls[:20])

        # Extract import statements
        imports = re.findall(r"(?:from|import)\s+(\S+)", text)
        patterns.extend(imports[:10])

        # Extract language/framework mentions
        frameworks = ["numpy", "pandas", "torch", "tensorflow", "flask", "django",
                      "fastapi", "pytest", "sqlalchemy", "asyncio", "matplotlib"]
        for fw in frameworks:
            if fw.lower() in text.lower():
                patterns.append(fw)

        return patterns

    def apply(
        self,
        examples: list[dict[str, Any]],
        pattern_extractor: str = "auto",
    ) -> list[dict[str, Any]]:
        """Assign Zipf-inverse weights to a list of training examples.

        Args:
            examples: List of training example dicts
            pattern_extractor: 'auto' (default) or a callable

        Returns:
            Examples with updated `weight` field
        """
        if not examples:
            return examples

        # Extract all patterns
        all_patterns = []
        for ex in examples:
            patterns = self.extract_patterns(ex)
            all_patterns.extend(patterns)

        # Compute weights
        pattern_weights = self.compute_weights(all_patterns)

        # Assign weights to examples
        weighted_examples = []
        for ex in examples:
            ex_patterns = self.extract_patterns(ex)
            if ex_patterns and pattern_weights:
                avg_weight = np.mean(
                    [pattern_weights.get(p, 1.0) for p in ex_patterns]
                )
            else:
                avg_weight = 1.0
            ex_copy = dict(ex)
            ex_copy["weight"] = round(avg_weight, 4)
            ex_copy["zipf_weight"] = ex_copy["weight"]
            weighted_examples.append(ex_copy)

        return weighted_examples

    def describe(self) -> dict[str, Any]:
        """Return description of the weighting scheme."""
        return {
            "method": "Zipf-Inverse Weighting",
            "rationale": "Rare patterns (security, edge cases) get upweighted. "
                         "Common patterns (standard imports) get downweighted.",
            "min_weight": self.min_weight,
            "max_weight": self.max_weight,
            "reference": "ForgeAI Original Research #2",
        }
