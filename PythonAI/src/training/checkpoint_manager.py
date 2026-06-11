"""Checkpoint Manager — Save, list, compare, and clean training checkpoints.

Provides structured checkpoint metadata management including:
  - Automatic naming with timestamps + metrics
  - Listing with filtering by model, date, metric
  - Comparing checkpoints side-by-side
  - Cleaning old checkpoints to save space
  - Best checkpoint selection by metric

Usage:
    from src.training.checkpoint_manager import CheckpointManager
    mgr = CheckpointManager(base_dir="checkpoints")
    mgr.save(metrics={"eval_loss": 0.5, "train_loss": 0.3})
    mgr.list()
    mgr.clean(keep_best=3)
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from src.training.config import TrainingConfig

# Metadata file name inside each checkpoint directory
META_FILE = ".checkpoint_meta.json"
BEST_CHECKPOINT_SYMLINK = "best"


@dataclass
class CheckpointMeta:
    """Metadata stored inside each checkpoint directory."""

    name: str
    created_at: str = ""  # ISO 8601
    step: int = 0
    epoch: float = 0.0
    train_loss: float | None = None
    eval_loss: float | None = None
    learning_rate: float | None = None
    max_length: int = 0
    base_model: str = ""
    dataset_version: str = ""
    config_hash: str = ""  # Hash of the config used
    tags: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    num_trainable_params: int = 0
    notes: str = ""


class CheckpointManager:
    """Manage training checkpoints in a base directory.

    Each checkpoint is stored in a subdirectory with a metadata JSON file.

    Attributes:
        base_dir: Root directory for all checkpoints.
        meta_file: Name of the metadata JSON file inside each checkpoint.
    """

    def __init__(
        self,
        base_dir: str | Path = "checkpoints",
        meta_file: str = META_FILE,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.meta_file = meta_file
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def checkpoint_dir(self, name: str) -> Path:
        """Return the path to a named checkpoint directory."""
        return self.base_dir / name

    def list(
        self,
        sort_by: str = "created_at",
        reverse: bool = True,
        max_results: int | None = None,
        model_filter: str | None = None,
        tag_filter: str | None = None,
    ) -> list[CheckpointMeta]:
        """List all checkpoints with their metadata.

        Args:
            sort_by: Field to sort by (created_at, step, eval_loss, train_loss).
            reverse: Sort descending if True.
            max_results: Limit number of results.
            model_filter: Only checkpoints from this base model.
            tag_filter: Only checkpoints with this tag.

        Returns:
            List of CheckpointMeta objects.
        """
        checkpoints: list[CheckpointMeta] = []

        for entry in sorted(self.base_dir.iterdir()):
            if not entry.is_dir():
                continue
            meta_path = entry / self.meta_file
            if not meta_path.exists():
                continue
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                meta = CheckpointMeta(**data)
                if model_filter and meta.base_model != model_filter:
                    continue
                if tag_filter and tag_filter not in meta.tags:
                    continue
                checkpoints.append(meta)
            except (json.JSONDecodeError, TypeError, KeyError):
                continue

        # Sort
        if sort_by == "created_at" or sort_by == "name":
            checkpoints.sort(key=lambda c: getattr(c, sort_by, ""), reverse=reverse)
        elif sort_by in ("step", "epoch", "duration_seconds"):
            checkpoints.sort(key=lambda c: getattr(c, sort_by, 0) or 0, reverse=reverse)
        elif sort_by in ("eval_loss", "train_loss"):
            # For loss, lower is better
            valid = [c for c in checkpoints if getattr(c, sort_by, None) is not None]
            valid.sort(key=lambda c: getattr(c, sort_by, float("inf")))
            others = [c for c in checkpoints if getattr(c, sort_by, None) is None]
            checkpoints = valid + others

        return checkpoints[:max_results] if max_results else checkpoints

    def save(
        self,
        name: str | None = None,
        step: int = 0,
        epoch: float = 0.0,
        train_loss: float | None = None,
        eval_loss: float | None = None,
        learning_rate: float | None = None,
        max_length: int = 0,
        base_model: str = "",
        dataset_version: str = "",
        config: TrainingConfig | None = None,
        tags: list[str] | None = None,
        duration_seconds: float = 0.0,
        num_trainable_params: int = 0,
        notes: str = "",
    ) -> str:
        """Save a checkpoint metadata record.

        Args:
            name: Checkpoint name (auto-generated if None).
            step: Current training step.
            epoch: Current epoch.
            train_loss: Current training loss.
            eval_loss: Current eval loss (if available).
            learning_rate: Current learning rate.
            max_length: Sequence length used.
            base_model: Base model name.
            dataset_version: Dataset version string.
            config: TrainingConfig snapshot.
            tags: Optional tags for filtering.
            duration_seconds: Training duration so far.
            num_trainable_params: Number of trainable parameters.
            notes: Optional notes/description.

        Returns:
            Name of the checkpoint directory created.
        """
        # Auto-generate name if not provided
        if not name:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            model_short = base_model.split("/")[-1][:20] if base_model else "model"
            name = f"{model_short}_step{step}_{timestamp}"

        meta = CheckpointMeta(
            name=name,
            created_at=datetime.now(timezone.utc).isoformat(),
            step=step,
            epoch=epoch,
            train_loss=train_loss,
            eval_loss=eval_loss,
            learning_rate=learning_rate,
            max_length=max_length,
            base_model=base_model,
            dataset_version=dataset_version,
            tags=tags or [],
            duration_seconds=duration_seconds,
            num_trainable_params=num_trainable_params,
            notes=notes,
        )

        if config:
            meta.config_hash = str(hash(json.dumps(config.to_dict(), sort_keys=True)))

        # Write metadata
        ckpt_dir = self.checkpoint_dir(name)
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        meta_path = ckpt_dir / self.meta_file
        meta_path.write_text(
            json.dumps(asdict(meta), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return name

    def get(self, name: str) -> CheckpointMeta | None:
        """Get metadata for a specific checkpoint."""
        ckpt_dir = self.checkpoint_dir(name)
        meta_path = ckpt_dir / self.meta_file
        if not meta_path.exists():
            return None
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            return CheckpointMeta(**data)
        except (json.JSONDecodeError, TypeError, KeyError):
            return None

    def delete(self, name: str, dry_run: bool = False) -> bool:
        """Delete a checkpoint directory.

        Args:
            name: Checkpoint name to delete.
            dry_run: If True, only print what would be deleted.

        Returns:
            True if deleted, False if not found.
        """
        ckpt_dir = self.checkpoint_dir(name)
        if not ckpt_dir.exists() or not ckpt_dir.is_dir():
            return False

        size = self._dir_size(ckpt_dir)
        if dry_run:
            print(f"[Dry Run] Would delete: {ckpt_dir} ({size / 1024:.1f} KB)")
            return True

        print(f"[CheckpointManager] Deleting: {ckpt_dir.name} ({size / 1024:.1f} KB)")
        shutil.rmtree(ckpt_dir)
        return True

    def clean(
        self,
        keep_best: int = 3,
        keep_last: int = 5,
        max_age_days: int = 90,
        dry_run: bool = False,
    ) -> list[str]:
        """Clean old checkpoints, keeping the best and most recent.

        Args:
            keep_best: Number of best checkpoints (by eval_loss) to keep.
            keep_last: Number of most recent checkpoints to keep.
            max_age_days: Delete checkpoints older than this.
            dry_run: If True, only print what would be deleted.

        Returns:
            List of deleted checkpoint names.
        """
        all_ckpts = self.list()
        deleted: list[str] = []

        # Keep the ones with best eval loss
        by_loss = [c for c in all_ckpts if c.eval_loss is not None]
        by_loss.sort(key=lambda c: c.eval_loss)  # Lowest loss first
        keep_names: set[str] = {c.name for c in by_loss[:keep_best]}

        # Keep the most recent by step
        by_step = sorted(
            [c for c in all_ckpts if c.name not in keep_names],
            key=lambda c: c.step,
            reverse=True,
        )
        keep_names.update(c.name for c in by_step[:keep_last])

        # Age-based deletion
        time.time()
        for c in all_ckpts:
            if c.name in keep_names:
                continue

            # Check age
            if c.created_at:
                try:
                    created = datetime.fromisoformat(c.created_at.replace("Z", "+00:00"))
                    age_days = (datetime.now(timezone.utc) - created).days
                    if age_days < max_age_days:
                        continue
                except (ValueError, AttributeError):
                    pass  # Can't parse date, don't delete

            if self.delete(c.name, dry_run=dry_run):
                deleted.append(c.name)

        return deleted

    def find_best(
        self,
        metric: str = "eval_loss",
        model_filter: str | None = None,
    ) -> CheckpointMeta | None:
        """Find the best checkpoint by a given metric.

        Args:
            metric: Metric to optimize ('eval_loss' or 'train_loss').
            model_filter: Optional base model filter.

        Returns:
            Best checkpoint metadata, or None if none found.
        """
        all_ckpts = self.list(
            sort_by=metric,
            reverse=False,  # Low loss = best
            model_filter=model_filter,
        )
        if all_ckpts:
            return all_ckpts[0]
        return None

    def compare(
        self,
        names: list[str] | None = None,
    ) -> str:
        """Compare multiple checkpoints side-by-side.

        Args:
            names: Checkpoint names to compare (default: last 5).

        Returns:
            Formatted comparison table as a string.
        """
        if not names:
            names = [c.name for c in self.list(max_results=5)]

        checkpoints = []
        for name in names:
            meta = self.get(name)
            if meta:
                checkpoints.append(meta)

        if not checkpoints:
            return "No checkpoints found."

        lines = [
            f"{'Name':30s} {'Step':>6s} {'Train Loss':>10s} {'Eval Loss':>10s} "
            f"{'LR':>10s} {'Duration':>8s} {'Tags':>20s}"
        ]
        lines.append("─" * len(lines[0]))

        for c in checkpoints:
            dur_str = f"{c.duration_seconds:.0f}s" if c.duration_seconds > 0 else ""
            tag_str = ",".join(c.tags[:3]) if c.tags else ""
            lines.append(
                f"{c.name[:30]:30s} {c.step:>6d} "
                f"{c.train_loss or '?':>10} {c.eval_loss or '?':>10} "
                f"{c.learning_rate or '?':>10} {dur_str:>8s} {tag_str:>20s}"
            )

        return "\n".join(lines)

    def get_latest(self) -> CheckpointMeta | None:
        """Get the most recently created checkpoint."""
        all_ckpts = self.list(sort_by="created_at", max_results=1)
        return all_ckpts[0] if all_ckpts else None

    def total_disk_usage(self) -> int:
        """Total bytes used by all checkpoints."""
        total = 0
        for entry in self.base_dir.iterdir():
            if entry.is_dir():
                total += self._dir_size(entry)
        return total

    @staticmethod
    def _dir_size(path: Path) -> int:
        """Compute total size of a directory in bytes."""
        total = 0
        for f in path.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
        return total


def format_meta(meta: CheckpointMeta) -> str:
    """Format a CheckpointMeta as a readable string."""
    lines = [
        f"  Name     : {meta.name}",
        f"  Created  : {meta.created_at}",
        f"  Step     : {meta.step}",
        f"  Epoch    : {meta.epoch}",
    ]
    if meta.train_loss is not None:
        lines.append(f"  Train    : {meta.train_loss:.4f}")
    if meta.eval_loss is not None:
        lines.append(f"  Eval     : {meta.eval_loss:.4f}")
    if meta.base_model:
        lines.append(f"  Model    : {meta.base_model}")
    if meta.dataset_version:
        lines.append(f"  Dataset  : {meta.dataset_version}")
    if meta.duration_seconds > 0:
        lines.append(f"  Duration : {meta.duration_seconds:.0f}s")
    if meta.num_trainable_params > 0:
        lines.append(f"  Params   : {meta.num_trainable_params:,}")
    if meta.tags:
        lines.append(f"  Tags     : {', '.join(meta.tags)}")
    if meta.notes:
        lines.append(f"  Notes    : {meta.notes}")
    return "\n".join(lines)


if __name__ == "__main__":
    print("[CheckpointManager] Demo\n")

    mgr = CheckpointManager(base_dir="checkpoints/demo_checkpoints")

    # Simulate saving a few checkpoints
    mgr.save(
        name="qwen_step10",
        step=10,
        epoch=0.2,
        train_loss=1.5,
        eval_loss=1.8,
        learning_rate=2e-4,
        base_model="Qwen/Qwen2.5-Coder-0.5B-Instruct",
        tags=["qwen", "experiment"],
        duration_seconds=120,
    )

    mgr.save(
        name="qwen_step20",
        step=20,
        epoch=0.4,
        train_loss=0.8,
        eval_loss=1.2,
        learning_rate=1.5e-4,
        base_model="Qwen/Qwen2.5-Coder-0.5B-Instruct",
        tags=["qwen", "experiment"],
        duration_seconds=240,
    )

    mgr.save(
        name="qwen_step30",
        step=30,
        epoch=0.6,
        train_loss=0.5,
        eval_loss=0.9,
        learning_rate=1e-4,
        base_model="Qwen/Qwen2.5-Coder-0.5B-Instruct",
        tags=["qwen", "experiment"],
        duration_seconds=360,
    )

    print("All checkpoints:")
    print(mgr.compare())

    print(f"\nBest checkpoint: {format_meta(mgr.find_best())}")

    print(f"\nLatest checkpoint: {format_meta(mgr.get_latest())}")

    # Clean up demo
    import shutil

    shutil.rmtree("checkpoints/demo_checkpoints", ignore_errors=True)
    print("\n[Done] Demo checkpoints cleaned up.")
