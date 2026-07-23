"""Discovery Engine — Automated dataset discovery for PythonAI.

Scans HuggingFace, arXiv, government portals, GitHub, and research
papers to find new training datasets and rank them by priority.

Modules:
  hf_catalog_scanner   — Scan HF datasets daily for new/relevant datasets
  arxiv_rss_watcher    — Watch arXiv RSS feeds for new papers
  gov_portal_crawler   — Crawl data.gov.in, data.gov for new datasets
  github_trending      — Track trending AI/ML repos + datasets
  paper_dataset_extractor — Extract dataset links from papers
  priority_ranker      — Score datasets by size × quality × domain_gap
  research_papers      — Research Paper Knowledge Harvester (arXiv, Semantic Scholar)
  book_knowledge       — Book & Educational Resource Knowledge Base
  knowledge_harvester  — Unified Knowledge Intelligence Engine
"""

from __future__ import annotations

from src.data.discovery.arxiv_rss_watcher import ArxivRSSWatcher
from src.data.discovery.github_trending import GitHubTrending
from src.data.discovery.gov_portal_crawler import GovPortalCrawler
from src.data.discovery.hf_catalog_scanner import HFCatalogScanner
from src.data.discovery.paper_dataset_extractor import PaperDatasetExtractor
from src.data.discovery.priority_ranker import PriorityRanker, ScoredDataset, print_ranking, rank_discovered

# ── Knowledge Intelligence Engine ────────────────────────────────────
from src.data.discovery.research_papers import (
    ArxivAPIClient,
    PaperAuthor,
    PaperKeyFinding,
    PaperKnowledge,
    PaperKnowledgeExtractor,
    PaperMethodology,
    ResearchPaperKnowledgeBase,
    SemanticScholarClient,
    collect_research_knowledge,
    print_paper_summary,
)
from src.data.discovery.book_knowledge import (
    BookKnowledge,
    BookKnowledgeBase,
    TutorialResource,
    collect_book_knowledge,
)
from src.data.discovery.knowledge_harvester import (
    HarvestReport,
    KnowledgeIntelligence,
    KnowledgeSource,
    get_knowledge_stats,
    harvest_all_knowledge,
    query_knowledge,
)

from src.data.metadata import DatasetRecord


# ── Convenience functions ────────────────────────────────────────────


def auto_discover(
    hf_limit: int = 50,
    arxiv_limit: int = 20,
    gov_limit: int = 30,
    github_limit: int = 20,
    paper_limit: int = 10,
    top_n: int = 20,
    verbose: bool = False,
) -> list[ScoredDataset]:
    """Run all discovery scanners and return top-ranked datasets.

    Args:
        hf_limit: Max HF datasets to scan.
        arxiv_limit: Max arXiv papers to check.
        gov_limit: Max gov portal datasets to scan.
        github_limit: Max GitHub repos to check.
        paper_limit: Max papers to extract from.
        top_n: Number of top results to return.
        verbose: Print progress during discovery.

    Returns:
        Top N scored datasets across all sources.
    """
    all_records: list[DatasetRecord] = []

    if verbose:
        print("[Discovery] Running automated discovery across all sources...")

    scanner = HFCatalogScanner()
    try:
        hf_records = scanner.scan_recent(limit=hf_limit, verbose=verbose)
        all_records.extend(hf_records)
        if verbose:
            print(f"  HF: {len(hf_records)} datasets found")
    except Exception as e:
        if verbose:
            print(f"  HF scan failed: {e}")

    watcher = ArxivRSSWatcher()
    try:
        arxiv_records = watcher.fetch_recent(categories=["cs.AI", "cs.LG", "cs.CL"], max_results=arxiv_limit)
        all_records.extend(arxiv_records)
        if verbose:
            print(f"  arXiv: {len(arxiv_records)} papers found")
    except Exception as e:
        if verbose:
            print(f"  arXiv fetch failed: {e}")

    crawler = GovPortalCrawler()
    try:
        gov_records = crawler.search(keywords=["machine learning", "AI", "education", "health"], limit=gov_limit)
        all_records.extend(gov_records)
        if verbose:
            print(f"  Gov: {len(gov_records)} datasets found")
    except Exception as e:
        if verbose:
            print(f"  Gov crawl failed: {e}")

    gh = GitHubTrending()
    try:
        gh_records = gh.scan_trending(limit=github_limit, verbose=verbose)
        all_records.extend(gh_records)
        if verbose:
            print(f"  GitHub: {len(gh_records)} repos found")
    except Exception as e:
        if verbose:
            print(f"  GitHub scan failed: {e}")

    extractor = PaperDatasetExtractor()
    try:
        paper_records = extractor.extract_from_papers(
            papers=[],
            max_datasets=paper_limit,
            verbose=verbose,
        )
        all_records.extend(paper_records)
        if verbose:
            print(f"  Papers: {len(paper_records)} datasets found")
    except Exception as e:
        if verbose:
            print(f"  Paper extraction failed: {e}")

    if verbose:
        print(f"\n  Total candidate records: {len(all_records)}")

    return rank_discovered(all_records, top_n=top_n)


