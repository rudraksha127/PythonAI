"""Priority Ranker — Score and rank discovered datasets.

Evaluates each candidate dataset on multiple axes:
  - Size factor      → larger = more training data (log scale)
  - Quality factor   → based on license, description, source reputation
  - Domain gap       → how different from existing data (novelty bonus)
  - Language value   → non-English, especially Indic, gets boosted
  - Freshness        → recently updated datasets score higher
  - Source diversity → promotes variety across sources

Produces a composite priority score 0-1 and assigns a priority tier.

Usage:
    from src.data.discovery import PriorityRanker
    ranker = PriorityRanker()
    scored = ranker.score(records)
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any

from src.data.metadata import DatasetRecord, DataDomain


# ── Domain gap weights (how much we need data in each domain) ─────────
# Higher = bigger gap to fill
DOMAIN_GAP_WEIGHTS: dict[DataDomain, float] = {
    DataDomain.FORMAL_SCIENCE: 0.6,       # Well-served by arXiv/MathPile
    DataDomain.NATURAL_SCIENCE: 0.7,      # Growing field
    DataDomain.ENGINEERING: 0.5,           # Heavily served by The Stack
    DataDomain.MEDICINE: 0.85,             # Underrepresented in pre-training
    DataDomain.SOCIAL_SCIENCE: 0.8,        # Underrepresented
    DataDomain.BUSINESS: 0.8,              # Scarce in open data
    DataDomain.ARTS: 0.9,                  # Rarely in pre-training corpora
    DataDomain.LANGUAGE: 0.65,             # Good coverage from FineWeb
    DataDomain.MULTIMODAL: 0.85,           # Vast gap in most models
    DataDomain.EMERGING: 0.9,              # Frontier domain, urgent
}

# Source reputation score (0-1)
SOURCE_REPUTATION: dict[str, float] = {
    "huggingface": 0.9,
    "arxiv": 0.85,
    "github": 0.8,
    "paper": 0.75,
    "data.gov.in": 0.7,
    "data.gov": 0.7,
    "data.europa.eu": 0.7,
    "worldbank": 0.75,
    "synthetic": 0.5,
    "web": 0.4,
}

# License bonus
LICENSE_BONUS: dict[str, float] = {
    "CC0": 0.1,
    "MIT": 0.1,
    "Apache": 0.1,
    "CC-BY": 0.05,
    "ODC-BY": 0.05,
    "Public Domain": 0.1,
    "Open Government License": 0.05,
}

# Language priority (Indic languages get boost)
HIGH_PRIORITY_LANGUAGES = {
    "hi", "bn", "te", "mr", "ta", "gu", "kn", "ml",
    "pa", "or", "ur", "as", "mai", "sat", "kok", "doi",
    "mni", "ne", "sd", "brx", "ks", "sa",
}


@dataclass
class ScoredDataset:
    """A dataset with computed priority score and breakdown."""
    record: DatasetRecord
    overall_score: float = 0.0
    priority: str = "low"
    breakdown: dict[str, float] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        return (
            f"[{self.priority.upper():6s}] {self.record.name[:40]:40s} "
            f"score={self.overall_score:.3f}"
        )


class PriorityRanker:
    """Score and rank discovered datasets by multiple criteria.

    Attributes:
        domain_weights: Override default domain gap weights.
        source_reputation: Override default source reputation scores.
        language_boost: Extra score for high-value languages (default: 0.15).
        freshness_weight: How much recency matters (default: 0.1).
        diversity_mode: When True, penalize duplicate sources/domains.
    """

    def __init__(
        self,
        domain_weights: dict[DataDomain, float] | None = None,
        source_reputation: dict[str, float] | None = None,
        language_boost: float = 0.15,
        freshness_weight: float = 0.1,
        diversity_mode: bool = False,
    ) -> None:
        self.domain_weights = domain_weights or DOMAIN_GAP_WEIGHTS
        self.source_reputation = source_reputation or SOURCE_REPUTATION
        self.language_boost = language_boost
        self.freshness_weight = freshness_weight
        self.diversity_mode = diversity_mode
        self._prev_sources: list[str] = []
        self._prev_domains: list[str] = []

    def reset_diversity(self) -> None:
        """Reset diversity tracking for a new scoring batch."""
        self._prev_sources = []
        self._prev_domains = []

    def score(
        self,
        records: list[DatasetRecord],
    ) -> list[ScoredDataset]:
        """Score a list of DatasetRecord objects.

        Args:
            records: List of dataset records to score.

        Returns:\n            List of ScoredDataset sorted by overall_score descending.
        """
        scored: list[ScoredDataset] = []
        for record in records:
            s = self._score_one(record)
            # Track source for diversity (use protocol as source identifier)
            self._prev_sources.append(record.protocol.value if record.protocol else "unknown")
            # Track single domain for diversity
            if record.domain:
                d_str = record.domain.value if isinstance(record.domain, DataDomain) else str(record.domain)
                self._prev_domains.append(d_str)
            scored.append(s)

        scored.sort(key=lambda x: x.overall_score, reverse=True)
        return scored

    def _score_one(self, record: DatasetRecord) -> ScoredDataset:
        """Compute overall score for a single record."""
        breakdown: dict[str, float] = {}

        # Helper: get source name from source_url or protocol
        source = record.protocol.value if record.protocol else "unknown"

        # 1. Size factor (log scale, up to 0.25)
        size_bytes = record.actual_size_bytes or 0
        size_gb = size_bytes / (1024 ** 3) if size_bytes > 0 else 0
        if size_gb > 0:
            size_score = min(0.25, 0.05 * math.log10(1 + size_gb))
        elif record.estimated_record_count and record.estimated_record_count > 0:
            size_score = min(0.2, 0.02 * math.log10(1 + record.estimated_record_count))
        elif record.estimated_size_bytes and record.estimated_size_bytes > 0:
            est_gb = record.estimated_size_bytes / (1024 ** 3)
            size_score = min(0.2, 0.02 * math.log10(1 + est_gb * 100))
        else:
            size_score = 0.05  # Unknown size = small bonus
        breakdown["size"] = round(size_score, 4)

        # 2. Source reputation (0-0.2) — derive source name from URL
        url_lower = (record.source_url or "").lower()
        if "huggingface" in url_lower:
            src_name = "huggingface"
        elif "arxiv" in url_lower:
            src_name = "arxiv"
        elif "github" in url_lower:
            src_name = "github"
        elif "data.gov" in url_lower:
            src_name = "data.gov.in"
        elif "worldbank" in url_lower:
            src_name = "worldbank"
        elif source == "local":
            src_name = "synthetic"
        else:
            src_name = "web"
        source_score = self.source_reputation.get(src_name, 0.4) * 0.2
        breakdown["source"] = round(source_score, 4)

        # 3. Domain gap (0-0.25) — use single domain field
        domain_score = 0.0
        d = record.domain
        if isinstance(d, DataDomain):
            weight = self.domain_weights.get(d, 0.5)
        else:
            # Try string matching
            for dd, w in self.domain_weights.items():
                if dd.value == d:
                    weight = w
                    break
            else:
                weight = 0.5
        domain_score = weight * 0.25
        breakdown["domain_gap"] = round(domain_score, 4)

        # 4. Language value (0-0.15)
        lang_score = 0.0
        for lang in (record.languages or []):
            lang_lower = lang.lower().split("-")[0]
            if lang_lower in HIGH_PRIORITY_LANGUAGES:
                lang_score = min(0.15, lang_score + 0.08)
            elif lang_lower != "en":
                lang_score = max(lang_score, 0.04)  # Non-English bonus
        breakdown["language"] = round(lang_score, 4)

        # 5. License bonus (0-0.05)
        license_score = 0.0
        lic_lower = (record.license or "").lower()
        for lic, bonus in LICENSE_BONUS.items():
            if lic.lower() in lic_lower:
                license_score = max(license_score, bonus)
        breakdown["license"] = round(license_score, 4)

        # 6. Quality score from existing metadata (0-0.1)
        quality_score = (record.quality_score or 0.5) * 0.1
        breakdown["quality"] = round(quality_score, 4)

        # 7. Diversity penalty (if enabled)
        diversity_penalty = 0.0
        if self.diversity_mode:
            if self._prev_sources.count(source) > 2:
                diversity_penalty = -0.05
            d_str = record.domain.value if isinstance(record.domain, DataDomain) else str(record.domain)
            if self._prev_domains.count(d_str) > 3:
                diversity_penalty -= 0.03
        breakdown["diversity"] = round(diversity_penalty, 4)

        # 8. Freshness bonus (0-0.05) — use completed_at as proxy for "last updated"
        freshness_score = 0.0
        freshness_field = getattr(record, "completed_at", None) or getattr(record, "started_at", None)
        if freshness_field:
            try:
                updated = datetime.fromtimestamp(freshness_field, tz=timezone.utc)
                days_old = (datetime.now(timezone.utc) - updated).days
                if days_old < 30:
                    freshness_score = 0.05
                elif days_old < 90:
                    freshness_score = 0.04
                elif days_old < 365:
                    freshness_score = 0.02
            except (ValueError, TypeError, OSError):
                pass
        breakdown["freshness"] = round(freshness_score, 4)

        # ── Composite score ────────────────────────────────────
        overall = sum(breakdown.values())
        overall = max(0.0, min(1.0, overall))

        # Priority tier
        if overall >= 0.7:
            priority = "critical"
        elif overall >= 0.5:
            priority = "high"
        elif overall >= 0.3:
            priority = "medium"
        else:
            priority = "low"

        return ScoredDataset(
            record=record,
            overall_score=round(overall, 4),
            priority=priority,
            breakdown=breakdown,
        )

    def top_datasets(
        self,
        records: list[DatasetRecord],
        n: int = 10,
        min_priority: str = "medium",
    ) -> list[ScoredDataset]:
        """Return the top N scored datasets above a priority threshold.

        Priority order: critical > high > medium > low

        Args:
            records: Datasets to score and filter.
            n: Max number to return.
            min_priority: Minimum priority tier to include.

        Returns:
            Top N scored datasets.
        """
        priority_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        min_val = priority_order.get(min_priority, 2)

        scored = self.score(records)
        filtered = [s for s in scored if priority_order.get(s.priority, 0) >= min_val]
        return filtered[:n]

    def batch_score_with_stats(
        self,
        records: list[DatasetRecord],
    ) -> dict[str, Any]:
        """Score and return detailed stats about the dataset landscape.

        Args:
            records: Datasets to evaluate.

        Returns:
            Dict with scoring results and aggregate statistics.
        """
        self.reset_diversity()
        scored = self.score(records)

        domains_covered: set[str] = set()
        sources_used: set[str] = set()
        total_size = 0
        priority_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        for s in scored:
            # Use single domain field
            d = s.record.domain
            d_str = d.value if isinstance(d, DataDomain) else str(d)
            domains_covered.add(d_str)
            sources_used.add(s.record.protocol.value if s.record.protocol else "unknown")
            total_size += s.record.actual_size_bytes if s.record.actual_size_bytes else 0
            priority_counts[s.priority] = priority_counts.get(s.priority, 0) + 1

        return {
            "total_datasets": len(scored),
            "scored": scored[:50],  # Top 50
            "domains_covered": sorted(domains_covered),
            "sources_used": sorted(sources_used),
            "total_size_gb": round(total_size / (1024 ** 3), 2),
            "priority_counts": priority_counts,
            "avg_score": round(
                sum(s.overall_score for s in scored) / len(scored), 4
            ) if scored else 0.0,
            "critical_datasets": [
                s.record.id for s in scored if s.priority == "critical"
            ],
            "recommended_first": [
                s.record.id for s in scored[:10]
            ],
        }


def rank_discovered(
    records: list[DatasetRecord],
    top_n: int = 20,
) -> list[ScoredDataset]:
    """Convenience: score and return top N datasets.

    Args:
        records: Dataset records to rank.
        top_n: How many top results to return.

    Returns:
        Top N scored datasets.
    """
    ranker = PriorityRanker()
    scored = ranker.score(records)
    return scored[:top_n]


def print_ranking(scored: list[ScoredDataset]) -> None:
    """Pretty-print a ranking of scored datasets to stdout."""
    if not scored:
        print("[PriorityRanker] No datasets to rank.")
        return

    print(f"{'Priority':8s} {'Score':6s} {'Name':40s} {'Domain':18s} {'Size':>10s}")
    print(f"{'─'*8} {'─'*6} {'─'*40} {'─'*18} {'─'*10}")
    for s in scored:
        domain_str = (
            s.record.domain.value[:16]
            if isinstance(s.record.domain, DataDomain)
            else str(s.record.domain)[:16]
        ) if s.record.domain else "unknown"
        size_bytes = s.record.actual_size_bytes or s.record.estimated_size_bytes or 0
        size_str = (
            f"{size_bytes / (1024**3):.1f}GB"
            if size_bytes > 0
            else "?"
        )
        print(
            f"{s.priority:8s} {s.overall_score:.4f} "
            f"{s.record.name[:40]:40s} {domain_str:18s} {size_str:>10s}"
        )


if __name__ == "__main__":
    # Demo: create some sample records and rank them
    from src.data.metadata import DatasetRecord, DataDomain, DownloadProtocol

    samples = [
        DatasetRecord(
            id="test_1", name="Hindi News Corpus",
            source_url="https://huggingface.co/datasets/hindi_news",
            protocol=DownloadProtocol.HUGGINGFACE,
            domain=DataDomain.LANGUAGE,
            estimated_size_bytes=50_000_000_000,
            estimated_record_count=500_000,
            languages=["hi"],
            license="CC-BY",
            quality_score=0.8,
        ),
        DatasetRecord(
            id="test_2", name="Medical QA Dataset",
            source_url="https://huggingface.co/datasets/med_qa",
            protocol=DownloadProtocol.HUGGINGFACE,
            domain=DataDomain.MEDICINE,
            estimated_size_bytes=5_000_000_000,
            estimated_record_count=100_000,
            languages=["en"],
            license="MIT",
            quality_score=0.9,
        ),
        DatasetRecord(
            id="test_3", name="GitHub Code Samples",
            source_url="https://github.com/example/code",
            protocol=DownloadProtocol.GIT_LFS,
            domain=DataDomain.ENGINEERING,
            estimated_size_bytes=1_000_000_000,
            estimated_record_count=10_000,
            languages=["en"],
            license="MIT",
            quality_score=0.7,
        ),
    ]

    print("[PriorityRanker] Demo ranking:\n")
    ranker = PriorityRanker()
    results = ranker.score(samples)
    print_ranking(results)
    print(f"\nBreakdown for '{results[0].record.name}':")
    for k, v in results[0].breakdown.items():
        print(f"  {k:15s}: {v:.4f}")
