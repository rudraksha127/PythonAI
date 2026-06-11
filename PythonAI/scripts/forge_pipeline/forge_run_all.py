#!/usr/bin/env python3
"""
forge_run_all.py — FORGE-OMEGA: COMPLETE TRAINING PIPELINE
===========================================================
Data Collection → Processing → Training → Deploy.
One command. Complete pipeline.

Usage:
    python forge_run_all.py                    # Full pipeline
    python forge_run_all.py --test             # Quick test mode
    python forge_run_all.py --start 3          # Resume from step 3
    python forge_run_all.py --skip 1           # Skip step 1
"""

from __future__ import annotations

import argparse
import importlib
import sys
import time
from pathlib import Path

# Ensure project root is on path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from forge_config import ForgeConfig

# ═══════════════════════════════════════════════════════════════════════════
# PIPELINE STEPS
# ═══════════════════════════════════════════════════════════════════════════

STEPS = [
    {
        "num": 0,
        "name": "System & Project Audit",
        "module": "forge_audit",
        "function": "scan_project",
        "kwargs": {},
    },
    {
        "num": 1,
        "name": "Data Collection",
        "module": "forge_step1_collect",
        "function": "run_collection",
        "kwargs": {},
    },
    {
        "num": 2,
        "name": "Data Processing & Cleaning",
        "module": "forge_step2_process",
        "function": "run_processing",
        "kwargs": {},
    },
    {
        "num": 3,
        "name": "Synthetic Data Generation",
        "module": "forge_step3_synthetic",
        "function": "run_synthetic_gen",
        "kwargs": {},
    },
    {
        "num": 4,
        "name": "Training Data Assembly",
        "module": "forge_step4_assemble",
        "function": "run_assemble",
        "kwargs": {},
    },
    {
        "num": 5,
        "name": "Model Training",
        "module": "forge_step5_train",
        "function": "run_training",
        "kwargs": {"test_mode": False},
    },
    {
        "num": 6,
        "name": "Model Evaluation",
        "module": "forge_step6_evaluate",
        "function": "run_evaluation",
        "kwargs": {},
    },
    {
        "num": 7,
        "name": "API Deployment",
        "module": "forge_step7_deploy",
        "function": "run_server",
        "kwargs": {},
    },
]


def run_step(step: dict, cfg: ForgeConfig, test_mode: bool = False):
    """Run a single pipeline step."""
    num = step["num"]
    name = step["name"]
    module_name = step["module"]
    func_name = step["function"]
    kwargs = dict(step["kwargs"])

    if test_mode and num == 5:
        kwargs["test_mode"] = True

    print(f"\n{'=' * 60}")
    print(f"  STEP {num}: {name}")
    print(f"{'=' * 60}")

    start = time.time()

    try:
        mod = importlib.import_module(module_name)
        func = getattr(mod, func_name)
        result = func(cfg, **kwargs) if kwargs else func(cfg)
        elapsed = time.time() - start
        print(f"  [OK] Step {num} complete ({elapsed / 60:.1f} min)")
        return True
    except Exception as e:
        elapsed = time.time() - start
        print(f"  [FAIL] Step {num} FAILED after {elapsed / 60:.1f} min: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="FORGE-OMEGA: Complete Training Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python forge_run_all.py                    # Full pipeline
  python forge_run_all.py --test             # Quick test mode
  python forge_run_all.py --start 3          # Resume from step 3
  python forge_run_all.py --skip 2 3         # Skip steps 2 and 3
        """,
    )
    parser.add_argument("--test", action="store_true", help="Quick test mode (2 training steps)")
    parser.add_argument("--start", type=int, default=0, help="Start from step number")
    parser.add_argument("--skip", type=int, nargs="+", default=[], help="Step numbers to skip")
    parser.add_argument("--until", type=int, default=7, help="Run until step number (inclusive)")

    args = parser.parse_args()

    print("=" * 70)
    print("      FORGE-OMEGA: COMPLETE TRAINING PIPELINE")
    print("      Data Collection -> Processing -> Training -> Deploy")
    print("=" * 70)

    # Initialize config
    cfg = ForgeConfig()
    cfg.save()

    print(f"Hardware: {cfg.hardware_profile.get('tier', 'unknown')} tier")
    print(f"Model:    {cfg.base_model}")
    print(f"CUDA:     {cfg.hardware_profile.get('has_cuda', False)}")
    print(f"RAM:      {cfg.hardware_profile.get('free_ram_gb', 0):.1f} GB free")
    print(f"Steps:    {args.start} -> {args.until}" + (" (TEST MODE)" if args.test else ""))
    if args.skip:
        print(f"Skipping: steps {args.skip}")

    start_total = time.time()

    for step in STEPS:
        num = step["num"]

        # Respect --start and --until
        if num < args.start:
            print(f"  [SKIP] Step {num}: {step['name']} (skipped: before --start)")
            continue
        if num > args.until:
            print(f"  [SKIP] Step {num}: {step['name']} (skipped: after --until)")
            continue

        # Respect --skip
        if num in args.skip:
            print(f"  [SKIP] Step {num}: {step['name']} (skipped by --skip)")
            continue

        success = run_step(step, cfg, test_mode=args.test)
        if not success:
            print(f"\n  Pipeline stopped at step {num}. To resume:")
            print(f"    python forge_run_all.py --start {num}")
            break

    total_time = (time.time() - start_total) / 3600
    print("=" * 70)
    print("              PIPELINE COMPLETE")
    print(f"  Total time: {total_time:.1f} hours")
    print(f"  Your model is ready at: {cfg.final_model_dir}")
    print("  Test API: python forge_step7_deploy.py")
    print("=" * 70)


if __name__ == "__main__":
    main()
