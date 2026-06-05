"""
Colab Launcher — Packages notebook + dataset and opens in Google Colab.
Usage:
    python colab_export/open_in_colab.py

This will:
1. Create a ZIP with the notebook and sample dataset
2. Generate a Colab link that opens the notebook
3. Print step-by-step instructions
"""

import json
import os
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPORT_DIR = PROJECT_ROOT / "colab_export"


def create_colab_package():
    """Create a ZIP package for manual upload to Colab."""
    package_dir = EXPORT_DIR / "colab_package"
    shutil.rmtree(package_dir, ignore_errors=True)
    package_dir.mkdir(parents=True, exist_ok=True)

    # Copy notebook
    src_notebook = EXPORT_DIR / "finetune_qwen14b_unsloth.ipynb"
    dst_notebook = package_dir / "finetune_qwen14b_unsloth.ipynb"
    shutil.copy2(src_notebook, dst_notebook)

    # Copy dataset (use sample for faster upload, full for full training)
    src_dataset = EXPORT_DIR / "training_dataset.jsonl"
    dst_dataset = package_dir / "training_dataset.jsonl"
    shutil.copy2(src_dataset, dst_dataset)

    # Create quick start sheet
    readme = package_dir / "INSTRUCTIONS.txt"
    readme.write_text(
        "=== Qwen2.5-Coder-14B Fine-Tuning on Colab ===\n\n"
        "STEPS:\n"
        "1. Go to https://colab.research.google.com/\n"
        "2. Click File > Upload Notebook > Upload finetune_qwen14b_unsloth.ipynb\n"
        "3. Go to Runtime > Change runtime type > T4 GPU\n"
        "4. In the notebook, use Step 2 > Option B (File Upload)\n"
        "5. Upload training_dataset.jsonl when prompted\n"
        "6. Run all cells (Runtime > Run all)\n\n"
        "TIPS:\n"
        "- For quick test: Use 'Quick Test Mode' cell (5 min)\n"
        "- For full training: 1 epoch ~ 2-4 hours\n"
        "- Colab may disconnect: Save checkpoints to Google Drive\n",
        encoding="utf-8",
    )

    # Create ZIP
    zip_path = EXPORT_DIR / "colab_upload_package.zip"
    shutil.make_archive(
        str(zip_path.with_suffix("")), "zip", str(package_dir)
    )

    # Clean up temp dir
    shutil.rmtree(package_dir, ignore_errors=True)

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"Package created: colab_upload_package.zip ({size_mb:.1f} MB)")
    return zip_path


def print_colab_instructions():
    """Print step-by-step Colab instructions."""
    print("\n" + "=" * 65)
    print("  Qwen2.5-Coder-14B Fine-Tuning on Google Colab (FREE T4 GPU)")
    print("=" * 65)

    print("\n  STEP 1: Open Google Colab")
    print("  " + "-" * 50)
    print("  Go to: https://colab.research.google.com/")
    print("  Click: File > Upload Notebook")
    print(
        "  Select: colab_package/finetune_qwen14b_unsloth.ipynb\n"
    )

    print("  STEP 2: Enable GPU")
    print("  " + "-" * 50)
    print("  Runtime > Change runtime type > T4 GPU\n")

    print("  STEP 3: Upload Dataset")
    print("  " + "-" * 50)
    print("  In the notebook, go to Step 2 > Option B (File Upload)")
    print("  Run that cell and upload training_dataset.jsonl when prompted\n")

    print("  STEP 4: Train!")
    print("  " + "-" * 50)
    print("  Runtime > Run all")
    print("  Quick test (~5 min): Use 'Quick Test Mode' cell")
    print("  Full training (~2-4 hrs): Let Step 6 run\n")

    print("  STEP 5: Download Your Trained Model")
    print("  " + "-" * 50)
    print("  After training, run Step 7 cells")
    print("  Adapter will download as pythonai_qwen14b_lora_adapter.zip\n")

    print("=" * 65)
    print("  OR just open Colab and paste this URL after uploading:")
    print()
    print("  https://colab.research.google.com/github/")
    print("  (Upload notebook file, don't use URL link)")
    print("=" * 65)


def generate_dataset_card():
    """Generate a dataset card with statistics for the README."""
    dataset_path = EXPORT_DIR / "training_dataset.jsonl"
    if not dataset_path.exists():
        print("Dataset not found. Skipping stats.")
        return None

    rows = []
    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))

    cats = {}
    for r in rows:
        c = r.get("category", "?")
        cats[c] = cats.get(c, 0) + 1

    versions = {}
    for r in rows:
        v = r.get("version", "?")
        versions[v] = versions.get(v, 0) + 1

    total_chars = sum(len(r.get("instruction", "")) + len(r.get("output", "")) for r in rows)
    avg_instr = sum(len(r.get("instruction", "")) for r in rows) / len(rows)
    avg_out = sum(len(r.get("output", "")) for r in rows) / len(rows)
    code_count = sum(1 for r in rows if "```" in r.get("output", ""))

    stats = {
        "total_examples": len(rows),
        "file_size_mb": round(os.path.getsize(dataset_path) / (1024 * 1024), 1),
        "categories": dict(sorted(cats.items(), key=lambda x: -x[1])),
        "python_versions": dict(sorted(versions.items(), key=lambda x: -x[1])),
        "total_characters": total_chars,
        "avg_instruction_length": round(avg_instr, 0),
        "avg_output_length": round(avg_out, 0),
        "code_examples": code_count,
    }

    stats_path = EXPORT_DIR / "dataset_card.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print(f"Dataset card saved: dataset_card.json")
    return stats


if __name__ == "__main__":
    print("=" * 65)
    print("  PythonAI - Qwen2.5-Coder-14B Colab Training Setup")
    print("=" * 65)

    # Generate dataset card
    print("\n[1/3] Generating dataset card...")
    stats = generate_dataset_card()
    if stats:
        print(f"  -> {stats['total_examples']:,} examples")
        print(f"  -> {len(stats['categories'])} categories")
        print(f"  -> {stats['code_examples']:,} code examples")

    # Create Colab package
    print("\n[2/3] Creating Colab upload package...")
    zip_path = create_colab_package()

    # Print instructions
    print("\n[3/3] Ready!\n")
    print_colab_instructions()
    print(f"\nOr manually upload: {zip_path}")
