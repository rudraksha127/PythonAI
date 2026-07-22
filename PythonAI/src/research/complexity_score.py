"""
Convention Complexity Score (K_team)
=====================================
Original Research Contribution #4 from ForgeAI Antigravity Prompt.

K_team = H(acceptance_patterns) / H(uniform_distribution)

Low K = simple, consistent conventions → fast convergence.
High K = complex, inconsistent conventions → recommend standardization before training.

ForgeAI shows this in Week 1 onboarding:
"Your convention complexity is moderate. Estimated time to 65% acceptance rate: 8 weeks."
"""

from __future__ import annotations

import math
import numpy as np
from collections import Counter
from typing import Any


class ConventionComplexityScore:
    """Computes K_team — a Kolmogorov-complexity proxy for team conventions.

    Measures how consistent/inconsistent a team's acceptance patterns are.
    Uses entropy ratio: actual entropy / max entropy (uniform distribution).

    Usage:
        scorer = ConventionComplexityScore()
        result = scorer.compute(signals)
        # Returns { k_team, estimated_convergence_weeks, recommendation }
    """

    def __init__(self):
        pass

    def compute(self, signals: list[dict[str, Any]]) -> dict[str, Any]:
        """Compute K_team from developer signals.

        Args:
            signals: List of signal dicts with fields like:
                - language: str
                - framework: str | None
                - project_type: str
                - file_path: str
                - signal_type: str

        Returns:
            Dict with k_team score, interpretation, and recommendation
        """
        if len(signals) < 20:
            return {
                "k_team": 0.0,
                "entropy": 0.0,
                "max_entropy": 0.0,
                "signal_count": len(signals),
                "interpretation": "insufficient_data",
                "estimated_convergence_weeks": None,
                "recommendation": "Collect more signals (need at least 20).",
            }

        # Analyze convention patterns from signals
        conventions = self._extract_conventions(signals)

        if not conventions:
            return {
                "k_team": 0.0,
                "entropy": 0.0,
                "max_entropy": 0.0,
                "signal_count": len(signals),
                "interpretation": "no_patterns_found",
                "estimated_convergence_weeks": None,
                "recommendation": "No clear convention patterns detected.",
            }

        # Compute entropy over convention distribution
        counter = Counter(conventions)
        total = sum(counter.values())
        
        # H(acceptance_patterns)
        entropy = 0.0
        for count in counter.values():
            prob = count / total
            if prob > 0:
                entropy -= prob * math.log2(prob)

        # H(uniform_distribution)
        n_types = len(counter)
        max_entropy = math.log2(n_types) if n_types > 1 else 1.0

        # K_team = H(actual) / H(uniform)
        k_team = entropy / max_entropy if max_entropy > 0 else 0.0

        # Estimate convergence time
        if k_team < 0.3:
            convergence_weeks = 4
            interpretation = "very_low"
            recommendation = (
                "Exceptionally consistent conventions. "
                "Estimated time to 65% acceptance: 4 weeks. "
                "Your team has strong coding standards."
            )
        elif k_team < 0.5:
            convergence_weeks = 6
            interpretation = "low"
            recommendation = (
                "Consistent conventions. "
                "Estimated time to 65% acceptance: 6 weeks. "
                "Minor standardization opportunities exist."
            )
        elif k_team < 0.7:
            convergence_weeks = 8
            interpretation = "moderate"
            recommendation = (
                "Moderate convention complexity. "
                "Estimated time to 65% acceptance: 8 weeks. "
                "Consider standardizing code review guidelines for faster convergence."
            )
        elif k_team < 0.85:
            convergence_weeks = 12
            interpretation = "high"
            recommendation = (
                "High convention complexity. "
                "Estimated time to 65% acceptance: 12 weeks. "
                "Strongly recommend establishing team coding standards before training."
            )
        else:
            convergence_weeks = 16
            interpretation = "very_high"
            recommendation = (
                "Very high convention complexity. "
                "Estimated time to 65% acceptance: 16+ weeks. "
                "Please establish consistent team conventions before using training."
            )

        return {
            "k_team": round(k_team, 3),
            "entropy": round(entropy, 3),
            "max_entropy": round(max_entropy, 3),
            "signal_count": len(signals),
            "pattern_count": n_types,
            "interpretation": interpretation,
            "estimated_convergence_weeks": convergence_weeks,
            "recommendation": recommendation,
            "language_diversity": self._compute_language_diversity(signals),
        }

    def _extract_conventions(self, signals: list[dict[str, Any]]) -> list[str]:
        """Extract convention patterns from signals."""
        patterns = []

        for s in signals:
            # Language conventions
            lang = s.get("language", "unknown")
            patterns.append(f"lang:{lang}")

            # Framework conventions
            framework = s.get("framework")
            if framework:
                patterns.append(f"fw:{framework}")

            # Project type conventions
            proj_type = s.get("project_type", "general")
            if proj_type != "general":
                patterns.append(f"proj:{proj_type}")

            # File extension-based conventions
            file_path = s.get("file_path", "")
            if "." in file_path:
                ext = file_path.rsplit(".", 1)[-1].lower()
                patterns.append(f"ext:{ext}")

        return patterns

    def _compute_language_diversity(self, signals: list[dict[str, Any]]) -> dict:
        """Compute language diversity metrics."""
        languages = Counter(
            s.get("language", "unknown") for s in signals if s.get("language")
        )
        total = sum(languages.values())
        if total == 0:
            return {"languages": {}, "primary_language": None, "diversity": 0.0}

        primary = languages.most_common(1)[0]
        diversity = 1.0 - (primary[1] / total)

        return {
            "languages": dict(languages.most_common(5)),
            "primary_language": primary[0],
            "primary_pct": round(primary[1] / total * 100, 1),
            "diversity": round(diversity, 3),
        }
