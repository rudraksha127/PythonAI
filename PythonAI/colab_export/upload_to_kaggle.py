"""
Kaggle Uploader — Uploads dataset + pushes notebook to Kaggle for GPU training.

Prerequisites:
    1. Kaggle API key at ~/.kaggle/kaggle.json
    2. kaggle CLI installed (pip install kaggle)
    3. Kaggle account

Quick setup:
    python colab_export/upload_to_kaggle.py --setup

Full upload:
    python colab_export/upload_to_kaggle.py --all
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPORT_DIR = PROJECT_ROOT / "colab_export"


def check_prerequisites():
    """Check if Kaggle CLI and API key are available."""
    issues = []

    # Check kaggle CLI
    kaggle_path = shutil.which("kaggle") or shutil.which("kaggle.CMD")
    if kaggle_path:
        print(f"[OK] Kaggle CLI: {kaggle_path}")
    else:
        issues.append(
            "Kaggle CLI not found. Install: pip install kaggle"
        )

    # Check API key
    kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
    if kaggle_json.exists():
        try:
            with open(kaggle_json) as f:
                config = json.load(f)
            if config.get("username") and config.get("key"):
                print(f"[OK] Kaggle API key: {config['username']}")
            else:
                issues.append(
                    "kaggle.json missing username/key fields"
                )
        except json.JSONDecodeError:
            issues.append("kaggle.json is not valid JSON")
    else:
        issues.append(
            "kaggle.json not found!\n"
            "  Go to https://www.kaggle.com/settings -> Create New API Token\n"
            "  Save to: ~/.kaggle/kaggle.json"
        )

    # Check dataset
    dataset_path = EXPORT_DIR / "training_dataset.jsonl"
    if dataset_path.exists():
        size_mb = os.path.getsize(dataset_path) / (1024 * 1024)
        print(f"[OK] Dataset: {dataset_path.name} ({size_mb:.1f} MB)")
    else:
        issues.append(f"Dataset not found at {dataset_path}")

    # Check notebook
    notebook_path = EXPORT_DIR / "finetune_qwen14b_unsloth.ipynb"
    if notebook_path.exists():
        print(f"[OK] Notebook: {notebook_path.name}")
    else:
        issues.append(f"Notebook not found at {notebook_path}")

    # Check kernel metadata
    metadata_path = EXPORT_DIR / "kernel-metadata.json"
    if metadata_path.exists():
        print(f"[OK] Kernel metadata: {metadata_path.name}")
    else:
        issues.append(f"Kernel metadata not found at {metadata_path}")

    return issues


def update_kernel_metadata(username=None):
    """Update kernel-metadata.json with the user's Kaggle username."""
    metadata_path = EXPORT_DIR / "kernel-metadata.json"
    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    if username:
        metadata["id"] = f"{username}/finetune-qwen14b-pythonai"
        print(f"[OK] Updated kernel ID: {metadata['id']}")

    # Add dataset sources
    metadata["dataset_sources"] = ["pythonai-training-data"]

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    return metadata


