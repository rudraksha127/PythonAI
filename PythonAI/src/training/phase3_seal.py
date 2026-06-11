"""\
SEAL Phase 3 — Main Orchestrator (NeurIPS 2025 Implementation)
===============================================================

Complete autonomous self-improvement loop:

  1. Curriculum Generator decides what to learn next
  2. Inner Loop generates synthetic data + runs SFT
  3. Outer Loop measures acceptance rate improvement
  4. Meta-Learner trains the curriculum generator

Usage:
    python -m src.training.phase3_seal \
        --model qwen2.5-coder:7b-instruct \
        --cycles 3 \
        --curriculum-model qwen2.5-coder:7b-instruct

    # Single cycle (dry-run curriculum only)
    python -m src.training.phase3_seal --dry-run

    # With capture engine integration
    python -m src.training.phase3_seal --capture
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any

from src.training.seal_curriculum import CurriculumGenerator
from src.training.seal_inner_loop import SealInnerLoop
from src.training.seal_meta_learner import MetaLearner, OuterLoopReward
from src.training.seal_types import (
    RewardRecord,
    SealActionType,
    SealConfig,
    SelfEditAction,
)

logger = logging.getLogger("forgeai.seal")


class SealOrchestrator:
    """Orchestrates the complete SEAL dual-loop training cycle.

    This is the top-level controller that runs the full
    curriculum → train → evaluate → meta-learn loop.
    """

    def __init__(
        self,
        config: SealConfig | None = None,
        capture_engine: Any = None,
    ):
        self.config = config or SealConfig()

        # Sub-components
        self.curriculum = CurriculumGenerator(config)
        self.inner_loop = SealInnerLoop(config, capture_engine)
        self.meta_learner = MetaLearner(config)
        self.reward_calc = OuterLoopReward()

        # Capture engine for real signal data
        self.capture_engine = capture_engine

        # Cycle tracking
        self.current_cycle = 0
        self.last_action: SelfEditAction | None = None
        self.last_inner_metrics: dict[str, Any] | None = None

    # ═══════════════════════════════════════════════════════════
    # Main Entry Point
    # ═══════════════════════════════════════════════════════════

    def run_cycle(self, dry_run: bool = False) -> dict[str, Any]:
        """Execute one complete SEAL cycle.

        Args:
            dry_run: If True, only generate the curriculum without training.

        Returns:
            Dict with cycle results.
        """
        self.current_cycle += 1
        cycle = self.current_cycle
        self.curriculum.state.cycle_number = cycle

        logger.info(f"\n{'='*60}")
        logger.info(f"  SEAL CYCLE {cycle} START")
        logger.info(f"{'='*60}")

        cycle_start = time.time()
        result: dict[str, Any] = {
            "cycle": cycle,
            "status": "running",
            "timestamp": cycle_start,
        }

        # Phase 1: Generate curriculum action
        logger.info("[SEAL] Phase 1/4: Generating curriculum...")
        action = self.curriculum.generate_action()
        self.last_action = action
        result["action"] = json.loads(action.to_json())

        if dry_run:
            # Record the action in curriculum state and persist so the
            # dashboard widget shows real data even on dry-runs
            self.curriculum.state.record_action(action, reward_delta=0.0)
            self._save_state()
            result["status"] = "dry_run"
            result["elapsed_seconds"] = time.time() - cycle_start
            logger.info(f"[SEAL] Dry-run complete. Action would be: {action.action_type.value}")
            return result

        # Phase 2: Inner loop (synthetic data + training)
        logger.info("[SEAL] Phase 2/4: Executing inner loop...")
        inner_metrics, synthetic_data = self.inner_loop.execute(action, cycle)
        self.last_inner_metrics = inner_metrics
        result["inner_metrics"] = inner_metrics

        if inner_metrics.get("status") == "skipped":
            result["status"] = "skipped"
            result["elapsed_seconds"] = time.time() - cycle_start
            logger.warning(f"[SEAL] Inner loop skipped: {inner_metrics.get('reason')}")
            return result

        if inner_metrics.get("status") == "failed":
            result["status"] = "failed"
            result["error"] = inner_metrics.get("error")
            result["elapsed_seconds"] = time.time() - cycle_start
            logger.error(f"[SEAL] Inner loop failed: {inner_metrics.get('error')}")
            return result

        result["synthetic_count"] = len(synthetic_data)
        result["examples_trained"] = inner_metrics.get("examples_trained", 0)

        # Phase 3: Compute outer loop reward
        logger.info("[SEAL] Phase 3/4: Computing outer loop reward...")
        reward = self._compute_reward(action, inner_metrics)
        if reward is not None:
            result["reward"] = reward.to_dict()
            self.meta_learner.add_reward(reward)
            self.curriculum.update_state(reward)
        else:
            # Use a simulated reward based on training loss improvement
            simulated = self._simulate_reward(action, inner_metrics)
            result["reward"] = simulated.to_dict()
            self.meta_learner.add_reward(simulated)
            self.curriculum.update_state(simulated)

        # Phase 4: Meta-learning (if enough data)
        logger.info("[SEAL] Phase 4/4: Meta-learning...")
        meta_metrics = self.meta_learner.train()
        result["meta_metrics"] = meta_metrics

        # Save state
        self._save_state()

        result["status"] = "completed"
        result["elapsed_seconds"] = round(time.time() - cycle_start, 2)

        logger.info(f"{'='*60}")
        logger.info(f"  SEAL CYCLE {cycle} COMPLETE")
        logger.info(f"  Action: {action.action_type.value} ({action.domain})")
        logger.info(f"  Examples: {result.get('examples_trained', 0)}")
        logger.info(f"  Reward Δ: {result.get('reward', {}).get('reward_delta', 'N/A')}")
        logger.info(f"  Elapsed: {result['elapsed_seconds']}s")
        logger.info(f"{'='*60}\n")

        return result

    def run_cycles(
        self,
        num_cycles: int = 3,
        dry_run: bool = False,
        cycle_delay: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Run multiple SEAL cycles sequentially.

        Args:
            num_cycles: Number of cycles to run.
            dry_run: If True, only generate curriculum without training.
            cycle_delay: Seconds to wait between cycles.

        Returns:
            List of cycle result dicts.
        """
        results = []
        for i in range(num_cycles):
            result = self.run_cycle(dry_run=dry_run)
            results.append(result)

            if i < num_cycles - 1 and cycle_delay > 0:
                logger.info(f"[SEAL] Waiting {cycle_delay}s before next cycle...")
                time.sleep(cycle_delay)

        # Summary
        completed = [r for r in results if r.get("status") == "completed"]
        if completed:
            avg_reward = sum(
                r.get("reward", {}).get("reward_delta", 0)
                for r in completed
            ) / len(completed)
            logger.info(f"\n{'='*60}")
            logger.info(f"  SEAL SUMMARY: {len(completed)}/{num_cycles} cycles completed")
            logger.info(f"  Avg reward Δ: {avg_reward:+.4f}")
            logger.info(f"  Curriculum state: cycle={self.curriculum.state.cycle_number}, "
                        f"actions={self.curriculum.state.total_actions_taken}")
            logger.info(f"{'='*60}\n")

        return results

    # ═══════════════════════════════════════════════════════════
    # Reward Computation
    # ═══════════════════════════════════════════════════════════

    def _compute_reward(
        self,
        action: SelfEditAction,
        inner_metrics: dict[str, Any],
    ) -> RewardRecord | None:
        """Compute reward from capture engine data."""
        reward = self.reward_calc.compute_from_capture_engine(
            self.capture_engine,
            self.current_cycle,
            action,
            inner_metrics,
        )
        return reward

    def _simulate_reward(
        self,
        action: SelfEditAction,
        inner_metrics: dict[str, Any],
    ) -> RewardRecord:
        """Simulate reward when capture engine data is unavailable.

        Uses training loss improvement as a proxy for acceptance rate
        improvement. This allows the SEAL loop to function during
        development/dogfooding without real user feedback.
        """
        # Simulate acceptance rate from training loss
        train_loss = inner_metrics.get("train_loss")
        eval_loss = inner_metrics.get("eval_loss")

        # Use loss improvement as proxy for quality
        if train_loss is not None:
            # Lower loss = better = higher simulated rate
            simulated_rate = max(0.3, min(0.9, 0.7 - (train_loss - 0.5) * 0.5))
        else:
            simulated_rate = 0.5

        # Previous simulated rate
        if self.curriculum.state.acceptance_rate_history:
            prev = self.curriculum.state.acceptance_rate_history[-1]
            prev_rate = prev.get("rate", 0.5)
        else:
            prev_rate = 0.3  # Starting baseline

        record = RewardRecord(
            cycle=self.current_cycle,
            action=action,
            acceptance_rate_before=prev_rate,
            acceptance_rate_after=simulated_rate,
            examples_generated=inner_metrics.get("examples_trained", 0),
            inner_train_loss=train_loss,
            inner_eval_loss=eval_loss,
        )

        logger.info(f"[SEAL] Simulated reward: Δ={record.reward_delta:+.4f} "
                    f"({prev_rate*100:.1f}% → {simulated_rate*100:.1f}%)")
        return record

    # ═══════════════════════════════════════════════════════════
    # State Persistence
    # ═══════════════════════════════════════════════════════════

    def _save_state(self) -> None:
        """Save all SEAL state to disk."""
        state_dir = Path(self.config.state_dir)
        state_dir.mkdir(parents=True, exist_ok=True)

        # Curriculum state
        self.curriculum.save_state(str(state_dir))

        # Reward history
        reward_file = state_dir / "reward_history.jsonl"
        with open(reward_file, "a", encoding="utf-8") as f:
            for record in self.meta_learner.reward_history[-1:]:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

        # Cycle summary
        summary_file = state_dir / "seal_summary.json"
        summary = {
            "current_cycle": self.current_cycle,
            "state": self.curriculum.state.to_dict(),
            "meta_trained": self.meta_learner.should_train(),
            "reward_count": len(self.meta_learner.reward_history),
        }
        summary_file.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def load_state(self) -> bool:
        """Load SEAL state from disk. Returns True on success."""
        state_dir = Path(self.config.state_dir)

        # Load curriculum state
        curriculum_loaded = self.curriculum.load_state(str(state_dir))
        if curriculum_loaded:
            self.current_cycle = self.curriculum.state.cycle_number

        # Load reward history
        reward_file = state_dir / "reward_history.jsonl"
        if reward_file.exists():
            try:
                with open(reward_file, encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)
                            # Convert back to RewardRecord (partial, for history)
                            action = SelfEditAction.from_json(
                                json.dumps(data.get("action", {}))
                            ) or SelfEditAction(action_type=SealActionType.GENERATE_EXAMPLES)
                            record = RewardRecord(
                                cycle=data.get("cycle", 0),
                                action=action,
                                acceptance_rate_before=data.get("acceptance_rate_before", 0),
                                acceptance_rate_after=data.get("acceptance_rate_after", 0),
                                examples_generated=data.get("examples_generated", 0),
                                inner_train_loss=data.get("inner_train_loss"),
                                inner_eval_loss=data.get("inner_eval_loss"),
                            )
                            self.meta_learner.add_reward(record)
            except Exception as e:
                logger.warning(f"[SEAL] Error loading reward history: {e}")

        logger.info(f"[SEAL] State loaded: cycle={self.current_cycle}, "
                    f"rewards={len(self.meta_learner.reward_history)}")
        return curriculum_loaded

    def status(self) -> dict[str, Any]:
        """Return a detailed status report of the SEAL system."""
        state = self.curriculum.state
        return {
            "system": "SEAL Phase 3",
            "cycle": self.current_cycle,
            "status": "active" if self.current_cycle > 0 else "idle",
            "curriculum_state": {
                "total_actions_taken": state.total_actions_taken,
                "domains_explored": len(state.domains_explored),
                "difficulties_tried": dict(state.difficulties_tried),
            },
            "meta_learning": {
                "ready_to_train": self.meta_learner.should_train(),
                "reward_count": len(self.meta_learner.reward_history),
                "total_rewards": len(self.meta_learner.reward_history),
            },
            "best_action": state.best_action,
            "config": self.config.to_dict(),
        }


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SEAL Phase 3 — Autonomous Self-Improving Training Loop",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  # Run 3 cycles with default config
  python -m src.training.phase3_seal --cycles 3

  # Dry run (curriculum generation only, no training)
  python -m src.training.phase3_seal --dry-run

  # Full system with capture engine
  python -m src.training.phase3_seal --cycles 5 --capture --meta

  # Show status
  python -m src.training.phase3_seal --status

  # Reset state
  python -m src.training.phase3_seal --reset
