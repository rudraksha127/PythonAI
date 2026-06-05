"""
Push training notebook to Kaggle and trigger execution with P100 GPU.
Run: python scripts/kaggle_push_training.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ["KAGGLE_USERNAME"] = "rudraksha1"
os.environ["KAGGLE_KEY"] = "ee6c5dbf5817d6f1fe842b709cd4fabe"
os.environ["KAGGLE_API_TOKEN"] = "ee6c5dbf5817d6f1fe842b709cd4fabe"

KAGGLE_EXE = r"C:\Users\lucky_vv7fub\AppData\Roaming\Python\Python314\Scripts\kaggle.exe"
ROOT = Path(r"C:\Users\lucky_vv7fub\OneDrive\Desktop\PythonAI")

def run_cmd(cmd: list[str]) -> subprocess.CompletedProcess:
    print(f"\n$ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env={**os.environ})
    if result.stdout:
        print(result.stdout[:2000])
    if result.stderr:
        print("STDERR:", result.stderr[:2000])
    print(f"Exit: {result.returncode}")
    return result

def step1_create_dataset():
    """Push dataset to Kaggle"""
    print("\n" + "=" * 60)
    print("STEP 1: Creating/Updating Dataset on Kaggle")
    print("=" * 60)

    tmpdir = tempfile.mkdtemp()
    dataset_dir = Path(tmpdir) / "dataset"
    dataset_dir.mkdir()

    # Copy JSONL
    shutil.copy2(str(ROOT / "colab_export" / "training_dataset.jsonl"), str(dataset_dir / "training_dataset.jsonl"))

    # Dataset metadata
    metadata = {
        "title": "PythonAI Training Data",
        "id": "rudraksha1/pythonai-training-data",
        "licenses": [{"name": "MIT"}],
        "description": "Python Q&A training dataset for fine-tuning Qwen2.5-Coder. 11,962 instruction-output pairs."
    }
    with open(str(dataset_dir / "dataset-metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)

    # Create via Kaggle CLI
    result = run_cmd([KAGGLE_EXE, "datasets", "create", "-p", str(dataset_dir), "--dir-mode", "zip"])
    
    if result.returncode == 0 or "already exists" in result.stderr.lower():
        print("Dataset ready!")
        # Try update instead
        run_cmd([KAGGLE_EXE, "datasets", "version", "-p", str(dataset_dir), "-m", "Updated dataset", "--dir-mode", "zip"])
        return True
    return False


def step2_push_notebook():
    """Push the training notebook to Kaggle"""
    print("\n" + "=" * 60)
    print("STEP 2: Pushing Training Notebook to Kaggle with GPU")
    print("=" * 60)

    folder = Path(tempfile.mkdtemp())

    # Copy notebook
    shutil.copy2(str(ROOT / "colab_export" / "finetune_qwen14b_unsloth.ipynb"),
                 str(folder / "finetune_qwen14b_unsloth.ipynb"))

    # Create kernel-metadata.json
    kmeta = {
        "id": "rudraksha1/finetune-qwen14b-pythonai",
        "title": "Finetune Qwen14B PythonAI",
        "code_file": "finetune_qwen14b_unsloth.ipynb",
        "language": "python",
        "kernel_type": "notebook",
        "is_private": True,
        "enable_gpu": True,
        "enable_tpu": False,
        "enable_internet": True,
        "dataset_sources": ["rudraksha1/pythonai-training-data"],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": []
    }
    with open(str(folder / "kernel-metadata.json"), "w") as f:
        json.dump(kmeta, f, indent=2)

    print(f"Folder contents: {os.listdir(str(folder))}")
    with open(str(folder / "kernel-metadata.json")) as f:
        print(f"kernel-metadata.json:\n{f.read()}")

    # Push via CLI
    result = run_cmd([KAGGLE_EXE, "kernels", "push", "-p", str(folder)])
    return result.returncode == 0


def step3_check_status():
    """Check kernel status"""
    print("\n" + "=" * 60)
    print("STEP 3: Checking Kernel Status")
    print("=" * 60)

    run_cmd([KAGGLE_EXE, "kernels", "status", "rudraksha1/finetune-qwen14b-pythonai"])
    run_cmd([KAGGLE_EXE, "kernels", "list", "--user", "rudraksha1", "--page-size", "5"])


if __name__ == "__main__":
    print("=" * 60)
    print("KAGGLE TRAINING PUSH")
    print("=" * 60)

    if len(sys.argv) > 1:
        step = sys.argv[1]
        if step == "dataset":
            step1_create_dataset()
        elif step == "notebook":
            step2_push_notebook()
        elif step == "status":
            step3_check_status()
        elif step == "all":
            step1_create_dataset()
            step2_push_notebook()
            step3_check_status()
        else:
            print(f"Unknown step: {step}")
            print("Usage: python scripts/kaggle_push_training.py [dataset|notebook|status|all]")
    else:
        step2_push_notebook()
        step3_check_status()
