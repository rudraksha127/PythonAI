"""GitHub Trending Scanner.

Tracks trending AI/ML repositories on GitHub, finds new datasets,
and identifies high-quality open-source code repositories for
training data collection.

Uses the GitHub API (read-only, no auth needed for public repos)
to discover trending repos in AI/ML categories.

Usage:
    from src.data.discovery import GitHubTrending
    scanner = GitHubTrending()
    repos = scanner.scan()
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.data.metadata import DataDomain, DatasetRecord, MetadataManager

DEFAULT_CACHE_PATH = Path(__file__).resolve().parent / ".github_cache.json"

# GitHub topics that signal high-value datasets
DATASET_TOPICS = [
    "dataset",
    "training-data",
    "nlp",
    "computer-vision",
    "machine-learning",
    "deep-learning",
    "llm",
    "large-language-model",
    "fine-tuning",
    "sft",
    "instruction-tuning",
    "rlhf",
    "text-classification",
    "sentiment-analysis",
    "translation",
    "speech-recognition",
    "image-classification",
    "object-detection",
]

# Languages we prioritize for code training data
PRIORITY_LANGUAGES = [
    "python",
    "javascript",
    "typescript",
    "rust",
    "go",
    "java",
    "c++",
    "c",
    "julia",
    "r",
    "swift",
    "kotlin",
]

TOPIC_DOMAIN_MAP: dict[str, DataDomain] = {
    "dataset": DataDomain.EMERGING,
    "machine-learning": DataDomain.ENGINEERING,
    "deep-learning": DataDomain.ENGINEERING,
    "nlp": DataDomain.LANGUAGE,
    "computer-vision": DataDomain.MULTIMODAL,
    "llm": DataDomain.ENGINEERING,
    "large-language-model": DataDomain.ENGINEERING,
    "fine-tuning": DataDomain.ENGINEERING,
    "instruction-tuning": DataDomain.ENGINEERING,
    "rlhf": DataDomain.ENGINEERING,
    "translation": DataDomain.LANGUAGE,
    "speech-recognition": DataDomain.MULTIMODAL,
    "image-classification": DataDomain.MULTIMODAL,
    "object-detection": DataDomain.MULTIMODAL,
}


@dataclass
class GitHubRepo:
    """A GitHub repository discovered as potentially useful."""

    full_name: str
    description: str = ""
    url: str = ""
    stars: int = 0
    forks: int = 0
    language: str = ""
    topics: list[str] = field(default_factory=list)
    license: str = ""
    size_kb: int = 0
    updated_at: str = ""
    is_dataset: bool = False
    is_new: bool = True
    relevance_score: float = 0.0


class GitHubTrending:
    """Discover trending GitHub repos relevant to AI training.

    Attributes:
        metadata_mgr: Optional MetadataManager for cross-reference.
        cache_path: Path to local cache.
        api_base: GitHub API base URL.
    """

    def __init__(
        self,
        metadata_mgr: MetadataManager | None = None,
        cache_path: str | Path | None = None,
    ) -> None:
        self.metadata_mgr = metadata_mgr or MetadataManager()
        self.cache_path = Path(cache_path) if cache_path else DEFAULT_CACHE_PATH
        self.api_base = "https://api.github.com"
        self._seen: set[str] = set()
        self._load_cache()

    def _load_cache(self) -> None:
        if self.cache_path.exists():
            try:
                data = json.loads(self.cache_path.read_text(encoding="utf-8"))
                self._seen = set(data.get("seen_ids", []))
            except (json.JSONDecodeError, KeyError):
                self._seen = set()

    def _save_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps({"seen_ids": sorted(self._seen)}, indent=2),
            encoding="utf-8",
        )

    def scan(
        self,
        max_results: int = 30,
        min_stars: int = 50,
        topics: list[str] | None = None,
    ) -> list[GitHubRepo]:
        """Scan GitHub for trending repos relevant to AI training.

        Args:
            max_results: Maximum repos to return.
            min_stars: Minimum stars threshold.
            topics: Topics to search for (defaults to DATASET_TOPICS).

        Returns:
            List of newly discovered GitHubRepo objects.
        """
        discovered: list[GitHubRepo] = []
        search_topics = topics or DATASET_TOPICS

        # Search by multiple topic combinations
        for topic in search_topics[:5]:  # Limit to top 5 topics
            if len(discovered) >= max_results:
                break
            repos = self._search_by_topic(topic, min_stars, max_results)
            for repo in repos:
                key = repo.full_name
                if key not in self._seen:
                    discovered.append(repo)
                    self._seen.add(key)

        # Also fetch GitHub trending page
        if len(discovered) < max_results:
            trending = self._fetch_trending(max_results - len(discovered))
            for repo in trending:
                key = repo.full_name
                if key not in self._seen:
                    discovered.append(repo)
                    self._seen.add(key)

        discovered.sort(key=lambda r: r.relevance_score, reverse=True)
        self._save_cache()
        return discovered[:max_results]

    def _search_by_topic(
        self,
        topic: str,
        min_stars: int,
        max_results: int,
    ) -> list[GitHubRepo]:
        """Search GitHub repos by topic using the search API."""
        try:
            import urllib.parse
            import urllib.request

            query = urllib.parse.quote(f"topic:{topic} stars:>={min_stars}")
            url = f"{self.api_base}/search/repositories?q={query}&sort=stars&order=desc&per_page={min(30, max_results)}"

            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "PythonAI/2.0 (data-discovery)",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            repos: list[GitHubRepo] = []
            for item in data.get("items", [])[:max_results]:
                repo = self._parse_repo(item)
                repo.relevance_score = self._compute_relevance(repo, topic)
                repos.append(repo)
            return repos

        except Exception as exc:
            print(f"[GitHubTrending] Search by topic '{topic}' failed: {exc}")
            return []

    def _fetch_trending(self, max_results: int) -> list[GitHubRepo]:
        """Fetch trending repos from GitHub's trending page."""
        try:
            import urllib.request

            url = "https://api.github.com/search/repositories?q=created:>2026-01-01+pushed:>2026-04-01&sort=stars&order=desc&per_page=25"

            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "PythonAI/2.0 (data-discovery)",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            repos: list[GitHubRepo] = []
            for item in data.get("items", [])[:max_results]:
                repo = self._parse_repo(item)
                # Check if repo has dataset-related content
                desc = (repo.description or "").lower()
                has_dataset_keywords = any(
                    kw in desc for kw in ["dataset", "data", "corpus", "benchmark", "collection"]
                )
                if has_dataset_keywords or any(t in DATASET_TOPICS for t in repo.topics):
                    repo.relevance_score = self._compute_relevance(repo, "trending")
                    repos.append(repo)
            return repos

        except Exception as exc:
            print(f"[GitHubTrending] Fetch trending failed: {exc}")
            return []

    def _parse_repo(self, item: dict[str, Any]) -> GitHubRepo:
        """Parse a GitHub API repo object into GitHubRepo."""
        topics = item.get("topics", [])
        if not topics:
            # Try to extract from topic strings
            topic_strings = item.get("topics", [])
            topics = topic_strings if isinstance(topic_strings, list) else []

        return GitHubRepo(
            full_name=item.get("full_name", item.get("name", "")),
            description=(item.get("description", "") or "")[:300],
            url=item.get("html_url", ""),
            stars=item.get("stargazers_count", 0),
            forks=item.get("forks_count", 0),
            language=item.get("language", "") or "",
            topics=topics,
            license=item.get("license", {}).get("spdx_id", "") if item.get("license") else "",
            size_kb=item.get("size", 0),
            updated_at=item.get("updated_at", ""),
            is_dataset="dataset" in (item.get("description", "") or "").lower(),
        )

    @staticmethod
    def _compute_relevance(repo: GitHubRepo, search_context: str) -> float:
        """Compute a relevance score 0-1 for a repo."""
        score = 0.0

        # Stars factor (log scale)
        if repo.stars > 0:
            score += min(0.3, 0.05 * (repo.stars**0.3))

        # Language bonus for priority languages
        if repo.language.lower() in PRIORITY_LANGUAGES:
            score += 0.15

        # Dataset topic bonus
        if repo.is_dataset:
            score += 0.2

        # Topic overlap
        topic_overlap = len(set(repo.topics) & set(DATASET_TOPICS))
        score += min(0.2, topic_overlap * 0.05)

        # Description quality
        if len(repo.description) > 50:
            score += 0.1

        # License clarity bonus
        if repo.license:
            score += 0.05

        return min(1.0, score)

    def to_metadata_records(
        self,
        repos: list[GitHubRepo],
    ) -> list[DatasetRecord]:
        """Convert discovered repos to DatasetRecord for registration."""
        records: list[DatasetRecord] = []

        for repo in repos:
            # Determine domain from topics
            domain = DataDomain.ENGINEERING  # default
            for topic in repo.topics:
                mapped = TOPIC_DOMAIN_MAP.get(topic.lower())
                if mapped:
                    domain = mapped
                    break

            priority = "high" if repo.relevance_score >= 0.7 else "medium" if repo.relevance_score >= 0.4 else "low"

            records.append(
                DatasetRecord(
                    id=f"github_{repo.full_name.replace('/', '_')}",
                    name=repo.full_name.split("/")[-1],
                    source="github",
                    url=repo.url,
                    size_bytes=repo.size_kb * 1024,
                    estimated_records=0,
                    languages=["en"] if repo.language else [],
                    domains=[domain],
                    modalities=["code"],
                    license=repo.license or "Various",
                    priority=priority,
                    quality_score=round(repo.relevance_score, 2),
                    description=repo.description[:200] or repo.full_name,
                )
            )

        return records


def discover_github_repos(
    metadata_mgr: MetadataManager | None = None,
    max_results: int = 20,
) -> list[DatasetRecord]:
    """Convenience: scan GitHub and return DatasetRecords."""
    scanner = GitHubTrending(metadata_mgr=metadata_mgr)
    repos = scanner.scan(max_results=max_results)
    return scanner.to_metadata_records(repos)


if __name__ == "__main__":
    print("[GitHubTrending] Scanning GitHub for trending AI repos...")
    records = discover_github_repos(max_results=10)
    if records:
        print(f"  Found {len(records)} repos:")
        for r in records:
            print(f"    - {r.id}: {r.description[:70]}")
    else:
        print("  No new repos found. (API may be unavailable)")
