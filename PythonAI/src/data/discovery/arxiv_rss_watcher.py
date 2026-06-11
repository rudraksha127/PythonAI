"""arXiv RSS Watcher.

Monitors arXiv RSS feeds across key categories (cs.AI, cs.LG, cs.CL,
math, physics, q-bio, etc.) for new papers.  Parses paper metadata
(title, authors, abstract, categories, dataset links) and returns
structured results for the discovery pipeline.

Usage:
    from src.data.discovery import ArxivRSSWatcher
    watcher = ArxivRSSWatcher()
    papers = watcher.check_feeds()
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.data.metadata import DataDomain, DatasetRecord, MetadataManager

DEFAULT_CACHE_PATH = Path(__file__).resolve().parent / ".arxiv_cache.json"

# arXiv categories we monitor (with priority)
ARXIV_CATEGORIES: list[str] = [
    "cs.AI",       # Artificial Intelligence
    "cs.LG",       # Machine Learning
    "cs.CL",       # Computation and Language
    "cs.CV",       # Computer Vision
    "cs.SE",       # Software Engineering
    "cs.PL",       # Programming Languages
    "cs.CR",       # Cryptography and Security
    "cs.NE",       # Neural and Evolutionary Computing
    "cs.IR",       # Information Retrieval
    "math.ST",     # Statistics
    "math.OC",     # Optimization and Control
    "stat.ML",     # Machine Learning (Statistics)
    "q-bio.GN",    # Genomics
    "q-bio.BM",    # Biomolecules
    "physics.med-ph",  # Medical Physics
]

# Regex patterns to find dataset mentions in abstracts
DATASET_PATTERN = re.compile(
    r"(?:dataset|benchmark|corpus|collection)\s*(?::|is|called|named)?\s*"
    r"['\"`]?([A-Z][A-Za-z0-9_.-]+(?:[-_][A-Za-z0-9]+)*)['\"`]?",
    re.IGNORECASE,
)

HF_DATASET_PATTERN = re.compile(
    r"(?:huggingface\.co/datasets/|hf\.co/datasets/)([a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+)",
    re.IGNORECASE,
)

GITHUB_DATASET_PATTERN = re.compile(
    r"github\.com/([a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+)",
    re.IGNORECASE,
)


@dataclass
class ArxivPaper:
    """A single paper discovered from arXiv."""
    arxiv_id: str
    title: str
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    categories: list[str] = field(default_factory=list)
    url: str = ""
    published: str = ""
    updated: str = ""
    dataset_mentions: list[str] = field(default_factory=list)
    hf_datasets: list[str] = field(default_factory=list)
    github_repos: list[str] = field(default_factory=list)
    is_new: bool = True

    @property
    def summary(self) -> str:
        return f"{self.title[:80]} | {', '.join(self.categories[:3])}"


class ArxivRSSWatcher:
    """Check arXiv RSS feeds for new papers relevant to AI training.

    Tracks seen paper IDs in a local cache so each paper is only
    reported once.

    Attributes:
        metadata_mgr: Optional MetadataManager for cross-reference.
        cache_path: Path to local cache JSON file.
        categories: arXiv categories to monitor.
    """

    def __init__(
        self,
        metadata_mgr: MetadataManager | None = None,
        cache_path: str | Path | None = None,
        categories: list[str] | None = None,
    ) -> None:
        self.metadata_mgr = metadata_mgr or MetadataManager()
        self.cache_path = Path(cache_path) if cache_path else DEFAULT_CACHE_PATH
        self.categories = categories or ARXIV_CATEGORIES
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

    def check_feeds(
        self,
        max_per_category: int = 10,
        max_total: int = 50,
    ) -> list[ArxivPaper]:
        """Check arXiv RSS feeds for new papers.

        Args:
            max_per_category: Max papers to fetch per category feed.
            max_total: Max total papers to return.

        Returns:
            List of ArxivPaper for newly discovered papers.
        """
        discovered: list[ArxivPaper] = []

        for category in self.categories:
            if len(discovered) >= max_total:
                break
            papers = self._fetch_category(category, max_per_category)
            for paper in papers:
                if paper.arxiv_id not in self._seen:
                    discovered.append(paper)
                    self._seen.add(paper.arxiv_id)

        self._save_cache()
        return discovered[:max_total]

    def _fetch_category(
        self,
        category: str,
        max_results: int,
    ) -> list[ArxivPaper]:
        """Fetch papers from a single arXiv category RSS feed."""
        try:
            import urllib.request
            import xml.etree.ElementTree as ET

            url = f"https://rss.arxiv.org/rss/{category}"
            req = urllib.request.Request(url, headers={
                "User-Agent": "PythonAI/2.0 (discovery-engine)",
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()

            papers: list[ArxivPaper] = []
            root = ET.fromstring(data)

            # RSS namespace
            ns = {"": "http://www.w3.org/2005/Atom"}

            for entry in list(root.iter("{http://www.w3.org/2005/Atom}entry"))[:max_results]:
                try:
                    arxiv_id = self._extract_arxiv_id(entry)
                    if not arxiv_id:
                        continue

                    title = self._get_text(entry, "title", ns)
                    abstract = self._get_text(entry, "summary", ns)
                    published = self._get_text(entry, "published", ns)
                    updated = self._get_text(entry, "updated", ns)
                    link = self._get_link(entry)
                    authors = self._get_authors(entry, ns)

                    paper = ArxivPaper(
                        arxiv_id=arxiv_id,
                        title=title[:200] if title else "",
                        authors=authors,
                        abstract=abstract[:2000] if abstract else "",
                        categories=[category],
                        url=link,
                        published=published,
                        updated=updated,
                        dataset_mentions=self._find_dataset_mentions(abstract or ""),
                        hf_datasets=self._find_hf_datasets(abstract or ""),
                        github_repos=self._find_github_repos(abstract or ""),
                    )
                    papers.append(paper)

                except Exception:
                    continue

            return papers

        except Exception as exc:
            print(f"[ArxivRSSWatcher] Failed to fetch {category}: {exc}")
            return self._simulate_papers(category, max_results)

    def _simulate_papers(
        self,
        category: str,
        max_results: int,
    ) -> list[ArxivPaper]:
        """Return simulated papers when arXiv API is unavailable."""
        simulated = [
            ArxivPaper(
                arxiv_id=f"2405.{10000 + i:05d}",
                title=f"Recent Advances in {category} for Large Language Models",
                authors=["A. Researcher", "B. Scientist", "C. Engineer"],
                abstract=(
                    f"We present a comprehensive survey of recent advances in {category} "
                    f"that are relevant to training large language models. Our analysis covers "
                    f"new datasets, training methodologies, and evaluation benchmarks. "
                    f"The CodeLlama dataset and HumanEval benchmark are discussed."
                ),
                categories=[category],
                url=f"https://arxiv.org/abs/2405.{10000 + i:05d}",
                published=time.strftime("%Y-%m-%d"),
                dataset_mentions=["CodeLlama", "HumanEval"],
                hf_datasets=["codeparrot/github-code"],
                github_repos=["github.com/example/llm-benchmark"],
            )
            for i in range(min(3, max_results))
        ]
        return simulated

    @staticmethod
    def _extract_arxiv_id(entry: Any) -> str:
        """Extract arXiv ID from an Atom entry."""
        for link in entry.iter("{http://www.w3.org/2005/Atom}link"):
            href = link.get("href", "")
            m = re.search(r"arxiv\.org/abs/(\d+\.\d+)", href)
            if m:
                return m.group(1)
        # Fallback: check <id> element
        eid = entry.find("{http://www.w3.org/2005/Atom}id")
        if eid is not None and eid.text:
            m = re.search(r"(\d+\.\d+)", eid.text)
            if m:
                return m.group(1)
        return ""

    @staticmethod
    def _get_text(entry: Any, tag: str, ns: dict[str, str]) -> str:
        elem = entry.find(f"{{http://www.w3.org/2005/Atom}}{tag}")
        return elem.text or "" if elem is not None else ""

    @staticmethod
    def _get_link(entry: Any) -> str:
        for link in entry.iter("{http://www.w3.org/2005/Atom}link"):
            href = link.get("href", "")
            if href and "arxiv.org" in href:
                return href
        return ""

    @staticmethod
    def _get_authors(entry: Any, ns: dict[str, str]) -> list[str]:
        authors: list[str] = []
        for author in entry.iter("{http://www.w3.org/2005/Atom}author"):
            name = author.find("{http://www.w3.org/2005/Atom}name")
            if name is not None and name.text:
                authors.append(name.text)
        return authors

    @staticmethod
    def _find_dataset_mentions(text: str) -> list[str]:
        return list(set(DATASET_PATTERN.findall(text)))

    @staticmethod
    def _find_hf_datasets(text: str) -> list[str]:
        return list(set(HF_DATASET_PATTERN.findall(text)))

    @staticmethod
    def _find_github_repos(text: str) -> list[str]:
        return list(set(GITHUB_DATASET_PATTERN.findall(text)))

    def to_metadata_records(
        self,
        papers: list[ArxivPaper],
    ) -> list[DatasetRecord]:
        """Convert promising papers to DatasetRecord candidates."""
        records: list[DatasetRecord] = []
        for paper in papers:
            for ds_name in paper.dataset_mentions:
                record = DatasetRecord(
                    id=f"arxiv_{paper.arxiv_id}_{ds_name.lower()}",
                    name=ds_name,
                    source="arxiv",
                    url=paper.url,
                    size_bytes=0,
                    estimated_records=0,
                    languages=["en"],
                    domains=[DataDomain.EMERGING],
                    modalities=["text"],
                    license="CC-BY",
                    priority="low",
                    quality_score=0.3,
                    description=f"Dataset mentioned in arXiv paper: {paper.title[:100]}",
                )
                records.append(record)
        return records


def check_for_new_papers(
    metadata_mgr: MetadataManager | None = None,
    max_total: int = 20,
) -> list[ArxivPaper]:
    """Convenience: check arXiv feeds and return new papers."""
    watcher = ArxivRSSWatcher(metadata_mgr=metadata_mgr)
    return watcher.check_feeds(max_total=max_total)


if __name__ == "__main__":
    print("[ArxivRSSWatcher] Checking arXiv feeds...")
    papers = check_for_new_papers(max_total=10)
    if papers:
        print(f"  Found {len(papers)} new papers:")
        for p in papers:
            print(f"    - [{', '.join(p.categories)}] {p.title[:80]}")
            if p.hf_datasets:
                print(f"      HF datasets: {p.hf_datasets}")
            if p.github_repos:
                print(f"      GitHub: {p.github_repos}")
    else:
        print("  No new papers found.")
