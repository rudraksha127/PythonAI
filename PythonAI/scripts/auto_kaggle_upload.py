"""
Auto Kaggle Upload - Dataset aur Notebook ek saath upload karo.
Run: python scripts/auto_kaggle_upload.py
"""
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPORT_DIR = ROOT / "colab_export"
NOTEBOOK_PATH = EXPORT_DIR / "finetune_qwen14b_unsloth.ipynb"
DATASET_PATH = EXPORT_DIR / "training_dataset.jsonl"
USERNAME = "rudraksha1"
KERNEL_ID = f"{USERNAME}/finetune-qwen14b-pythonai"
DATASET_ID = f"{USERNAME}/pythonai-training-data"


def step0_check():
    """Check sab kuch ready hai ya nahi"""
    print("=" * 60)
    print("STEP 0: Prerequisites Check")
    print("=" * 60)

    issues = []
    if not NOTEBOOK_PATH.exists():
        issues.append(f"Notebook not found: {NOTEBOOK_PATH}")
    else:
        size_kb = os.path.getsize(NOTEBOOK_PATH) / 1024
        print(f"  [OK] Notebook: {NOTEBOOK_PATH.name} ({size_kb:.1f} KB)")

    if not DATASET_PATH.exists():
        issues.append(f"Dataset not found: {DATASET_PATH}")
    else:
        size_mb = os.path.getsize(DATASET_PATH) / (1024 * 1024)
        print(f"  [OK] Dataset: {DATASET_PATH.name} ({size_mb:.1f} MB)")

    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
        api = KaggleApi()
        api.authenticate()
        print(f"  [OK] Kaggle API: Authenticated as {USERNAME}")
    except Exception as e:
        issues.append(f"Kaggle auth failed: {e}")

    if issues:
        print("\n[X] Issues found:")
        for i in issues:
            print(f"   {i}")
        return False
    else:
        print("\n[OK] All prerequisites satisfied!\n")
        return True


def step1_create_dataset():
    """Kaggle par dataset create/update karo"""
    print("=" * 60)
    print("STEP 1: Upload Dataset to Kaggle")
    print("=" * 60)

    from kaggle.api.kaggle_api_extended import KaggleApi
    api = KaggleApi()
    api.authenticate()

    tmpdir = tempfile.mkdtemp()
    dataset_dir = Path(tmpdir) / "dataset"
    dataset_dir.mkdir()

    # Copy JSONL
    shutil.copy2(str(DATASET_PATH), str(dataset_dir / "training_dataset.jsonl"))

    # Dataset metadata
    metadata = {
        "title": "PythonAI Training Data",
        "id": DATASET_ID,
        "licenses": [{"name": "MIT"}],
        "description": (
            "Python Q&A training dataset for fine-tuning Qwen2.5-Coder.\n"
            "11,962 instruction-output pairs across 20+ Python categories.\n"
        ),
    }
    with open(str(dataset_dir / "dataset-metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)

    try:
        print(f"Creating dataset: {DATASET_ID} ...")
        api.dataset_create_new(
            folder=str(dataset_dir),
            public=False,
            convert_to_csv=False,
            dir_mode="zip",
        )
        print("[OK] Dataset created successfully!")
        return True
    except Exception as e:
        err_str = str(e).lower()
        if "already exists" in err_str:
            print("Dataset already exists. Updating version...")
            try:
                api.dataset_create_version(
                    folder=str(dataset_dir),
                    version_notes="Updated training dataset",
                    dir_mode="zip",
                )
                print("[OK] Dataset updated successfully!")
                return True
            except Exception as e2:
                print(f"[FAIL] Update failed: {e2}")
                return False
        else:
            print(f"[FAIL] Create failed: {e}")
            return False


def step2_push_notebook():
    """Kaggle par notebook push karo"""
    print("=" * 60)
    print("STEP 2: Push Notebook to Kaggle")
    print("=" * 60)

    from kaggle.api.kaggle_api_extended import KaggleApi
    api = KaggleApi()
    api.authenticate()

    folder = Path(tempfile.mkdtemp())
    shutil.copy2(str(NOTEBOOK_PATH), str(folder / "finetune_qwen14b_unsloth.ipynb"))

    kmeta = {
        "id": KERNEL_ID,
        "title": "Finetune Qwen14B PythonAI",
        "code_file": "finetune_qwen14b_unsloth.ipynb",
        "language": "python",
        "kernel_type": "notebook",
        "is_private": True,
        "enable_gpu": True,
        "enable_tpu": False,
        "enable_internet": True,
        "dataset_sources": [DATASET_ID],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": [],
    }
    with open(str(folder / "kernel-metadata.json"), "w") as f:
        json.dump(kmeta, f, indent=2)

    try:
        print(f"Pushing kernel: {KERNEL_ID} ...")
        api.kernels_push(str(folder))
        print("[OK] Notebook pushed successfully!")
        return True
    except Exception as e:
        err_str = str(e).lower()
        if "already exists" in err_str:
            print("Kernel already exists. Updating...")
            try:
                api.kernels_push(str(folder))
                print("[OK] Kernel updated successfully!")
                return True
            except Exception as e2:
                print(f"[FAIL] Update failed: {e2}")
                return False
        else:
            print(f"[FAIL] Push failed: {e}")
            return False


def step3_check_status():
    """Kernel status check karo"""
    print("=" * 60)
    print("STEP 3: Check Kernel Status")
    print("=" * 60)

    from kaggle.api.kaggle_api_extended import KaggleApi
    api = KaggleApi()
    api.authenticate()

    try:
        status = api.kernels_status(KERNEL_ID)
        print(f"  Status: {status}")
        return status
    except Exception as e:
        print(f"  Status error: {e}")
        return None


def print_next_steps():
    """Next steps batayein"""
    print()
    print("=" * 60)
    print("NEXT STEPS - Kaggle Par Training Start Karo")
    print("=" * 60)
    print(f"""
  1. Go to: https://www.kaggle.com/code/{USERNAME}/finetune-qwen14b-pythonai

  2. Settings (right panel) -> Accelerator -> GPU P100

  3. Check that dataset is attached:
     Add Data -> search "pythonai-training-data"

  4. Click "Run All" (or run each cell one by one)

  5. Quick test: ~5 min ("Quick Test Mode" cell)
     Full training: ~2-3 hours (let Step 6 run)

  6. After training, download adapter from:
     /kaggle/working/pythonai_qwen14b_lora_adapter/

  7. Local use:
     unzip pythonai_qwen14b_lora_adapter.zip -d checkpoints/qwen14b_pythonai/
     python -m src.training.evaluator --adapter-path checkpoints/qwen14b_pythonai
""")


if __name__ == "__main__":
    print()
    print("=== PYTHONAI - AUTO KAGGLE UPLOAD ===")
    print()

    if not step0_check():
        exit(1)

    dataset_ok = step1_create_dataset()
    if dataset_ok:
        print("\nWaiting 60s for Kaggle to index dataset...")
        time.sleep(60)

    notebook_ok = step2_push_notebook()

    print()
    step3_check_status()
    print_next_steps()

    print("\n" + "=" * 60)
    if dataset_ok and notebook_ok:
        print("SAB KAAM HO GAYA! Kaggle par training start karo!")
    else:
        print("Kuch issues hain, upar dekho details.")
    print("=" * 60)
