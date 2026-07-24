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
import os
import ssl
import time
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import certifi
from src.data.metadata import DataDomain, DatasetRecord, MetadataManager

# SSL context using certifi CA bundle — fixes SSL errors on Windows
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

# GitHub API token — set GITHUB_TOKEN env var for 5,000 req/hr instead of 60
_GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# Rate limiting constants
_GITHUB_RATE_LIMIT_WARNED = False
_RATE_LIMIT_DELAY = 2.0  # seconds between API calls to avoid rate limits

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

    # Cache for rate-limited responses (class-level, shared across instances)
    _request_cache: dict[str, tuple[float, dict[str, Any]]] = {}
    _last_request_time: float = 0.0
    _rate_limited_until: float = 0.0

    def __init__(
        self,
        metadata_mgr: MetadataManager | None = None,
        cache_path: str | Path | None = None,
        github_token: str | None = None,
    ) -> None:
        self.metadata_mgr = metadata_mgr or MetadataManager()
        self.cache_path = Path(cache_path) if cache_path else DEFAULT_CACHE_PATH
        self.api_base = "https://api.github.com"
        self._token = github_token or _GITHUB_TOKEN
        self._seen: set[str] = set()
        self._rate_limit_delay = _RATE_LIMIT_DELAY if not self._token else 0.5  # Faster with token
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

    def _respect_rate_limit(self) -> None:
        """Respect rate limits by waiting between requests."""
        global _GITHUB_RATE_LIMIT_WARNED

        # Check if we're in a rate limit cooldown period
        if GitHubTrending._rate_limited_until > time.time():
            wait = GitHubTrending._rate_limited_until - time.time()
            print(f"  [GitHubTrending] Rate limited — waiting {wait:.0f}s...")
            time.sleep(wait)
            return

        # Enforce minimum delay between requests
        elapsed = time.time() - GitHubTrending._last_request_time
        if elapsed < self._rate_limit_delay:
            time.sleep(self._rate_limit_delay - elapsed)

        # Warn about missing token
        if not _GITHUB_TOKEN and not _GITHUB_RATE_LIMIT_WARNED:
            print("  [GitHubTrending] No GITHUB_TOKEN set — limited to 60 req/hr. Set GITHUB_TOKEN for 5,000 req/hr.")
            _GITHUB_RATE_LIMIT_WARNED = True

    def _handle_rate_limit_response(self, exc: Exception) -> bool:
        """Handle rate limit response. Returns True if we should retry."""
        if isinstance(exc, urllib.error.HTTPError):
            if exc.code in (403, 429):
                retry_after = 60
                try:
                    retry_after = int(exc.headers.get("Retry-After", "60"))
                except (ValueError, AttributeError):
                    pass
                retry_after = max(retry_after, 30)
                GitHubTrending._rate_limited_until = time.time() + retry_after
                print(f"  [GitHubTrending] Rate limited (HTTP {exc.code}) — cooling down for {retry_after}s")
                return True
        return False

    def _api_request(self, url: str) -> dict[str, Any] | None:
        """Make an API request with rate limit handling and caching.

        Uses a response cache to avoid repeat requests for the same URL
        within a 5-minute window.
        """
        import urllib.parse
        import urllib.request

        # Check response cache (5 min TTL)
        cache_key = url
        if cache_key in GitHubTrending._request_cache:
            cached_time, cached_data = GitHubTrending._request_cache[cache_key]
            if time.time() - cached_time < 300:  # 5 min cache
                return cached_data

        self._respect_rate_limit()

        try:
            req = urllib.request.Request(url, headers=self._build_headers())
            with urllib.request.urlopen(req, timeout=10, context=_SSL_CONTEXT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                GitHubTrending._last_request_time = time.time()
                GitHubTrending._request_cache[cache_key] = (time.time(), data)
                return data
        except urllib.error.HTTPError as exc:
            if self._handle_rate_limit_response(exc):
                return None
            print(f"  [GitHubTrending] HTTP {exc.code} for {url[:80]}")
            return None
        except Exception as exc:
            print(f"  [GitHubTrending] Request failed: {exc}")
            return None

    def scan(
        self,
        max_results: int = 30,
        min_stars: int = 50,
        topics: list[str] | None = None,
        force_refresh: bool = False,
    ) -> list[GitHubRepo]:
        """Scan GitHub for trending repos relevant to AI training.

        Uses cached responses to minimize API calls. When rate-limited,
        returns whatever has been collected so far instead of crashing.

        Args:
            max_results: Maximum repos to return.
            min_stars: Minimum stars threshold.
            topics: Topics to search for (defaults to DATASET_TOPICS).
            force_refresh: If True, ignore the seen-ids cache and return
                           all matching repos. Useful for scheduled scans.

        Returns:
            List of newly discovered GitHubRepo objects.
        """
        discovered: list[GitHubRepo] = []
        search_topics = topics or DATASET_TOPICS

        seen: set[str] = set() if force_refresh else self._seen

        # Search by multiple topic combinations
        for topic in search_topics[:3]:  # Reduced from 5 to 3 to save API calls
            if len(discovered) >= max_results:
                break
            if self._is_rate_limited():
                print("  [GitHubTrending] Skipping remaining topics — rate limited")
                break
            repos = self._search_by_topic(topic, min_stars, max_results)
            for repo in repos:
                key = repo.full_name
                if key not in seen:
                    discovered.append(repo)
                    seen.add(key)

        # Also fetch GitHub trending page (only if not rate limited)
        if len(discovered) < max_results and not self._is_rate_limited():
            trending = self._fetch_trending(max_results - len(discovered))
            for repo in trending:
                key = repo.full_name
                if key not in seen:
                    discovered.append(repo)
                    seen.add(key)

        if force_refresh:
            for repo in discovered:
                self._seen.add(repo.full_name)

        discovered.sort(key=lambda r: r.relevance_score, reverse=True)
        self._save_cache()
        return discovered[:max_results]

    def _is_rate_limited(self) -> bool:
        """Check if we're currently in a rate limit cooldown."""
        return GitHubTrending._rate_limited_until > time.time()

    def _build_headers(self) -> dict[str, str]:
        """Build headers with optional GITHUB_TOKEN auth."""
        headers: dict[str, str] = {
            "User-Agent": "PythonAI/2.0 (data-discovery)",
            "Accept": "application/vnd.github.v3+json",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _search_by_topic(
        self,
        topic: str,
        min_stars: int,
        max_results: int,
    ) -> list[GitHubRepo]:
        """Search GitHub repos by topic using the search API.

        Uses class-level caching to avoid repeat API calls for the same topic
        within a 5-minute window."
        """
        import urllib.parse

        query = urllib.parse.quote(f"topic:{topic} stars:>={min_stars}")
        url = f"{self.api_base}/search/repositories?q={query}&sort=stars&order=desc&per_page={min(30, max_results)}"

        data = self._api_request(url)
        if data is None:
            return []

        repos: list[GitHubRepo] = []
        for item in data.get("items", [])[:max_results]:
            repo = self._parse_repo(item)
            repo.relevance_score = self._compute_relevance(repo, topic)
            repos.append(repo)
        return repos

    def _fetch_trending(self, max_results: int) -> list[GitHubRepo]:
        """Fetch trending repos from GitHub's trending page."""
        url = "https://api.github.com/search/repositories?q=created:>2026-01-01+pushed:>2026-04-01&sort=stars&order=desc&per_page=25"

        data = self._api_request(url)
        if data is None:
            return []

        repos: list[GitHubRepo] = []
        for item in data.get("items", [])[:max_results]:
            repo = self._parse_repo(item)
            desc = (repo.description or "").lower()
            has_dataset_keywords = any(
                kw in desc for kw in ["dataset", "data", "corpus", "benchmark", "collection"]
            )
            if has_dataset_keywords or any(t in DATASET_TOPICS for t in repo.topics):
                repo.relevance_score = self._compute_relevance(repo, "trending")
                repos.append(repo)
        return repos

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
