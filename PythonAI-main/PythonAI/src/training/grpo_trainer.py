"""
GRPO Trainer — Group Relative Policy Optimization (DeepSeek 2025)
==================================================================

Implements GRPO (Group Relative Policy Optimization) for RL-based training
using accept/reject pairs. No separate reward model needed.

Key insight from DeepSeek-R1: GRPO can achieve o1-level performance without
any supervised fine-tuning, using only RL with verifiable rewards.

For code: Accept = positive reward, Reject = negative reward.
Code execution = verifiable reward (test pass/fail, compile success).

Research Foundation:
- DeepSeek-R1 (2025): GRPO for reasoning
- 2-GRPO (2025): Minimum 2 responses needed (accept + reject pair)
- RLVR: RL with Verifiable Rewards (code execution as reward)

Algorithm:
1. Generate K responses for same prompt (K=2 minimum)
2. Compute rewards: accept=+1, reject=-1, test_pass=+2
3. Compute group-relative advantages
4. Update policy with GRPO loss
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import torch
    from torch.utils.data import DataLoader, Dataset

    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    Dataset = object

try:
    from peft import LoraConfig, TaskType, get_peft_model
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
    )

    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False


@dataclass
class GRPOPair:
    """A pair of accepted and rejected responses for the same prompt."""

    prompt: str  # The code context/instruction
    accepted_response: str  # Developer accepted this
    rejected_response: str  # Developer rejected this (or AI alternative)

    # Optional verifiable rewards
    accepted_test_passed: bool = False
    rejected_test_passed: bool = False
    accepted_lint_passed: bool = False
    rejected_lint_passed: bool = False

    # Metadata
    signal_id: str | None = None
    language: str = "python"
    framework: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "accepted_response": self.accepted_response,
            "rejected_response": self.rejected_response,
            "accepted_test_passed": self.accepted_test_passed,
            "rejected_test_passed": self.rejected_test_passed,
            "accepted_lint_passed": self.accepted_lint_passed,
            "rejected_lint_passed": self.rejected_lint_passed,
            "signal_id": self.signal_id,
            "language": self.language,
            "framework": self.framework,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GRPOPair:
        return cls(
            prompt=data["prompt"],
            accepted_response=data["accepted_response"],
            rejected_response=data["rejected_response"],
            accepted_test_passed=data.get("accepted_test_passed", False),
            rejected_test_passed=data.get("rejected_test_passed", False),
            accepted_lint_passed=data.get("accepted_lint_passed", False),
            rejected_lint_passed=data.get("rejected_lint_passed", False),
            signal_id=data.get("signal_id"),
            language=data.get("language", "python"),
            framework=data.get("framework"),
        )


def compute_reward(
    response: str,
    test_passed: bool = False,
    lint_passed: bool = False,
    is_accepted: bool = True,
) -> float:
    """
    Compute verifiable reward for a response.

    Reward structure (RLVR):
    - Base acceptance: +1.0 (accepted) or -1.0 (rejected)
    - Test passed: +2.0 (verifiable correctness)
    - Lint passed: +0.5 (code quality)
    - Format penalty: -0.1 per 100 chars over 500 (encourage conciseness)
    """
    base = 1.0 if is_accepted else -1.0
    test_bonus = 2.0 if test_passed else 0.0
    lint_bonus = 0.5 if lint_passed else 0.0

    # Format penalty for overly long responses
    length = len(response)
    format_penalty = -0.1 * max(0, (length - 500) // 100)

    return base + test_bonus + lint_bonus + format_penalty


class GRPODataset(Dataset):
    """Dataset of accept/reject pairs for GRPO training."""

    def __init__(
        self,
        pairs: list[GRPOPair],
        tokenizer: Any,
        max_length: int = 2048,
    ):
        self.pairs = pairs
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.pairs)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        pair = self.pairs[idx]

        # Tokenize prompt
        prompt_encoded = self.tokenizer(
            pair.prompt,
            truncation=True,
            max_length=self.max_length // 2,
            padding=False,
            return_tensors=None,
        )

        # Tokenize accepted response
        accepted_encoded = self.tokenizer(
            pair.accepted_response,
            truncation=True,
            max_length=self.max_length // 2,
            padding=False,
            return_tensors=None,
        )

        # Tokenize rejected response
        rejected_encoded = self.tokenizer(
            pair.rejected_response,
            truncation=True,
            max_length=self.max_length // 2,
            padding=False,
            return_tensors=None,
        )

        return {
            "prompt_input_ids": prompt_encoded["input_ids"],
            "prompt_attention_mask": prompt_encoded["attention_mask"],
            "accepted_input_ids": accepted_encoded["input_ids"],
            "accepted_attention_mask": accepted_encoded["attention_mask"],
            "rejected_input_ids": rejected_encoded["input_ids"],
            "rejected_attention_mask": rejected_encoded["attention_mask"],
            "accepted_reward": compute_reward(
                pair.accepted_response,
                pair.accepted_test_passed,
                pair.accepted_lint_passed,
                is_accepted=True,
            ),
            "rejected_reward": compute_reward(
                pair.rejected_response,
                pair.rejected_test_passed,
                pair.rejected_lint_passed,
                is_accepted=False,
            ),
        }


class GRPOTrainer:
    """
    GRPO (Group Relative Policy Optimization) trainer.

    Implements 2-GRPO: minimum viable GRPO with just 2 responses per prompt
    (one accepted, one rejected). This is computationally efficient while
    maintaining the core RL benefits.
    """

    def __init__(
        self,
        model_name: str,
        lora_rank: int = 16,
        lora_alpha: int = 32,
        learning_rate: float = 1e-5,
        kl_coef: float = 0.04,
        gamma: float = 1.0,
        max_length: int = 2048,
        device: str = "cuda" if torch.cuda.is_available() else "cpu",
    ):
        self.model_name = model_name
        self.lora_rank = lora_rank
        self.lora_alpha = lora_alpha
        self.learning_rate = learning_rate
        self.kl_coef = kl_coef  # KL penalty to prevent mode collapse
        self.gamma = gamma  # Reward discount factor
        self.max_length = max_length
        self.device = device

        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        # Load reference model (for KL penalty)
        self.ref_model = None

    def prepare_model(self, model_path: str | None = None, use_4bit: bool = True):
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

        if model_path:
            model = AutoModelForCausalLM.from_pretrained(model_path, **model_kwargs)
        else:
            model = AutoModelForCausalLM.from_pretrained(self.model_name, **model_kwargs)

        model.config.use_cache = False

        # Apply LoRA
        target_modules = ["q_proj", "v_proj", "k_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
        actual_modules = []
        for name, _ in model.named_modules():
            for target in target_modules:
                if name.endswith(target) and target not in actual_modules:
                    actual_modules.append(target)

        if not actual_modules:
            actual_modules = ["c_attn", "c_proj"]

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

        # Create reference model for KL penalty (frozen)
        self.ref_model = AutoModelForCausalLM.from_pretrained(
            model_path or self.model_name,
            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
            device_map=self.device,
        )
        self.ref_model.eval()

        return model

    def compute_grpo_loss(
        self,
        model: Any,
        batch: dict[str, Any],
        optimizer: torch.optim.Optimizer,
    ) -> dict[str, float]:
        """
        Compute GRPO loss for a batch of pairs.

        GRPO loss = -log(π(a|s)) * A + β * KL(π || π_ref)

        Where A is the group-relative advantage:
        A = (r_accepted - mean(r)) / std(r)
        """
        model.train()

        total_loss = 0.0
        total_policy_loss = 0.0
        total_kl_loss = 0.0

        for i in range(len(batch["prompt_input_ids"])):
            prompt_ids = torch.tensor(batch["prompt_input_ids"][i], device=self.device).unsqueeze(0)
            prompt_mask = torch.tensor(batch["prompt_attention_mask"][i], device=self.device).unsqueeze(0)

            # Generate response with current policy
            accepted_ids = torch.tensor(batch["accepted_input_ids"][i], device=self.device).unsqueeze(0)
            torch.tensor(batch["accepted_attention_mask"][i], device=self.device).unsqueeze(0)

            rejected_ids = torch.tensor(batch["rejected_input_ids"][i], device=self.device).unsqueeze(0)
            torch.tensor(batch["rejected_attention_mask"][i], device=self.device).unsqueeze(0)

            # Compute log probabilities
            with torch.no_grad():
                ref_accepted_outputs = self.ref_model(
                    input_ids=prompt_ids,
                    attention_mask=prompt_mask,
                    labels=accepted_ids,
                )
                ref_rejected_outputs = self.ref_model(
                    input_ids=prompt_ids,
                    attention_mask=prompt_mask,
                    labels=rejected_ids,
                )
                ref_accepted_log_probs = -ref_accepted_outputs.loss.item()
                ref_rejected_log_probs = -ref_rejected_outputs.loss.item()

            accepted_outputs = model(
                input_ids=prompt_ids,
                attention_mask=prompt_mask,
                labels=accepted_ids,
            )
            rejected_outputs = model(
                input_ids=prompt_ids,
                attention_mask=prompt_mask,
                labels=rejected_ids,
            )

            accepted_log_probs = -accepted_outputs.loss
            rejected_log_probs = -rejected_outputs.loss

            # Compute rewards
            r_accepted = batch["accepted_reward"][i]
            r_rejected = batch["rejected_reward"][i]

            # Group-relative advantage (2-GRPO)
            rewards = torch.tensor([r_accepted, r_rejected], device=self.device)
            mean_reward = rewards.mean()
            std_reward = rewards.std() + 1e-8  # Avoid division by zero

            adv_accepted = (r_accepted - mean_reward) / std_reward
            adv_rejected = (r_rejected - mean_reward) / std_reward

            # Policy loss (negative because we want to maximize reward)
            policy_loss = -(accepted_log_probs * adv_accepted + rejected_log_probs * adv_rejected)

            # KL penalty
            kl_accepted = (
                torch.exp(ref_accepted_log_probs - accepted_log_probs)
                - (ref_accepted_log_probs - accepted_log_probs)
                - 1
            )
            kl_rejected = (
                torch.exp(ref_rejected_log_probs - rejected_log_probs)
                - (ref_rejected_log_probs - rejected_log_probs)
                - 1
            )
            kl_loss = (kl_accepted + kl_rejected) * self.kl_coef

            # Total loss
            loss = policy_loss.mean() + kl_loss.mean()

            # Backprop
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

            total_loss += loss.item()
            total_policy_loss += policy_loss.mean().item()
            total_kl_loss += kl_loss.mean().item()

        n = len(batch["prompt_input_ids"])
        return {
            "loss": total_loss / n,
            "policy_loss": total_policy_loss / n,
            "kl_loss": total_kl_loss / n,
            "mean_reward_accepted": sum(batch["accepted_reward"]) / n,
            "mean_reward_rejected": sum(batch["rejected_reward"]) / n,
        }

    def train(
        self,
        pairs: list[GRPOPair],
        model_path: str | None = None,
        output_dir: str | Path = "checkpoints/grpo",
        num_epochs: int = 1,
        batch_size: int = 4,
        learning_rate: float = 1e-5,
        save_steps: int = 100,
        logging_steps: int = 10,
        use_4bit: bool = True,
    ) -> dict[str, Any]:
        """
        Train with GRPO.

        Args:
            pairs: List of accept/reject pairs
            model_path: Path to SFT-trained model (from Phase 1)
            output_dir: Output directory
            num_epochs: Number of training epochs
            batch_size: Batch size
            learning_rate: Learning rate
            save_steps: Save checkpoint every N steps
            logging_steps: Log every N steps
            use_4bit: Use 4-bit quantization

        Returns:
            Training metrics
        """
        # Prepare model
        model = self.prepare_model(model_path, use_4bit)

        # Create dataset
        dataset = GRPODataset(pairs, self.tokenizer, self.max_length)
        dataloader = DataLoader(
            dataset,
            batch_size=batch_size,
            shuffle=True,
            collate_fn=lambda x: {
                "prompt_input_ids": [item["prompt_input_ids"] for item in x],
                "prompt_attention_mask": [item["prompt_attention_mask"] for item in x],
                "accepted_input_ids": [item["accepted_input_ids"] for item in x],
                "accepted_attention_mask": [item["accepted_attention_mask"] for item in x],
                "rejected_input_ids": [item["rejected_input_ids"] for item in x],
                "rejected_attention_mask": [item["rejected_attention_mask"] for item in x],
                "accepted_reward": [item["accepted_reward"] for item in x],
                "rejected_reward": [item["rejected_reward"] for item in x],
            },
        )

        # Optimizer
        optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)

        # Training loop
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        global_step = 0
        metrics_history = []

        print(f"\n{'=' * 60}")
        print("GRPO TRAINING START")
        print(f"  Model: {model_path or self.model_name}")
        print(f"  Pairs: {len(pairs)}")
        print(f"  Epochs: {num_epochs}")
        print(f"  Batch size: {batch_size}")
        print(f"  Learning rate: {learning_rate}")
        print(f"  KL coefficient: {self.kl_coef}")
        print(f"{'=' * 60}\n")

        for epoch in range(num_epochs):
            for batch in dataloader:
                metrics = self.compute_grpo_loss(model, batch, optimizer)
                metrics["step"] = global_step
                metrics["epoch"] = epoch
                metrics_history.append(metrics)

                if global_step % logging_steps == 0:
                    print(
                        f"Step {global_step}: loss={metrics['loss']:.4f}, "
                        f"policy_loss={metrics['policy_loss']:.4f}, "
                        f"kl_loss={metrics['kl_loss']:.4f}, "
                        f"reward_accepted={metrics['mean_reward_accepted']:.2f}, "
                        f"reward_rejected={metrics['mean_reward_rejected']:.2f}"
                    )

                if global_step % save_steps == 0 and global_step > 0:
                    checkpoint_dir = output_dir / f"checkpoint-{global_step}"
                    checkpoint_dir.mkdir(parents=True, exist_ok=True)
                    model.save_pretrained(str(checkpoint_dir))
                    self.tokenizer.save_pretrained(str(checkpoint_dir))
                    print(f"Saved checkpoint: {checkpoint_dir}")

                global_step += 1

        # Save final model
        model.save_pretrained(str(output_dir))
        self.tokenizer.save_pretrained(str(output_dir))

        # Summary metrics
        final_metrics = {
            "final_loss": metrics_history[-1]["loss"] if metrics_history else None,
            "final_policy_loss": metrics_history[-1]["policy_loss"] if metrics_history else None,
            "final_kl_loss": metrics_history[-1]["kl_loss"] if metrics_history else None,
            "total_steps": global_step,
            "pairs_trained": len(pairs),
            "model_path": str(output_dir),
        }

        with open(output_dir / "grpo_metrics.json", "w") as f:
            json.dump(final_metrics, f, indent=2)

        print(f"\n{'=' * 60}")
        print("GRPO TRAINING COMPLETE")
        print(f"  Final loss: {final_metrics['final_loss']}")
        print(f"  Final policy loss: {final_metrics['final_policy_loss']}")
        print(f"  Final KL loss: {final_metrics['final_kl_loss']}")
        print(f"  Model saved: {output_dir}")
        print(f"{'=' * 60}\n")

        return final_metrics


def create_grpo_pairs_from_signals(
    accept_signals: list[dict],
    reject_signals: list[dict],
    edit_signals: list[dict],
) -> list[GRPOPair]:
    """
    Create GRPO training pairs from capture engine signals.

    Strategy:
    - Match accepts with rejects from same file/language
    - Use edits as additional positive examples (final_code vs original suggestion)
    """
    pairs = []

    # Match accepts with rejects
    for accept in accept_signals:
        # Find a reject with similar context
        for reject in reject_signals:
            if (
                accept.get("language") == reject.get("language")
                and accept.get("file_path", "").split(".")[-1] == reject.get("file_path", "").split(".")[-1]
            ):
                pair = GRPOPair(
                    prompt=accept.get("full_context", accept.get("context_before", "")),
                    accepted_response=accept.get("suggestion", ""),
                    rejected_response=reject.get("suggestion", ""),
                    accepted_test_passed=accept.get("test_passed", False),
                    rejected_test_passed=reject.get("test_passed", False),
                    signal_id=accept.get("signal_id"),
                    language=accept.get("language", "python"),
                )
                pairs.append(pair)
                break  # One reject per accept

    # Create pairs from edits (final_code is the "accepted" version)
    for edit in edit_signals:
        pair = GRPOPair(
            prompt=edit.get("full_context", edit.get("context_before", "")),
            accepted_response=edit.get("final_code", ""),
            rejected_response=edit.get("suggestion", ""),  # Original suggestion was "rejected"
            signal_id=edit.get("signal_id"),
            language=edit.get("language", "python"),
        )
        pairs.append(pair)

    random.shuffle(pairs)
    return pairs


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="GRPO Trainer — RL with Verifiable Rewards")
    parser.add_argument("--model", required=True, help="Base model or SFT-trained model path")
    parser.add_argument("--data", required=True, help="GRPO pairs file (JSONL)")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--lr", type=float, default=1e-5)
    parser.add_argument("--kl-coef", type=float, default=0.04)
    parser.add_argument("--lora-rank", type=int, default=16)
    args = parser.parse_args()

    # Load pairs
    pairs = []
    with open(args.data, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    data = json.loads(line)
                    pairs.append(GRPOPair.from_dict(data))
                except json.JSONDecodeError:
                    pass

    print(f"Loaded {len(pairs)} GRPO pairs")

    # Train
    trainer = GRPOTrainer(
        model_name=args.model,
        lora_rank=args.lora_rank,
        learning_rate=args.lr,
        kl_coef=args.kl_coef,
    )

    metrics = trainer.train(
        pairs=pairs,
        output_dir=args.output,
        num_epochs=args.epochs,
        batch_size=args.batch_size,
    )

    print(json.dumps(metrics, indent=2))
