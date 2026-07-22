from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.cli.common import ROOT, VERSION, project_python, run
from src.utils.models import (
    audit_project,
    cleanup_dry_run,
    dataset_profile,
    discover_qwen_hf_candidates,
    hardware_profile,
    list_hf_cached_models,
    list_ollama_models,
)


def status(args: argparse.Namespace) -> int:
    python_exe = project_python()
    audit = audit_project()
    cleanup = cleanup_dry_run()
    dataset = dataset_profile()
    hardware = hardware_profile(python_exe)
    ollama_models = list_ollama_models()
    hf_models = list_hf_cached_models()
    qwen_hf = discover_qwen_hf_candidates()

    adapter = ROOT / "checkpoints" / "local_auto_model" / "adapter_model.safetensors"
    rag_db = ROOT / "python_brain_godmode" / "chroma.sqlite3"

    watch = getattr(args, "watch", False)
    if watch:
        import time

        try:
            while True:
                print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] PythonAI Status (--watch, Ctrl+C to stop)")
                print("=" * 72)
                print(f"Project files: {audit['total_files']} ({audit['total_mb']} MB)")
                print(f"Dataset      : {dataset['rows']} rows, avg {dataset['length_avg']} chars")
                print(f"Adapter      : {'ready' if adapter.exists() else 'missing'}")
                print(f"RAG DB       : {'ready' if rag_db.exists() else 'missing'}")
                print(f"RAM          : {hardware.get('ram_gb')} GB")
                time.sleep(args.watch_interval)
        except KeyboardInterrupt:
            print("\n[Bye] Exiting watch mode.")
            return 0

    if getattr(args, "json_output", False):
        info = {
            "python": str(python_exe),
            "project_files": audit["total_files"],
            "project_mb": audit["total_mb"],
            "cleanup_targets": cleanup["candidate_count"],
            "cleanup_mb": cleanup["recoverable_mb"],
            "dataset_rows": dataset["rows"],
            "dataset_avg_chars": dataset["length_avg"],
            "cuda": hardware.get("cuda_available"),
            "gpu": hardware.get("gpu_name"),
            "ram_gb": hardware.get("ram_gb"),
            "ollama_models": ollama_models,
            "hf_models": hf_models,
            "qwen_candidates": qwen_hf,
            "adapter_ready": adapter.exists(),
            "rag_db_ready": rag_db.exists(),
        }
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0

    print(f"PythonAI v{VERSION} — Status")
    print("=" * 72)
    print(f"Python       : {python_exe}")
    print(f"Project files: {audit['total_files']} ({audit['total_mb']} MB, excluding .venv/.git)")

    if getattr(args, "verbose", False):
        print("  Largest files:")
        for f in audit.get("largest_files", [])[:5]:
            print(f"    {f['path']}: {f['bytes'] / 1024:.1f} KB")
        print("  By extension:")
        for ext, info in list(audit.get("by_extension", {}).items())[:8]:
            print(f"    {ext or '(none)':10s}: {info['files']:4d} files, {info['bytes'] / 1024:.1f} KB")

    print(f"Cleanup      : {cleanup['candidate_count']} targets, {cleanup['recoverable_mb']} MB")
    print(f"Dataset      : {dataset['rows']} rows, avg {dataset['length_avg']} chars")
    print(f"CUDA         : {hardware.get('cuda_available')} ({hardware.get('gpu_name')})")
    print(f"RAM          : {hardware.get('ram_gb')} GB")
    print(f"Ollama       : {ollama_models or 'none'}")
    print(f"HF cache     : {hf_models or 'none'}")
    print(f"HF Qwen      : {qwen_hf or 'none'}")
    print(f"Adapter      : {'ready' if adapter.exists() else 'missing'}")
    print(f"RAG DB       : {'ready' if rag_db.exists() else 'missing'}")

    if not qwen_hf:
        print("\nNext real-training step: prepare/download an HF-format Qwen model, then run:")
        print(r"  .\.venv\Scripts\python.exe -m src.training.run --mode qwen --max-steps 50")
    return 0


def clean(args: argparse.Namespace) -> int:
    command = [str(project_python()), "-m", "src.utils.cleanup"]
    if args.apply:
        command.append("--apply")
    return run(command)


def forge_cmd(args: argparse.Namespace) -> int:
    """
    ForgeAI: Acceptance rate tracking & dashboard (MIT SEAL architecture).

    Generates interactive HTML dashboards from CaptureEngine signal data,
    showing acceptance rate curves, signal breakdown, and training history.
    """

    from src.learning.capture_engine import CaptureEngine
    from src.learning.forge_dashboard import generate_dashboard

    if args.action == "dashboard":
        generate_dashboard(
            output_path=args.output,
            weeks=args.weeks,
            demo=args.demo,
        )
        if args.open:
            import webbrowser

            path = Path(args.output).resolve()
            webbrowser.open(f"file:///{path}")
            print(f"[ForgeAI] Opened dashboard: {path}")
        return 0

    elif args.action == "stats":
        engine = CaptureEngine()
        stats = engine.get_statistics()
        print(json.dumps(stats, indent=2, default=str))

        rates = engine.get_acceptance_rate(days=7)
        if rates:
            print("\nLast 7 days acceptance rate:")
            print(f"  {'Date':14s} {'Rate':8s} {'Accept':8s} {'Reject':8s} {'Edit':8s}")
            print(f"  {'-' * 14} {'-' * 8} {'-' * 8} {'-' * 8} {'-' * 8}")
            for r in rates:
                print(
                    f"  {r['date']:14s} {r['acceptance_rate']:6.1f}%  {r['accepts']:5d}   {r['rejects']:5d}   {r['edits']:5d}"
                )
        else:
            print("\n  No recent data. Use CaptureEngine to start collecting signals.")
        return 0

    return 1


def learn_cmd(args: argparse.Namespace) -> int:
    """Learning Engine CLI hooks."""

    if args.action == "daemon":
        return run([str(project_python()), "-m", "src.learning.daemon", "--interval", str(args.interval)])

    if args.action == "sync-so":
        return run(
            [
                str(project_python()),
                "-c",
                "from src.learning.so_sync import sync_stackoverflow; print(sync_stackoverflow(pages=1))",
            ]
        )

    if args.action == "eval":
        return run(
            [
                str(project_python()),
                "-c",
                "from src.learning.self_eval import run_self_evaluation; print(run_self_evaluation(sample_size=10))",
            ]
        )

    return 1


def recommend_cmd(args: argparse.Namespace) -> int:
    """
    Search and recommend PyPI packages from 853,111 package index.
    """
    from src.recommender.pypi_recommender import PyPIPackageRecommender

    rec = PyPIPackageRecommender()
    query = args.query
    limit = getattr(args, "limit", 10)
    results = rec.recommend(query, limit=limit)

    print(f"\nPyPI Package Recommendations for '{query}'")
    print("=" * 60)

    curated = results.get("curated_recommendations", [])
    if curated:
        print("\nTop Curated Packages:")
        for c in curated:
            print(f"  - {c['name']:25s} : {c['description']}")

    matches = results.get("pypi_matches", [])
    if matches:
        print(f"\nMatching Packages in 853,111 PyPI Index (total indexed: {results.get('total_pypi_indexed', 0):,}):")
        for m in matches:
            print(f"  - {m['name']}")

    if not curated and not matches:
        print("  No matching packages found.")

    return 0
