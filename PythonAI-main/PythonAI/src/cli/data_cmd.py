from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.cli.common import ROOT, project_python, run
from src.utils.models import dataset_profile


def dataset_info(args: argparse.Namespace) -> int:
    profile = dataset_profile(ROOT / args.path)
    print(json.dumps(profile, ensure_ascii=False, indent=2))
    return 0


def augment(args: argparse.Namespace) -> int:
    command = [
        str(project_python()),
        "-m",
        "src.data.augmenter",
        "--model",
        args.model,
        "--limit",
        str(args.limit),
        "--offset",
        str(args.offset),
        "--num-ctx",
        str(args.num_ctx),
        "--num-predict",
        str(args.num_predict),
        "--pairs-per-chunk",
        str(args.pairs_per_chunk),
        "--output",
        args.output,
    ]
    if args.merge:
        command.append("--merge")
    if args.dry_run:
        command.append("--dry-run")
    return run(command)


def merge_data(args: argparse.Namespace) -> int:
    return run(
        [
            str(project_python()),
            "-m",
            "src.data.merger",
            "--base",
            args.base,
            "--add",
            args.add,
            "--output",
            args.output,
        ]
    )


def generate_api(args: argparse.Namespace) -> int:
    cmd = [
        str(project_python()),
        "-m",
        "src.data.api_dataset_gen",
        "--workers",
        str(args.workers),
    ]
    if args.resume:
        cmd.append("--resume")
    if args.limit > 0:
        cmd.extend(["--limit", str(args.limit)])
    if args.so_only:
        cmd.append("--so-only")
    if args.github_only:
        cmd.append("--github-only")
    if args.no_llm:
        cmd.append("--no-llm")
    return run(cmd)


def hf_collect(args: argparse.Namespace) -> int:
    """Download Python code SFT datasets from HuggingFace."""
    from src.data.hf_collector import HF_DATASETS, print_stats
    from src.data.hf_collector import run as hf_run

    if args.list:
        print("[HuggingFace Datasets Available]")
        print("=" * 60)
        for key, info in HF_DATASETS.items():
            print(f"  {key:35s} {info['description']}")
            print(f"  {'':35s} Path: {info['path']}")
            print()
        return 0

    if args.stats:
        print_stats(args.output)
        return 0

    datasets = args.datasets if args.datasets else None
    result = hf_run(datasets=datasets, max_rows=args.max_rows, output=args.output)
    total = result.get("total", 0)
    if total == 0:
        print(
            "[WARN] No chunks were collected. Check your internet connection or try --list to see available datasets."
        )
        return 1
    print(f"Done. {total:,} chunks collected.")
    return 0


def collect_data_cmd(args: argparse.Namespace) -> int:
    """Collect data and store on D: drive."""
    cmd = [str(project_python()), "-m", "src.data.d_drive_collector"]
    if args.all:
        cmd.append("--all")
    if args.setup:
        cmd.append("--setup")
    if args.source:
        cmd.extend(["--source", args.source])
    cmd.extend(["--so-pages", str(args.so_pages)])
    cmd.extend(["--github-pages", str(args.github_pages)])
    return run(cmd)


