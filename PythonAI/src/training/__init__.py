"""PythonAI Training Pipeline.

Modules:
  pipeline     — Full training pipeline: collect → clean → generate → train
  trainer      — LoRA fine-tuning using PEFT + transformers
  evaluator    — Benchmark evaluation (perplexity, loss, generation quality)
  config       — TrainingConfig dataclass with JSON/YAML loading and presets
  checkpoint_manager — Save, list, compare, clean training checkpoints
  comparison   — Compare model outputs side-by-side
  viz          — Training visualization dashboards
  run          — CLI entry point for training runs
  indra_prompt — INDRA model system prompt for training configuration
"""

from __future__ import annotations

from src.training.config import (
    TrainingConfig,
    smoke_config,
    quick_config,
    qwen_config,
    production_config,
)

from src.training.checkpoint_manager import (
    CheckpointManager,
    CheckpointMeta,
    format_meta,
)

from src.training.indra_prompt import (
    INDRA_SYSTEM_PROMPT,
    INDRA_CONSTITUTION,
    INDRA_CORE_TENETS,
    build_training_system_prompt,
    get_indra_config,
    setup_indra_training,
)

__all__ = [
    "TrainingConfig",
    "smoke_config",
    "quick_config",
    "qwen_config",
    "production_config",
    "CheckpointManager",
    "CheckpointMeta",
    "format_meta",
    # INDRA Model System Prompt
    "INDRA_SYSTEM_PROMPT",
    "INDRA_CONSTITUTION",
    "INDRA_CORE_TENETS",
    "build_training_system_prompt",
    "get_indra_config",
    "setup_indra_training",
]
