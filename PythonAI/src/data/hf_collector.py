"""
HuggingFace dataset collector for Python code SFT (Supervised Fine-Tuning).

Downloads popular Python code datasets from HuggingFace and converts them into
the standard raw chunk format used by collector.py so the generator pipeline can
process them alongside scraped documentation.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent.parent
os.makedirs(ROOT / "extra_data", exist_ok=True)

CACHE_FILE = ROOT / "extra_data" / "hf_collector_cache.json"
HF_CACHE_DIR = ROOT / "extra_data" / "hf_datasets"

# ═════════════════════════════════════════
#  Cache helpers
# ═════════════════════════════════════════

def load_cache() -> dict[str, float]:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_cache(cache: dict[str, float]) -> None:
    CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def needs_update(source_key: str, cache: dict[str, float], ttl_hours: int = 168) -> bool:
    """Check if a dataset needs re-downloading (default: 7-day TTL)."""
    if source_key not in cache:
        return True
    elapsed = time.time() - cache[source_key]
    return elapsed > ttl_hours * 3600


# ═════════════════════════════════════════
#  HF Dataset definitions
# ═════════════════════════════════════════

HF_DATASETS: dict[str, dict[str, Any]] = {
    "glaive_code_assistant": {
        "path": "glaiveai/glaive-code-assistant-v2",
        "description": "High-quality code instruction dataset (~120K pairs, multi-language)",
        "split": "train",
        "input_fields": ["question", "answer"],
        "instruction_field": "question",
        "output_field": "answer",
        "license": "MIT",
        "estimated_size": 120_000,
    },
    "instructional_code_search": {
        "path": "Nan-Do/instructional-code-search-net-python",
        "description": "Python instruction tuning dataset from CodeSearchNet (~25K pairs)",
        "split": "train",
        "input_fields": ["instruction", "response"],
        "instruction_field": "instruction",
        "output_field": "response",
        "license": "MIT",
        "estimated_size": 25_000,
    },
    "code_search_net_python": {
        "path": "code_search_net",
        "description": "Python code search dataset (~450K functions with docstrings)",
        "config": "python",
        "split": "train",
        "input_fields": ["func_code_string", "func_documentation_string", "func_name"],
        "instruction_field": "func_documentation_string",
        "output_field": "func_code_string",
        "license": "MIT",
        "estimated_size": 450_000,
    },
}


def describe_source(dataset_key: str) -> str:
    info = HF_DATASETS[dataset_key]
    parts = [info["description"]]
    parts.append(f"Path: {info['path']}")
    if info.get("config"):
        parts.append(f"Config: {info['config']}")
    parts.append(f"Split: {info['split']}")
    parts.append(f"License: {info['license']}")
    return " | ".join(parts)


# ═════════════════════════════════════════
#  Dataset converters
# ═════════════════════════════════════════

def convert_glaive_row(row: dict[str, Any], idx: int) -> dict[str, Any] | None:
    """Convert a glaive-code-assistant row to chunk format."""
    question = str(row.get("question", "")).strip()
    answer = str(row.get("answer", "")).strip()
    if len(question) < 10 or len(answer) < 30:
        return None

    text = f"Q: {question}\n\nA: {answer}"
    codes = re.findall(r"```python\n?(.*?)```", answer, re.DOTALL)

    return {
        "id": f"hf_glaive_{idx:07d}",
        "title": question[:80],
        "text": text[:4000],
        "type": "hf_dataset",
        "category": "hf_glaive_code_assistant",
        "version": "latest",
        "codes": codes,
    }


def convert_code_search_net_row(row: dict[str, Any], idx: int) -> dict[str, Any] | None:
    """Convert a code_search_net Python row to chunk format."""
    func_code = str(row.get("func_code_string", "")).strip()
    func_doc = str(row.get("func_documentation_string", "")).strip()
    func_name = str(row.get("func_name", "")).strip()

    if not func_code or not func_doc:
        return None

    text = f"Function: {func_name}\n\nDocumentation: {func_doc}\n\nCode:\n{func_code[:2000]}"

    return {
        "id": f"hf_codesearch_{idx:07d}",
        "title": f"Python function: {func_name}",
        "text": text[:4000],
        "type": "hf_dataset",
        "category": "hf_code_search_net",
        "version": "latest",
        "codes": [func_code],
    }


def convert_instructional_row(row: dict[str, Any], idx: int) -> dict[str, Any] | None:
    """Convert an instructional-code-search-net row to chunk format."""
    instruction = str(row.get("instruction", "")).strip()
    response = str(row.get("response", "")).strip()
    if len(instruction) < 10 or len(response) < 30:
        return None

    text = f"Instruction: {instruction}\n\nResponse: {response}"
    codes = re.findall(r"```python\n?(.*?)```", response, re.DOTALL)

    return {
        "id": f"hf_instructional_{idx:07d}",
        "title": instruction[:80],
        "text": text[:4000],
        "type": "hf_dataset",
        "category": "hf_instructional_code_search",
        "version": "latest",
        "codes": codes,
    }


# ═════════════════════════════════════════
#  Download & convert pipeline
# ═════════════════════════════════════════

def download_dataset(dataset_key: str, max_rows: int | None = None) -> list[dict[str, Any]]:
    """
    Download a HuggingFace dataset and convert rows to chunk format.

    Args:
        dataset_key: Key in HF_DATASETS dict.
        max_rows: Max rows to process (None = all).

    Returns:
        List of chunk dicts.
    """
    from datasets import load_dataset

    info = HF_DATASETS[dataset_key]
    path = info["path"]
    config = info.get("config")
    split = info.get("split", "train")

    print(f"  Loading {path}...")
    kwargs: dict[str, Any] = {"split": split, "streaming": False}
    if config:
        kwargs["name"] = config

    try:
        dataset = load_dataset(path, **kwargs)
    except Exception as e:
        print(f"  [WARN] Failed to load {path}: {e}")
        return []

    # Determine converter function
    if dataset_key == "glaive_code_assistant":
        converter = convert_glaive_row
    elif dataset_key == "code_search_net_python":
        converter = convert_code_search_net_row
    elif dataset_key == "instructional_code_search":
        converter = convert_instructional_row
    else:
        raise ValueError(f"No converter for dataset: {dataset_key}")

    chunks: list[dict[str, Any]] = []
    total = min(len(dataset), max_rows) if max_rows else len(dataset)

    for idx in tqdm(range(total), desc=f"  {info['path'].split('/')[-1][:30]}", leave=False):
        try:
            row = dataset[idx]
            chunk = converter(row, idx)
            if chunk:
                chunks.append(chunk)
        except Exception:
            continue

    print(f"  Converted {len(chunks):,} chunks from {path}")
    return chunks


# ═════════════════════════════════════════
#  Main runner
# ═════════════════════════════════════════

def run(
    datasets: list[str] | None = None,
    max_rows: int = 25000,
    output: str | None = None,
) -> dict[str, Any]:
    """
    Download HF datasets and save as raw chunks.

    Args:
        datasets: List of dataset keys to download (None = all).
        max_rows: Max rows per dataset (None = all).
        output: Output path (default: data/raw/raw_chunks_hf.json).

    Returns:
        Stats dict: {dataset_key: chunk_count, total: chunk_count}
    """
    cache = load_cache()

    if datasets is None:
        datasets = list(HF_DATASETS.keys())

    all_chunks: list[dict[str, Any]] = []
    stats: dict[str, int] = {}

    print("=" * 60)
    print("HuggingFace Dataset Collector")
    print("=" * 60)

    for ds_key in datasets:
        if ds_key not in HF_DATASETS:
            print(f"  [WARN] Unknown dataset: {ds_key}")
            continue

        info = HF_DATASETS[ds_key]
        print(f"\n[{ds_key}]")
        print(f"  {describe_source(ds_key)}")

        if not needs_update(ds_key, cache, ttl_hours=168):
            print("  Using cached version (last downloaded < 7 days ago). Run with --force to refresh.")
            # Try to load cached output
            cached_path = HF_CACHE_DIR / f"{ds_key}.json"
            if cached_path.exists():
                try:
                    cached = json.loads(cached_path.read_text(encoding="utf-8"))
                    all_chunks.extend(cached)
                    stats[ds_key] = len(cached)
                    print(f"  Loaded {len(cached):,} chunks from cache")
                    continue
                except Exception:
                    pass

        chunks = download_dataset(ds_key, max_rows=max_rows)
        all_chunks.extend(chunks)
        stats[ds_key] = len(chunks)
        cache[ds_key] = time.time()

        # Save per-dataset cache
        HF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (HF_CACHE_DIR / f"{ds_key}.json").write_text(
            json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    save_cache(cache)

    # Save combined output
    output_path = ROOT / (output or "data/raw/raw_chunks_hf.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(all_chunks, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n{'='*60}")
    print("COMPLETE!")
    print(f"Total chunks: {len(all_chunks):,}")
    print(f"Output file : {output_path}")
    print("\nPer dataset:")
    for ds, count in stats.items():
        label = HF_DATASETS[ds]['path']
        print(f"  {label:50s}: {count:>8,}")
    print(f"{'='*60}")

    return {"total": len(all_chunks), **stats}


def print_stats(chunks_file: str | Path = "data/raw/raw_chunks_hf.json") -> None:
    """Print quality statistics about collected HF dataset chunks."""
    path = ROOT / chunks_file
    if not path.exists():
        print(f"[WARN] File not found: {path}")
        return

    chunks = json.loads(path.read_text(encoding="utf-8"))
    if not chunks:
        print("No chunks to analyze.")
        return

    categories = Counter(c.get("category", "unknown") for c in chunks)
    with_code = sum(1 for c in chunks if c.get("codes"))
    avg_text_len = sum(len(c.get("text", "")) for c in chunks) / len(chunks)

    print("\nHF Dataset Chunk Statistics:")
    print(f"  Total chunks      : {len(chunks):,}")
    print(f"  With code examples : {with_code:,} ({100 * with_code // len(chunks)}%)")
    print(f"  Avg text length    : {avg_text_len:.0f} chars")
    print("\n  Categories:")
    for cat, count in categories.most_common():
        print(f"    {cat}: {count:,} ({100 * count // len(chunks)}%)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download Python code SFT datasets from HuggingFace")
    parser.add_argument("--datasets", nargs="*", help="Datasets to download (default: all)")
    parser.add_argument("--max-rows", type=int, default=None, help="Max rows per dataset")
    parser.add_argument("--output", default="data/raw/raw_chunks_hf.json", help="Output path")
    parser.add_argument("--stats", action="store_true",
                        help="Show statistics about previously collected data")
    parser.add_argument("--force", action="store_true",
                        help="Force re-download even if cached")
    args = parser.parse_args()

    if args.stats:
        print_stats(args.output)
    elif args.force:
        # Clear cache timestamp to force refresh
        cache = load_cache()
        for ds in (args.datasets or HF_DATASETS.keys()):
            cache.pop(ds, None)
        save_cache(cache)
        run(datasets=args.datasets, max_rows=args.max_rows, output=args.output)
    else:
        run(datasets=args.datasets, max_rows=args.max_rows, output=args.output)