def discovery_cmd(args: argparse.Namespace) -> int:
    """Discovery Engine — automated dataset discovery."""
    from src.data.discovery import (
        PriorityRanker,
        auto_discover,
        check_for_new_papers,
        discover_github_repos,
        discover_government_data,
        print_ranking,
    )
    from src.data.metadata import MetadataManager

    if args.action == "scan":
        print("[Discovery] Scanning all sources for new datasets...\n")
        results = auto_discover(
            hf_limit=args.hf_limit,
            arxiv_limit=args.arxiv_limit,
            gov_limit=args.gov_limit,
            github_limit=args.github_limit,
            top_n=args.top_n,
            verbose=args.verbose,
        )
        print()
        print_ranking(results)
        print(f"\nTotal ranked: {len(results)}")

        if args.register and results:
            mgr = MetadataManager()
            records = [s.record for s in results if s.priority in ("critical", "high")]
            if records:
                mgr.register_many(records)
                print(f"\nRegistered {len(records)} high-priority datasets to metadata registry.")
        return 0

    if args.action == "papers":
        print("[Discovery] Checking arXiv for new papers...")
        records = check_for_new_papers(
            categories=args.categories or None,
            max_results=args.arxiv_limit,
            verbose=True,
        )
        if not records:
            print("  No papers found (or arXiv API unavailable).")
        return 0

    if args.action == "gov":
        print("[Discovery] Searching government data portals...")
        records = discover_government_data(
            keywords=args.keywords or None,
            limit=args.gov_limit,
            verbose=True,
        )
        if not records:
            print("  No datasets found (or portal unavailable).")
        return 0

    if args.action == "github":
        print("[Discovery] Scanning trending GitHub repos...")
        records = discover_github_repos(
            languages=args.languages or None,
            limit=args.github_limit,
            verbose=True,
        )
        if not records:
            print("  No repos found (or GitHub API unavailable).")
        return 0

    if args.action == "rank":
        mgr = MetadataManager()
        records = mgr.all()
        if not records:
            print("[Discovery] No datasets in registry. Run 'python -m src.cli data init' first.")
            return 1

        ranker = PriorityRanker()
        scored = ranker.score(records)
        print(f"[Discovery] Ranking {len(records)} registered datasets:\n")
        print_ranking(scored[: args.top_n])

        tiers = {}
        for s in scored:
            tiers[s.priority] = tiers.get(s.priority, 0) + 1
        print("\nSummary by priority tier:")
        for tier in ("critical", "high", "medium", "low"):
            if tier in tiers:
                print(f"  {tier:10s}: {tiers[tier]}")
        return 0

    return 1