def check_for_new_papers(
    categories: list[str] | None = None,
    max_results: int = 20,
    verbose: bool = False,
) -> list[DatasetRecord]:
    """Quick check for new arXiv papers that might contain datasets."""
    watcher = ArxivRSSWatcher()
    cats = categories or ["cs.AI", "cs.LG", "cs.CL", "cs.SE"]
    records = watcher.fetch_recent(categories=cats, max_results=max_results)
    if verbose:
        print(f"[arXiv] Found {len(records)} recent papers")
    return records


def discover_government_data(
    keywords: list[str] | None = None,
    limit: int = 30,
    verbose: bool = False,
) -> list[DatasetRecord]:
    """Discover datasets from government open data portals."""
    crawler = GovPortalCrawler()
    kw = keywords or ["machine learning", "AI", "data", "education", "health", "agriculture"]
    records = crawler.search(keywords=kw, limit=limit)
    if verbose:
        print(f"[Gov] Found {len(records)} datasets")
    return records


def discover_github_repos(
    languages: list[str] | None = None,
    limit: int = 20,
    verbose: bool = False,
) -> list[DatasetRecord]:
    """Discover trending GitHub repos with training data."""
    gh = GitHubTrending()
    langs = languages or ["Python", "Jupyter Notebook", "TypeScript"]
    all_records: list[DatasetRecord] = []
    for lang in langs:
        try:
            records = gh.scan_trending(language=lang, limit=limit, verbose=verbose)
            all_records.extend(records)
        except Exception as e:
            if verbose:
                print(f"  GitHub ({lang}) scan failed: {e}")
    if verbose:
        print(f"[GitHub] Found {len(all_records)} repos")
    return all_records


def extract_datasets_from_papers(
    paper_urls: list[str] | None = None,
    max_datasets: int = 10,
    verbose: bool = False,
) -> list[DatasetRecord]:
    """Extract dataset references from research papers."""
    extractor = PaperDatasetExtractor()
    papers = paper_urls or []
    records = extractor.extract_from_papers(papers=papers, max_datasets=max_datasets, verbose=verbose)
    if verbose:
        print(f"[Papers] Extracted {len(records)} datasets")
    return records


__all__ = [
    "HFCatalogScanner",
    "ArxivRSSWatcher",
    "GovPortalCrawler",
    "GitHubTrending",
    "PaperDatasetExtractor",
    "PriorityRanker",
    "ScoredDataset",
    # Knowledge Intelligence
    "ResearchPaperKnowledgeBase",
    "PaperKnowledge",
    "PaperAuthor",
    "PaperKeyFinding",
    "PaperMethodology",
    "ArxivAPIClient",
    "SemanticScholarClient",
    "PaperKnowledgeExtractor",
    "BookKnowledgeBase",
    "BookKnowledge",
    "TutorialResource",
    "KnowledgeIntelligence",
    "KnowledgeSource",
    "HarvestReport",
    # Knowledge functions
    "collect_research_knowledge",
    "collect_book_knowledge",
    "harvest_all_knowledge",
    "query_knowledge",
    "get_knowledge_stats",
    "print_paper_summary",
    # Auto-discovery
    "auto_discover",
    "check_for_new_papers",
    "discover_government_data",
    "discover_github_repos",
    "extract_datasets_from_papers",
    "rank_discovered",
    "print_ranking",
]
