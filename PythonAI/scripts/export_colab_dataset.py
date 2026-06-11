"""Export the training dataset for use with Unsloth on Google Colab.

Usage:
    python scripts/export_colab_dataset.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "training"
OUTPUT = ROOT / "colab_export"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)

    # Load main training dataset
    src_path = DATA_DIR / "training_dataset.json"
    if not src_path.exists():
        src_path = ROOT / "training_dataset.json"

    with src_path.open("r", encoding="utf-8") as f:
        rows = json.load(f)

    print(f"Loaded {len(rows):,} rows from {src_path.name}")

    # Convert to Unsloth-compatible JSONL format
    jsonl_path = OUTPUT / "training_dataset.jsonl"
    valid_count = 0
    skipped = 0
    with jsonl_path.open("w", encoding="utf-8") as f:
        for row in rows:
            instr = str(row.get("instruction", "")).strip()
            out = str(row.get("output", "")).strip()
            if len(instr) < 10 or len(out) < 20:
                skipped += 1
                continue
            obj = {
                "instruction": instr,
                "output": out,
                "source": row.get("source", ""),
                "category": row.get("category", ""),
            }
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            valid_count += 1

    print(f"Exported {valid_count:,} valid examples to {jsonl_path}")
    print(f"Skipped {skipped:,} short/invalid examples")

    # Create a smaller sample for quick testing
    sample_path = OUTPUT / "training_sample_500.jsonl"
    with jsonl_path.open("r", encoding="utf-8") as f_in, sample_path.open("w", encoding="utf-8") as f_out:
        for i, line in enumerate(f_in):
            if i >= 500:
                break
            f_out.write(line)
    print(f"Exported 500-sample subset to {sample_path}")

    # Create dataset statistics
    import collections

    cats = collections.Counter()
    lengths_instr = []
    lengths_out = []
    code_count = 0

    for row in rows:
        instr = str(row.get("instruction", "")).strip()
        out = str(row.get("output", "")).strip()
        cats[row.get("category", "other")] += 1
        lengths_instr.append(len(instr))
        lengths_out.append(len(out))
        if "```" in out:
            code_count += 1

    stats = {
        "total_rows": len(rows),
        "valid_rows": valid_count,
        "categories": dict(cats.most_common(20)),
        "avg_instruction_chars": round(sum(lengths_instr) / len(lengths_instr), 1),
        "avg_output_chars": round(sum(lengths_out) / len(lengths_out), 1),
        "max_instruction_chars": max(lengths_instr),
        "max_output_chars": max(lengths_out),
        "code_examples_pct": round(code_count / len(rows) * 100, 1),
        "recommended_max_seq_length": min(2048, max(max(lengths_instr), max(lengths_out)) + 256),
    }

    stats_path = OUTPUT / "dataset_stats.json"
    with stats_path.open("w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    print(f"\nDataset stats saved to {stats_path}")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # Create README
    readme_path = OUTPUT / "README.md"
    readme_content = f"""# Colab Training Dataset Export

Exported on: {__import__("datetime").datetime.now().isoformat()}

## Files

| File | Description |
|------|-------------|
| `training_dataset.jsonl` | Full dataset ({valid_count:,} examples) — for Unsloth |
| `training_sample_500.jsonl` | 500-example subset for quick testing |
| `dataset_stats.json` | Statistical breakdown of the dataset |

## Upload to Google Colab

1. Zip this folder: `tar -czf colab_export.tar.gz colab_export/`
2. Upload to your Google Drive or directly to Colab runtime
3. Or use the HuggingFace Datasets method (see notebook)

## Dataset Stats

- Total rows: {stats["total_rows"]:,}
- Valid rows: {stats["valid_rows"]:,}
- Avg instruction length: {stats["avg_instruction_chars"]} chars
- Avg output length: {stats["avg_output_chars"]} chars
- Code examples: {stats["code_examples_pct"]}%
- Recommended max_seq_length: {stats["recommended_max_seq_length"]}
"""
    readme_path.write_text(readme_content, encoding="utf-8")
    print(f"README saved to {readme_path}")

    # Create HuggingFace upload script
    hf_script = OUTPUT / "upload_to_hf.py"
    hf_script.write_text(
        f'''"""Upload the training dataset to HuggingFace Hub so Colab can load it directly.

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
dataset_dict = DatasetDict({{"train": dataset}})

# Change this to your HF username
HF_REPO = "YOUR_HF_USERNAME/pythonai-training-data"

dataset_dict.push_to_hub(HF_REPO, private=False)
print(f"Uploaded {{len(rows):,}} rows to https://huggingface.co/datasets/{{HF_REPO}}")
''',
        encoding="utf-8",
    )

    print(f"Upload script created: {hf_script}")
    print(f"\n[OK] Export complete! Files in: {OUTPUT}")


if __name__ == "__main__":
    main()