""",
    )

    # Main options
    parser.add_argument("--cycles", type=int, default=1,
                        help="Number of SEAL cycles to run (default: 1)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate curriculum only, skip training")
    parser.add_argument("--cycle-delay", type=float, default=0.0,
                        help="Seconds to wait between cycles")

    # Model configuration
    parser.add_argument("--model", default="",
                        help="Base model for inner loop training (default: from config)")
    parser.add_argument("--curriculum-model", default="",
                        help="Model for curriculum generation (default: from config)")
    parser.add_argument("--synthetic-model", default="",
                        help="Model for synthetic data generation (default: from config)")

    # Inner loop
    parser.add_argument("--lora-rank", type=int, default=0,
                        help="LoRA rank for inner loop training")
    parser.add_argument("--inner-steps", type=int, default=0,
                        help="Max training steps per inner loop cycle")
    parser.add_argument("--examples-per-action", type=int, default=0,
                        help="Number of synthetic examples per action")

    # Meta-learning
    parser.add_argument("--meta", action="store_true", default=None,
                        help="Enable meta-learning for curriculum generator")
    parser.add_argument("--no-meta", action="store_true", default=None,
                        help="Disable meta-learning")
    parser.add_argument("--meta-lora-rank", type=int, default=0,
                        help="LoRA rank for meta-learning")

    # Integration
    parser.add_argument("--capture", action="store_true",
                        help="Integrate with capture engine for real signals")
    parser.add_argument("--server", action="store_true",
                        help="Start SEAL server that responds to API calls")

    # State management
    parser.add_argument("--status", action="store_true",
                        help="Show current SEAL status and exit")
    parser.add_argument("--reset", action="store_true",
                        help="Reset all SEAL state and start fresh")
    parser.add_argument("--state-dir", default="",
                        help="Directory for SEAL state files")

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Build config with CLI overrides
    config_dict = {}
    if args.model:
        config_dict["inner_model"] = args.model
    if args.curriculum_model:
        config_dict["curriculum_model"] = args.curriculum_model
    if args.synthetic_model:
        config_dict["inner_synthetic_model"] = args.synthetic_model
    if args.lora_rank > 0:
        config_dict["inner_lora_rank"] = args.lora_rank
    if args.inner_steps > 0:
        config_dict["inner_max_steps"] = args.inner_steps
    if args.examples_per_action > 0:
        config_dict["synthetic_examples_per_action"] = args.examples_per_action
    if args.meta is True:
        config_dict["meta_enabled"] = True
    if args.no_meta is True:
        config_dict["meta_enabled"] = False
    if args.meta_lora_rank > 0:
        config_dict["meta_lora_rank"] = args.meta_lora_rank
    if args.state_dir:
        config_dict["state_dir"] = args.state_dir

    config = SealConfig.from_dict(config_dict)

    # Initialize capture engine if requested
    capture_engine = None
    if args.capture:
        try:
            from src.learning.capture_engine import CaptureEngine
            capture_engine = CaptureEngine()
            stats = capture_engine.get_statistics()
            total_signals = sum(stats.get("signals_by_type", {}).values())
            logger.info(f"[SEAL] Capture engine connected: {total_signals} total signals")
        except Exception as e:
            logger.warning(f"[SEAL] Could not initialize capture engine: {e}")

    # Create orchestrator
    orchestrator = SealOrchestrator(config=config, capture_engine=capture_engine)

    # Load previous state
    if args.reset:
        logger.info("[SEAL] Resetting all state...")
        state_dir = Path(config.state_dir)
        if state_dir.exists():
            import shutil
            shutil.rmtree(state_dir)
        orchestrator.current_cycle = 0
        logger.info("[SEAL] State reset complete")
    else:
        orchestrator.load_state()

    # Show status and exit
    if args.status:
        status = orchestrator.status()
        print(json.dumps(status, indent=2, ensure_ascii=False))
        return

    # Run SEAL cycles
    results = orchestrator.run_cycles(
        num_cycles=args.cycles,
        dry_run=args.dry_run,
        cycle_delay=args.cycle_delay,
    )

    # Print summary
    print(f"\n{'='*60}")
    print("  SEAL PHASE 3 — COMPLETE")
    print(f"  Cycles requested: {args.cycles}")
    print(f"  Cycles completed: {sum(1 for r in results if r.get('status') == 'completed')}")
    print(f"  Curriculum actions: {[r.get('action', {}).get('action', '?') for r in results]}")
    print(f"{'='*60}\n")

    # Print cycle results as JSON
    if not args.dry_run:
        print(json.dumps(results, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
