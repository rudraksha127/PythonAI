#!/usr/bin/env python3
"""
START DATA COLLECTION — Phase 1 + Massive Engine
=================================================
Main entry point for the PythonAI data collection pipeline.

Usage:
    python start_data_collection.py                    # Register datasets + start engine
    python start_data_collection.py --phase1-only       # Only download Phase 1 datasets
    python start_data_collection.py --massive-only      # Only run massive worker engine
    python start_data_collection.py --status            # Show current pipeline status
    python start_data_collection.py --quick-test        # Quick test: download 1 small dataset
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure project root is on PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Environment setup
os.environ.setdefault("DATA_DIR", "D:/PythonAI_Data")

from src.data.metadata import MetadataManager, DownloadStatus
from src.data.phase1 import generate_phase1_datasets, phase1_stats
from src.data.massive_config import generate_all_configs, get_source_type_breakdown
from src.data.massive_engine import MassiveWorkerEngine, BASE_DATA_DIR


# ── Logging ──────────────────────────────────────────────────────────

def print_banner():
    banner = """
    ================================================================
         PYTHONAI DATA COLLECTION PIPELINE
         DataForge-GodMode: Machines of Loving Grace
    ================================================================
    """
    print(banner)
    print(f"  Started at : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Data dir   : {os.environ.get('DATA_DIR', 'D:/PythonAI_Data')}")
    print()


def print_separator(title: str):
    print(f"\n  ── {title} ─{'─' * (60 - len(title))}\n")


# ── Phase 1 Registration ────────────────────────────────────────────

def register_phase1_datasets(mgr: MetadataManager) -> None:
    """Register all Phase 1 datasets with the metadata manager."""
    print_separator("Phase 1 — Registering Datasets")
    records = generate_phase1_datasets()
    for record in records:
        mgr.register(record)

    stats = phase1_stats()
    print(f"  Registered {stats['total_datasets']} datasets across 4 weeks")
    print(f"  Estimated total records: {stats['estimated_total_records']:,}")
    print(f"  Estimated total size   : {stats['estimated_total_gb']} GB")
    print()
    print("  By Week:")
    for w in range(1, 5):
        count = sum(1 for r in records if r.week == w)
        print(f"    Week {w}: {count} datasets")
    print()
    print("  By Domain:")
    from collections import Counter
    domain_counts = Counter(r.domain.value for r in records)
    for domain, count in sorted(domain_counts.items()):
        print(f"    {domain}: {count}")
    print()


# ── Status Display ──────────────────────────────────────────────────

def show_status(mgr: MetadataManager) -> None:
    """Display current pipeline status."""
    print_separator("Pipeline Status")
    summary = mgr.summary()
    print(f"  Total datasets   : {summary['total_datasets']}")
    print(f"  Actual records   : {summary['actual_records']:,}")
    print(f"  Ready records    : {summary['ready_records']:,}")
    print(f"  Ready data       : {summary['ready_gb']} GB")
    print()
    print("  By Status:")
    for status, count in sorted(summary['by_status'].items()):
        print(f"    {status}: {count}")
    print()
    if summary['errors']:
        print("  Errors:")
        for err in summary['errors'][:10]:
            print(f"    ✗ {err['id']}: {err['error']}")

    # Pipeline health
    pipeline = mgr.pipeline_status()
    print("\n  Phases:")
    for phase, info in pipeline['phases'].items():
        print(f"    {phase}: {info['datasets']} datasets, "
              f"{info['ready']} ready, "
              f"{info['errors']} errors, "
              f"progress: {info['progress_pct']}%")

    # Week-level progress for Phase 1
    print("\n  Phase 1 Week Progress:")
    for w in range(1, 5):
        prog = mgr.week_progress(1, w)
        bar = "█" * int(prog['progress_pct'] / 10) + "░" * (10 - int(prog['progress_pct'] / 10))
        print(f"    Week {w}: [{bar}] {prog['progress_pct']}%  "
              f"({prog['done']}/{prog['total']} done, "
              f"{prog.get('records_collected', 0):,} records)")


# ── Massive Engine Runner ──────────────────────────────────────────

async def run_massive_engine(mgr: MetadataManager, max_concurrent: int = 20) -> None:
    """Start the continuous massive data collection engine."""
    print_separator("Massive Worker Engine")
    configs = generate_all_configs()
    breakdown = get_source_type_breakdown()
    print(f"  Total source configs: {len(configs)}")
    print(f"  Source types:")
    for stype, count in sorted(breakdown.items()):
        print(f"    {stype:20s}: {count}")
    print(f"  Max concurrent     : {max_concurrent}")
    print()

    async def log_callback(**kw):
        level = kw.get("level", "info")
        msg = kw.get("msg", "")
        icon = {"info": "ℹ", "warn": "⚠", "error": "✗", "success": "✓"}.get(level, "•")
        print(f"  {icon} {msg}")

    async def progress_callback(**kw):
        source = kw.get("source", "?")
        source_type = kw.get("source_type", "?")
        records = kw.get("records", 0)
        total = kw.get("total_collected", 0)
        print(f"  ✓ {source_type}/{source}: {records} records (total: {total:,})")

    engine = MassiveWorkerEngine(
        max_concurrent=max_concurrent,
        log_callback=log_callback,
        progress_callback=progress_callback,
    )

    try:
        await engine.run_forever()
    except KeyboardInterrupt:
        print("\n  ⏹ Shutting down engine...")
        await engine.close()
        print("  ✓ Engine stopped.")


# ── Quick Test ──────────────────────────────────────────────────────

async def quick_test(mgr: MetadataManager) -> None:
    """Quick test: download a small Phase 1 dataset to verify the pipeline."""
    print_separator("Quick Test — Verifying Pipeline")

    # Find a small dataset to test
    test_datasets = [
        "flores200_dev",     # Very small (2000 records)
        "numinamath",        # Small (860K records, limited to 100K)
        "wikipedia_hi",      # Small (160K records)
    ]

    from src.data.downloader import DownloadOrchestrator

    def log(msg):
        print(f"  {msg}")

    def progress(ds_id, current, total):
        if current % 10000 == 0:
            print(f"    {ds_id}: {current}/{total}")

    orch = DownloadOrchestrator(
        metadata_mgr=mgr,
        max_concurrent=2,
        progress_callback=progress,
        log_callback=log,
    )

    for ds_id in test_datasets:
        record = mgr.get(ds_id)
        if not record:
            print(f"  ✗ Dataset '{ds_id}' not found in registry")
            continue
        if record.is_ready:
            print(f"  ✓ {ds_id}: already downloaded ({record.actual_record_count:,} records)")
            continue

        print(f"  → Downloading {ds_id}...")
        result = await orch.download_one(ds_id)
        status = result.get("status", result.get("error", "unknown"))
        print(f"  {'✓' if status == 'downloaded' else '✗'} {ds_id}: {status}")
        if "records" in result:
            print(f"    Records: {result.get('records', 0):,}")
        if "error" in result:
            print(f"    Error: {result['error']}")

    await orch.close()
    print("\n  ✓ Quick test complete.")


# ── Phase 1 Runner ──────────────────────────────────────────────────

async def run_phase1(mgr: MetadataManager, weeks: list[int] | None = None) -> None:
    """Run Phase 1 downloads for specified weeks (or all 4 weeks)."""
    from src.data.downloader import DownloadOrchestrator

    phase = 1
    weeks_to_run = weeks or [1, 2, 3, 4]

    print_separator(f"Phase 1 — Downloading Week(s) {', '.join(str(w) for w in weeks_to_run)}")

    def log(msg: str):
        print(f"  {msg}")

    def progress(ds_id: str, current: int, total: int):
        label = f"  {ds_id}: {current:,}"
        if total:
            label += f" / {total:,}"
        if current % 50000 == 0:
            print(label)


    orch = DownloadOrchestrator(
        metadata_mgr=mgr,
        max_concurrent=3,
        progress_callback=progress,
        log_callback=log,
    )

    start_time = time.time()
    total_records = 0
    total_errors = 0

    for week in weeks_to_run:
        print(f"\n  → Week {week} — Starting...")
        results = await orch.download_week(phase, week)
        for r in results:
            if "records" in r:
                total_records += r.get("records", 0)
            if "error" in r:
                total_errors += 1
                print(f"    ✗ {r.get('dataset_id', '?')}: {r['error'][:80]}")

    elapsed = time.time() - start_time
    print(f"\n  ✓ Phase 1 Week(s) {', '.join(str(w) for w in weeks_to_run)} complete!")
    print(f"    Datasets: {len(weeks_to_run) * 10}+")
    print(f"    Records : {total_records:,}")
    print(f"    Errors  : {total_errors}")
    print(f"    Time    : {elapsed:.0f}s ({elapsed/60:.1f}min)")

    await orch.close()


# ── Main ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="PythonAI Data Collection Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python start_data_collection.py                         # Start engine
  python start_data_collection.py --phase1-only           # Download Phase 1
  python start_data_collection.py --massive-only          # Start massive engine
  python start_data_collection.py --status                # Show pipeline status
  python start_data_collection.py --quick-test            # Quick pipeline test
  python start_data_collection.py --weeks 1 2             # Download weeks 1-2
        """,
    )
    parser.add_argument("--phase1-only", action="store_true", help="Only download Phase 1 datasets")
    parser.add_argument("--massive-only", action="store_true", help="Only run massive worker engine")
    parser.add_argument("--status", action="store_true", help="Show pipeline status")
    parser.add_argument("--quick-test", action="store_true", help="Quick test download")
    parser.add_argument("--weeks", type=int, nargs="+", help="Specific Phase 1 weeks to download")
    parser.add_argument("--concurrent", type=int, default=20, help="Max concurrent downloads (default: 20)")

    args = parser.parse_args()

    print_banner()

    # Initialize metadata manager
    mgr = MetadataManager(storage_path="D:/PythonAI_Data/.metadata_registry.json")

    # Register Phase 1 datasets (idempotent — skips already-registered)
    register_phase1_datasets(mgr)

    # Route commands
    if args.status:
        show_status(mgr)

    elif args.quick_test:
        asyncio.run(quick_test(mgr))
        show_status(mgr)

    elif args.phase1_only:
        weeks = args.weeks or [1, 2, 3, 4]
        asyncio.run(run_phase1(mgr, weeks=weeks))
        show_status(mgr)

    elif args.massive_only:
        asyncio.run(run_massive_engine(mgr, max_concurrent=args.concurrent))

    elif args.weeks:
        asyncio.run(run_phase1(mgr, weeks=args.weeks))
        show_status(mgr)

    else:
        # Default: Show status + start massive engine
        show_status(mgr)
        print("\n")
        print("  ⏳ Starting continuous data collection engine...")
        print("  Press Ctrl+C to stop.\n")
        asyncio.run(run_massive_engine(mgr, max_concurrent=args.concurrent))


if __name__ == "__main__":
    main()
