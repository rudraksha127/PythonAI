"""Upload the training dataset to HuggingFace Hub so Colab can load it directly.

Steps:
1. Set your HF token:  huggingface-cli login
2. Run: python upload_to_hf.py
3. In Colab: dataset = load_dataset("YOUR_USERNAME/pythonai-training-data", split="train")
"""
from pathlib import Path
import json
from datasets import Dataset, DatasetDict

jsonl_path = Path(__file__).parent / "training_dataset.jsonl"

rows = []
with jsonl_path.open("r", encoding="utf-8") as f:
    for line in f:
        rows.append(json.loads(line))

dataset = Dataset.from_list(rows)
dataset_dict = DatasetDict({"train": dataset})

# Change this to your HF username
HF_REPO = "YOUR_HF_USERNAME/pythonai-training-data"

dataset_dict.push_to_hub(HF_REPO, private=False)
print(f"Uploaded {len(rows):,} rows to https://huggingface.co/datasets/{HF_REPO}")
