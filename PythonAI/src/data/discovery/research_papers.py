"""
RESEARCH PAPER KNOWLEDGE HARVESTER
===================================
Comprehensive research paper knowledge base that:

1. Fetches papers from arXiv API (full metadata, categories, citations)
2. Integrates with Semantic Scholar API (citations, recommendations, TLDRs)
3. Integrates with PapersWithCode (links papers to code implementations)
4. Extracts key findings, methodologies, datasets, and benchmarks
5. Builds a structured knowledge index for RAG integration
6. Prioritizes papers by relevance, citations, and recency

Usage:
    from src.data.discovery.research_papers import ResearchPaperKnowledgeBase
    rpk = ResearchPaperKnowledgeBase()
    papers = rpk.collect_papers(topics=["machine learning", "LLM", "Python"], limit=100)
    rpk.index_papers(papers)
"""

from __future__ import annotations

import json
import os
import re
import ssl
import time
import hashlib
import urllib.error
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from collections import defaultdict

import certifi

# SSL context using certifi CA bundle — fixes SSL errors on Windows
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

# ── Paths ───────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent.parent
KNOWLEDGE_DIR = ROOT / "data" / "research_knowledge"
PAPERS_INDEX_FILE = KNOWLEDGE_DIR / "papers_index.json"
PAPERS_CACHE_FILE = KNOWLEDGE_DIR / "papers_cache.json"
FINDINGS_FILE = KNOWLEDGE_DIR / "key_findings.json"
METHODOLOGIES_FILE = KNOWLEDGE_DIR / "methodologies.json"
KNOWLEDGE_CHUNKS_FILE = KNOWLEDGE_DIR / "knowledge_chunks.json"


# ── Data Models ─────────────────────────────────────────────────────


@dataclass
class PaperAuthor:
    """Author of a research paper."""

    name: str
    affiliations: list[str] = field(default_factory=list)
    orcid: str = ""


@dataclass
class PaperReference:
    """A reference/citation between papers."""

    paper_id: str
    title: str
    year: int = 0
    citation_count: int = 0


@dataclass
class PaperMethodology:
    """Methodology extracted from a paper."""

    name: str
    category: str = ""  # "architecture", "training", "dataset", "evaluation", "theory"
    description: str = ""
    key_innovation: str = ""
    performance_gain: str = ""


@dataclass
class PaperKeyFinding:
    """Key finding extracted from a paper."""

    finding: str
    category: str = ""  # "result", "insight", "limitation", "future_work"
    confidence: float = 0.7
    source_sentence: str = ""


@dataclass
class PaperKnowledge:
    """
    Structured knowledge extracted from a research paper.

    This is the core data structure that bridges papers to the RAG system.
    """

    # Identity
    paper_id: str
    title: str
    authors: list[PaperAuthor] = field(default_factory=list)
    abstract: str = ""
    full_text_snippet: str = ""

    # Classification
    categories: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)

    # Sources
    arxiv_id: str = ""
    doi: str = ""
    semantic_scholar_id: str = ""
    paperswithcode_url: str = ""
    pdf_url: str = ""

    # Metadata
    published_date: str = ""
    updated_date: str = ""
    venue: str = ""  # Conference/Journal name
    citation_count: int = 0
    reference_count: int = 0

    # Extracted knowledge
    key_findings: list[PaperKeyFinding] = field(default_factory=list)
    methodologies: list[PaperMethodology] = field(default_factory=list)
    datasets_used: list[str] = field(default_factory=list)
    datasets_introduced: list[str] = field(default_factory=list)
    code_repositories: list[str] = field(default_factory=list)
    benchmark_results: dict[str, float] = field(default_factory=dict)

    # Quality
    relevance_score: float = 0.5  # 0.0 to 1.0
    knowledge_density: float = 0.5  # How much actionable knowledge per page
    is_survey: bool = False
    is_implementation: bool = False

    # Tracking
    ingested_at: str = ""
    last_updated: str = ""

    @property
    def summary(self) -> str:
        return f"[{', '.join(self.categories[:3])}] {self.title[:100]} | citations: {self.citation_count}"

    @property
    def as_chunk_dict(self) -> dict[str, Any]:
        """Convert to a chunk dict compatible with the RAG ingestion system."""
        # Build a rich text representation for embedding
        text_parts = [
            f"Title: {self.title}",
            f"Authors: {', '.join(a.name for a in self.authors[:5])}",
            f"Published: {self.published_date}",
            f"Venue: {self.venue}" if self.venue else "",
            f"Categories: {', '.join(self.categories)}",
            f"Keywords: {', '.join(self.keywords)}",
            f"DOI: {self.doi}" if self.doi else "",
            "",
            "ABSTRACT:",
            self.abstract,
        ]

        if self.key_findings:
            text_parts.append("")
            text_parts.append("KEY FINDINGS:")
            for f in self.key_findings:
                text_parts.append(f"  - [{f.category}] {f.finding}")

        if self.methodologies:
            text_parts.append("")
            text_parts.append("METHODOLOGIES:")
            for m in self.methodologies:
                text_parts.append(f"  - {m.name}: {m.description[:200]}")

        if self.datasets_introduced:
            text_parts.append("")
            text_parts.append(f"DATASETS INTRODUCED: {', '.join(self.datasets_introduced)}")

        if self.datasets_used:
            text_parts.append("")
            text_parts.append(f"DATASETS USED: {', '.join(self.datasets_used)}")

        if self.benchmark_results:
            text_parts.append("")
            text_parts.append("BENCHMARK RESULTS:")
            for k, v in self.benchmark_results.items():
                text_parts.append(f"  {k}: {v}")

        if self.code_repositories:
            text_parts.append("")
            text_parts.append(f"CODE: {', '.join(self.code_repositories)}")

        if self.full_text_snippet:
            text_parts.append("")
            text_parts.append("FULL TEXT SNIPPET:")
            text_parts.append(self.full_text_snippet[:2000])

        chunk_text = "\n".join(text_parts)

        return {
            "id": f"paper_{self.paper_id}",
            "title": self.title[:200],
            "text": chunk_text[:4000],
            "type": "research_paper",
            "category": f"paper_{self.categories[0] if self.categories else 'general'}",
            "version": self.published_date[:4] if self.published_date else "2024",
            "codes": self.code_repositories,
            "paper_id": self.paper_id,
            "citation_count": self.citation_count,
            "relevance_score": self.relevance_score,
            "arxiv_id": self.arxiv_id,
            "doi": self.doi,
            "is_survey": self.is_survey,
        }


