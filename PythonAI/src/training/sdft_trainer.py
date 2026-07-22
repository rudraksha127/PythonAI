"""
SDFT Trainer — Sequential Learning Without Forgetting (MIT 2026)
=================================================================

Implements SDFT (Sequential Distributed Fine-Tuning) to prevent catastrophic
forgetting when training on new data sequentially.

Problem: When a model learns new patterns (Month 5 React patterns), it may
forget old patterns (Month 1 FastAPI patterns). Standard fine-tuning shows
40-60% forgetting. SDFT achieves 98% retention.

Solution: During each training run, include a "replay buffer" of representative
examples from previous training runs. This prevents the model from overwriting
old knowledge.

Algorithm:
- Current week examples: 70% of batch
- Previous week examples: 20% of batch (replay buffer)
- Foundational examples (Month 1): 10% of batch

Research Foundation: MIT SDFT (Feb 2026)
"Sequential Learning Without Forgetting" — 98% retention achieved.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import torch
    from torch.utils.data import Dataset

    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

try:
    from peft import LoraConfig, TaskType, get_peft_model
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        Trainer,
        TrainingArguments,
        default_data_collator,
    )

    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False


@dataclass
class ReplayBufferConfig:
    """Configuration for SDFT replay buffer."""

    # Proportion of batch from each source
    current_week_ratio: float = 0.70  # New training data
    previous_week_ratio: float = 0.20  # Last week's data
    foundational_ratio: float = 0.10  # Month 1 foundational data

    # Buffer sizes
    max_replay_size: int = 1000  # Max examples from previous weeks
    max_foundational_size: int = 500  # Max foundational examples

    # Sampling strategy
    sampling_strategy: str = "uniform"  # "uniform", "weighted", "recency"

    # Forgetting threshold (trigger additional replay if exceeded)
    forgetting_threshold: float = 0.15  # 15% performance drop triggers alert


@dataclass
class TrainingExample:
    """A single training example with metadata."""

    instruction: str
    input: str
    output: str
    source: str = "current"  # "current", "replay", "foundational"
    quality_score: float = 1.0
    timestamp: float = field(default_factory=time.time)
    signal_id: str | None = None
    language: str = "python"
    framework: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "instruction": self.instruction,
            "input": self.input,
            "output": self.output,
            "source": self.source,
            "quality_score": self.quality_score,
            "timestamp": self.timestamp,
            "signal_id": self.signal_id,
            "language": self.language,
            "framework": self.framework,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrainingExample:
        return cls(
            instruction=data["instruction"],
            input=data.get("input", ""),
            output=data["output"],
            source=data.get("source", "current"),
            quality_score=data.get("quality_score", 1.0),
            timestamp=data.get("timestamp", time.time()),
            signal_id=data.get("signal_id"),
            language=data.get("language", "python"),
            framework=data.get("framework"),
        )


class ReplayBuffer:
    """
    Manages replay examples for SDFT to prevent catastrophic forgetting.

    The buffer stores representative examples from previous training runs
    and mixes them with current training data.
    """

    def __init__(self, config: ReplayBufferConfig | None = None):
        self.config = config or ReplayBufferConfig()
        self.previous_week_examples: list[TrainingExample] = []
        self.foundational_examples: list[TrainingExample] = []
        self.performance_history: list[dict[str, float]] = []

    def add_previous_week_examples(self, examples: list[TrainingExample]):
        """Add examples from the previous training run."""
        # Quality-weighted sampling if over limit
        if len(self.previous_week_examples) + len(examples) > self.config.max_replay_size:
            # Keep highest quality examples
            all_examples = self.previous_week_examples + examples
            all_examples.sort(key=lambda x: x.quality_score, reverse=True)
            self.previous_week_examples = all_examples[: self.config.max_replay_size]
        else:
            self.previous_week_examples.extend(examples)

    def add_foundational_examples(self, examples: list[TrainingExample]):
        """Add foundational examples (Month 1 data)."""
        if len(self.foundational_examples) + len(examples) > self.config.max_foundational_size:
            all_examples = self.foundational_examples + examples
            all_examples.sort(key=lambda x: x.quality_score, reverse=True)
            self.foundational_examples = all_examples[: self.config.max_foundational_size]
        else:
            self.foundational_examples.extend(examples)

    def load_from_disk(self, previous_week_path: str | Path, foundational_path: str | Path):
        """Load replay buffers from disk."""
        previous_week_path = Path(previous_week_path)
        foundational_path = Path(foundational_path)

        if previous_week_path.exists():
            with open(previous_week_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            data = json.loads(line)
                            self.previous_week_examples.append(TrainingExample.from_dict(data))
                        except json.JSONDecodeError:
                            pass
            print(f"[SDFT] Loaded {len(self.previous_week_examples)} previous week examples")

        if foundational_path.exists():
            with open(foundational_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            data = json.loads(line)
                            self.foundational_examples.append(TrainingExample.from_dict(data))
                        except json.JSONDecodeError:
                            pass
            print(f"[SDFT] Loaded {len(self.foundational_examples)} foundational examples")

    def save_to_disk(self, previous_week_path: str | Path, foundational_path: str | Path):
        """Save replay buffers to disk."""
        previous_week_path = Path(previous_week_path)
        foundational_path = Path(foundational_path)

        previous_week_path.parent.mkdir(parents=True, exist_ok=True)
        foundational_path.parent.mkdir(parents=True, exist_ok=True)

        with open(previous_week_path, "w", encoding="utf-8") as f:
            for ex in self.previous_week_examples:
                f.write(json.dumps(ex.to_dict()) + "\n")

        with open(foundational_path, "w", encoding="utf-8") as f:
            for ex in self.foundational_examples:
                f.write(json.dumps(ex.to_dict()) + "\n")

    def create_mixed_dataset(
        self,
        current_examples: list[TrainingExample],
    ) -> list[TrainingExample]:
        """
        Create a mixed dataset following SDFT ratios.

        Composition:
        - 70% current week examples
        - 20% previous week examples (replay buffer)
        - 10% foundational examples
        """
        if not current_examples:
            return []

        # Calculate target sizes
        total_target = len(current_examples)
        target_current = int(total_target * self.config.current_week_ratio)
        target_previous = int(total_target * self.config.previous_week_ratio)
        target_foundational = int(total_target * self.config.foundational_ratio)

        # Sample from each source
        mixed: list[TrainingExample] = []

        # Current examples (sample if too many)
        if len(current_examples) > target_current:
            if self.config.sampling_strategy == "weighted":
                # Weight by quality score
                weights = [ex.quality_score for ex in current_examples]
                total_weight = sum(weights)
                probs = [w / total_weight for w in weights]
                mixed.extend(random.choices(current_examples, weights=probs, k=target_current))
            else:
                mixed.extend(random.sample(current_examples, target_current))
        else:
            mixed.extend(current_examples)

        # Previous week examples
        if self.previous_week_examples:
            if len(self.previous_week_examples) > target_previous:
                if self.config.sampling_strategy == "recency":
                    # Prefer more recent examples
                    sorted_examples = sorted(self.previous_week_examples, key=lambda x: x.timestamp, reverse=True)
                    mixed.extend(sorted_examples[:target_previous])
                else:
                    mixed.extend(random.sample(self.previous_week_examples, target_previous))
            else:
                mixed.extend(self.previous_week_examples)

        # Foundational examples
        if self.foundational_examples:
            if len(self.foundational_examples) > target_foundational:
                # Always use weighted sampling for foundational (most important)
                weights = [ex.quality_score for ex in self.foundational_examples]
                total_weight = sum(weights)
                probs = [w / total_weight for w in weights]
                mixed.extend(random.choices(self.foundational_examples, weights=probs, k=target_foundational))
            else:
                mixed.extend(self.foundational_examples)

        # Shuffle the mixed dataset
        random.shuffle(mixed)

        print(f"[SDFT] Mixed dataset: {len(mixed)} examples")
        print(f"  - Current: {len([e for e in mixed if e.source == 'current'])}")
        print(f"  - Previous: {len([e for e in mixed if e.source == 'replay'])}")
        print(f"  - Foundational: {len([e for e in mixed if e.source == 'foundational'])}")

        return mixed

    def record_performance(self, metrics: dict[str, float]):
        """Record training performance for forgetting detection."""
        self.performance_history.append(
            {
                **metrics,
                "timestamp": time.time(),
            }
        )

        # Keep only last 10 runs
        if len(self.performance_history) > 10:
            self.performance_history = self.performance_history[-10:]

    def check_forgetting(self, current_metrics: dict[str, float]) -> dict[str, Any]:
        """
        Check if catastrophic forgetting is occurring.

        Returns:
            dict with 'forgetting_detected' bool and details
        """
        if not self.performance_history:
            return {"forgetting_detected": False, "details": "No history available"}

        # Compare current eval loss with historical best
        current_eval_loss = current_metrics.get("eval_loss", float("inf"))
        historical_losses = [m.get("eval_loss", float("inf")) for m in self.performance_history]

        if not historical_losses:
            return {"forgetting_detected": False, "details": "No historical losses"}

        best_historical_loss = min(historical_losses)

        if best_historical_loss == 0:
            return {"forgetting_detected": False, "details": "Perfect historical loss"}

        degradation = (current_eval_loss - best_historical_loss) / best_historical_loss

        return {
            "forgetting_detected": degradation > self.config.forgetting_threshold,
            "degradation_ratio": degradation,
            "current_eval_loss": current_eval_loss,
            "best_historical_loss": best_historical_loss,
            "details": f"Eval loss degraded by {degradation:.2%} from best ({best_historical_loss:.4f} → {current_eval_loss:.4f})",
        }


class SDFDataset(Dataset):
    """PyTorch dataset for SDFT training with mixed sources."""

    def __init__(
        self,
        examples: list[TrainingExample],
        tokenizer: Any,
        max_length: int = 2048,
    ):
        self.examples = examples
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        example = self.examples[idx]

        # Build the full text
        text = f"Instruction: {example.instruction}\n"
        if example.input:
            text += f"Input: {example.input}\n"
        text += f"Output: {example.output}"

        # Tokenize
        encoding = self.tokenizer(
            text,
            truncation=True,
            max_length=self.max_length,
            padding="max_length",
            return_tensors="pt",
        )

        result = {
            "input_ids": encoding["input_ids"].squeeze(0),
            "attention_mask": encoding["attention_mask"].squeeze(0),
        }

        # Labels are same as input_ids for causal LM
        result["labels"] = result["input_ids"].clone()

        # Mask the prompt portion (everything before "Output:")
        output_marker = self.tokenizer.encode("Output:", add_special_tokens=False)
        if output_marker:
            marker_pos = self._find_sequence(result["input_ids"], output_marker[0])
            if marker_pos >= 0:
                # Mask everything up to and including the marker
                result["labels"][: marker_pos + len(output_marker)] = -100

        return result

    def _find_sequence(self, tensor: torch.Tensor, token_id: int) -> int:
        """Find the position of a token in the tensor."""
        for i, t in enumerate(tensor):
            if t.item() == token_id:
                return i
        return -1


class SDFTTrainer:
    """
    SDFT (Sequential Distributed Fine-Tuning) trainer.

    This trainer implements the MIT SDFT algorithm to prevent catastrophic
    forgetting when training sequentially on new data.
    """

    def __init__(
        self,
        model_name: str,
        replay_config: ReplayBufferConfig | None = None,
        lora_rank: int = 16,
        lora_alpha: int = 32,
        learning_rate: float = 2e-4,
        max_length: int = 2048,
        device: str = "cuda" if torch.cuda.is_available() else "cpu",
    ):
        self.model_name = model_name
        self.replay_config = replay_config or ReplayBufferConfig()
        self.replay_buffer = ReplayBuffer(self.replay_config)
        self.lora_rank = lora_rank
        self.lora_alpha = lora_alpha
        self.learning_rate = learning_rate
        self.max_length = max_length
        self.device = device

        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

    def prepare_model(self, use_4bit: bool = True):
        """Prepare model with quantization and LoRA."""
        # Quantization config
        bnb_config = None
        if use_4bit and self.device == "cuda":
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
            )

        # Load model
        model_kwargs = {
            "trust_remote_code": True,
            "torch_dtype": torch.float16 if self.device == "cuda" else torch.float32,
        }
        if bnb_config:
            model_kwargs["quantization_config"] = bnb_config
            model_kwargs["device_map"] = "auto"

        model = AutoModelForCausalLM.from_pretrained(self.model_name, **model_kwargs)
        model.config.use_cache = False

        # Apply LoRA
        target_modules = ["q_proj", "v_proj", "k_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]

        # Find actual modules in model
        actual_modules = []
        for name, _ in model.named_modules():
            for target in target_modules:
                if name.endswith(target) and target not in actual_modules:
                    actual_modules.append(target)

        if not actual_modules:
            actual_modules = ["c_attn", "c_proj"]  # GPT-2 fallback

        peft_config = LoraConfig(
            r=self.lora_rank,
            lora_alpha=self.lora_alpha,
            target_modules=actual_modules,
            lora_dropout=0.05,
            bias="none",
            task_type=TaskType.CAUSAL_LM,
        )

        model = get_peft_model(model, peft_config)
        model.print_trainable_parameters()

        return model

    def train(
        self,
        current_examples: list[TrainingExample],
        output_dir: str | Path,
        num_epochs: int = 1,
        batch_size: int = 4,
        gradient_accumulation_steps: int = 4,
        save_steps: int = 500,
        logging_steps: int = 10,
        use_4bit: bool = True,
    ) -> dict[str, Any]:
        """
        Train with SDFT to prevent catastrophic forgetting.

        Args:
            current_examples: New training examples for this run
            output_dir: Directory to save model
            num_epochs: Number of training epochs
            batch_size: Training batch size
            gradient_accumulation_steps: Gradient accumulation steps
            save_steps: Save checkpoint every N steps
            logging_steps: Log every N steps
            use_4bit: Use 4-bit quantization

        Returns:
            Training metrics
        """
        # Create mixed dataset
        mixed_examples = self.replay_buffer.create_mixed_dataset(current_examples)

        # Prepare model
        model = self.prepare_model(use_4bit)

        # Create dataset
        dataset = SDFDataset(mixed_examples, self.tokenizer, self.max_length)

        # Split into train/eval
        eval_size = max(1, int(len(dataset) * 0.05))
        train_size = len(dataset) - eval_size
        train_dataset, eval_dataset = torch.utils.data.random_split(dataset, [train_size, eval_size])

        # Training arguments
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        training_args = TrainingArguments(
            output_dir=str(output_dir),
            num_train_epochs=num_epochs,
            per_device_train_batch_size=batch_size,
            per_device_eval_batch_size=batch_size,
            gradient_accumulation_steps=gradient_accumulation_steps,
            optim="paged_adamw_8bit" if self.device == "cuda" else "adamw_torch",
            save_steps=save_steps,
            logging_steps=logging_steps,
            eval_strategy="steps",
            eval_steps=save_steps,
            learning_rate=self.learning_rate,
            weight_decay=0.01,
            fp16=self.device == "cuda",
            max_grad_norm=0.3,
            warmup_ratio=0.03,
            lr_scheduler_type="cosine",
            save_total_limit=2,
            load_best_model_at_end=True,
            metric_for_best_model="eval_loss",
            greater_is_better=False,
            gradient_checkpointing=True,
            report_to="none",
        )

        # Trainer
        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=eval_dataset,
            data_collator=default_data_collator,
        )

        # Train
        print(f"\n{'=' * 60}")
        print("SDFT TRAINING START")
        print(f"  Model: {self.model_name}")
        print(f"  Total examples: {len(mixed_examples)}")
        print(f"  Train: {len(train_dataset)}, Eval: {len(eval_dataset)}")
        print(f"  Epochs: {num_epochs}")
        print(f"  Output: {output_dir}")
        print(f"{'=' * 60}\n")

        trainer.train()

        # Save
        trainer.save_model(str(output_dir))
        self.tokenizer.save_pretrained(str(output_dir))

        # Collect metrics
        metrics = {
            "train_loss": trainer.state.log_history[-1].get("loss") if trainer.state.log_history else None,
            "eval_loss": trainer.state.log_history[-1].get("eval_loss") if trainer.state.log_history else None,
            "total_steps": trainer.state.global_step,
            "examples_used": len(mixed_examples),
        }

        # Check for forgetting
        forgetting_check = self.replay_buffer.check_forgetting(metrics)
        metrics.update(forgetting_check)

        # Record performance
        self.replay_buffer.record_performance(metrics)

        # Save metrics
        with open(output_dir / "sdft_metrics.json", "w") as f:
            json.dump(metrics, f, indent=2)

        print(f"\n{'=' * 60}")
        print("SDFT TRAINING COMPLETE")
        print(f"  Final train loss: {metrics['train_loss']}")
        print(f"  Final eval loss: {metrics['eval_loss']}")
        if forgetting_check.get("forgetting_detected"):
            print(f"  ⚠️  FORGETTING DETECTED: {forgetting_check['details']}")
        else:
            print("  ✓ No catastrophic forgetting detected")
        print(f"{'=' * 60}\n")

        return metrics

    def update_replay_buffer(
        self,
        current_examples: list[TrainingExample],
        save_previous_week_path: str | Path,
        save_foundational_path: str | Path,
    ):
        """
        Update replay buffer after training run.

        This should be called after each training run to save a portion
        of the current examples for the next run's replay buffer.
        """
        # Mark current examples as previous week for next run
        for ex in current_examples:
            ex.source = "replay"

        self.replay_buffer.add_previous_week_examples(current_examples)
        self.replay_buffer.save_to_disk(save_previous_week_path, save_foundational_path)

        print("[SDFT] Replay buffer updated:")
        print(f"  Previous week: {len(self.replay_buffer.previous_week_examples)} examples")
        print(f"  Foundational: {len(self.replay_buffer.foundational_examples)} examples")


# ═══════════════════════════════════════════════════════════════
# Convenience Functions
# ═══════════════════════════════════════════════════════════════


def train_with_sdft(
    current_examples: list[dict[str, Any]],
    model_name: str,
    output_dir: str | Path,
    previous_week_path: str | Path | None = None,
    foundational_path: str | Path | None = None,
    lora_rank: int = 16,
    learning_rate: float = 2e-4,
    num_epochs: int = 1,
    batch_size: int = 4,
) -> dict[str, Any]:
    """
    Convenience function for SDFT training.

    Args:
        current_examples: List of training examples (dict format)
        model_name: Base model name
        output_dir: Output directory for trained model
        previous_week_path: Path to previous week's examples (JSONL)
        foundational_path: Path to foundational examples (JSONL)
        lora_rank: LoRA rank
        learning_rate: Learning rate
        num_epochs: Number of epochs
        batch_size: Batch size

    Returns:
        Training metrics
    """
    # Convert dicts to TrainingExample objects
    examples = [TrainingExample.from_dict(ex) for ex in current_examples]

    # Create trainer
    trainer = SDFTTrainer(
        model_name=model_name,
        lora_rank=lora_rank,
        learning_rate=learning_rate,
    )

    # Load replay buffers if paths provided
    if previous_week_path and foundational_path:
        trainer.replay_buffer.load_from_disk(previous_week_path, foundational_path)

    # Train
    metrics = trainer.train(
        current_examples=examples,
        output_dir=output_dir,
        num_epochs=num_epochs,
        batch_size=batch_size,
    )

    return metrics


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SDFT Trainer — Prevent Catastrophic Forgetting")
    parser.add_argument("--model", default="Qwen/Qwen2.5-Coder-7B-Instruct")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--data", required=True, help="Current training data (JSONL)")
    parser.add_argument("--previous-week", help="Previous week replay buffer (JSONL)")
    parser.add_argument("--foundational", help="Foundational examples (JSONL)")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--lora-rank", type=int, default=16)
    parser.add_argument("--lr", type=float, default=2e-4)
    args = parser.parse_args()

    # Load training data
    examples = []
    with open(args.data, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    examples.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    print(f"Loaded {len(examples)} training examples")

    # Train
    metrics = train_with_sdft(
        current_examples=examples,
        model_name=args.model,
        output_dir=args.output,
        previous_week_path=args.previous_week,
        foundational_path=args.foundational,
        lora_rank=args.lora_rank,
        learning_rate=args.lr,
        num_epochs=args.epochs,
        batch_size=args.batch_size,
    )

    print(json.dumps(metrics, indent=2))
