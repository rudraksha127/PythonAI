"""
PythonAI Data Collection Pipeline

Modules:
  metadata    — Dataset metadata schema and persistent MetadataManager registry
  downloader  — Multi-protocol download orchestrator (HF, HTTP, Git LFS, S3, API)
  quality     — Quality control pipeline (length filter, language detection, PII, dedup)
  phase1      — Phase 1 dataset definitions across all 4 weeks
  discovery   — Discovery Engine: HF scanner, arXiv watcher, gov crawler, etc.
    .../priority_ranker — Score & rank discovered datasets for priority
"""

from src.data.metadata import (
    DatasetRecord,
    DownloadProtocol,
    DownloadStatus,
    DataDomain,
    QualityCheck,
    MetadataManager,
)

from src.data.downloader import (
    DownloadOrchestrator,
    RateLimiter,
    decompress_file,
    BASE_DATA_DIR,
)

from src.data.quality import (
    QualityPipeline,
    check_text_length,
    detect_language,
    filter_by_language,
    scan_pii,
    mask_pii,
    exact_dedup,
    near_dedup,
    check_boilerplate,
    check_repetition,
)

from src.data.phase1 import (
    generate_phase1_datasets,
    generate_week1,
    generate_week2,
    generate_week3,
    generate_week4,
    phase1_stats,
)

# ── AntiGravity Orchestrator ────────────────────────────────────────
from src.data.orchestrator import (
    AntiGravityOrchestrator,
    OrchestratorConfig,
    Phase,
    PhaseStatus,
    CollectionTask,
    TaskStatus,
)

# ── Discovery Engine exports ────────────────────────────────────────
from src.data.discovery import (
    HFCatalogScanner,
    ArxivRSSWatcher,
    GovPortalCrawler,
    GitHubTrending,
    PaperDatasetExtractor,
    PriorityRanker,
    ScoredDataset,
    # Convenience functions
    auto_discover,
    check_for_new_papers,
    discover_government_data,
    discover_github_repos,
    extract_datasets_from_papers,
    rank_discovered,
    print_ranking,
)

__all__ = [
    # Metadata
    "DatasetRecord",
    "DownloadProtocol",
    "DownloadStatus",
    "DataDomain",
    "QualityCheck",
    "MetadataManager",
    # Downloader
    "DownloadOrchestrator",
    "RateLimiter",
    "decompress_file",
    "BASE_DATA_DIR",
    # Quality
    "QualityPipeline",
    "check_text_length",
    "detect_language",
    "filter_by_language",
    "scan_pii",
    "mask_pii",
    "exact_dedup",
    "near_dedup",
    "check_boilerplate",
    "check_repetition",
    # Phase 1
    "generate_phase1_datasets",
    "generate_week1",
    "generate_week2",
    "generate_week3",
    "generate_week4",
    "phase1_stats",
    # Discovery Engine
    "HFCatalogScanner",
    "ArxivRSSWatcher",
    "GovPortalCrawler",
    "GitHubTrending",
    "PaperDatasetExtractor",
    "PriorityRanker",
    "ScoredDataset",
    "auto_discover",
    "check_for_new_papers",
    "discover_government_data",
    "discover_github_repos",
    "extract_datasets_from_papers",
    "rank_discovered",
    "print_ranking",
    # AntiGravity Orchestrator
    "AntiGravityOrchestrator",
    "OrchestratorConfig",
    "Phase",
    "PhaseStatus",
    "CollectionTask",
    "TaskStatus",
]