# ── PapersWithCode / Code Linking Client ───────────────────────


class PapersWithCodeClient:
    """
    Links papers to code implementations.

    Uses two strategies:
      1. (Attempts) Fetches the paperswithcode-data GitHub archive (static JSON dumps)
      2. Primary: Uses GitHub search API to find repos by paper title / arxiv ID

    Notes:
      - The official PapersWithCode API was discontinued in July 2025.
      - The static archive at paperswithcode-data may be stale or 404.
      - GitHub search is the primary method; archive is a nice-to-have supplement.
      - Set GITHUB_TOKEN env var for 5,000 req/hr instead of 60.
    """

    # Try multiple known archive file paths
    ARCHIVE_CANDIDATES = [
        "https://raw.githubusercontent.com/paperswithcode/paperswithcode-data/master/data/links-between-papers-and-code.json",
        "https://raw.githubusercontent.com/paperswithcode/paperswithcode-data/master/links-between-papers-and-code.json",
        "https://raw.githubusercontent.com/paperswithcode/paperswithcode-data/main/data/links-between-papers-and-code.json",
        "https://raw.githubusercontent.com/paperswithcode/paperswithcode-data/main/links-between-papers-and-code.json",
        "https://paperswithcode.com/api/v1/papers/?items_per_page=1",  # API ping to check if REST API is alive
    ]
    _ARCHIVE_CACHE: dict[str, list[str]] | None = None  # Class-level cache
    _ARCHIVE_CACHE_TIME: float = 0.0
    _ARCHIVE_CACHE_TTL: int = 86400  # 24 hours

    def __init__(self) -> None:
        self._gh_token = os.environ.get("GITHUB_TOKEN", "")

    def link_papers(self, papers: list[PaperKnowledge]) -> int:
        """
        Find code implementations for a list of papers.

        First tries the paperswithcode-data archive, then falls back
        to GitHub search for papers still missing code links.

        Args:
            papers: List of PaperKnowledge objects to enrich.

        Returns:
            Number of papers that received new code links.
        """
        linked = 0

        # Strategy 1: Fetch the paper-to-code mapping from the archive
        archive_links = self._fetch_archive_links()
        if archive_links:
            for paper in papers:
                # Try matching by arXiv ID first, then by title
                matched: list[str] = []
                for key in [paper.arxiv_id, paper.doi, paper.title.lower().strip()]:
                    if not key:
                        continue
                    if key in archive_links:
                        matched = archive_links[key]
                        break
                    # Also try partial title match
                    for archive_key, repos in archive_links.items():
                        if len(key) > 20 and (key in archive_key or archive_key in key):
                            matched = repos
                            break
                    if matched:
                        break

                if matched:
                    new_repos = [r for r in matched if r not in paper.code_repositories]
                    if new_repos:
                        paper.code_repositories.extend(new_repos)
                        paper.paperswithcode_url = matched[0]
                        linked += 1

        # Strategy 2: GitHub search for papers still missing code links
        missing = [p for p in papers if not p.code_repositories]
        if missing:
            gh_linked = self._search_github(missing)
            linked += gh_linked

        return linked

    def _fetch_archive_links(self) -> dict[str, list[str]]:
        """
        Fetch paper-to-code mappings from the paperswithcode-data archive.

        Tries multiple known archive paths (the repo has changed structure
        over time) and caches results class-wide to avoid retrying failed
        URLs on every scan.
        """
        # Check class-level cache first
        if PapersWithCodeClient._ARCHIVE_CACHE is not None:
            cache_age = time.time() - PapersWithCodeClient._ARCHIVE_CACHE_TIME
            if cache_age < PapersWithCodeClient._ARCHIVE_CACHE_TTL:
                return PapersWithCodeClient._ARCHIVE_CACHE

        links: dict[str, list[str]] = {}

        for url in self.ARCHIVE_CANDIDATES:
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "PythonAI/2.0"},
                )
                with urllib.request.urlopen(req, timeout=10, context=_SSL_CONTEXT) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                # Archive files: list of {arxiv_id, repo_url, title, ...}
                if isinstance(data, list):
                    for entry in data:
                        arxiv_id = (entry.get("arxiv_id", "") or "").strip()
                        repo_url = (entry.get("repo_url", "") or entry.get("code_url", "") or "").strip()
                        title = (entry.get("title", "") or "").strip().lower()
                        if arxiv_id and repo_url:
                            links.setdefault(arxiv_id, []).append(repo_url)
                        if title and repo_url:
                            links.setdefault(title, []).append(repo_url)

                    print(f"  [PwC] Loaded {len(data)} entries from archive")
                    break  # Success — stop trying more URLs

                # API response: {count, next, previous, results}
                elif isinstance(data, dict) and "count" in data:
                    print(f"  [PwC] REST API responded (not archive) — not used")
                    continue

            except urllib.error.HTTPError as exc:
                if exc.code in (404, 410):
                    continue  # Try next candidate silently
                elif exc.code == 403:
                    print(f"  [PwC] Rate limited (403) on {url[:70]}...")
                    continue
                else:
                    print(f"  [PwC] HTTP {exc.code} on {url[:70]}...")
                    continue
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                continue  # Try next candidate
            except Exception as exc:
                continue  # Try next candidate

        # Cache the result (even empty, to avoid retrying every scan)
        PapersWithCodeClient._ARCHIVE_CACHE = links
        PapersWithCodeClient._ARCHIVE_CACHE_TIME = time.time()

        if links:
            print(f"  [PwC] {len(links)} unique paper-code mappings loaded from archive")
        else:
            print(f"  [PwC] No archive available — using GitHub search as primary method")

        return links

    def _search_github(self, papers: list[PaperKnowledge]) -> int:
        """
        Search GitHub for code repositories related to papers.

        Uses the GitHub search API to find repos whose name or
        description matches the paper title or arxiv ID.

        Tracks papers with no results to avoid re-querying.
        """
        linked = 0
        rate_limit_warned = False

        for paper in papers:
            # Skip papers already searched with zero results
            if getattr(paper, '_gh_searched_empty', False):
                continue

            # Build search queries from paper metadata
            search_terms = []
            if paper.arxiv_id:
                search_terms.append(paper.arxiv_id)
            # Use the first few meaningful words from the title
            title_words = [w for w in paper.title.split() if len(w) > 3 and w.lower() not in {"with", "from", "that", "this", "what", "were", "been", "have", "their"}]
            search_terms.extend(title_words[:4])

            query = " ".join(search_terms[:5])
            if not query:
                continue

            try:
                params = urllib.parse.urlencode({
                    "q": query,
                    "sort": "stars",
                    "order": "desc",
                    "per_page": 3,
                })
                url = f"https://api.github.com/search/repositories?{params}"

                headers: dict[str, str] = {
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "PythonAI/2.0",
                }
                if self._gh_token:
                    headers["Authorization"] = f"Bearer {self._gh_token}"

                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=10, context=_SSL_CONTEXT) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                repos = data.get("items", [])
                if not repos:
                    # Mark as empty-searched to avoid re-querying
                    paper._gh_searched_empty = True
                    continue

                for repo in repos[:3]:
                    repo_url = repo.get("html_url", "")
                    description = (repo.get("description", "") or "").lower()
                    full_name = repo.get("full_name", "")

                    # Verify relevance: repo should match paper topic
                    if repo_url and repo_url not in paper.code_repositories:
                        # Only add if relevant (title word overlap or arxiv ID mention)
                        title_overlap = any(
                            w.lower() in (description + " " + full_name).lower()
                            for w in title_words[:3]
                        )
                        if title_overlap or any(t in (description + " " + full_name).lower() for t in search_terms[:2]):
                            paper.code_repositories.append(repo_url)
                            if not paper.paperswithcode_url:
                                paper.paperswithcode_url = repo_url
                            linked += 1

            except urllib.error.HTTPError as exc:
                if exc.code in (403, 429) and not rate_limit_warned:
                    print(f"  [PwC] GitHub API rate limit hit (HTTP {exc.code}) — stopping GitHub search")
                    print(f"  [PwC] Set GITHUB_TOKEN env var for 5,000 req/hr")
                    rate_limit_warned = True
                    break  # Stop making more requests
                continue
            except Exception:
                continue

            # Be gentle with GitHub API rate limits
            time.sleep(0.3)

        return linked


