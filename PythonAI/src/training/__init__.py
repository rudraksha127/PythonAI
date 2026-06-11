"""PythonAI Training Pipeline.

Modules:
  pipeline       — Full training pipeline: collect → clean → generate → train
  trainer        — LoRA fine-tuning using PEFT + transformers
  evaluator      — Benchmark evaluation (perplexity, loss, generation quality)
  config         — TrainingConfig dataclass with JSON/YAML loading and presets
  checkpoint_manager — Save, list, compare, clean training checkpoints
  comparison     — Compare model outputs side-by-side
  viz            — Training visualization dashboards
  run            — CLI entry point for training runs
  indra_prompt   — INDRA model system prompt for training configuration
  seal_types     — SEAL Phase 3 shared dataclasses (SelfEditAction, CurriculumState, RewardRecord)
  seal_curriculum  — Self-curriculum generator (LLM decides what to learn next)
  seal_inner_loop  — Inner SFT loop: synthetic data generation + QLoRA training
  seal_meta_learner — Meta-learning: trains curriculum generator from outer loop rewards
  phase3_seal    — Main SEAL orchestrator (curriculum → train → reward → meta-learn)
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

# SEAL Phase 3 — Autonomous Self-Improvement Loop
from src.training.seal_types import (
    SealActionType,
    SelfEditAction,
    CurriculumState,
    RewardRecord,
    SealConfig,
)
from src.training.seal_curriculum import CurriculumGenerator
from src.training.seal_inner_loop import SealInnerLoop, SyntheticExampleGenerator
from src.training.seal_meta_learner import MetaLearner, OuterLoopReward
from src.training.phase3_seal import SealOrchestrator

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
    # SEAL Phase 3
    "SealActionType",
    "SelfEditAction",
    "CurriculumState",
    "RewardRecord",
    "SealConfig",
    "CurriculumGenerator",
    "SealInnerLoop",
    "SyntheticExampleGenerator",
    "MetaLearner",
    "OuterLoopReward",
    "SealOrchestrator",
]