def phase1_cmd(args: argparse.Namespace) -> int:
    """Phase 1 data collection commands."""
    from src.data.downloader import BASE_DATA_DIR, DownloadOrchestrator
    from src.data.metadata import MetadataManager
    from src.data.phase1 import generate_phase1_datasets, phase1_stats
    from src.data.quality import QualityPipeline

    if args.action == "init":
        mgr = MetadataManager()
        records = generate_phase1_datasets()
        mgr.register_many(records)
        stats = mgr.summary()
        print(f"[Phase1] Initialized metadata registry with {stats['total_datasets']} datasets over 4 weeks")
        for phase in range(1, 5):
            ds = mgr.list_by_phase(phase)
            ready = sum(1 for d in ds if d.is_ready)
            print(f"  Phase {phase}: {len(ds)} datasets ({ready} ready)")
        print(f"  Estimated total records: {stats['estimated_records']:,}")
        print(f"  Registry path: {mgr.storage_path}")
        print(f"  Data directory: {BASE_DATA_DIR}")
        print()
        print("  Next: Run 'python -m src.cli data phase1 status' to see collection status.")
        print("        Run 'python -m src.cli data phase1 download --week 1' to start downloading.")
        return 0

    if args.action == "status":
        mgr = MetadataManager()
        stats = mgr.summary()
        pipeline = mgr.pipeline_status()
        print("[Phase1] Collection Status")
        print(f"  Total datasets : {stats['total_datasets']}")
        print("  By status:")
        for status, count in sorted(stats["by_status"].items()):
            print(f"    {status:20s}: {count}")
        print("  By phase:")
        for phase, count in sorted(stats["by_phase"].items()):
            pp = pipeline["phases"].get(f"phase_{phase}", {})
            ready = pp.get("ready", 0)
            pct = pp.get("progress_pct", 0)
            print(f"    Phase {phase}: {count} datasets ({ready} ready, {pct}%)")
        print(f"  Ready records  : {stats['ready_records']:,}")
        print(f"  Ready size     : {stats['ready_gb']} GB")
        if stats.get("errors"):
            print(f"  Errors ({len(stats['errors'])}):")
            for err in stats["errors"][:5]:
                print(f"    - {err['id']}: {err['error'][:100]}")
        print()
        for w in range(1, 5):
            wp = mgr.week_progress(1, w)
            if wp["total"] > 0:
                print(f"  Week {w}: {wp['done']}/{wp['total']} done ({wp['progress_pct']}%)")
        return 0

    if args.action == "stats":
        stats = phase1_stats()
        print("Phase 1 — Foundation Data Collection")
        print(f"  Total datasets    : {stats['total_datasets']}")
        print(f"  Estimated records : {stats['estimated_total_records']:,}")
        print(f"  Estimated size    : {stats['estimated_total_gb']} GB")
        print()
        print("  By Week:")
        for w, c in sorted(stats["by_week"].items()):
            print(f"    Week {w}: {c} datasets")
        print()
        print("  By Domain:")
        for d, c in sorted(stats["by_domain"].items()):
            print(f"    {d}: {c} datasets")
        return 0

    if args.action == "list":
        mgr = MetadataManager()
        if args.week:
            records = mgr.list_by_week(1, args.week)
        elif args.status:
            records = mgr.list_by_status(args.status)
        elif args.domain:
            from src.data.metadata import DataDomain

            records = mgr.list_by_domain(DataDomain(args.domain))
        else:
            records = mgr.list_by_phase(1)

        print(f"{'ID':40s} {'Status':16s} {'Lang':8s} {'Records':>12s} {'GB':>8s}")
        print(f"{'=' * 40} {'=' * 16} {'=' * 8} {'=' * 12} {'=' * 8}")
        for r in records:
            lang_str = ",".join(r.languages)[:8]
            rec_str = f"{r.actual_record_count:,}" if r.actual_record_count > 0 else "-"
            gb_str = f"{r.size_mb / 1024:.1f}" if r.actual_size_bytes > 0 else "-"
            print(f"{r.id:40s} {r.status.value:16s} {lang_str:8s} {rec_str:>12s} {gb_str:>8s}")
        print(f"\nTotal: {len(records)} datasets")
        return 0

    if args.action == "download":
        import asyncio

        mgr = MetadataManager()

        orch = DownloadOrchestrator(
            metadata_mgr=mgr,
            max_concurrent=args.workers,
            log_callback=lambda msg: print(msg),
        )

        async def run_downloads():
            try:
                if args.dataset:
                    results = [await orch.download_one(args.dataset)]
                elif args.week:
                    results = await orch.download_week(1, args.week)
                else:
                    results = await orch.download_all_phase(1)
            finally:
                await orch.close()
            return results

        results = asyncio.run(run_downloads())

        success = sum(1 for r in results if "error" not in r)
        failed = sum(1 for r in results if "error" in r)
        total_records = sum(r.get("records", 0) for r in results if "error" not in r)

        print(f"\n[Download Complete] {success} succeeded, {failed} failed, {total_records:,} records")
        for r in results:
            if "error" in r:
                print(f"  ✗ {r['dataset_id']}: {r['error'][:80]}")
            else:
                records = r.get("records", 0)
                print(f"  ✓ {r['dataset_id']}: {records:,} records")
        return 0 if failed == 0 else 1

    if args.action == "quality":
        mgr = MetadataManager()
        dataset_ids = args.datasets if args.datasets else [d.id for d in mgr.list_by_status("downloaded")]

        qp = QualityPipeline(
            min_text_length=args.min_length,
            quality_threshold=args.threshold,
            metadata_mgr=mgr,
        )

        for did in dataset_ids:
            record = mgr.get(did)
            if not record:
                print(f"[Error] Dataset '{did}' not found")
                continue

            if not args.input_dir:
                import os as os_mod

                data_dir = os_mod.environ.get("DATA_DIR", "D:/PythonAI_Data")
                dataset_path = Path(data_dir) / record.output_subdir / f"{did}.jsonl"
            else:
                dataset_path = Path(args.input_dir) / f"{did}.jsonl"

            if not dataset_path.exists():
                print(f"[Skip] {did}: data file not found at {dataset_path}")
                continue

            print(f"[Quality] Running pipeline on {did}...")
            stats = qp.run_file(dataset_path, did)
            if "error" in stats:
                print(f"  Error: {stats['error']}")
                continue

            print(f"  Input: {stats['total_input']:,} records")
            print(f"  Output: {stats['total_output']:,} records")
            print(f"  Filtered: {stats['filtered_pct']}%")
            print(f"  Avg quality score: {stats.get('avg_quality_score', 'N/A')}")
            for stage_name, stage_data in stats.get("stages", {}).items():
                if isinstance(stage_data, dict):
                    removed = stage_data.get("removed", 0)
                    if removed:
                        print(f"    {stage_name}: removed {removed}")
            print(f"  Elapsed: {stats.get('elapsed_seconds', '?')}s")
        return 0

    return 1