# ── API Wrappers ────────────────────────────────────────────────────


class ArxivAPIClient:
    """Client for the arXiv API to fetch paper metadata."""

    BASE_URL = "http://export.arxiv.org/api/query"

    # Major AI/ML categories to monitor
    # Expanded Oct 2026: added cs.RO (robotics), cs.MA (multi-agent), cs.GT (game theory)
    TARGET_CATEGORIES = [
        "cs.AI", "cs.LG", "cs.CL", "cs.CV", "cs.SE",
        "cs.PL", "cs.NE", "cs.IR", "cs.CR",
        "cs.RO", "cs.MA", "cs.GT",
        "stat.ML", "math.OC", "math.ST",
    ]

    # Topics to search within categories
    KEYWORDS = [
        "large language model", "LLM", "transformer", "attention",
        "reinforcement learning", "deep learning", "neural network",
        "dataset", "benchmark", "training", "fine-tuning",
        "Python", "code generation", "program synthesis",
        "RAG", "retrieval augmented", "knowledge graph",
        "reasoning", "chain of thought", "agent",
        "optimization", "distributed training", "quantization",
        "embedding", "representation learning", "self-supervised",
    ]

    def __init__(self, cache_ttl_hours: int = 24):
        self.cache_ttl = cache_ttl_hours * 3600
        self._cache: dict[str, list[dict[str, Any]]] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        if PAPERS_CACHE_FILE.exists():
            try:
                data = json.loads(PAPERS_CACHE_FILE.read_text(encoding="utf-8"))
                self._cache = data.get("arxiv_cache", {})
            except (json.JSONDecodeError, KeyError):
                self._cache = {}

    def _save_cache(self) -> None:
        KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        PAPERS_CACHE_FILE.write_text(
            json.dumps({"arxiv_cache": self._cache}, indent=2),
            encoding="utf-8",
        )

    def _is_cache_valid(self, key: str) -> bool:
        if key not in self._cache:
            return False
        entry = self._cache[key]
        timestamp = entry.get("_timestamp", 0)
        return time.time() - timestamp < self.cache_ttl

    def search(
        self,
        query: str,
        max_results: int = 50,
        sort_by: str = "relevance",  # "relevance", "lastUpdatedDate", "submittedDate"
    ) -> list[dict[str, Any]]:
        """Search arXiv API for papers matching a query."""
        cache_key = f"search_{query}_{max_results}_{sort_by}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key].get("results", [])

        encoded_query = urllib.parse.quote(f"all:{query}")
        url = (
            f"{self.BASE_URL}?search_query={encoded_query}"
            f"&max_results={max_results}&sortBy={sort_by}"
            f"&sortOrder=descending"
        )

        papers = self._fetch_papers(url)
        self._cache[cache_key] = {"results": papers, "_timestamp": time.time()}
        self._save_cache()
        return papers

    def search_by_categories(
        self,
        categories: list[str] | None = None,
        max_per_category: int = 20,
        max_total: int = 100,
    ) -> list[dict[str, Any]]:
        """Search recent papers across multiple arXiv categories."""
        cats = categories or self.TARGET_CATEGORIES
        all_papers: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for category in cats:
            if len(all_papers) >= max_total:
                break
            papers = self._fetch_category(category, max_per_category)
            for paper in papers:
                paper_id = paper.get("arxiv_id", "")
                if paper_id not in seen_ids:
                    seen_ids.add(paper_id)
                    all_papers.append(paper)

        return all_papers[:max_total]

    def search_by_keywords(
        self,
        keywords: list[str] | None = None,
        max_per_keyword: int = 20,
        max_total: int = 200,
    ) -> list[dict[str, Any]]:
        """Search for papers matching specific keywords."""
        kw = keywords or self.KEYWORDS
        all_papers: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for keyword in kw[:20]:  # Limit to first 20 keywords
            if len(all_papers) >= max_total:
                break
            try:
                papers = self.search(keyword, max_results=max_per_keyword)
                for paper in papers:
                    paper_id = paper.get("arxiv_id", "")
                    if paper_id not in seen_ids:
                        seen_ids.add(paper_id)
                        all_papers.append(paper)
            except Exception:
                continue

        return all_papers[:max_total]

    def fetch_by_ids(self, arxiv_ids: list[str]) -> list[dict[str, Any]]:
        """Fetch specific papers by their arXiv IDs."""
        id_list = ",".join(arxiv_ids)
        url = f"{self.BASE_URL}?id_list={id_list}&max_results={len(arxiv_ids)}"
        return self._fetch_papers(url)

    def _fetch_category(self, category: str, max_results: int) -> list[dict[str, Any]]:
        """Fetch papers from a specific arXiv category."""
        cache_key = f"category_{category}_{max_results}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key].get("results", [])

        url = f"{self.BASE_URL}?search_query=cat:{category}&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"
        papers = self._fetch_papers(url)
        self._cache[cache_key] = {"results": papers, "_timestamp": time.time()}
        self._save_cache()
        return papers

    def _fetch_papers(self, url: str, max_retries: int = 3) -> list[dict[str, Any]]:
        """Fetch and parse papers from arXiv API.

        Handles rate-limiting (429) with exponential backoff retry and
        adds a gentle 1s delay between calls to stay within arXiv API limits.

        Args:
            url: The arXiv API URL to fetch.
            max_retries: Number of retries on 429 rate-limit errors.
        """
        papers: list[dict[str, Any]] = []

        for attempt in range(max_retries + 1):
            try:
                # Respect arXiv rate limits — light pause between calls
                time.sleep(1.0)

                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "PythonAI/2.0 (research-knowledge-base)"},
                )
                with urllib.request.urlopen(req, timeout=30, context=_SSL_CONTEXT) as resp:
                    xml_data = resp.read().decode("utf-8")

                root = ET.fromstring(xml_data)
                ns = {"a": "http://www.w3.org/2005/Atom"}

                for entry in root.findall("a:entry", ns):
                    try:
                        paper = self._parse_entry(entry)
                        if paper:
                            papers.append(paper)
                    except Exception:
                        continue

                # Success — break out of retry loop
                break

            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < max_retries:
                    backoff = 5 * (2 ** attempt)  # 5s, 10s, 20s
                    print(f"[ArxivAPI] Rate limited (429). Retrying in {backoff}s (attempt {attempt + 1}/{max_retries})...")
                    time.sleep(backoff)
                else:
                    print(f"[ArxivAPI] HTTP error fetching {url[:80]}: {exc}")
                    break
            except Exception as exc:
                print(f"[ArxivAPI] Error fetching {url[:80]}: {exc}")
                break

        return papers

    def _parse_entry(self, entry: Any) -> dict[str, Any] | None:
        """Parse an Atom entry into a paper dict."""
        ns = {"a": "http://www.w3.org/2005/Atom"}

        # arXiv ID
        id_elem = entry.find("a:id", ns)
        if id_elem is None or not id_elem.text:
            return None
        arxiv_id_match = re.search(r"(\d+\.\d+)", id_elem.text)
        if not arxiv_id_match:
            return None
        arxiv_id = arxiv_id_match.group(1)

        # Title
        title_elem = entry.find("a:title", ns)
        title = title_elem.text.strip().replace("\n", " ") if title_elem is not None and title_elem.text else ""

        # Abstract
        summary_elem = entry.find("a:summary", ns)
        abstract = summary_elem.text.strip() if summary_elem is not None and summary_elem.text else ""

        # Published / Updated
        published = entry.find("a:published", ns)
        updated = entry.find("a:updated", ns)

        # Authors
        authors: list[str] = []
        for author in entry.findall("a:author", ns):
            name_elem = author.find("a:name", ns)
            if name_elem is not None and name_elem.text:
                authors.append(name_elem.text)

        # Categories
        categories: list[str] = []
        for cat in entry.findall("a:category", ns):
            term = cat.get("term", "")
            if term:
                categories.append(term)

        # Links
        pdf_url = ""
        doi = ""
        for link in entry.findall("a:link", ns):
            href = link.get("href", "")
            title_attr = link.get("title", "")
            if title_attr == "pdf":
                pdf_url = href
            elif "doi.org" in href:
                doi = href.replace("https://doi.org/", "")

        return {
            "arxiv_id": arxiv_id,
            "title": title[:300],
            "abstract": abstract[:3000],
            "authors": authors[:20],
            "categories": categories[:10],
            "published": published.text if published is not None else "",
            "updated": updated.text if updated is not None else "",
            "pdf_url": pdf_url or f"https://arxiv.org/pdf/{arxiv_id}",
            "doi": doi,
            "source": "arxiv",
        }

    def get_recent_papers(self, days: int = 7, max_results: int = 200) -> list[dict[str, Any]]:
        """Get papers published in the last N days across all target categories."""
        return self.search_by_categories(
            categories=self.TARGET_CATEGORIES,
            max_per_category=30,
            max_total=max_results,
        )


