"""Training Configuration System.

Provides a structured `TrainingConfig` dataclass that can be loaded from
JSON, YAML, or dict.  Supports partial overrides, environment variable
expansion, and validation.

Usage:
    from src.training.config import TrainingConfig

    # From dict
    cfg = TrainingConfig.from_dict({"max_steps": 50, "learning_rate": 3e-4})

    # From JSON file
    cfg = TrainingConfig.from_file("configs/train_config.json")

    # Merge with overrides
    cfg = TrainingConfig.merge(base_cfg, overrides)
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Regex for environment variable references: ${VAR_NAME} or ${VAR_NAME:default}
ENV_VAR_PATTERN = re.compile(r"\$\{([^}:]+)(?::([^}]*))?\}")


def _resolve_env_vars(value: str) -> str:
    """Replace ${VAR} and ${VAR:default} with environment variable values."""

    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        default = match.group(2)
        return os.environ.get(var_name, default) if default else os.environ.get(var_name, match.group(0))

    return ENV_VAR_PATTERN.sub(_replace, value)


def _resolve_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Recursively resolve environment variables in a dict."""
    resolved: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, str):
            resolved[k] = _resolve_env_vars(v)
        elif isinstance(v, dict):
            resolved[k] = _resolve_dict(v)
        elif isinstance(v, list):
            resolved[k] = [_resolve_env_vars(item) if isinstance(item, str) else item for item in v]
        else:
            resolved[k] = v
    return resolved


