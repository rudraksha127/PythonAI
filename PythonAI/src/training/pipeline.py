from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

from src.utils.models import dataset_profile, save_json


ROOT = Path(__file__).resolve().parent.parent.parent
RAW_CHUNKS = ROOT / "data" / "raw" / "raw_chunks_godmode.json"
CLEAN_CHUNKS = ROOT / "data" / "processed" / "cleaned_chunks.json"
ANALYSIS_REPORT = ROOT / "data" / "processed" / "analysis_report.json"
TRAINING_DATA = ROOT / "data" / "training" / "training_dataset.json"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json_file(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def run_data_collection(refresh: bool) -> None:
    from src.data import collector

    if RAW_CHUNKS.exists() and not refresh:
        print("[1/4] Collecting source data... skipped (existing file found)")
        return

    print("[1/4] Collecting source data...")
    collector.run()


def clean_and_analyze_chunks() -> list[dict[str, Any]]:
    print("[2/4] Cleaning and analyzing chunks...")

    if not RAW_CHUNKS.exists():
        raise FileNotFoundError(f"Missing source file: {RAW_CHUNKS}")

    chunks = load_json(RAW_CHUNKS)
    cleaned: list[dict[str, Any]] = []
    type_counts: Counter = Counter()
    category_counts: Counter = Counter()
    version_counts: Counter = Counter()

    skip_types = {"font", "image_png", "image_jpg", "image_gif", "static", "css"}

    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue

        text = str(chunk.get("text", "")).strip()
        title = str(chunk.get("title", "")).strip()
        chunk_type = str(chunk.get("type", "")).strip()

        if len(text) < 80 or chunk_type in skip_types:
            continue

        normalized = {
            **chunk,
            "title": title or chunk.get("filepath", "Python docs chunk"),
            "text": text,
            "category": str(chunk.get("category", "general")),
            "version": str(chunk.get("version", "")),
            "type": chunk_type or "document",
        }
        cleaned.append(normalized)
        type_counts[normalized["type"]] += 1
        category_counts[normalized["category"]] += 1
        version_counts[normalized["version"]] += 1

    save_json_file(CLEAN_CHUNKS, cleaned)

    report = {
        "total_chunks": len(chunks),
        "cleaned_chunks": len(cleaned),
        "by_type": type_counts.most_common(),
        "by_category": category_counts.most_common(20),
        "by_version": version_counts.most_common(20),
    }
    save_json_file(ANALYSIS_REPORT, report)

    print(f"    raw chunks   : {len(chunks):,}")
    print(f"    cleaned      : {len(cleaned):,}")
    print(f"    report       : {ANALYSIS_REPORT.name}")
    return cleaned


def build_training_examples(chunks: list[dict[str, Any]], max_examples: int) -> None:
    print("[3/4] Generating training pairs locally...")

    examples: list[dict[str, Any]] = []
    seen: set[str] = set()

    shuffled_chunks = list(chunks)
    random.Random(42).shuffle(shuffled_chunks)

    for chunk in shuffled_chunks:
        title = str(chunk.get("title", "Python docs"))
        text = str(chunk.get("text", ""))
        version = str(chunk.get("version", ""))
        category = str(chunk.get("category", "general"))
        code_blocks = chunk.get("codes", []) or []
        code = str(code_blocks[0]).strip() if code_blocks else ""

        source = str(chunk.get("filepath", title))

        candidates = [
            (
                f"Explain {title} like a senior engineer would for a task handoff.",
                f"{title}:\n{text[:1500]}\n\nKey point: focus on practical usage and failure modes.",
            ),
            (
                f"Write a practical implementation note for {title}.",
                f"Implementation summary for {title}:\n{text[:1200]}\n\nWhen you use it, verify inputs, outputs, and error handling.",
            ),
            (
                f"What are the pitfalls and edge cases for {title}?",
                f"Pitfalls for {title}:\n- version drift\n- input validation\n- performance trade-offs\n- compatibility checks\n\nContext:\n{text[:1000]}",
            ),
        ]

        if code:
            candidates.append(
                (
                    f"Review this code example for {title} and improve it.",
                    f"Code review notes for {title}:\n```python\n{code[:1000]}\n```\n\nRecommended improvement: keep the interface small and test the edge cases.",
                )
            )

        for instruction, output in candidates:
            fingerprint = (instruction + "|" + output).strip()
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            examples.append({
                "instruction": instruction,
                "output": output,
                "source": source,
                "category": category,
                "version": version,
            })

            if len(examples) >= max_examples:
                break

        if len(examples) >= max_examples:
            break

    save_json_file(TRAINING_DATA, examples)
    print(f"    training pairs: {len(examples):,}")
    print(f"    feed file      : {TRAINING_DATA.name}")


def launch_training(
    model_name: str,
    max_examples: int,
    max_steps: int,
    batch_size: int,
    grad_accum: int,
    dataset_version: str,
) -> None:
    print("[4/4] Launching fine-tuning...")
    command = [
        sys.executable,
        "-m", "src.training.trainer",
        "--base-model", model_name,
        "--source-files", str(TRAINING_DATA),
        "--max-examples", str(max_examples),
        "--max-steps", str(max_steps),
        "--batch-size", str(batch_size),
        "--grad-accum", str(grad_accum),
        "--output-dir", str(ROOT / "checkpoints" / "full_pipeline_model"),
    ]

    if dataset_version:
        command.extend(["--dataset-version", dataset_version])

    print("    command:")
    print("    " + " ".join(command))
    subprocess.run(command, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run collect -> clean -> generate -> train pipeline.")
    parser.add_argument("--base-model", default="sshleifer/tiny-gpt2")
    parser.add_argument("--max-examples", type=int, default=256)
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=2)
    parser.add_argument("--refresh-collection", action="store_true")
    parser.add_argument("--skip-collection", action="store_true",
                        help="Skip data collection step")
    parser.add_argument("--skip-generation", action="store_true",
                        help="Skip training pair generation step")
    parser.add_argument("--dataset-version", default="",
                        help="Label to tag output checkpoints")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start_time = time.time()
    stage_times: dict[str, float] = {}

    print(f"\nPipeline started at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Base model: {args.base_model}")
    if args.dataset_version:
        print(f"Dataset version: {args.dataset_version}")

    stage_start = time.time()
    if not args.skip_collection:
        run_data_collection(args.refresh_collection)
    else:
        print("[1/4] Collecting source data... skipped (--skip-collection)")
    stage_times["collection"] = time.time() - stage_start

    stage_start = time.time()
    chunks = clean_and_analyze_chunks()
    stage_times["clean_analyze"] = time.time() - stage_start

    stage_start = time.time()
    if not args.skip_generation:
        build_training_examples(chunks, args.max_examples)
    else:
        print("[3/4] Generating training pairs... skipped (--skip-generation)")
    stage_times["generation"] = time.time() - stage_start

    stage_start = time.time()
    launch_training(
        args.base_model,
        args.max_examples,
        args.max_steps,
        args.batch_size,
        args.grad_accum,
        args.dataset_version,
    )
    stage_times["training"] = time.time() - stage_start

    elapsed = time.time() - start_time
    print("\nStage timing:")
    for name, seconds in stage_times.items():
        print(f"  {name:14s}: {seconds:.0f}s")
    print(f"\nPipeline completed in {elapsed:.0f}s ({elapsed / 60:.1f} min)")
    print(f"Finished at {time.strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
