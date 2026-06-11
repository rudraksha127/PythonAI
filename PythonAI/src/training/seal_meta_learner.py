"""\
SEAL Meta-Learner — Curriculum Generator Training (Phase 3)
=============================================================

The meta-learner fine-tunes the curriculum generator model so that
over time, it produces better self-edit instructions.

How it works:
1. The outer loop produces reward records (acceptance rate deltas)
2. The meta-learner aggregates these into a training dataset
3. It fine-tunes the curriculum generator model (via QLoRA) on
   successful actions paired with the state context
4. Over cycles, the curriculum generator learns to choose actions
   that lead to positive acceptance rate improvements

Key insight: This is RL for RL — the curriculum generator learns
which types of training data lead to the best downstream improvements.
"""

from __future__ import annotations

import json
import logging
import random
import time
from pathlib import Path
from typing import Any, Optional

from src.training.seal_types import (
    CurriculumState,
    RewardRecord,
    SealConfig,
    SelfEditAction,
)

logger = logging.getLogger("forgeai.seal.meta")


# ═══════════════════════════════════════════════════════════════
# Meta-Training Data Builder
# ═══════════════════════════════════════════════════════════════


class MetaLearner:
    """Trains the curriculum generator to produce better self-edit actions.

    The meta-learner uses successful actions (those that improved acceptance
    rate) as positive training examples. Over time, the curriculum generator
    learns to prefer actions that yield the best results.
    """

    def __init__(self, config: Optional[SealConfig] = None):
        self.config = config or SealConfig()
        self.reward_history: list[RewardRecord] = []

    def add_reward(self, record: RewardRecord) -> None:
        """Record a reward from a completed SEAL cycle."""
        self.reward_history.append(record)
        logger.debug(f"[SEAL-META] Reward recorded: cycle={record.cycle}, "
                     f"delta={record.reward_delta:+.4f}, "
                     f"{record.improvement_direction}")

    def should_train(self) -> bool:
        """Check if there are enough reward records to run meta-learning.

        Requires at least meta_min_rewards_for_training records,
        and at least 1 positive example.
        """
        if len(self.reward_history) < self.config.meta_min_rewards_for_training:
            return False

        positive = sum(1 for r in self.reward_history if r.is_improvement())
        return positive >= 1

    def build_training_data(self) -> list[dict[str, Any]]:
        """Build a dataset of (state → successful_action) pairs.

        Returns a list of training examples where:
        - instruction: the state context
        - output: the action JSON that succeeded in that state
        """
        examples = []

        for record in self.reward_history:
            if not record.is_improvement():
                continue

            # Build the "state context" that led to the action
            state_items = []
            if record.acceptance_rate_before > 0:
                state_items.append(f"acceptance_rate: {record.acceptance_rate_before:.2%}")
            state_items.append(f"cycle: {record.cycle}")
            state_items.append(f"previous_action: {record.action.action_type.value}")
            state_items.append(f"previous_domain: {record.action.domain}")

            state_context = " | ".join(state_items)

            # The training example: given this state, generate this action
            action_json = record.action.to_json()
            reward_info = json.dumps({
                "reward_delta": record.reward_delta,
                "improvement_direction": record.improvement_direction,
            })

            example = {
                "instruction": f"State: {state_context}\nGoal: Generate the best curriculum action for this state",
                "input": f"Previous cycle reward: {reward_info}",
                "output": action_json,
                "source": "seal_meta",
                "quality_score": min(1.0, max(0.1, record.reward_delta + 0.5)),
                "timestamp": record.timestamp,
            }
            examples.append(example)

        # Add negative examples too (what NOT to do)
        for record in self.reward_history:
            if record.is_improvement():
                continue
            if random.random() > 0.3:  # Only 30% of negative examples
                continue

            state_items = [
                f"acceptance_rate: {record.acceptance_rate_before:.2%}",
                f"cycle: {record.cycle}",
                f"failed_action: {record.action.action_type.value}",
                f"failed_domain: {record.action.domain}",
            ]
            state_context = " | ".join(state_items)

            example = {
                "instruction": f"State: {state_context}\nGoal: Generate a DIFFERENT, better curriculum action",
                "input": f"Previous action failed (delta={record.reward_delta:+.2%})",
                "output": record.action.to_json(),
                "source": "seal_meta_negative",
                "quality_score": 0.3,  # Low quality = don't repeat
                "timestamp": record.timestamp,
            }
            examples.append(example)

        logger.info(f"[SEAL-META] Built {len(examples)} meta-training examples "
                    f"({sum(1 for r in self.reward_history if r.is_improvement())} positive cycles)")
        return examples

    def train(self) -> dict[str, Any]:
        """Run meta-training on the curriculum generator model.

        Fine-tunes the curriculum generator using QLoRA on successful
        (state → action) pairs so it learns to generate better instructions.
        """
        if not self.should_train():
            logger.info(f"[SEAL-META] Not enough data to train yet "
                        f"({len(self.reward_history)}/{self.config.meta_min_rewards_for_training} min)")
            return {"status": "skipped", "reason": "insufficient_data"}

        examples = self.build_training_data()
        if len(examples) < 2:
            return {"status": "skipped", "reason": "too_few_examples"}

        logger.info(f"[SEAL-META] Starting meta-training with {len(examples)} examples...")

        try:
            metrics = self._run_meta_sft(examples)
            logger.info(f"[SEAL-META] Training complete: "
                        f"loss={metrics.get('train_loss', 'N/A')}")
            return metrics

        except ImportError as e:
            logger.warning(f"[SEAL-META] Training dependencies unavailable: {e}")
            return {"status": "skipped", "reason": f"dependencies: {e}"}
        except Exception as e:
            logger.error(f"[SEAL-META] Training failed: {e}")
            return {"status": "failed", "error": str(e)}

    def _run_meta_sft(self, examples: list[dict[str, Any]]) -> dict[str, Any]:
        """Run SFT to fine-tune the curriculum generator model.

        Uses the same SDFTTrainer infrastructure but on the curriculum
        generator model and with the (state → action) dataset.
        """
        from src.training.sdft_trainer import SDFTTrainer, TrainingExample

        output_dir = Path(self.config.curriculum_adapter_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Convert to TrainingExample objects
        train_examples = [
            TrainingExample(
                instruction=ex["instruction"],
                input=ex.get("input", ""),
                output=ex["output"],
                source=ex["source"],
                quality_score=ex.get("quality_score", 0.8),
                timestamp=ex.get("timestamp", time.time()),
                language="json",
            )
            for ex in examples
        ]

        # Use a small LoRA rank for curriculum generator fine-tuning
        trainer = SDFTTrainer(
            model_name=self.config.curriculum_model,
            lora_rank=self.config.meta_lora_rank,
            learning_rate=self.config.meta_learning_rate,
            max_length=1024,
        )

        metrics = trainer.train(
            current_examples=train_examples,
            output_dir=str(output_dir),
            num_epochs=2,
            batch_size=2,
            gradient_accumulation_steps=2,
            use_4bit=True,
        )

        metrics["meta_examples"] = len(examples)
        metrics["cycle"] = len(self.reward_history)
        metrics["curriculum_adapter_path"] = str(output_dir)
        return metrics


# ═══════════════════════════════════════════════════════════════
# Outer Loop Reward Calculator
# ═══════════════════════════════════════════════════════════════

class OuterLoopReward:
    """Computes the outer loop reward signal.

    The reward is primarily the acceptance rate delta after deploying
    a new adapter. Secondary signals include training loss improvement
    and code quality metrics.
    """

    @staticmethod
    def compute_reward(
        rate_before: float,
        rate_after: float,
        inner_metrics: Optional[dict[str, Any]] = None,
    ) -> RewardRecord:
        """Compute a reward record from before/after metrics.

        Args:
            rate_before: Acceptance rate before deploying new adapter.
            rate_after: Acceptance rate after deploying new adapter.
            inner_metrics: Optional metrics from the inner loop training.

        Returns:
            A RewardRecord with the computed reward.
        """
        return RewardRecord(
            cycle=0,  # Set by caller
            action=SelfEditAction(action_type="generate_examples"),  # Set by caller
            acceptance_rate_before=rate_before,
            acceptance_rate_after=rate_after,
            examples_generated=inner_metrics.get("examples_trained", 0) if inner_metrics else 0,
            inner_train_loss=inner_metrics.get("train_loss") if inner_metrics else None,
            inner_eval_loss=inner_metrics.get("eval_loss") if inner_metrics else None,
        )

    @staticmethod
    def compute_from_capture_engine(
        capture_engine: Any,
        cycle: int,
        action: SelfEditAction,
        inner_metrics: Optional[dict[str, Any]] = None,
    ) -> Optional[RewardRecord]:
        """Compute reward using the capture engine's acceptance rate data.

        Uses the last 7 days before the current time as "before" and
        the most recent 24 hours as "after" for comparison.
        """
        if capture_engine is None:
            return None

        try:
            # Get acceptance rates over time
            rates = capture_engine.get_acceptance_rate(days=14)

            if len(rates) < 2:
                logger.warning("[SEAL] Not enough acceptance rate data for reward computation")
                return None

            # Split into before (older half) and after (newer half)
            mid = len(rates) // 2
            before_rates = [r["acceptance_rate"] for r in rates[:mid]]
            after_rates = [r["acceptance_rate"] for r in rates[mid:]]

            rate_before = sum(before_rates) / len(before_rates) if before_rates else 0.0
            rate_after = sum(after_rates) / len(after_rates) if after_rates else 0.0

            # Normalize to 0-1 scale
            rate_before /= 100.0
            rate_after /= 100.0

            record = RewardRecord(
                cycle=cycle,
                action=action,
                acceptance_rate_before=rate_before,
                acceptance_rate_after=rate_after,
                examples_generated=inner_metrics.get("examples_trained", 0) if inner_metrics else 0,
                inner_train_loss=inner_metrics.get("train_loss") if inner_metrics else None,
                inner_eval_loss=inner_metrics.get("eval_loss") if inner_metrics else None,
            )

            logger.info(f"[SEAL] Reward: Δ={record.reward_delta:+.4f} "
                        f"({rate_before*100:.1f}% → {rate_after*100:.1f}%) "
                        f"— {record.improvement_direction}")
            return record

        except Exception as e:
            logger.error(f"[SEAL] Reward computation error: {e}")
            return None
