from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STANDARD_CLEANUP_TARGETS = [
    "__pycache__",
    ".sixth",
    "FREEBUFF_HANDOFF_PROMPT.md",
    "checkpoints/augment_last_response.txt",
    "checkpoints/local_50.json",
    "checkpoints/god_mode_smoke",
    "checkpoints/local_auto_model/checkpoint-4",
    "checkpoints/local_auto_model/checkpoint-8",
    "checkpoints/full_pipeline_model/checkpoint-5",
    "checkpoints/full_pipeline_model/checkpoint-50",
]


def resolve_inside_root(relative_path: str) -> Path:
    root = ROOT.resolve()
    target = (ROOT / relative_path).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"Refusing to touch path outside project: {target}")
    return target


def path_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(file.stat().st_size for file in path.rglob("*") if file.is_file())


def collect_targets() -> list[tuple[str, Path, int]]:
    targets = []
    seen: set[Path] = set()
    for relative in STANDARD_CLEANUP_TARGETS:
        path = resolve_inside_root(relative)
        if path.exists() and path not in seen:
            targets.append((relative, path, path_size(path)))
            seen.add(path)

    checkpoints_dir = ROOT / "checkpoints"
    if checkpoints_dir.exists():
        for path in checkpoints_dir.glob("*/checkpoint-*"):
            path = path.resolve()
            if path.exists() and path not in seen:
                targets.append((str(path.relative_to(ROOT)), path, path_size(path)))
                seen.add(path)
    return targets


def remove_target(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safely clean generated clutter from the PythonAI project.")
    parser.add_argument("--apply", action="store_true", help="Actually delete cleanup targets.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    targets = collect_targets()
    total = sum(size for _, _, size in targets)

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"Cleanup mode: {mode}")
    print(f"Project root: {ROOT}")
    print(f"Targets     : {len(targets)}")
    print(f"Recoverable : {total / 1024 / 1024:.4f} MB")

    for relative, path, size in targets:
        print(f"  {'DELETE' if args.apply else 'WOULD DELETE'} {relative} ({size / 1024 / 1024:.4f} MB)")
        if args.apply:
            remove_target(path)

    if args.apply:
        print("Cleanup complete.")
    else:
        print("Run with --apply to delete these targets.")


if __name__ == "__main__":
    main()