@dataclass
class TrainingConfig:
    """Complete training configuration with defaults.

    Each field has a reasonable default.  Use `from_dict` or `from_file`
    to create a config with overrides, then pass to the trainer.
    """

    # ── Model ───────────────────────────────────────────────────
    base_model: str = "sshleifer/tiny-gpt2"
    trust_remote_code: bool = True
    load_in_4bit: bool = False
    torch_dtype: str = "float16"  # "float16", "float32", "bfloat16"

    # ── Data ────────────────────────────────────────────────────
    dataset_path: str = "data/training/training_dataset.json"
    source_files: list[str] = field(
        default_factory=lambda: [
            "training_dataset.json",
            "python_ultra_dataset_FINAL.json",
            "raw_chunks_godmode.json",
            "raw_chunks.json",
        ]
    )
    max_examples: int = 256
    max_length: int = 512
    validation_split: float = 0.1
    dataset_version: str = ""

    # ── Training ────────────────────────────────────────────────
    epochs: float = 1.0
    max_steps: int = 20
    batch_size: int = 1
    grad_accum: int = 4
    learning_rate: float = 2e-4
    lr_scheduler_type: str = "linear"  # "linear", "cosine", "constant"
    warmup_ratio: float = 0.03
    seed: int = 42

    # ── LoRA ────────────────────────────────────────────────────
    lora_rank: int = 8
    lora_alpha: int = 16
    lora_dropout: float = 0.05

    # ── Checkpointing ───────────────────────────────────────────
    output_dir: str = "checkpoints/local_auto_model"
    save_strategy: str = "steps"  # "no", "steps", "epoch"
    save_steps: int = 25
    save_total_limit: int = 3
    resume_from_checkpoint: str = ""

    # ── Evaluation ──────────────────────────────────────────────
    eval_strategy: str = "steps"  # "no", "steps", "epoch"
    eval_steps: int = 25

    # ── Unsloth (Optional — 2x faster QLoRA, 70% less VRAM) ────
    use_unsloth: bool = False
    unsloth_max_seq_length: int = 2048

    # ── Advanced ────────────────────────────────────────────────
    gradient_checkpointing: bool = False
    gradient_clip: float = 0.0  # 0 = disabled
    early_stopping_patience: int = 0  # 0 = disabled
    fp16: bool = True
    bf16: bool = False

    # ── Logging ─────────────────────────────────────────────────
    logging_steps: int = 1
    report_to_wandb: bool = False
    save_training_curves: bool = False
    viz: bool = False

    # ── INDRA Model Prompt Integration ───────────────────────────
    use_indra_prompt: bool = False
    indra_prompt_path: str = ""  # Path to custom INDRA prompt file, if any

    # ── Metadata ────────────────────────────────────────────────
    experiment_name: str = ""
    tags: list[str] = field(default_factory=list)
    notes: str = ""

    def __post_init__(self) -> None:
        """Validate config after initialization."""
        if self.learning_rate <= 0:
            raise ValueError(f"learning_rate must be positive, got {self.learning_rate}")
        if self.max_steps <= 0 and self.epochs <= 0:
            raise ValueError("Either max_steps or epochs must be > 0")
        if self.lora_rank < 1:
            raise ValueError(f"lora_rank must be >= 1, got {self.lora_rank}")
        if self.lr_scheduler_type not in ("linear", "cosine", "constant"):
            raise ValueError(f"Unknown lr_scheduler_type: {self.lr_scheduler_type}")
        if self.use_unsloth and not self.load_in_4bit:
            import warnings

            warnings.warn("Unsloth is optimized for 4-bit QLoRA. Consider setting --load-in-4bit for best results.")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TrainingConfig:
        """Create config from a (possibly partial) dict.

        Environment variables in string values (${VAR}) are resolved.
        """
        resolved = _resolve_dict(d)
        # Only pass known fields
        valid_keys = set(cls.__dataclass_fields__.keys())
        filtered = {k: v for k, v in resolved.items() if k in valid_keys}
        return cls(**filtered)

    @classmethod
    def from_file(cls, path: str | Path) -> TrainingConfig:
        """Load config from a JSON or YAML file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        content = path.read_text(encoding="utf-8")

        if path.suffix in (".yaml", ".yml"):
            try:
                import yaml

                data = yaml.safe_load(content)
            except ImportError:
                raise ImportError("PyYAML is required to load YAML configs. pip install pyyaml")
        elif path.suffix == ".json":
            data = json.loads(content)
        else:
            raise ValueError(f"Unsupported config format: {path.suffix}. Use .json or .yaml")

        if not isinstance(data, dict):
            raise ValueError(f"Config file must contain a dict, got {type(data)}")

        return cls.from_dict(data)

    @classmethod
    def merge(cls, base: TrainingConfig, overrides: dict[str, Any] | TrainingConfig) -> TrainingConfig:
        """Merge two configs, with overrides taking precedence."""
        if isinstance(overrides, TrainingConfig):
            overrides = asdict(overrides)
        base_dict = asdict(base)
        base_dict.update(overrides)
        return cls(**base_dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert config to a plain dict."""
        return asdict(self)

    def to_json(self, path: str | Path, indent: int = 2) -> Path:
        """Save config to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=indent),
            encoding="utf-8",
        )
        return path

    def update(self, **kwargs: Any) -> TrainingConfig:
        """Return a new config with the given fields updated."""
        d = self.to_dict()
        d.update(kwargs)
        return TrainingConfig(**d)

    @property
    def effective_steps(self) -> int:
        """Return the effective number of training steps."""
        return self.max_steps if self.max_steps > 0 else int(self.epochs * 100)

    @property
    def summary(self) -> str:
        """Human-readable summary of key training parameters."""
        un = "[Unsloth] " if self.use_unsloth else ""
        return (
            f"Model: {self.base_model}\n"
            f"  {un}Steps: {self.effective_steps} | LR: {self.learning_rate:.2e}\n"
            f"  LoRA: r={self.lora_rank}, alpha={self.lora_alpha}\n"
            f"  Batch: {self.batch_size} x {self.grad_accum} accum\n"
            f"  Max length: {self.max_length} | Max examples: {self.max_examples}\n"
            f"  Output: {self.output_dir}\n"
            f"  Scheduler: {self.lr_scheduler_type} | 4-bit: {self.load_in_4bit}"
        )


# ── Preset configurations ─────────────────────────────────────────────


def smoke_config() -> TrainingConfig:
    """Minimal config for smoke testing."""
    return TrainingConfig(
        base_model="sshleifer/tiny-gpt2",
        max_examples=32,
        max_steps=5,
        max_length=128,
        batch_size=1,
        grad_accum=1,
        save_strategy="no",
        eval_strategy="no",
        output_dir="checkpoints/smoke_test",
    )


def quick_config() -> TrainingConfig:
    """Quick training config for rapid iteration."""
    return TrainingConfig(
        base_model="sshleifer/tiny-gpt2",
        max_examples=128,
        max_steps=20,
        max_length=384,
        batch_size=1,
        grad_accum=4,
        learning_rate=2e-4,
        save_strategy="steps",
        save_steps=10,
        eval_strategy="steps",
        eval_steps=10,
        output_dir="checkpoints/quick_train",
    )


def qwen_config() -> TrainingConfig:
    """Config for training on a Qwen model."""
    return TrainingConfig(
        base_model="Qwen/Qwen2.5-Coder-0.5B-Instruct",
        max_examples=256,
        max_steps=50,
        max_length=512,
        batch_size=1,
        grad_accum=4,
        learning_rate=2e-4,
        lora_rank=8,
        lora_alpha=16,
        save_strategy="steps",
        save_steps=25,
        eval_strategy="steps",
        eval_steps=25,
        output_dir="checkpoints/qwen_finetune",
        dataset_path="data/training/training_dataset.json",
    )


def production_config() -> TrainingConfig:
    """Config for a more serious training run."""
    return TrainingConfig(
        base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
        max_examples=4096,
        max_steps=500,
        max_length=1024,
        batch_size=2,
        grad_accum=8,
        learning_rate=1e-4,
        lora_rank=16,
        lora_alpha=32,
        lora_dropout=0.05,
        load_in_4bit=True,
        use_unsloth=True,
        save_strategy="steps",
        save_steps=50,
        eval_strategy="steps",
        eval_steps=50,
        output_dir="checkpoints/production_run",
        dataset_path="data/training/training_dataset.json",
        dataset_version="v2.0",
        experiment_name="production_v2",
        tags=["production", "qwen", "v2", "unsloth"],
        viz=True,
    )


# ── INDRA Model Prompt Integration ────────────────────────────────────


def config_with_indra(
    base_config: TrainingConfig,
    use_indra: bool = True,
    custom_prompt_path: str = "",
) -> TrainingConfig:
    """Return a config with INDRA model system prompt integration enabled."""
    if use_indra:
        try:
            from src.training.indra_prompt import get_indra_config

            get_indra_config()
            return base_config.update(
                use_indra_prompt=True,
                indra_prompt_path=custom_prompt_path or "",
                tags=base_config.tags + ["indra"],
                notes=(base_config.notes + "\n" if base_config.notes else "")
                + "INDRA System Prompt: Built from GENERALIST_AI_MODEL_PROMPT.md "
                "and ANTI_GRAVITY_GOD_MODE_PROMPT.md",
            )
        except ImportError:
            pass
    return base_config


def indra_smoke_config() -> TrainingConfig:
    """Smoke test config with INDRA prompt enabled."""
    return config_with_indra(smoke_config(), use_indra=True)


def indra_quick_config() -> TrainingConfig:
    """Quick training config with INDRA prompt enabled."""
    return config_with_indra(quick_config(), use_indra=True)


def indra_qwen_config() -> TrainingConfig:
    """Qwen finetune config with INDRA prompt enabled."""
    return config_with_indra(qwen_config(), use_indra=True)


def indra_production_config() -> TrainingConfig:
    """Production config with INDRA prompt enabled."""
    return config_with_indra(production_config(), use_indra=True)


if __name__ == "__main__":
    print("[TrainingConfig] Smoke test:\n")
    cfg = smoke_config()
    print(cfg.summary)
    print()

    # Test merge
    cfg2 = cfg.update(max_steps=10, learning_rate=1e-3)
    print(f"Merged steps: {cfg2.max_steps}")
    print(f"Merged LR: {cfg2.learning_rate}")
    print(f"Original steps: {cfg.max_steps} (unchanged)")
    print()

    # Test INDRA integration
    cfg_indra = indra_smoke_config()
    print(f"INDRA enabled: {cfg_indra.use_indra_prompt}")
    print(f"INDRA tags: {cfg_indra.tags}")
    print()

    # Test env var resolution
    import os

    os.environ["TRAIN_OUTPUT_DIR"] = "checkpoints/env_test"
    cfg3 = TrainingConfig.from_dict({"output_dir": "${TRAIN_OUTPUT_DIR}"})
    print(f"Env var resolved: {cfg3.output_dir}")
