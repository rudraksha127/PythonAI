"""
forge_audit.py — PHASE 0: Full System & Project Audit
======================================================
Run FIRST. Understand everything before touching anything.
Performs: hardware audit, project structure scan, duplicate detection, safe cleanup, data analysis.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import platform
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import psutil
from rich.console import Console
from rich.table import Table

from forge_config import ForgeConfig

console = Console()


# ── HARDWARE AUDIT ──────────────────────────────────────────────────────────


def audit_hardware(cfg: ForgeConfig) -> dict:
    """Audit CPU, RAM, Disk, GPU and return recommended config."""
    print("\n== HARDWARE ==================================================")

    hw = cfg.hardware_profile

    cpu = platform.processor()
    cores = hw.get("cpu_cores", 0)
    print(f"CPU:     {cpu}")
    print(f"Cores:   {cores} physical")

    ram_total = hw.get("total_ram_gb", 0)
    ram_free = hw.get("free_ram_gb", 0)
    print(f"RAM:     {ram_total:.1f} GB total / {ram_free:.1f} GB free")

    disk_free = hw.get("disk_free_gb", 0)
    disk_total = psutil.disk_usage(str(cfg.root_dir)).total / (1024**3)
    print(f"DISK:    {disk_free:.1f} GB free / {disk_total:.1f} GB total")

    if hw.get("has_cuda"):
        print(f"GPU:     {hw.get('gpu_name')} - {hw.get('vram_gb', 0):.1f} GB VRAM")
        vram = hw.get("vram_gb", 0)
        if vram >= 40:
            rec = "Full 70B fine-tune possible. batch=8, bf16"
        elif vram >= 24:
            rec = "Full 13B or QLoRA 70B. batch=4, bf16"
        elif vram >= 12:
            rec = "QLoRA 7B. batch=2, fp16"
        elif vram >= 6:
            rec = "QLoRA 3B. batch=1, fp16, grad_accum=16"
        else:
            rec = "CPU mode recommended. TinyLlama-1.1B or Phi-2"
        print(f"         => RECOMMENDED: {rec}")
    else:
        print("GPU:     None detected - CPU training only")
        print("         => RECOMMENDED: TinyLlama-1.1B-Chat, batch=1, LoRA rank=4")

    return hw


# ── PROJECT AUDIT ───────────────────────────────────────────────────────────


def audit_project(cfg: ForgeConfig) -> tuple[list[dict], dict, list[dict]]:
    """Scan the project for files, grouped by type."""
    print("\n== PROJECT STRUCTURE =========================================")
    root_path = Path(cfg.root_dir)

    all_files = []
    excluded_dirs = {".git", "__pycache__", ".venv", "node_modules", ".gemini", "forge_workspace"}

    for f in root_path.rglob("*"):
        if f.is_file():
            # Skip excluded dirs
            if any(part in excluded_dirs for part in f.relative_to(root_path).parts):
                continue
            size = f.stat().st_size
            all_files.append(
                {
                    "path": str(f.relative_to(root_path)),
                    "size_kb": round(size / 1024, 2),
                    "ext": f.suffix.lower(),
                    "name": f.name,
                }
            )

    by_ext = defaultdict(list)
    for f in all_files:
        by_ext[f["ext"]].append(f)

    total_mb = sum(f["size_kb"] for f in all_files) / 1024
    print(f"Total files: {len(all_files)}")
    print(f"Total size:  {total_mb:.1f} MB")
    print(f"\nBy type:")
    for ext, files in sorted(by_ext.items(), key=lambda x: -sum(f["size_kb"] for f in x[1])):
        sz = sum(f["size_kb"] for f in files) / 1024
        if sz > 0.01:
            print(f"  {ext or '(none)':12} {len(files):5} files  {sz:8.1f} MB")

    # Important files summary
    important = {
        "Training scripts": [
            f for f in all_files if any(k in f["name"].lower() for k in ["train", "finetune", "fine_tune"])
        ],
        "Config files": [
            f for f in all_files if f["ext"] in [".yaml", ".json", ".toml"] and "checkpoint" not in f["path"]
        ],
        "Data files": [
            f for f in all_files if f["ext"] in [".jsonl", ".parquet", ".csv", ".txt"] and f["size_kb"] > 10
        ],
        "Model weights": [f for f in all_files if f["ext"] in [".safetensors", ".bin", ".pt", ".pth", ".ckpt"]],
        "Requirements": [f for f in all_files if "requirements" in f["name"].lower()],
    }

    print(f"\nKey files found:")
    for category, files in important.items():
        if files:
            print(f"\n  {category}:")
            for f in files[:5]:
                print(f"    {f['path']:50} ({f['size_kb'] / 1024:.2f} MB)")

    data_files = [
        f for f in all_files if f["ext"] in [".jsonl", ".json", ".parquet", ".csv", ".txt"] and f["size_kb"] > 1
    ]

    return all_files, important, data_files


# ── DUPLICATE DETECTION ─────────────────────────────────────────────────────


def find_duplicates(all_files: list[dict], min_size_kb: float = 10) -> list[list[dict]]:
    """Find duplicate files by MD5 hash."""
    print("\n== DUPLICATE FILES ===========================================")

    hash_map = defaultdict(list)
    for f_info in all_files:
        if f_info["size_kb"] < min_size_kb:
            continue
        p = Path(f_info["path"])
        if p.exists():
            try:
                h = hashlib.md5(p.read_bytes()).hexdigest()
                hash_map[h].append(f_info)
            except Exception:
                pass

    waste_mb = 0
    dup_count = 0
    duplicates_found = []

    for h, files in hash_map.items():
        if len(files) > 1:
            wasted = sum(f["size_kb"] for f in files[1:]) / 1024
            waste_mb += wasted
            dup_count += len(files) - 1
            duplicates_found.append(files)
            print(f"  DUPLICATE ({wasted:.1f} MB wasted):")
            for f in files:
                marker = "KEEP" if f == files[0] else "DELETE"
                print(f"    [{marker}] {f['path']}")

    if dup_count == 0:
        print("  No duplicates found [OK]")
    else:
        print(f"\n  Total duplicates: {dup_count} files ({waste_mb:.1f} MB recoverable)")

    return duplicates_found


# ── SAFE CLEANUP ────────────────────────────────────────────────────────────


def safe_cleanup(cfg: ForgeConfig, dry_run: bool = True):
    """Remove cache, pyc, temp files. Dry-run by default."""
    print(f"\n== CLEANUP {'(DRY RUN)' if dry_run else '(EXECUTING)'} ====")

    patterns_to_delete = [
        "**/__pycache__",
        "**/*.pyc",
        "**/*.pyo",
        "**/.DS_Store",
        "**/Thumbs.db",
        "**/.ipynb_checkpoints",
        "**/.pytest_cache",
        "**/*.egg-info",
    ]

    to_delete = []
    total_bytes = 0
    root = Path(cfg.root_dir)

    for pattern in patterns_to_delete:
        # Handle **/ as rglob
        glob_part = pattern.replace("**/", "")
        for path in root.rglob(glob_part):
            if path.is_dir():
                size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            else:
                size = path.stat().st_size
            to_delete.append((path, size))
            total_bytes += size

    for path, size in to_delete:
        print(f"  {'[WOULD DELETE]' if dry_run else '[DELETING]':16} {path.relative_to(root)} ({size / 1024:.1f} KB)")
        if not dry_run:
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            except Exception as e:
                print(f"    ERROR: {e}")

    print(f"\n  Total: {len(to_delete)} items, {total_bytes / 1024 / 1024:.1f} MB")
    if dry_run and to_delete:
        print("  Run with --clean to execute deletion.")


# ── EXISTING DATA ANALYSIS ──────────────────────────────────────────────────


def analyze_existing_data(data_files: list[dict]):
    """Sample and describe existing training data files."""
    print("\n== EXISTING TRAINING DATA ===================================")

    analyzed = 0
    for f_info in data_files[:15]:
        path = Path(f_info["path"])
        if not path.exists():
            continue

        size_mb = f_info["size_kb"] / 1024
        print(f"\n  File: {path} ({size_mb:.2f} MB)")

        try:
            if path.suffix == ".jsonl":
                with open(path, encoding="utf-8") as fp:
                    lines = [l for l in fp if l.strip()][:5]
                if lines:
                    sample = json.loads(lines[0])
                    print(f"  Records: {sum(1 for _ in open(path, encoding='utf-8') if _.strip()):,}")
                    print(f"  Keys: {list(sample.keys())[:8]}")
                    print(f"  Sample: {json.dumps(sample, ensure_ascii=False)[:200]}")

            elif path.suffix == ".json":
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    print(f"  Records: {len(data):,}")
                    if data:
                        print(f"  Keys: {list(data[0].keys())[:8]}")
                elif isinstance(data, dict):
                    print(f"  Keys: {list(data.keys())[:12]}")

            elif path.suffix == ".parquet":
                try:
                    import pandas as pd

                    df = pd.read_parquet(path, nrows=5)
                    print(f"  Columns: {list(df.columns)}")
                    print(f"  Sample:\n{df.head(2).to_string()[:300]}")
                except ImportError:
                    print("  (pandas not installed)")

            analyzed += 1

        except Exception as e:
            print(f"  Error reading: {e}")


# ── MAIN ────────────────────────────────────────────────────────────────────


def scan_project(cfg: ForgeConfig) -> dict:
    """Run full audit and return results."""
    print("=" * 70)
    print("FORGE-OMEGA: SYSTEM & PROJECT AUDIT")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    hw = audit_hardware(cfg)
    all_files, important, data_files = audit_project(cfg)
    duplicates = find_duplicates(all_files)
    analyze_existing_data(data_files)
    safe_cleanup(cfg, dry_run=True)

    report = {
        "hardware": hw,
        "config": {
            "base_model": cfg.base_model,
            "max_length": cfg.max_length,
            "batch_size": cfg.batch_size,
            "tier": cfg.hardware_profile.get("tier", "unknown"),
        },
        "duplicates_found": len(duplicates),
        "existing_data_files": {f_info["path"]: f_info["size_kb"] / 1024 for f_info in data_files[:20]},
    }

    report_path = Path(cfg.workspace_dir) / "audit_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 70}")
    print("AUDIT COMPLETE — Report saved to forge_workspace/audit_report.json")
    print("Next step: python forge_step1_collect.py")
    print(f"{'=' * 70}")

    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FORGE-OMEGA System Audit")
    parser.add_argument("--clean", action="store_true", help="Actually execute cleanup")
    args = parser.parse_args()

    cfg = ForgeConfig()
    cfg.save()

    if args.clean:
        safe_cleanup(cfg, dry_run=False)

    scan_project(cfg)
