from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent.parent


def load_rows(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON list.")
    return [row for row in data if isinstance(row, dict)]


def save_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def row_hash(row: dict[str, Any]) -> str:
    instruction = str(row.get("instruction", "")).strip()
    output = str(row.get("output", "")).strip()
    return hashlib.sha256(f"{instruction}\n---\n{output}".encode("utf-8")).hexdigest()


def output_len(row: dict[str, Any]) -> int:
    return len(str(row.get("output", "")).strip())


def valid_row(row: dict[str, Any], min_output_chars: int) -> bool:
    instruction = str(row.get("instruction", "")).strip()
    output = str(row.get("output", "")).strip()
    return len(instruction) >= 10 and len(output) >= min_output_chars


def print_distribution(rows: list[dict[str, Any]], label: str = "") -> None:
    """Print category and version distribution for a set of rows."""
    if not rows:
        print("No rows to display.")
        return

    if label:
        print(f"\n{label} Distribution:")
    else:
        print("\nDistribution:")

    categories = Counter(str(r.get("category", "unknown")) for r in rows)
    versions = Counter(str(r.get("version", "unknown")) for r in rows)
    types = Counter(str(r.get("_type", r.get("type", "unknown"))) for r in rows)

    print(f"  Total rows: {len(rows)}")

    if categories:
        print(f"  Categories (top 10):")
        for cat, count in categories.most_common(10):
            print(f"    {cat}: {count} ({100 * count // len(rows)}%)")

    if versions:
        print(f"  Versions (top 10):")
        for ver, count in versions.most_common(10):
            print(f"    {ver}: {count} ({100 * count // len(rows)}%)")

    if types:
        print(f"  Types (top 10):")
        for t, count in types.most_common(10):
            print(f"    {t}: {count} ({100 * count // len(rows)}%)")


def merge(
    base_rows: list[dict[str, Any]],
    addition_rows: list[dict[str, Any]],
    min_output_chars: int,
    keep_old: bool = False,
) -> list[dict[str, Any]]:
    """Merge two datasets with deduplication.

    Args:
        base_rows: The original/base dataset rows.
        addition_rows: The new rows to add.
        min_output_chars: Minimum output length to accept a row.
        keep_old: When duplicates conflict, keep the base row (True) or the longer one (False).

    Returns:
        Merged list of rows.
    """
    merged = [row for row in base_rows if valid_row(row, min_output_chars)]
    seen: dict[str, int] = {}  # hash -> index in merged

    for i, row in enumerate(merged):
        digest = row_hash(row)
        seen[digest] = i

    added = 0
    conflicts = 0

    for row in addition_rows:
        if not valid_row(row, min_output_chars):
            continue
        digest = row_hash(row)
        if digest in seen:
            # Conflict resolution
            conflicts += 1
            existing_idx = seen[digest]
            existing = merged[existing_idx]
            if not keep_old and output_len(row) > output_len(existing):
                merged[existing_idx] = row  # Replace with longer output
            continue
        seen[digest] = len(merged)
        merged.append(row)
        added += 1

    print(f"Base rows        : {len(base_rows)}")
    print(f"Addition rows    : {len(addition_rows)}")
    print(f"Valid added      : {added}")
    print(f"Duplicates       : {conflicts}")
    print(f"Conflict strategy: {'keep old' if keep_old else 'keep longer'}")
    print(f"Output rows      : {len(merged)}")

    if conflicts > 0:
        resolved = conflicts
        if not keep_old:
            # Count how many were actually replaced (had longer output)
            replaced = sum(
                1 for row in addition_rows
                if valid_row(row, min_output_chars) and row_hash(row) in seen
            )
            print(f"Replaced (longer) : {replaced}")

    return merged


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge supervised training datasets with deduplication.")
    parser.add_argument("--base", default="training_dataset.json")
    parser.add_argument("--add", required=True, help="Dataset to merge in")
    parser.add_argument("--output", default="training_dataset_augmented.json")
    parser.add_argument("--min-output-chars", type=int, default=80)
    parser.add_argument("--keep-old", action="store_true", help="Keep base row when duplicates conflict")
    parser.add_argument("--stats-only", action="store_true", help="Print distribution stats without saving")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    base_rows = load_rows(ROOT / args.base)
    addition_rows = load_rows(ROOT / args.add)

    # Stats-only mode: print distribution and exit
    if args.stats_only:
        print_distribution(base_rows, "Base")
        print_distribution(addition_rows, "Addition")
        return

    rows = merge(base_rows, addition_rows, args.min_output_chars, keep_old=args.keep_old)
    save_rows(ROOT / args.output, rows)

    print(f"\nDistribution (merged):")
    print_distribution(rows)
    print(f"\nSaved: {args.output}")


if __name__ == "__main__":
    main()