class SemanticScholarClient:
    """Client for Semantic Scholar API to get citation data and recommendations."""

    BASE_URL = "https://api.semanticscholar.org/graph/v1"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key

    def get_paper_details(
        self,
        arxiv_id: str = "",
        doi: str = "",
        fields: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Get detailed paper information from Semantic Scholar."""
        if not fields:
            fields = [
                "title", "abstract", "authors", "year", "citationCount",
                "referenceCount", "venue", "externalIds", "tldr",
                "publicationDate", "fieldsOfStudy",
            ]

        paper_id = f"ArXiv:{arxiv_id}" if arxiv_id else f"DOI:{doi}"
        if not paper_id:
            return None

        url = f"{self.BASE_URL}/paper/{paper_id}?fields={','.join(fields)}"

        try:
            req = urllib.request.Request(url)
            if self.api_key:
                req.add_header("x-api-key", self.api_key)
            req.add_header("User-Agent", "PythonAI/2.0")

            with urllib.request.urlopen(req, timeout=15, context=_SSL_CONTEXT) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            # Parse TLDR
            tldr_text = ""
            if data.get("tldr"):
                tldr_text = data["tldr"].get("text", "")

            return {
                "semantic_scholar_id": data.get("paperId", ""),
                "title": data.get("title", ""),
                "abstract": data.get("abstract", ""),
                "year": data.get("year", 0),
                "citation_count": data.get("citationCount", 0),
                "reference_count": data.get("referenceCount", 0),
                "venue": data.get("venue", ""),
                "tldr": tldr_text,
                "publication_date": data.get("publicationDate", ""),
                "fields_of_study": data.get("fieldsOfStudy", []),
                "external_ids": data.get("externalIds", {}),
                "authors": [a.get("name", "") for a in data.get("authors", [])],
            }
        except Exception as exc:
            return None

    def search(
        self,
        query: str,
        limit: int = 20,
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search for papers on Semantic Scholar."""
        if not fields:
            fields = [
                "title", "abstract", "year", "citationCount",
                "venue", "externalIds", "tldr", "publicationDate",
            ]

        url = f"{self.BASE_URL}/paper/search?query={urllib.parse.quote(query)}&limit={limit}&fields={','.join(fields)}"

        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "PythonAI/2.0")

            with urllib.request.urlopen(req, timeout=15, context=_SSL_CONTEXT) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            results: list[dict[str, Any]] = []
            for paper in data.get("data", []):
                tldr_text = ""
                if paper.get("tldr"):
                    tldr_text = paper["tldr"].get("text", "")

                results.append({
                    "semantic_scholar_id": paper.get("paperId", ""),
                    "title": paper.get("title", ""),
                    "abstract": paper.get("abstract", ""),
                    "year": paper.get("year", 0),
                    "citation_count": paper.get("citationCount", 0),
                    "venue": paper.get("venue", ""),
                    "tldr": tldr_text,
                    "publication_date": paper.get("publicationDate", ""),
                    "external_ids": paper.get("externalIds", {}),
                })

            return results
        except Exception as exc:
            return []

    def get_recommendations(
        self,
        paper_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get paper recommendations from Semantic Scholar."""
        url = f"{self.BASE_URL}/paper/{paper_id}/recommendations?limit={limit}"

        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "PythonAI/2.0")

            with urllib.request.urlopen(req, timeout=15, context=_SSL_CONTEXT) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            results: list[dict[str, Any]] = []
            for paper in data.get("data", []):
                results.append({
                    "semantic_scholar_id": paper.get("paperId", ""),
                    "title": paper.get("title", ""),
                    "year": paper.get("year", 0),
                    "citation_count": paper.get("citationCount", 0),
                    "venue": paper.get("venue", ""),
                })

            return results
        except Exception as exc:
            return []


# ── Knowledge Extraction ────────────────────────────────────────────


class PaperKnowledgeExtractor:
    """Extract structured knowledge from paper metadata."""

    # Patterns for identifying key information in abstracts
    FINDING_PATTERNS = [
        (r"(?:we|our|this paper)\s+(?:show|demonstrate|find|achieve|outperform|improve)", "result"),
        (r"(?:achieves?|obtains?|reaches?|attains?)\s+(?:state-of-the-art|SOTA|new.*best)", "result"),
        (r"(?:however|limitation|drawback|challenge|issue|problem)\s+(?:is|remains|persists)", "limitation"),
        (r"(?:future work|future direction|open problem|next steps?)", "future_work"),
        (r"(?:key insight|key idea|main insight|crucial|importantly)", "insight"),
        (r"(?:we introduce|we present|we propose|we develop|novel)", "innovation"),
    ]

    DATASET_PATTERNS = [
        # Pattern 1: "dataset/benchmark called X" (name after keyword)
        r"(?:dataset|benchmark|corpus|collection)\s+(?:called|named|:)\s+([A-Z][A-Za-z0-9_-]+)",
        # Pattern 2: "introduce/present a new dataset/benchmark X" (name after keyword with intro verb)
        r"(?:introduce|release|present|propose)\s+(?:a\s+)?(?:new\s+)?(?:large-scale\s+)?(?:dataset|benchmark|corpus)\s+(?:called\s+)?(?:named\s+)?:?\s*([A-Z][A-Za-z0-9_-]+)",
        # Pattern 3: "XBench, XSet, XEval" style names followed by dataset/benchmark
        r"([A-Z][A-Za-z0-9_-]*(?:Bench|Set|Data|Eval|QA))[,.]?\s+(?:dataset|benchmark|corpus)",
        # Pattern 4: X, a new/large-scale dataset/benchmark (name BEFORE keyword)
        r"([A-Z][A-Za-z][A-Za-z0-9_-]{2,})[,.]?\s+(?:a\s+)?(?:new\s+)?(?:large-scale\s+)?(?:dataset|benchmark|corpus|collection)",
    ]

    METHODOLOGY_PATTERNS = [
        (r"(?:architecture|framework|model|system)\s+(?:called|named|proposed|based)", "architecture"),
        (r"(?:train|training|fine-tune|fine-tuning|optimize|optimization)", "training"),
        (r"(?:evaluate|evaluation|benchmark|measure|assess)", "evaluation"),
        (r"(?:dataset|data|corpus|collection)", "dataset"),
    ]

    BENCHMARK_PATTERNS = [
        r"([A-Z][A-Za-z0-9_-]+(?:Bench|Score|Accuracy|F1|BLEU|ROUGE|Perplexity))\s*(?::|is|reaches?|achieves?)\s*([\d.]+)",
    ]

    def extract_findings(self, abstract: str) -> list[PaperKeyFinding]:
        """Extract key findings from paper abstract."""
        findings: list[PaperKeyFinding] = []

        for pattern, category in self.FINDING_PATTERNS:
            matches = re.finditer(pattern, abstract, re.IGNORECASE)
            for match in matches:
                # Extract the surrounding sentence
                start = max(0, match.start() - 50)
                end = min(len(abstract), match.end() + 150)
                sentence = abstract[start:end].strip()
                # Clean up
                sentence = re.sub(r"\s+", " ", sentence)

                findings.append(PaperKeyFinding(
                    finding=sentence[:200],
                    category=category,
                    confidence=0.6,
                    source_sentence=sentence[:300],
                ))

        return findings[:10]

    def extract_datasets(self, text: str) -> tuple[list[str], list[str]]:
        """Extract dataset mentions from text."""
        introduced: list[str] = []
        used: list[str] = []

        for pattern in self.DATASET_PATTERNS:
            matches = re.findall(pattern, text)
            for m in matches:
                if m not in introduced and m not in used:
                    # Check if "introduce" or "release" is nearby
                    pos = text.find(m)
                    context_start = max(0, pos - 100)
                    context = text[context_start:pos + len(m)]
                    if re.search(r"(introduce|release|present|new|propose)", context, re.IGNORECASE):
                        if m not in introduced:
                            introduced.append(m)
                    else:
                        if m not in used:
                            used.append(m)

        return introduced, used

    def extract_methodologies(self, abstract: str) -> list[PaperMethodology]:
        """Extract methodology descriptions from abstract."""
        methodologies: list[PaperMethodology] = []
        seen: set[str] = set()

        for pattern, category in self.METHODOLOGY_PATTERNS:
            matches = re.finditer(pattern, abstract, re.IGNORECASE)
            for match in matches:
                # Extract surrounding context
                start = max(0, match.start() - 30)
                end = min(len(abstract), match.end() + 100)
                context = abstract[start:end].strip()
                context = re.sub(r"\s+", " ", context)

                # Extract a name if present
                name_match = re.search(r"(?:called|named|:)\s*([A-Z][A-Za-z0-9_-]+)", context)
                name = name_match.group(1) if name_match else context[:50]

                if name not in seen:
                    seen.add(name)
                    methodologies.append(PaperMethodology(
                        name=name[:60],
                        category=category,
                        description=context[:200],
                    ))

        return methodologies[:5]

    def extract_keywords(self, title: str, abstract: str, categories: list[str]) -> list[str]:
        """Extract relevant keywords from paper metadata."""
        text = f"{title} {abstract}".lower()
        keywords: list[str] = []

        # Known AI/ML terms to look for
        term_patterns = [
            r"\b(transformer|attention|llm|gpt|bert|t5|bart|roberta)\b",
            r"\b(reinforcement learning|deep learning|machine learning|few-shot|zero-shot)\b",
            r"\b(reasoning|planning|inference|generation|summarization|translation)\b",
            r"\b(Python|code generation|program synthesis|software engineering)\b",
            r"\b(dataset|benchmark|evaluation|fine-tuning|pre-training|transfer learning)\b",
            r"\b(knowledge graph|RAG|retrieval|embedding|vector database)\b",
            r"\b(optimization|distributed|parallel|scalable|efficient|quantization)\b",
        ]

        for pattern in term_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            keywords.extend(m.upper() if len(m) <= 5 else m.lower() for m in matches)

        return list(set(keywords))[:20]

    def extract_code_repos(self, text: str) -> list[str]:
        """Extract GitHub repository URLs from text."""
        pattern = r"github\.com/([a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+)"
        matches = re.findall(pattern, text)
        return [f"https://github.com/{m}" for m in set(matches)]


# ── Research Paper Knowledge Base ───────────────────────────────────


class ResearchPaperKnowledgeBase:
    """
    Comprehensive research paper knowledge base.

    Collects papers from arXiv, enriches with Semantic Scholar data,
    extracts structured knowledge, and indexes everything for RAG.
    """

    def __init__(
        self,
        data_dir: str | Path | None = None,
        arxiv_client: ArxivAPIClient | None = None,
        semantic_client: SemanticScholarClient | None = None,
        pwc_client: PapersWithCodeClient | None = None,
    ):
        self.data_dir = Path(data_dir) if data_dir else KNOWLEDGE_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.arxiv = arxiv_client or ArxivAPIClient()
        self.semantic = semantic_client or SemanticScholarClient()
        self.pwc = pwc_client or PapersWithCodeClient()
        self.extractor = PaperKnowledgeExtractor()

        # In-memory index
        self._papers: dict[str, PaperKnowledge] = {}
        self._load_index()

    # ── Persistence ───────────────────────────────────────────

    def _load_index(self) -> None:
        """Load previously collected papers from disk."""
        if PAPERS_INDEX_FILE.exists():
            try:
                data = json.loads(PAPERS_INDEX_FILE.read_text(encoding="utf-8"))
                for paper_data in data.get("papers", []):
                    paper = self._dict_to_paper(paper_data)
                    self._papers[paper.paper_id] = paper
            except (json.JSONDecodeError, KeyError):
                pass

    def _save_index(self) -> None:
        """Save paper index to disk."""
        papers_data = [asdict(p) for p in self._papers.values()]
        PAPERS_INDEX_FILE.write_text(
            json.dumps({"papers": papers_data, "count": len(papers_data)}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def get_all_papers(self) -> list[PaperKnowledge]:
        """Get all collected papers. Public accessor for KnowledgeIntelligence."""
        return list(self._papers.values())

    def _dict_to_paper(self, d: dict[str, Any]) -> PaperKnowledge:
        """Convert a dict back to PaperKnowledge."""
        authors = [PaperAuthor(**a) if isinstance(a, dict) else PaperAuthor(name=str(a)) for a in d.get("authors", [])]
        findings = [PaperKeyFinding(**f) for f in d.get("key_findings", [])]
        methodologies = [PaperMethodology(**m) for m in d.get("methodologies", [])]

        return PaperKnowledge(
            paper_id=d.get("paper_id", ""),
            title=d.get("title", ""),
            authors=authors,
            abstract=d.get("abstract", ""),
            full_text_snippet=d.get("full_text_snippet", ""),
            categories=d.get("categories", []),
            keywords=d.get("keywords", []),
            domains=d.get("domains", []),
            arxiv_id=d.get("arxiv_id", ""),
            doi=d.get("doi", ""),
            semantic_scholar_id=d.get("semantic_scholar_id", ""),
            paperswithcode_url=d.get("paperswithcode_url", ""),
            pdf_url=d.get("pdf_url", ""),
            published_date=d.get("published_date", ""),
            updated_date=d.get("updated_date", ""),
            venue=d.get("venue", ""),
            citation_count=d.get("citation_count", 0),
            reference_count=d.get("reference_count", 0),
            key_findings=findings,
            methodologies=methodologies,
            datasets_used=d.get("datasets_used", []),
            datasets_introduced=d.get("datasets_introduced", []),
            code_repositories=d.get("code_repositories", []),
            benchmark_results=d.get("benchmark_results", {}),
            relevance_score=d.get("relevance_score", 0.5),
            knowledge_density=d.get("knowledge_density", 0.5),
            is_survey=d.get("is_survey", False),
            is_implementation=d.get("is_implementation", False),
            ingested_at=d.get("ingested_at", ""),
            last_updated=d.get("last_updated", ""),
        )

    # ── Collection ────────────────────────────────────────────

    def collect_papers(
        self,
        topics: list[str] | None = None,
        limit: int = 100,
        include_recent: bool = True,
        use_semantic_scholar: bool = True,
    ) -> list[PaperKnowledge]:
        """
        Main collection method: gathers papers from all sources.

        Args:
            topics: Specific topics to search for (e.g., ["LLM", "Python", "RAG"]).
            limit: Maximum number of papers to collect.
            include_recent: Whether to include recent papers from all categories.
            use_semantic_scholar: Whether to enrich with Semantic Scholar data.

        Returns:
            List of PaperKnowledge objects.
        """
        print(f"\n{'='*60}")
        print(f"[RESEARCH PAPER KNOWLEDGE BASE]")
        print(f"{'='*60}")
        print(f"Collecting papers (limit: {limit})...")

        # Step 1: Get papers from arXiv
        raw_papers: list[dict[str, Any]] = []

        if include_recent:
            print("\n[1/3] Fetching recent papers from arXiv categories...")
            recent = self.arxiv.search_by_categories(max_total=limit // 2)
            raw_papers.extend(recent)
            print(f"  -> {len(recent)} recent papers found")

        if topics:
            print(f"\n[2/3] Searching arXiv for topics: {topics[:5]}...")
            for topic in topics[:10]:
                topic_papers = self.arxiv.search(topic, max_results=20)
                raw_papers.extend(topic_papers)
            print(f"  -> Topic search returned {len(raw_papers)} papers total")

        # Step 2: Convert to PaperKnowledge
        print(f"\n[3/3] Processing {len(raw_papers)} papers...")
        new_count = 0
        for raw in raw_papers:
            paper = self._raw_to_paper(raw)

            # Enrich with Semantic Scholar
            if use_semantic_scholar and raw.get("arxiv_id"):
                enriched = self.semantic.get_paper_details(arxiv_id=raw["arxiv_id"])
                if enriched:
                    self._apply_enrichment(paper, enriched)

            # Extract knowledge
            self._extract_paper_knowledge(paper)

            # Deduplicate by paper_id
            if paper.paper_id not in self._papers:
                self._papers[paper.paper_id] = paper
                new_count += 1

        # Link papers to code implementations via PapersWithCode + GitHub search
        print("\n  Linking papers to code implementations...")
        try:
            linked = self.pwc.link_papers(list(self._papers.values()))
            print(f"  -> {linked} papers linked to code repos")
        except Exception as e:
            print(f"  -> Code linking skipped: {e}")

        self._save_index()
        print(f"\n[OK] Collection complete: {new_count} new papers (total: {len(self._papers)})")
        return list(self._papers.values())

    def _raw_to_paper(self, raw: dict[str, Any]) -> PaperKnowledge:
        """Convert raw API data to PaperKnowledge."""
        arxiv_id = raw.get("arxiv_id", "")
        paper_id = arxiv_id or hashlib.md5(raw.get("title", "").encode()).hexdigest()[:16]
        now = datetime.now(timezone.utc).isoformat()

        return PaperKnowledge(
            paper_id=paper_id,
            title=raw.get("title", "Untitled"),
            authors=[PaperAuthor(name=a) for a in raw.get("authors", [])],
            abstract=raw.get("abstract", ""),
            categories=raw.get("categories", []),
            arxiv_id=arxiv_id,
            doi=raw.get("doi", ""),
            pdf_url=raw.get("pdf_url", ""),
            published_date=raw.get("published", "")[:10],
            updated_date=raw.get("updated", "")[:10],
            ingested_at=now,
            last_updated=now,
        )

    def _apply_enrichment(self, paper: PaperKnowledge, enriched: dict[str, Any]) -> None:
        """Apply Semantic Scholar enrichment data to a paper."""
        if enriched.get("citation_count", 0) > paper.citation_count:
            paper.citation_count = enriched["citation_count"]
        if enriched.get("reference_count", 0) > paper.reference_count:
            paper.reference_count = enriched["reference_count"]
        if enriched.get("venue"):
            paper.venue = enriched["venue"]
        if enriched.get("semantic_scholar_id"):
            paper.semantic_scholar_id = enriched["semantic_scholar_id"]
        if enriched.get("tldr"):
            paper.full_text_snippet = enriched["tldr"]
        if enriched.get("fields_of_study"):
            paper.domains = enriched["fields_of_study"]

    def _extract_paper_knowledge(self, paper: PaperKnowledge) -> None:
        """Extract structured knowledge from a paper."""
        text = f"{paper.title} {paper.abstract} {paper.full_text_snippet}"

        # Key findings
        findings = self.extractor.extract_findings(text)
        if findings:
            paper.key_findings = findings

        # Datasets
        introduced, used = self.extractor.extract_datasets(text)
        paper.datasets_introduced = introduced
        paper.datasets_used = used

        # Methodologies
        methodologies = self.extractor.extract_methodologies(text)
        if methodologies:
            paper.methodologies = methodologies

        # Keywords
        paper.keywords = self.extractor.extract_keywords(paper.title, paper.abstract, paper.categories)

        # Code repos
        paper.code_repositories = self.extractor.extract_code_repos(text)

        # Compute relevance score based on citation count, recency, category
        paper.relevance_score = self._compute_relevance(paper)

        # Survey detection
        survey_keywords = ["survey", "review", "overview", "taxonomy", "comprehensive"]
        paper.is_survey = any(kw in paper.title.lower() for kw in survey_keywords)

    def _compute_relevance(self, paper: PaperKnowledge) -> float:
        """Compute a relevance score for a paper."""
        score = 0.5  # Base score

        # Citation bonus (up to +0.3)
        score += min(0.3, paper.citation_count / 1000)

        # Recency bonus (up to +0.2)
        if paper.published_date:
            try:
                pub_year = int(paper.published_date[:4])
                current_year = datetime.now().year
                years_old = current_year - pub_year
                score += max(0, 0.2 - years_old * 0.05)
            except (ValueError, IndexError):
                pass

        # Survey bonus (+0.1)
        if paper.is_survey:
            score += 0.1

        # Implementation bonus (+0.05)
        if paper.code_repositories:
            score += 0.05

        return min(1.0, max(0.0, score))

    # ── Indexing ──────────────────────────────────────────────

    def generate_knowledge_chunks(self) -> list[dict[str, Any]]:
        """
        Generate RAG-compatible knowledge chunks from all collected papers.

        Returns:
            List of chunk dicts compatible with the ingestion pipeline.
        """
        chunks: list[dict[str, Any]] = []

        for paper in self._papers.values():
            if paper.relevance_score < 0.3:
                continue  # Skip low-relevance papers

            chunk = paper.as_chunk_dict
            chunks.append(chunk)

            # Also create individual finding chunks for higher granularity
            for i, finding in enumerate(paper.key_findings[:5]):
                finding_chunk = {
                    "id": f"finding_{paper.paper_id}_{i}",
                    "title": f"Finding: {finding.finding[:80]}",
                    "text": (
                        f"Paper: {paper.title}\n"
                        f"Finding ({finding.category}): {finding.finding}\n"
                        f"Confidence: {finding.confidence}\n"
                        f"arXiv: {paper.arxiv_id}"
                    ),
                    "type": "research_finding",
                    "category": f"finding_{finding.category}",
                    "version": paper.published_date[:4] if paper.published_date else "",
                    "paper_id": paper.paper_id,
                }
                chunks.append(finding_chunk)

        return chunks

    def save_knowledge_chunks(self) -> Path:
        """Save knowledge chunks to disk for RAG ingestion."""
        chunks = self.generate_knowledge_chunks()
        KNOWLEDGE_CHUNKS_FILE.write_text(
            json.dumps(chunks, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\n[SAVED] {len(chunks)} knowledge chunks to {KNOWLEDGE_CHUNKS_FILE}")
        return KNOWLEDGE_CHUNKS_FILE

    # ── Query & Discovery ─────────────────────────────────────

    def search_papers(
        self,
        query: str,
        min_relevance: float = 0.3,
        max_results: int = 20,
    ) -> list[PaperKnowledge]:
        """Search collected papers by keyword matching."""
        query_lower = query.lower()
        scored: list[tuple[PaperKnowledge, float]] = []

        for paper in self._papers.values():
            if paper.relevance_score < min_relevance:
                continue

            score = 0.0
            # Title match (high weight)
            if query_lower in paper.title.lower():
                score += 0.5
            # Keyword match
            if any(query_lower in kw.lower() for kw in paper.keywords):
                score += 0.3
            # Abstract match
            if query_lower in paper.abstract.lower():
                score += 0.2
            # Finding match
            for finding in paper.key_findings:
                if query_lower in finding.finding.lower():
                    score += 0.25

            if score > 0:
                # Boost by relevance
                score *= paper.relevance_score
                scored.append((paper, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [p for p, s in scored[:max_results]]

    def get_top_papers(self, n: int = 20) -> list[PaperKnowledge]:
        """Get the top N papers by relevance score."""
        sorted_papers = sorted(
            self._papers.values(),
            key=lambda p: (p.relevance_score, p.citation_count),
            reverse=True,
        )
        return sorted_papers[:n]

    def get_statistics(self) -> dict[str, Any]:
        """Get statistics about the paper knowledge base."""
        if not self._papers:
            return {"total_papers": 0}

        categories: dict[str, int] = defaultdict(int)
        total_citations = sum(p.citation_count for p in self._papers.values())
        total_findings = sum(len(p.key_findings) for p in self._papers.values())
        total_datasets = sum(len(p.datasets_introduced) for p in self._papers.values())

        for paper in self._papers.values():
            for cat in paper.categories:
                categories[cat] += 1

        top_categories = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "total_papers": len(self._papers),
            "total_citations": total_citations,
            "avg_citations": round(total_citations / len(self._papers), 1),
            "total_findings": total_findings,
            "total_datasets_introduced": total_datasets,
            "surveys": sum(1 for p in self._papers.values() if p.is_survey),
            "with_code": sum(1 for p in self._papers.values() if p.code_repositories),
            "top_categories": dict(top_categories),
        }

    def collect_continuously(
        self,
        interval_hours: int = 24,
        max_per_run: int = 100,
    ) -> None:
        """
        Continuously collect new papers. Designed to be called by a scheduler.

        Args:
            interval_hours: How often to check for new papers.
            max_per_run: Maximum papers to collect per run.
        """
        print(f"\n[CONTINUOUS] Paper collection (interval: {interval_hours}h)")
        self.collect_papers(limit=max_per_run, include_recent=True)
        self.save_knowledge_chunks()
        stats = self.get_statistics()
        print(f"[KB] {stats['total_papers']} papers, {stats['total_findings']} findings")
        print(f"   Top categories: {list(stats['top_categories'].keys())[:5]}")


# ═════════════════════════════════════════════════════════════════════
# Convenience Functions
# ═════════════════════════════════════════════════════════════════════


def collect_research_knowledge(
    topics: list[str] | None = None,
    limit: int = 100,
) -> ResearchPaperKnowledgeBase:
    """Convenience: collect research paper knowledge and save chunks."""
    kb = ResearchPaperKnowledgeBase()
    kb.collect_papers(topics=topics, limit=limit)
    kb.save_knowledge_chunks()
    return kb


def print_paper_summary(papers: list[PaperKnowledge], top_n: int = 10) -> None:
    """Print a formatted summary of papers."""
    print(f"\n{'='*70}")
    print(f"{'TOP PAPERS':^70}")
    print(f"{'='*70}")

    for i, paper in enumerate(papers[:top_n], 1):
        citations = f"cited {paper.citation_count}x" if paper.citation_count else "new"
        cats = ", ".join(paper.categories[:2])
        findings = len(paper.key_findings)
        datasets = len(paper.datasets_introduced)

        print(f"\n  {i:2d}. {paper.title[:80]}")
        print(f"      {', '.join(a.name for a in paper.authors[:3])} | {citations}")
        print(f"      [{cats}] | {findings} findings, {datasets} datasets | score: {paper.relevance_score:.2f}")
        if paper.key_findings:
            print(f"      -> {paper.key_findings[0].finding[:100]}")
    print(f"\n{'='*70}")


if __name__ == "__main__":
    # Quick test
    kb = collect_research_knowledge(
        topics=["Large Language Models", "Python Code Generation", "RAG"],
        limit=30,
    )
    print_paper_summary(kb.get_top_papers(10))
    print(json.dumps(kb.get_statistics(), indent=2))
