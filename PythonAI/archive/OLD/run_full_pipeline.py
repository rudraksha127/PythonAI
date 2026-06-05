#!/usr/bin/env python3
"""
RUN FULL PIPELINE — End-to-End Data Collection to Training
==========================================================
Single entry point for the entire PythonAI model training pipeline.

Steps:
  1. Register & check Phase 1 datasets
  2. Download pending datasets
  3. Run quality checks (dedup, PII, language, length)
  4. Format collected data into INDRA training format
  5. Generate training statistics & ready report

Usage:
    python run_full_pipeline.py                         # Full pipeline
    python run_full_pipeline.py --step collect          # Only data collection
    python run_full_pipeline.py --step quality          # Only quality checks
    python run_full_pipeline.py --step format           # Only format for training
    python run_full_pipeline.py --step report           # Only show status report
    python run_full_pipeline.py --weeks 1 2             # Collect specific weeks
    python run_full_pipeline.py --concurrent 10         # Max concurrent downloads
    python run_full_pipeline.py --skip-download         # Skip download, run quality+format
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

# Ensure project root is on PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Environment setup
os.environ.setdefault("DATA_DIR", "D:/PythonAI_Data")

from src.data.metadata import (
    MetadataManager, DatasetRecord, DownloadStatus, DataDomain, QualityCheck
)
from src.data.phase1 import generate_phase1_datasets, phase1_stats
from src.data.quality import QualityPipeline, check_text_length, detect_language, scan_pii


# ── Constants ──────────────────────────────────────────────────────────

BASE_DATA_DIR = Path(os.environ.get("DATA_DIR", "D:/PythonAI_Data"))
METADATA_PATH = BASE_DATA_DIR / ".metadata_registry.json"
TRAINING_DIR = BASE_DATA_DIR / "training"
FORMATTED_DIR = TRAINING_DIR / "formatted"
QUALITY_DIR = BASE_DATA_DIR / "quality_reports"


# ── Logging ────────────────────────────────────────────────────────────

class PipelineLogger:
    """Simple colored logger for pipeline steps."""

    COLORS = {
        "header": "\033[95m",
        "blue": "\033[94m",
        "cyan": "\033[96m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "red": "\033[91m",
        "bold": "\033[1m",
        "end": "\033[0m",
    }

    @staticmethod
    def _c(color: str) -> str:
        return PipelineLogger.COLORS.get(color, "")

    @staticmethod
    def header(msg: str):
        print(f"\n{PipelineLogger._c('bold')}{'=' * 70}{PipelineLogger._c('end')}")
        print(f"{PipelineLogger._c('header')}  {msg}{PipelineLogger._c('end')}")
        print(f"{PipelineLogger._c('bold')}{'=' * 70}{PipelineLogger._c('end')}\n")

    @staticmethod
    def step(num: int, total: int, msg: str):
        print(f"\n{PipelineLogger._c('cyan')}  [{num}/{total}] {msg}{PipelineLogger._c('end')}")
        print(f"  {'─' * 60}")

    @staticmethod
    def success(msg: str):
        print(f"  {PipelineLogger._c('green')}✓{PipelineLogger._c('end')} {msg}")

    @staticmethod
    def warn(msg: str):
        print(f"  {PipelineLogger._c('yellow')}⚠{PipelineLogger._c('end')} {msg}")

    @staticmethod
    def error(msg: str):
        print(f"  {PipelineLogger._c('red')}✗{PipelineLogger._c('end')} {msg}")

    @staticmethod
    def info(msg: str):
        print(f"  ℹ {msg}")

    @staticmethod
    def progress_bar(current: int, total: int, width: int = 30):
        if total == 0:
            return
        pct = current / total
        filled = int(width * pct)
        bar = "█" * filled + "░" * (width - filled)
        print(f"  [{bar}] {pct * 100:.1f}% ({current:,}/{total:,})", end="\r")


log = PipelineLogger()


# ── STEP 1: Register & Status Check ───────────────────────────────────

def step_register_datasets(mgr: MetadataManager) -> dict[str, Any]:
    """Register all Phase 1 datasets and return status summary."""
    log.step(1, 5, "Registering Datasets & Checking Status")

    records = generate_phase1_datasets()
    for record in records:
        mgr.register(record)

    # Count by status
    all_records = mgr.all()
    by_status = Counter(r.status.value for r in all_records)
    by_domain = Counter(r.domain.value for r in all_records)
    by_week = Counter(f"Week {r.week}" for r in all_records if r.phase == 1)

    total = len(all_records)
    ready = sum(1 for r in all_records if r.is_ready)
    pending = by_status.get("pending", 0)
    errors = by_status.get("error", 0)
    downloading = by_status.get("downloading", 0)

    log.success(f"Total datasets registered: {total}")
    log.info(f"  Ready     : {ready}")
    log.info(f"  Pending   : {pending}")
    log.info(f"  Downloading: {downloading}")
    log.info(f"  Errors    : {errors}")

    print(f"\n  By Status:")
    for status, count in sorted(by_status.items()):
        log.info(f"  {status:20s}: {count}")

    print(f"\n  By Week:")
    for week, count in sorted(by_week.items()):
        log.info(f"  {week:10s}: {count}")

    return {
        "total": total,
        "ready": ready,
        "pending": pending,
        "errors": errors,
        "by_status": dict(by_status),
    }


# ── STEP 2: Download Pending Datasets ─────────────────────────────────

async def step_download_datasets(mgr: MetadataManager, weeks: list[int] | None = None,
                                  concurrent: int = 4) -> dict[str, Any]:
    """Download all pending Phase 1 datasets."""
    log.step(2, 5, "Downloading Pending Datasets")

    from src.data.downloader import DownloadOrchestrator

    pending = mgr.list_pending()
    # Also retry errored ones
    errored = mgr.list_errors()
    to_download = pending + errored

    if weeks:
        to_download = [d for d in to_download if d.week in weeks and d.phase == 1]

    if not to_download:
        log.success("No pending/errored datasets to download!")
        return {"downloaded": 0, "errors": 0, "records": 0}

    log.info(f"Datasets to download: {len(to_download)}")
    log.info(f"Max concurrent: {concurrent}")

    def log_msg(msg: str):
        print(f"    {msg}")

    def progress_cb(ds_id: str, current: int, total: int):
        if total > 0 and current % 50000 == 0:
            print(f"    {ds_id}: {current:,} / {total:,}")

    orch = DownloadOrchestrator(
        metadata_mgr=mgr,
        max_concurrent=concurrent,
        progress_callback=progress_cb,
        log_callback=log_msg,
    )

    start_time = time.time()
    total_records = 0
    total_errors = 0
    total_downloaded = 0

    for record in to_download:
        log.info(f"Downloading: {record.id} ({record.name})")
        result = await orch.download_one(record.id)

        if "error" in result:
            total_errors += 1
            log.error(f"{record.id}: {result['error'][:100]}")
        else:
            total_downloaded += 1
            records = result.get("records", 0)
            total_records += records
            log.success(f"{record.id}: {records:,} records")

    elapsed = time.time() - start_time
    await orch.close()

    log.success(f"Download complete!")
    log.info(f"  Downloaded: {total_downloaded}")
    log.info(f"  Errors    : {total_errors}")
    log.info(f"  Records   : {total_records:,}")
    log.info(f"  Time      : {elapsed:.0f}s ({elapsed / 60:.1f}min)")

    return {
        "downloaded": total_downloaded,
        "errors": total_errors,
        "records": total_records,
        "elapsed_seconds": elapsed,
    }


# ── STEP 3: Quality Checks ────────────────────────────────────────────

def step_quality_checks(mgr: MetadataManager) -> dict[str, Any]:
    """Run quality checks on downloaded datasets."""
    log.step(3, 5, "Running Quality Checks")

    QUALITY_DIR.mkdir(parents=True, exist_ok=True)

    downloaded = [d for d in mgr.all()
                  if d.status in (DownloadStatus.DOWNLOADED, DownloadStatus.VALIDATED)]

    if not downloaded:
        log.warn("No downloaded datasets found to quality-check.")
        # Also check datasets that are ready but haven't been quality-checked
        ready = [d for d in mgr.all() if d.is_ready]
        if ready:
            log.info(f"Found {len(ready)} ready datasets (may already be quality-checked).")
        return {"checked": 0, "passed": 0, "failed": 0}

    log.info(f"Datasets to quality-check: {len(downloaded)}")

    qp = QualityPipeline(min_text_length=50)
    checked = 0
    passed = 0
    failed = 0

    for record in downloaded:
        # Find the data files for this dataset
        data_dir = BASE_DATA_DIR / record.output_subdir
        if not data_dir.exists():
            log.warn(f"{record.id}: data directory not found ({data_dir})")
            continue

        # Find JSONL/Parquet files
        data_files = list(data_dir.glob("*.jsonl")) + list(data_dir.glob("*.parquet"))
        if not data_files:
            # Check subdirectories
            for sub in data_dir.iterdir():
                if sub.is_dir():
                    data_files += list(sub.glob("*.jsonl")) + list(sub.glob("*.parquet"))

        if not data_files:
            log.warn(f"{record.id}: no data files found")
            continue

        log.info(f"Checking {record.id}: {len(data_files)} file(s)")

        try:
            # Run quality pipeline on the first data file
            for data_file in data_files[:3]:  # Check up to 3 files per dataset
                if data_file.suffix == ".jsonl":
                    stats = qp.run(str(data_file))
                    report_path = QUALITY_DIR / f"{record.id}_quality.json"
                    report_path.write_text(
                        json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8"
                    )

                    # Update quality checks in metadata
                    if stats.get("passed", False):
                        mgr.update_quality(record.id, QualityCheck.TEXT_LENGTH, True,
                                          score=stats.get("quality_score", 0.0))
                        passed += 1
                    else:
                        mgr.update_quality(record.id, QualityCheck.TEXT_LENGTH, False)
                        failed += 1

                    checked += 1

        except Exception as e:
            log.error(f"{record.id}: quality check failed - {e}")
            failed += 1

    log.success(f"Quality checks complete!")
    log.info(f"  Checked: {checked}")
    log.info(f"  Passed : {passed}")
    log.info(f"  Failed : {failed}")

    return {"checked": checked, "passed": passed, "failed": failed}


# ── STEP 4: Format for Training ───────────────────────────────────────

def step_format_training_data(mgr: MetadataManager) -> dict[str, Any]:
    """Format collected data into INDRA training format (instruction-output pairs)."""
    log.step(4, 5, "Formatting Data for Training")

    FORMATTED_DIR.mkdir(parents=True, exist_ok=True)

    # Collect all ready datasets
    ready_datasets = mgr.list_ready()
    if not ready_datasets:
        # Also scan D: drive for any collected data
        log.warn("No ready datasets in metadata. Scanning D: drive for collected data...")
        ready_datasets = _scan_collected_data()

    if not ready_datasets:
        log.error("No data found to format!")
        return {"examples": 0, "files": 0}

    log.info(f"Datasets to format: {len(ready_datasets)}")

    all_examples: list[dict[str, Any]] = []
    domain_counts: Counter = Counter()
    files_processed = 0
    total_bytes = 0

    for record in ready_datasets:
        data_dir = BASE_DATA_DIR / record.output_subdir if hasattr(record, 'output_subdir') else None
        if data_dir and data_dir.exists():
            examples = _format_dataset(record, data_dir)
            all_examples.extend(examples)
            domain_counts[record.domain.value if hasattr(record, 'domain') else 'unknown'] += len(examples)
            files_processed += 1

    # Also scan the massive engine output directories
    massive_dirs = ["arxiv", "openalex", "github", "pubmed", "stackexchange",
                    "crossref", "openlibrary", "gutendex", "worldbank", "europeana",
                    "gbif", "musicbrainz", "preprints", "rss", "semantic_scholar",
                    "pypi", "reddit"]

    for dirname in massive_dirs:
        data_dir = BASE_DATA_DIR / dirname
        if data_dir.exists():
            examples = _format_massive_data(data_dir, dirname)
            all_examples.extend(examples)
            domain_counts[dirname] += len(examples)
            files_processed += 1

    if not all_examples:
        log.warn("No training examples generated!")
        return {"examples": 0, "files": 0}

    # Write formatted training data
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # JSONL format (primary)
    jsonl_path = FORMATTED_DIR / f"indra_training_{timestamp}.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for ex in all_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    total_bytes = jsonl_path.stat().st_size

    # Also write a combined base file
    base_path = FORMATTED_DIR / "indra_training_latest.jsonl"
    with open(base_path, "w", encoding="utf-8") as f:
        for ex in all_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    # Stats
    log.success(f"Training data formatted!")
    log.info(f"  Total examples : {len(all_examples):,}")
    log.info(f"  Files processed: {files_processed}")
    log.info(f"  Output file    : {jsonl_path.name}")
    log.info(f"  Output size    : {total_bytes / (1024 * 1024):.1f} MB")

    print(f"\n  By Domain:")
    for domain, count in domain_counts.most_common(20):
        log.info(f"  {domain:25s}: {count:,}")

    return {
        "examples": len(all_examples),
        "files": files_processed,
        "output_path": str(jsonl_path),
        "size_mb": round(total_bytes / (1024 * 1024), 1),
        "domain_counts": dict(domain_counts.most_common(20)),
    }


def _format_dataset(record, data_dir: Path) -> list[dict[str, Any]]:
    """Format a single dataset record into training examples."""
    examples = []

    # Find data files
    data_files = list(data_dir.glob("**/*.jsonl")) + list(data_dir.glob("**/*.parquet"))

    for data_file in data_files[:5]:  # Limit files per dataset
        try:
            if data_file.suffix == ".jsonl":
                examples.extend(_format_jsonl_file(data_file, record))
            elif data_file.suffix == ".parquet":
                examples.extend(_format_parquet_file(data_file, record))
        except Exception:
            continue

    return examples[:50000]  # Cap per dataset


def _format_jsonl_file(filepath: Path, record) -> list[dict[str, Any]]:
    """Convert JSONL data to instruction-output training pairs."""
    examples = []
    domain = record.domain.value if hasattr(record, 'domain') else "general"
    source_name = record.name if hasattr(record, 'name') else filepath.stem

    with open(filepath, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= 10000:  # Max records per file
                break
            try:
                item = json.loads(line.strip())
            except json.JSONDecodeError:
                continue

            text = item.get("text", "") or item.get("content", "") or item.get("abstract", "")
            title = item.get("title", "") or item.get("name", "")

            if len(text) < 100:
                continue

            # Generate instruction-output pairs based on content type
            if title:
                examples.append({
                    "instruction": f"Explain {title} in detail with practical examples.",
                    "output": text[:2000],
                    "domain": domain,
                    "source": source_name,
                })
                examples.append({
                    "instruction": f"What are the key concepts and applications of {title}?",
                    "output": f"Key concepts of {title}:\n\n{text[:1500]}",
                    "domain": domain,
                    "source": source_name,
                })

            # Code-related content
            code = item.get("code", "") or item.get("body", "")
            if code and len(code) > 50:
                examples.append({
                    "instruction": f"Review and explain this code for {title or source_name}:",
                    "output": f"```\n{code[:1500]}\n```\n\nExplanation: This code implements {title or 'the functionality'}.",
                    "domain": "code" if domain != "code" else domain,
                    "source": source_name,
                })

    return examples


def _format_parquet_file(filepath: Path, record) -> list[dict[str, Any]]:
    """Convert Parquet data to training examples."""
    examples = []
    try:
        import pyarrow.parquet as pq
        table = pq.read_table(filepath)
        df = table.to_pandas()

        domain = record.domain.value if hasattr(record, 'domain') else "general"
        source_name = record.name if hasattr(record, 'name') else filepath.stem

        # Try common column names
        text_col = next((c for c in ['text', 'content', 'abstract', 'body', 'passage']
                        if c in df.columns), None)
        title_col = next((c for c in ['title', 'name', 'header']
                         if c in df.columns), None)

        if not text_col:
            return []

        for _, row in df.head(5000).iterrows():
            text = str(row.get(text_col, ""))
            title = str(row.get(title_col, "")) if title_col else ""

            if len(text) < 100:
                continue

            if title:
                examples.append({
                    "instruction": f"Explain {title} in detail.",
                    "output": text[:2000],
                    "domain": domain,
                    "source": source_name,
                })

    except Exception:
        pass

    return examples[:20000]


def _format_massive_data(data_dir: Path, source_type: str) -> list[dict[str, Any]]:
    """Format data collected by the massive worker engine."""
    examples = []

    data_files = list(data_dir.glob("**/*.jsonl"))
    if not data_files:
        data_files = list(data_dir.glob("**/*.json"))

    for data_file in data_files[:10]:
        try:
            if data_file.suffix == ".jsonl":
                with open(data_file, "r", encoding="utf-8") as f:
                    for i, line in enumerate(f):
                        if i >= 5000:
                            break
                        try:
                            item = json.loads(line.strip())
                        except json.JSONDecodeError:
                            continue

                        text = item.get("text", "") or item.get("abstract", "") or item.get("content", "")
                        title = item.get("title", "") or item.get("name", "")

                        if len(text) < 80:
                            continue

                        examples.append({
                            "instruction": f"Tell me about {title or source_type}" if title
                                          else f"Explain this {source_type} content in detail.",
                            "output": text[:2000],
                            "domain": source_type,
                            "source": source_type,
                        })
        except Exception:
            continue

    return examples[:30000]


def _scan_collected_data() -> list[DatasetRecord]:
    """Scan D: drive for any collected data directories and create virtual records."""
    records = []
    known_dirs = ["arxiv", "openalex", "github", "pubmed", "stackexchange",
                  "crossref", "openlibrary", "gutendex", "worldbank", "europeana",
                  "gbif", "musicbrainz", "preprints", "rss", "semantic_scholar",
                  "pypi", "reddit", "github_code", "python_docs", "stackoverflow",
                  "conversations", "embeddings", "knowledge_graph", "benchmarks"]

    for dirname in known_dirs:
        data_dir = BASE_DATA_DIR / dirname
        if data_dir.exists() and any(data_dir.iterdir()):
            record = DatasetRecord(
                id=f"massive_{dirname}",
                name=f"Massive Engine: {dirname}",
                source_url="",
                phase=2,
                week=1,
                domain=DataDomain.OTHER,
                output_subdir=dirname,
                status=DownloadStatus.READY,
            )
            records.append(record)

    return records


# ── STEP 5: Generate Report ───────────────────────────────────────────

def step_generate_report(mgr: MetadataManager, format_stats: dict | None = None) -> dict[str, Any]:
    """Generate comprehensive pipeline status report."""
    log.step(5, 5, "Generating Pipeline Report")

    summary = mgr.summary()
    pipeline = mgr.pipeline_status()

    report = {
        "timestamp": datetime.now().isoformat(),
        "pipeline_overview": {
            "total_datasets": summary["total_datasets"],
            "ready_datasets": sum(1 for d in mgr.all() if d.is_ready),
            "pending_datasets": len(mgr.list_pending()),
            "error_datasets": len(mgr.list_errors()),
            "actual_records": summary["actual_records"],
            "ready_records": summary["ready_records"],
            "ready_gb": summary["ready_gb"],
        },
        "phases": pipeline["phases"],
        "by_status": summary["by_status"],
        "training_data": format_stats or {},
        "data_directories": [],
    }

    # Scan D: drive directories
    if BASE_DATA_DIR.exists():
        for item in sorted(BASE_DATA_DIR.iterdir()):
            if item.is_dir() and not item.name.startswith("."):
                file_count = sum(1 for _ in item.rglob("*") if _.is_file())
                total_size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                report["data_directories"].append({
                    "name": item.name,
                    "files": file_count,
                    "size_mb": round(total_size / (1024 * 1024), 1),
                })

    # Save report
    report_path = BASE_DATA_DIR / "pipeline_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Print report
    print(f"\n  {'═' * 60}")
    print(f"  PIPELINE REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  {'═' * 60}")

    ov = report["pipeline_overview"]
    print(f"\n  Overview:")
    print(f"    Total datasets  : {ov['total_datasets']}")
    print(f"    Ready           : {ov['ready_datasets']}")
    print(f"    Pending         : {ov['pending_datasets']}")
    print(f"    Errors          : {ov['error_datasets']}")
    print(f"    Actual records  : {ov['actual_records']:,}")
    print(f"    Ready records   : {ov['ready_records']:,}")
    print(f"    Ready data      : {ov['ready_gb']:.2f} GB")

    print(f"\n  Phase Progress:")
    for phase, info in report["phases"].items():
        pct = info["progress_pct"]
        bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
        print(f"    {phase:12s}: [{bar}] {pct}% ({info['ready']}/{info['datasets']})")

    if report["data_directories"]:
        print(f"\n  Collected Data on D: Drive:")
        for d in report["data_directories"][:20]:
            print(f"    {d['name']:25s}: {d['files']:>5} files, {d['size_mb']:>8.1f} MB")

    if format_stats and format_stats.get("domain_counts"):
        print(f"\n  Training Data by Domain:")
        for domain, count in format_stats["domain_counts"].items():
            print(f"    {domain:25s}: {count:,}")

    print(f"\n  Report saved: {report_path}")

    log.success("Pipeline report generated!")
    return report


# ── Main ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="PythonAI Full Pipeline — Data Collection to Training",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_full_pipeline.py                         # Full pipeline
  python run_full_pipeline.py --step collect          # Only download data
  python run_full_pipeline.py --step quality          # Only quality checks
  python run_full_pipeline.py --step format           # Only format training data
  python run_full_pipeline.py --step report           # Only show report
  python run_full_pipeline.py --weeks 1 2             # Collect weeks 1-2
  python run_full_pipeline.py --skip-download         # Skip downloads
  python run_full_pipeline.py --concurrent 10         # Max concurrent
        """,
    )
    parser.add_argument("--step", choices=["collect", "quality", "format", "report"],
                        help="Run only a specific step")
    parser.add_argument("--weeks", type=int, nargs="+", help="Specific Phase 1 weeks")
    parser.add_argument("--concurrent", type=int, default=4, help="Max concurrent downloads")
    parser.add_argument("--skip-download", action="store_true", help="Skip download step")
    parser.add_argument("--skip-quality", action="store_true", help="Skip quality checks")
    parser.add_argument("--skip-format", action="store_true", help="Skip training format step")

    args = parser.parse_args()

    # Banner
    print(f"\n{'═' * 70}")
    print(f"  PYTHONAI FULL PIPELINE")
    print(f"  Data Collection → Quality → Format → Training Ready")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Data Dir: {BASE_DATA_DIR}")
    print(f"{'═' * 70}")

    start_time = time.time()
    mgr = MetadataManager(storage_path=str(METADATA_PATH))
    format_stats = None

    if args.step == "collect":
        step_register_datasets(mgr)
        asyncio.run(step_download_datasets(mgr, weeks=args.weeks, concurrent=args.concurrent))

    elif args.step == "quality":
        step_quality_checks(mgr)

    elif args.step == "format":
        format_stats = step_format_training_data(mgr)

    elif args.step == "report":
        step_generate_report(mgr)

    else:
        # Full pipeline
        status = step_register_datasets(mgr)

        if not args.skip_download and status["pending"] > 0:
            asyncio.run(step_download_datasets(mgr, weeks=args.weeks, concurrent=args.concurrent))
        elif args.skip_download:
            log.info("Skipping downloads (--skip-download)")
        else:
            log.success("All datasets already downloaded!")

        if not args.skip_quality:
            step_quality_checks(mgr)
        else:
            log.info("Skipping quality checks (--skip-quality)")

        if not args.skip_format:
            format_stats = step_format_training_data(mgr)
        else:
            log.info("Skipping training format (--skip-format)")

        step_generate_report(mgr, format_stats)

    elapsed = time.time() - start_time
    print(f"\n{'═' * 70}")
    print(f"  Pipeline completed in {elapsed:.0f}s ({elapsed / 60:.1f}min)")
    print(f"  Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═' * 70}\n")


if __name__ == "__main__":
    main()
