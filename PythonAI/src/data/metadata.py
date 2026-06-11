"""
METADATA SCHEMA & MANAGER
Central registry for tracking all datasets across Phase 1-4 collection.
Each dataset has a record tracking its source, protocol, quality checks,
download status, and relationship to the INDRA training pipeline.

Usage:
    from src.data.metadata import MetadataManager, DatasetRecord
    mgr = MetadataManager()
    mgr.register_dataset(DatasetRecord(...))
    mgr.update_status("fineweb", "downloaded")
    print(mgr.summary())
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


# ════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════

class DownloadProtocol(Enum):
    HUGGINGFACE = "hf"
    HTTP = "http"
    GIT_LFS = "git-lfs"
    S3 = "s3"
    SFTP = "sftp"
    API = "api"
    LOCAL = "local"


class DownloadStatus(Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    VALIDATED = "validated"
    QUALITY_PASSED = "quality_passed"
    QUALITY_FAILED = "quality_failed"
    DEDUPLICATED = "deduplicated"
    READY = "ready"
    ERROR = "error"
    SKIPPED = "skipped"


class DataDomain(Enum):
    FOUNDATION_TEXT = "foundation_text"
    CODE = "code"
    SCIENCE = "science"
    MEDICINE = "medicine"
    LAW = "law"
    BUSINESS = "business"
    MATH = "math"
    MULTILINGUAL = "multilingual"
    INDIAN_LANGUAGES = "indian_languages"
    INSTRUCTION = "instruction"
    MULTIMODAL = "multimodal"
    AUDIO = "audio"
    SYNTHETIC = "synthetic"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    EMERGING = "emerging"
    OTHER = "other"
    # Discovery Engine domains
    NATURAL_SCIENCE = "natural_science"
    ENGINEERING = "engineering"
    SOCIAL_SCIENCE = "social_science"
    ARTS = "arts"
    LANGUAGE = "language"
    FORMAL_SCIENCE = "formal_science"


class QualityCheck(Enum):
    TEXT_LENGTH = "text_length"
    LANGUAGE_DETECTION = "language_detection"
    PII_SCAN = "pii_scan"
    DEDUP_MINHASH = "dedup_minhash"
    DEDUP_EXACT = "dedup_exact"
    PERPLEXITY = "perplexity"
    TOXICITY = "toxicity"
    FORMAT_VALID = "format_valid"


# ════════════════════════════════════════════
# DatasetRecord — the atomic unit of the collection plan
# ════════════════════════════════════════════

@dataclass
class DatasetRecord:
    """Complete metadata record for one dataset in the collection pipeline."""

    # Identity
    id: str                              # Unique identifier, e.g. "fineweb_edu_en"
    name: str                            # Human-readable name, e.g. "FineWeb-Edu (English)"
    source_url: str = ""                 # Origin URL / HF path
    protocol: DownloadProtocol = DownloadProtocol.HUGGINGFACE

    # Classification
    phase: int = 1                       # 1-4
    week: int = 1                        # 1-4 within phase
    domain: DataDomain = DataDomain.FOUNDATION_TEXT
    category: str = ""                   # Fine-grained category
    languages: list[str] = field(default_factory=lambda: ["en"])
    license: str = "unknown"

    # Scale
    estimated_size_bytes: int = 0
    estimated_record_count: int = 0
    actual_record_count: int = 0
    actual_size_bytes: int = 0

    # Configuration
    hf_config: str | None = None         # HuggingFace config name (if applicable)
    hf_split: str = "train"
    download_params: dict[str, Any] = field(default_factory=dict)
    output_subdir: str = ""              # Relative path under D:/PythonAI_Data/

    # Pipeline state
    status: DownloadStatus = DownloadStatus.PENDING
    quality_checks: dict[str, bool] = field(default_factory=dict)
    quality_score: float = 0.0           # 0.0 - 1.0
    started_at: float | None = None
    completed_at: float | None = None
    error_message: str = ""

    # Relationships
    depends_on: list[str] = field(default_factory=list)  # IDs of datasets needed first
    tags: list[str] = field(default_factory=list)

    # Training path
    training_weight: float = 1.0         # How much to weight this in training mix
    training_phase: int = 1              # Which training phase uses this

    def __post_init__(self):
        if isinstance(self.protocol, str):
            self.protocol = DownloadProtocol(self.protocol)
        if isinstance(self.status, str):
            self.status = DownloadStatus(self.status)
        if isinstance(self.domain, str):
            self.domain = DataDomain(self.domain)
        if isinstance(self.quality_checks, list):
            self.quality_checks = {qc: False for qc in self.quality_checks}

    @property
    def elapsed_seconds(self) -> float:
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return 0.0

    @property
    def size_mb(self) -> float:
        return self.actual_size_bytes / (1024 * 1024)

    @property
    def is_ready(self) -> bool:
        return self.status in (DownloadStatus.READY, DownloadStatus.DEDUPLICATED,
                                DownloadStatus.QUALITY_PASSED, DownloadStatus.VALIDATED)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["protocol"] = self.protocol.value
        d["status"] = self.status.value
        d["domain"] = self.domain.value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DatasetRecord":
        return cls(**d)


# ════════════════════════════════════════════
# MetadataManager — persistent registry
# ════════════════════════════════════════════

class MetadataManager:
    """
    Persistent metadata registry for the entire data collection pipeline.
    
    Features:
    - Register, update, query datasets
    - Persistent JSON storage
    - Summary statistics
    - Progress tracking across phases/weeks
    """

    def __init__(self, storage_path: str | Path | None = None):
        if storage_path is None:
            storage_path = Path("D:/PythonAI_Data") / ".metadata_registry.json"
        self.storage_path = Path(storage_path)
        self._datasets: dict[str, DatasetRecord] = {}
        self._load()

    # ── Persistence ──────────────────────────────────────────────

    def _load(self) -> None:
        if self.storage_path.exists():
            try:
                raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
                for d in raw.get("datasets", []):
                    record = DatasetRecord.from_dict(d)
                    self._datasets[record.id] = record
            except Exception:
                self._datasets = {}

    def save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "schema_version": "1.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "dataset_count": len(self._datasets),
            "datasets": [d.to_dict() for d in self._datasets.values()],
        }
        self.storage_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── CRUD ─────────────────────────────────────────────────────

    def register(self, record: DatasetRecord) -> "DatasetRecord":
        """Register a new dataset. If it exists, updates metadata fields (not status)."""
        existing = self._datasets.get(record.id)
        if existing:
            # Keep the status, update metadata
            record.status = existing.status
            record.quality_checks = existing.quality_checks
            record.quality_score = existing.quality_score
            record.actual_record_count = existing.actual_record_count
            record.actual_size_bytes = existing.actual_size_bytes
            record.error_message = existing.error_message
        self._datasets[record.id] = record
        self.save()
        return record

    def register_many(self, records: list[DatasetRecord]) -> list[DatasetRecord]:
        for r in records:
            self.register(r)
        return records

    def get(self, dataset_id: str) -> DatasetRecord | None:
        return self._datasets.get(dataset_id)

    def update_status(self, dataset_id: str, status: DownloadStatus,
                      error_message: str = "") -> DatasetRecord | None:
        record = self._datasets.get(dataset_id)
        if not record:
            return None
        record.status = status if isinstance(status, DownloadStatus) else DownloadStatus(status)
        if error_message:
            record.error_message = error_message
        if status == DownloadStatus.DOWNLOADING and record.started_at is None:
            record.started_at = time.time()
        if status in (DownloadStatus.DOWNLOADED, DownloadStatus.READY, DownloadStatus.ERROR):
            record.completed_at = time.time()
        self.save()
        return record

    def update_quality(self, dataset_id: str, check: QualityCheck | str,
                       passed: bool, score: float | None = None) -> DatasetRecord | None:
        record = self._datasets.get(dataset_id)
        if not record:
            return None
        check_str = check.value if isinstance(check, QualityCheck) else check
        record.quality_checks[check_str] = passed
        if score is not None:
            record.quality_score = score
        if all(record.quality_checks.values()):
            record.status = DownloadStatus.QUALITY_PASSED
        self.save()
        return record

    def update_size(self, dataset_id: str, records: int, bytes_: int) -> DatasetRecord | None:
        record = self._datasets.get(dataset_id)
        if not record:
            return None
        record.actual_record_count = records
        record.actual_size_bytes = bytes_
        self.save()
        return record

    def remove(self, dataset_id: str) -> bool:
        if dataset_id in self._datasets:
            del self._datasets[dataset_id]
            self.save()
            return True
        return False

    # ── Queries ──────────────────────────────────────────────────

    def list_by_status(self, status: DownloadStatus | str) -> list[DatasetRecord]:
        if isinstance(status, str):
            status = DownloadStatus(status)
        return [d for d in self._datasets.values() if d.status == status]

    def list_by_phase(self, phase: int) -> list[DatasetRecord]:
        return [d for d in self._datasets.values() if d.phase == phase]

    def list_by_week(self, phase: int, week: int) -> list[DatasetRecord]:
        return [d for d in self._datasets.values() if d.phase == phase and d.week == week]

    def list_by_domain(self, domain: DataDomain | str) -> list[DatasetRecord]:
        if isinstance(domain, str):
            domain = DataDomain(domain)
        return [d for d in self._datasets.values() if d.domain == domain]

    def list_ready(self) -> list[DatasetRecord]:
        return [d for d in self._datasets.values() if d.is_ready]

    def list_pending(self) -> list[DatasetRecord]:
        return [d for d in self._datasets.values()
                if d.status == DownloadStatus.PENDING]

    def list_errors(self) -> list[DatasetRecord]:
        return [d for d in self._datasets.values()
                if d.status == DownloadStatus.ERROR]

    def search(self, query: str) -> list[DatasetRecord]:
        q = query.lower()
        return [d for d in self._datasets.values()
                if q in d.name.lower() or q in d.id.lower() or q in d.category.lower()]

    def all(self) -> list[DatasetRecord]:
        return list(self._datasets.values())

    # ── Summary ──────────────────────────────────────────────────

    def summary(self) -> dict[str, Any]:
        total = len(self._datasets)
        by_status: dict[str, int] = {}
        by_phase: dict[int, int] = {}
        ready_records = 0
        ready_bytes = 0
        total_estimated = sum(d.estimated_record_count or 0 for d in self._datasets.values())
        total_actual = sum(d.actual_record_count for d in self._datasets.values())

        for d in self._datasets.values():
            by_status[d.status.value] = by_status.get(d.status.value, 0) + 1
            by_phase[d.phase] = by_phase.get(d.phase, 0) + 1
            if d.is_ready:
                ready_records += d.actual_record_count
                ready_bytes += d.actual_size_bytes

        return {
            "total_datasets": total,
            "by_status": dict(sorted(by_status.items())),
            "by_phase": dict(sorted(by_phase.items())),
            "estimated_records": total_estimated,
            "actual_records": total_actual,
            "ready_records": ready_records,
            "ready_gb": round(ready_bytes / (1024**3), 2),
            "errors": [{"id": d.id, "error": d.error_message}
                       for d in self._datasets.values() if d.status == DownloadStatus.ERROR],
        }

    def week_progress(self, phase: int, week: int) -> dict[str, Any]:
        datasets = self.list_by_week(phase, week)
        total = len(datasets)
        done = sum(1 for d in datasets if d.is_ready)
        errors = sum(1 for d in datasets if d.status == DownloadStatus.ERROR)
        pending = sum(1 for d in datasets if d.status == DownloadStatus.PENDING)
        records = sum(d.actual_record_count for d in datasets)
        return {
            "phase": phase,
            "week": week,
            "total": total,
            "done": done,
            "errors": errors,
            "pending": pending,
            "progress_pct": round(done / total * 100, 1) if total > 0 else 0,
            "records_collected": records,
        }

    def pipeline_status(self) -> dict[str, Any]:
        """Overall pipeline health summary across all phases."""
        phases = {}
        for phase in range(1, 5):
            ds = self.list_by_phase(phase)
            total = len(ds)
            ready = sum(1 for d in ds if d.is_ready)
            errors = sum(1 for d in ds if d.status == DownloadStatus.ERROR)
            phases[f"phase_{phase}"] = {
                "datasets": total,
                "ready": ready,
                "errors": errors,
                "progress_pct": round(ready / total * 100, 1) if total > 0 else 0,
                "records": sum(d.actual_record_count for d in ds),
            }
        return {
            "phases": phases,
            "total_datasets": len(self._datasets),
            "total_ready": sum(p["ready"] for p in phases.values()),
            "total_records": sum(p["records"] for p in phases.values()),
        }