def create_kaggle_dataset():
    """Create a Kaggle Dataset from our training data."""
    print("\n--- Creating Kaggle Dataset ---")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Prepare dataset folder
        dataset_dir = Path(tmpdir) / "dataset"
        dataset_dir.mkdir()

        # Copy JSONL
        shutil.copy2(
            EXPORT_DIR / "training_dataset.jsonl",
            dataset_dir / "training_dataset.jsonl",
        )

        # Create dataset metadata
        dataset_metadata = {
            "title": "PythonAI Training Data",
            "id": "pythonai-training-data",
            "licenses": [{"name": "MIT"}],
            "description": (
                "Python Q&A training dataset for fine-tuning Qwen2.5-Coder.\n"
                "11,962 instruction-output pairs across 20 Python categories."
            ),
        }
        with open(dataset_dir / "dataset-metadata.json", "w") as f:
            json.dump(dataset_metadata, f, indent=2)

        # Create Kaggle dataset
        cmd = [
            "kaggle",
            "datasets",
            "create",
            "-p",
            str(dataset_dir),
            "--dir-mode",
            "tar",
        ]
        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            print("[OK] Dataset created on Kaggle!")
            print(result.stdout)
        else:
            # Already exists? Try update
            if "already exists" in result.stderr.lower():
                print("Dataset already exists. Updating...")
                cmd = [
                    "kaggle",
                    "datasets",
                    "version",
                    "-p",
                    str(dataset_dir),
                    "-m",
                    "Updated training data",
                    "--dir-mode",
                    "tar",
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    print("[OK] Dataset updated!")
                else:
                    print(f"[FAIL] Update failed: {result.stderr}")
            else:
                print(f"[FAIL] Create failed: {result.stderr}")
                return False

    return True


def push_kaggle_notebook():
    """Push the notebook to Kaggle as a new kernel."""
    print("\n--- Pushing Notebook to Kaggle ---")

    cmd = [
        "kaggle",
        "kernels",
        "push",
        "-p",
        str(EXPORT_DIR),
    ]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print("[OK] Notebook pushed to Kaggle!")
        print(result.stdout)
        return True
    else:
        # Already exists? Try pull + push
        if "already exists" in result.stderr.lower():
            print("Kernel already exists. Updating...")

            # Pull existing version
            metadata_path = EXPORT_DIR / "kernel-metadata.json"
            with open(metadata_path) as f:
                metadata = json.load(f)
            kernel_id = metadata["id"]

            pull_cmd = ["kaggle", "kernels", "pull", kernel_id, "-p", str(EXPORT_DIR)]
            subprocess.run(pull_cmd, capture_output=True, text=True)

            # Push updated version
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print("[OK] Kernel updated!")
            else:
                print(f"[FAIL] Push failed: {result.stderr}")
                return False
        else:
            print(f"[FAIL] Push failed: {result.stderr}")
            return False

    return True


def get_kaggle_username():
    """Get Kaggle username from API key."""
    kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
    if kaggle_json.exists():
        with open(kaggle_json) as f:
            config = json.load(f)
        return config.get("username")
    return None


def print_kaggle_instructions():
    """Print manual instructions for Kaggle setup."""
    print("\n" + "=" * 65)
    print("  Manual Kaggle Setup Instructions")
    print("=" * 65)
    print("""
  Step 1: Go to https://www.kaggle.com/ and login

  Step 2: Upload the dataset
    - Click 'Create' > 'New Dataset'
    - Upload training_dataset.jsonl from colab_export/
    - Name it: pythonai-training-data
    - Set license to MIT

  Step 3: Create a new notebook
    - Click 'Create' > 'New Notebook'
    - Settings > Accelerator > GPU P100
    - Settings > Internet > On
    - Copy the content from colab_export/finetune_qwen14b_unsloth.ipynb

  Step 4: Add your dataset
    - Click 'Add Data' > find 'pythonai-training-data'
    - The notebook's Option D cell will auto-detect it

  Step 5: Train!
    - Runtime > Run all
    - Quick test: Use the 'Quick Test Mode' cell (~5 min)
    - Full training: 1 epoch ~ 2-3 hours on P100

  Step 6: Download result
    - After training, the adapter will be in /kaggle/working/pythonai_qwen14b_lora_adapter/
    - Download via Kaggle file browser

  Step 7: Use locally
    - Extract to: checkpoints/qwen14b_pythonai/
    - python -m src.training.evaluator --adapter-path checkpoints/qwen14b_pythonai
    """)

    print("=" * 65)
    print("  OR use CLI (if API key configured):")
    print(f"    python colab_export/upload_to_kaggle.py --all")
    print("=" * 65)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Upload PythonAI training to Kaggle for GPU training"
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Check prerequisites and show setup status",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Upload dataset AND push notebook to Kaggle",
    )
    parser.add_argument(
        "--dataset-only",
        action="store_true",
        help="Upload only the dataset",
    )
    parser.add_argument(
        "--notebook-only",
        action="store_true",
        help="Push only the notebook",
    )
    parser.add_argument(
        "--username",
        type=str,
        help="Your Kaggle username (for kernel metadata)",
    )
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Show manual Kaggle setup instructions",
    )

    args = parser.parse_args()

    # Default: show instructions
    if not any([args.setup, args.all, args.dataset_only, args.notebook_only, args.manual]):
        print("Usage:")
        print("  Check setup:   python colab_export/upload_to_kaggle.py --setup")
        print("  Full upload:   python colab_export/upload_to_kaggle.py --all")
        print("  Dataset only:  python colab_export/upload_to_kaggle.py --dataset-only")
        print("  Notebook only: python colab_export/upload_to_kaggle.py --notebook-only")
        print("  Manual guide:  python colab_export/upload_to_kaggle.py --manual")
        sys.exit(0)

    if args.setup:
        print("=== Kaggle Setup Check ===\n")
        issues = check_prerequisites()
        if issues:
            print("\nIssues found:")
            for issue in issues:
                print(f"  [X] {issue}")
            sys.exit(1)
        else:
            print("\n[OK] All prerequisites satisfied!")
        sys.exit(0)

    if args.manual:
        print_kaggle_instructions()
        sys.exit(0)

    # For --all, --dataset-only, --notebook-only
    if args.username:
        update_kernel_metadata(args.username)
    else:
        username = get_kaggle_username()
        if username:
            update_kernel_metadata(username)

    if args.dataset_only or args.all:
        create_kaggle_dataset()
        # Kaggle needs ~60s to index a new dataset before notebook can use it
        if args.all:
            import time
            print("\nWaiting 60s for Kaggle to index the dataset...")
            time.sleep(60)

    if args.notebook_only or args.all:
        push_kaggle_notebook()

    print("\n[DONE] Check your Kaggle account to start training!")
