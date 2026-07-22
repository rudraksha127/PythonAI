from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import sys
import time
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import datasets
import torch
from datasets import Dataset, load_from_disk

datasets.disable_caching()
import datasets.fingerprint  # noqa: E402

datasets.fingerprint.generate_fingerprint = lambda *args, **kwargs: "dummy_fingerprint"

# ── Unsloth (optional — 2x faster QLoRA, 70% less VRAM) ──
_HAS_UNSLOTH: bool = False
try:
    # noqa: E402  # noqa: F811
    from unsloth import FastLanguageModel, is_bfloat16_supported

    _HAS_UNSLOTH = True
except (ImportError, NotImplementedError, RuntimeError):
    pass

# noqa: E402
from peft import LoraConfig, get_peft_model  # noqa: E402, I001
from transformers import (  # noqa: E402
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    Trainer,
    TrainerCallback,
    TrainingArguments,
    default_data_collator,
)

from src.training.viz import TrainingMetrics, render_all  # noqa: E402

DEFAULT_SOURCE_FILES = [
    "training_dataset.json",
    "python_ultra_dataset_FINAL.json",
    "raw_chunks_godmode.json",
    "raw_chunks.json",
]


@dataclass
class Example:
    prompt: str
    response: str
    source: str


def load_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        try:
            return json.load(handle)
        except json.JSONDecodeError:
            handle.seek(0)
            return [json.loads(line) for line in handle if line.strip()]


def build_examples_from_pairs(rows: list[dict[str, Any]], limit: int) -> list[Example]:
    examples: list[Example] = []

    for row in rows:
        if "messages" in row:
            # Handle INDRA formatted data
            user_msg = ""
            ast_msg = ""
            for msg in row["messages"]:
                if msg.get("role") == "user":
                    user_msg = msg.get("content", "")
                elif msg.get("role") == "assistant":
                    ast_msg = msg.get("content", "")
            if not user_msg or not ast_msg:
                continue

            examples.append(
                Example(
                    prompt=user_msg,
                    response=ast_msg,
                    source=row.get("metadata", {}).get("source", "indra_formatted"),
                )
            )
        else:
            # Fallback for old format
            instruction = str(row.get("instruction", "")).strip()
            output = str(row.get("output", "")).strip()
            if len(instruction) < 10 or len(output) < 30:
                continue

            examples.append(
                Example(
                    prompt=f"You are a task-performing Python expert. Complete the request fully.\n\nTask: {instruction}",
                    response=output,
                    source=str(row.get("source", "generated")),
                )
            )

        if len(examples) >= limit:
            break

    return examples


def build_examples_from_chunks(rows: list[dict[str, Any]], limit: int) -> list[Example]:
    examples: list[Example] = []

    for chunk in rows:
        title = str(chunk.get("title", "Python topic")).strip() or "Python topic"
        text = str(chunk.get("text", "")).strip()
        code_blocks = chunk.get("codes", []) or []
        code = str(code_blocks[0]).strip() if code_blocks else ""

        if len(text) < 40:
            continue

        prompt = (
            f"You are a task-performing Python expert.\n"
            f"Explain the topic and include a practical example.\n\n"
            f"Topic: {title}\n"
            f"Context: {text[:1500]}"
        )

        response_parts = [
            f"Topic summary: {title}",
            text[:1800],
        ]
        if code:
            response_parts.append(f"Practical code example:\n```python\n{code[:1000]}\n```")

        examples.append(
            Example(
                prompt=prompt,
                response="\n\n".join(response_parts),
                source=str(chunk.get("filepath", chunk.get("category", "docs"))),
            )
        )

        if len(examples) >= limit:
            break

    return examples


def load_examples(source_files: list[str], limit: int) -> list[Example]:
    for name in source_files:
        path = Path(name)
        if not path.exists():
            continue

        rows = load_json_file(path)
        if not isinstance(rows, list):
            continue

        if rows and isinstance(rows[0], dict):
            if {"instruction", "output"}.issubset(rows[0]) or "messages" in rows[0]:
                return build_examples_from_pairs(rows, limit)
            if "text" in rows[0]:
                return build_examples_from_chunks(rows, limit)

    raise FileNotFoundError("No usable training source file found.")


def make_dataset(examples: list[Example], tokenizer, max_length: int, use_indra: bool = False) -> Dataset:
    rows = []

    # Pre-build system prompt if using INDRA
    system_msg = ""
    if use_indra:
        try:
            from src.training.indra_prompt import build_training_system_prompt

            system_msg = build_training_system_prompt()
        except ImportError:
            print("[WARN] Could not import INDRA prompt, using empty system prompt.")

    for example in examples:
        # Chat format if tokenizer has chat template, else fallback
        if hasattr(tokenizer, "apply_chat_template") and tokenizer.chat_template:
            messages = []
            if system_msg:
                messages.append({"role": "system", "content": system_msg})
            messages.append({"role": "user", "content": example.prompt})
            messages.append({"role": "assistant", "content": example.response})

            try:
                # Get the full templated string
                full_text = tokenizer.apply_chat_template(messages, tokenize=False)

                # We need to mask the prompt part for loss calculation
                prompt_messages = messages[:-1]
                prompt_text = tokenizer.apply_chat_template(prompt_messages, tokenize=False, add_generation_prompt=True)

                prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
                full_ids = tokenizer(full_text, add_special_tokens=False)["input_ids"]

                response_ids = full_ids[len(prompt_ids) :]

            except Exception:
                # Fallback on error
                prompt_text = f"### Instruction:\n{system_msg}\n{example.prompt}\n\n### Response:\n"
                eos = tokenizer.eos_token or ""
                prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
                response_ids = tokenizer(example.response + eos, add_special_tokens=False)["input_ids"]
        else:
            # Standard fallback (Alpaca style)
            prompt_text = f"### Instruction:\n{system_msg}\n{example.prompt}\n\n### Response:\n"
            eos = tokenizer.eos_token or ""
            prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
            response_ids = tokenizer(example.response + eos, add_special_tokens=False)["input_ids"]

        if not response_ids:
            continue

        if len(response_ids) >= max_length:
            prompt_ids = []
            response_ids = response_ids[:max_length]
        else:
            prompt_budget = max_length - len(response_ids)
            prompt_ids = prompt_ids[:prompt_budget]

        input_ids = prompt_ids + response_ids
        attention_mask = [1] * len(input_ids)
        labels = [-100] * len(prompt_ids) + list(response_ids)

        pad_id = tokenizer.pad_token_id
        if pad_id is None:
            pad_id = tokenizer.eos_token_id or 0

        pad_count = max_length - len(input_ids)
        if pad_count > 0:
            input_ids.extend([pad_id] * pad_count)
            attention_mask.extend([0] * pad_count)
            labels.extend([-100] * pad_count)

        if all(label == -100 for label in labels):
            continue

        rows.append(
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "labels": labels,
                "source": example.source,
            }
        )

    if not rows:
        raise RuntimeError("Dataset formatting produced zero trainable examples.")

    return Dataset.from_list(rows)


def build_dataset_cache_key(args: argparse.Namespace, tokenizer) -> str:
    """Build a stable cache key based on sources and tokenization settings."""
    hasher = hashlib.sha256()
    hasher.update(str(getattr(tokenizer, "name_or_path", "")).encode("utf-8"))
    hasher.update(str(args.max_length).encode("utf-8"))
    hasher.update(str(args.max_examples).encode("utf-8"))
    hasher.update(str(args.validation_split).encode("utf-8"))
    hasher.update(str(args.dataset_version).encode("utf-8"))

    for name in args.source_files:
        path = Path(name)
        if path.exists():
            stat = path.stat()
            payload = f"{path.resolve()}|{stat.st_size}|{int(stat.st_mtime)}"
        else:
            payload = f"{name}|missing"
        hasher.update(payload.encode("utf-8"))

    return hasher.hexdigest()[:16]


def load_cached_datasets(cache_root: Path, cache_key: str) -> tuple[Dataset, Dataset] | None:
    train_path = cache_root / cache_key / "train"
    eval_path = cache_root / cache_key / "eval"
    if not train_path.exists() or not eval_path.exists():
        return None

    try:
        train_dataset = load_from_disk(str(train_path))
        eval_dataset = load_from_disk(str(eval_path))
        return train_dataset, eval_dataset
    except Exception:
        return None


def save_cached_datasets(
    cache_root: Path,
    cache_key: str,
    train_dataset: Dataset,
    eval_dataset: Dataset,
    meta: dict[str, Any],
) -> None:
    cache_dir = cache_root / cache_key
    (cache_dir / "train").mkdir(parents=True, exist_ok=True)
    (cache_dir / "eval").mkdir(parents=True, exist_ok=True)
    train_dataset.save_to_disk(str(cache_dir / "train"))
    eval_dataset.save_to_disk(str(cache_dir / "eval"))
    (cache_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def resolve_deepspeed_config(args: argparse.Namespace, output_dir: str) -> str | None:
    if not args.deepspeed:
        return None

    if not torch.cuda.is_available():
        raise RuntimeError("DeepSpeed requires CUDA; disable --deepspeed on CPU.")

    if importlib.util.find_spec("deepspeed") is None:
        raise RuntimeError("DeepSpeed is not installed. Run: pip install deepspeed")

    value = str(args.deepspeed).strip().lower()
    if value in {"zero2", "zero-2", "2"}:
        stage = 2
    elif value in {"zero3", "zero-3", "3"}:
        stage = 3
    else:
        # Treat as a path to a JSON config
        cfg_path = Path(args.deepspeed)
        if not cfg_path.exists():
            raise FileNotFoundError(f"DeepSpeed config not found: {cfg_path}")
        return str(cfg_path)

    config = {
        "train_micro_batch_size_per_gpu": args.batch_size,
        "gradient_accumulation_steps": args.grad_accum,
        "fp16": {"enabled": True},
        "zero_optimization": {
            "stage": stage,
            "overlap_comm": True,
            "contiguous_gradients": True,
            "reduce_scatter": True,
            "allgather_partitions": True,
            "allgather_bucket_size": 2e8,
            "reduce_bucket_size": 2e8,
        },
        "wall_clock_breakdown": False,
    }

    if stage == 3:
        config["zero_optimization"].update(
            {
                "stage3_param_persistence_threshold": 1e5,
                "offload_param": {"device": "cpu", "pin_memory": True},
                "offload_optimizer": {"device": "cpu", "pin_memory": True},
            }
        )

    output_path = Path(output_dir) / "deepspeed_config.json"
    output_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return str(output_path)


def choose_lora_targets(model) -> list[str]:
    model_type = getattr(getattr(model, "config", None), "model_type", "").lower()

    if "gpt2" in model_type:
        return ["c_attn", "c_proj"]

    if any(token in model_type for token in ["qwen", "llama", "mistral", "mixtral", "baichuan", "internlm"]):
        return ["q_proj", "k_proj", "v_proj", "o_proj"]

    return ["q_proj", "k_proj", "v_proj", "o_proj"]


# ─── Custom callback for token throughput logging ───
class ThroughputCallback(TrainerCallback):
    """Logs tokens-per-second during training."""

    def __init__(self, max_length: int) -> None:
        super().__init__()
        self.max_length = max_length
        self.start_time: float | None = None
        self.total_tokens = 0

    def on_log(self, args, state, control, model=None, **kwargs):
        if self.start_time is None:
            self.start_time = time.time()
            return

        elapsed = time.time() - self.start_time
        if elapsed > 0 and state.global_step > 0:
            batch_size = args.per_device_train_batch_size * max(1, args.gradient_accumulation_steps)
            tokens_per_step = self.max_length * batch_size
            total_tokens = tokens_per_step * state.global_step
            tps = total_tokens / elapsed
            print(f"  [Throughput] {tps:.0f} tokens/sec | step {state.global_step}")


# ─── Custom callback for training curves ───
class TrainingCurvesCallback(TrainerCallback):
    """Collects loss values for plotting. (Legacy — kept for backward compat.)"""

    def __init__(self, output_dir: str) -> None:
        super().__init__()
        self.output_dir = output_dir
        self.steps: list[int] = []
        self.losses: list[float] = []

    def on_log(self, args, state, control, model=None, **kwargs):
        logs = kwargs.get("logs", {})
        if "loss" in logs:
            self.steps.append(state.global_step)
            self.losses.append(logs["loss"])

    def save_plot(self) -> None:
        if len(self.steps) < 2:
            return
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            plt.figure(figsize=(10, 6))
            plt.plot(self.steps, self.losses, marker="o", linestyle="-")
            plt.xlabel("Step")
            plt.ylabel("Loss")
            plt.title("Training Loss Curve")
            plt.grid(True)
            path = Path(self.output_dir) / "training_curve.png"
            plt.savefig(str(path))
            plt.close()
            print(f"Training curve saved: {path}")
        except ImportError:
            print("matplotlib not installed; skipping training curve plot.")


# ─── Enhanced callback for comprehensive training visualization ───
class EnhancedTrainingCurvesCallback(TrainerCallback):
    """Collects all training metrics (loss, LR, throughput, eval loss) for visualization.

    When combined with --viz / --save-training-curves, produces:
      - Professional loss curves (train + eval)
      - Learning rate schedule plot
      - Token throughput bar chart
      - Multi-panel dashboard figure
      - JSON metrics export
      - HTML dashboard report
    """

    def __init__(self, output_dir: str) -> None:
        super().__init__()
        self.output_dir = output_dir
        self.metrics = TrainingMetrics()
        self._start_time: float | None = None
        self._first_log = True

    def on_log(self, args, state, control, model=None, **kwargs):
        logs = kwargs.get("logs", {})
        step = state.global_step

        if self._first_log:
            self._start_time = time.time()
            # Capture metadata
            self.metrics.max_length = getattr(args, "max_length", 512)
            self.metrics.batch_size = getattr(args, "per_device_train_batch_size", 1)
            self.metrics.grad_accum = max(1, getattr(args, "gradient_accumulation_steps", 4))
            self.metrics.base_model = getattr(args, "base_model", "") or ""
            self.metrics.total_train_examples = getattr(state, "num_train_examples", 0) or 0
            self.metrics.total_eval_examples = getattr(state, "num_eval_examples", 0) or 0
            self.metrics.lr_scheduler_type = getattr(args, "lr_scheduler_type", "linear") or "linear"
            self.metrics.early_stopping_patience = getattr(args, "early_stopping_patience", 0) or 0
            self._first_log = False

        # Record train loss
        if "loss" in logs:
            self.metrics.record_train_loss(step, logs["loss"])

        # Record eval loss
        if "eval_loss" in logs:
            self.metrics.record_eval_loss(step, logs["eval_loss"])

        # Record learning rate
        if "learning_rate" in logs:
            self.metrics.record_lr(step, logs["learning_rate"])

        # Record throughput
        if self._start_time and step > 0:
            elapsed = time.time() - self._start_time
            if elapsed > 0:
                batch_size = self.metrics.batch_size * self.metrics.grad_accum
                tokens_per_step = self.metrics.max_length * batch_size
                total_tokens = tokens_per_step * step
                tps = total_tokens / elapsed
                self.metrics.record_throughput(step, tps)

    def save_all(self) -> None:
        """Save all visualization outputs to the output directory."""
        if len(self.metrics.train_steps) < 2:
            print("Not enough data for visualization; skipping.")
            return
        try:
            results = render_all(self.metrics, self.output_dir)
            print(f"Visualization: {len(results)} files generated.")
        except Exception as exc:
            print(f"Visualization failed (matplotlib may be missing): {exc}")

    def finalize(self, args) -> None:
        """Capture any remaining metadata and save."""
        # Update metadata from args if not already set
        if not self.metrics.base_model:
            self.metrics.base_model = getattr(args, "base_model", "") or ""
        if not self.metrics.lr_scheduler_type:
            self.metrics.lr_scheduler_type = getattr(args, "lr_scheduler_type", "linear") or "linear"
        self.metrics.total_train_examples = max(
            self.metrics.total_train_examples,
            getattr(args, "max_examples", 0) or 0,
        )
        self.save_all()


def maybe_enable_airllm_probe(model_name: str, prompt: str, max_length: int) -> None:
    if not torch.cuda.is_available():
        print("AirLLM probe skipped: CUDA is not available.")
        return

    try:
        if "optimum.bettertransformer" not in sys.modules:
            optimum_module = sys.modules.get("optimum")
            if optimum_module is None:
                optimum_module = types.ModuleType("optimum")
                optimum_module.__path__ = []  # type: ignore[attr-defined]
                sys.modules["optimum"] = optimum_module

            bettertransformer_module = types.ModuleType("optimum.bettertransformer")

            class _BetterTransformerShim:
                @staticmethod
                def transform(model):
                    return model

            bettertransformer_module.BetterTransformer = _BetterTransformerShim
            sys.modules["optimum.bettertransformer"] = bettertransformer_module

        from airllm import AutoModel
    except Exception as exc:
        print(f"AirLLM probe skipped: import failed ({exc}).")
        return

    try:
        airllm_model = AutoModel.from_pretrained(model_name)
        inputs = airllm_model.tokenizer(
            [prompt],
            return_tensors="pt",
            return_attention_mask=False,
            truncation=True,
            max_length=max_length,
            padding=True,
        )
        output = airllm_model.generate(
            inputs["input_ids"].cuda(),
            max_new_tokens=32,
            use_cache=True,
            return_dict_in_generate=True,
        )
        text = airllm_model.tokenizer.decode(output.sequences[0])
        print("AirLLM probe output:")
        print(text[:500])
    except Exception as exc:
        print(f"AirLLM probe skipped: runtime failure ({exc}).")


# ─── Unsloth training path ───
def train_with_unsloth(args: argparse.Namespace) -> None:
    """
    Train using Unsloth for 2x faster QLoRA with 70% less VRAM.
    Mirrors the standard train() function but uses FastLanguageModel.
    """
    if not _HAS_UNSLOTH:
        raise ImportError("Unsloth is not installed. Run: pip install unsloth")

    random.seed(args.seed)
    torch.manual_seed(args.seed)

    if getattr(args, "test_mode", False):
        args.max_steps = 2
        args.max_examples = 4
        print("[Test mode] Overriding: --max-steps 2 --max-examples 4")

    if args.base_model.startswith("ollama:"):
        raise ValueError("Ollama/GGUF models cannot be fine-tuned. Use an HF-format model id for Unsloth training.")

    print(f"\n{'=' * 60}")
    print("  ⚡ UNSLOTH MODE — 2x faster, 70% less VRAM")
    print(f"  Model: {args.base_model}")
    print(f"{'=' * 60}\n")

    # ── Load tokenizer ──
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # ── Load examples ──
    examples = load_examples(args.source_files, args.max_examples)
    if not args.test_mode and len(examples) < 8:
        raise RuntimeError(f"Not enough training examples: {len(examples)}")

    random.shuffle(examples)
    split_index = max(1, int(len(examples) * (1 - args.validation_split)))
    train_examples = examples[:split_index]
    eval_examples = examples[split_index:] or examples[: min(8, len(examples))]

    train_dataset = make_dataset(train_examples, tokenizer, args.max_length, args.use_indra_prompt)
    eval_dataset = make_dataset(eval_examples, tokenizer, args.max_length, args.use_indra_prompt)

    print(f"Base model       : {args.base_model}")
    print(f"Output directory : {args.output_dir}")
    print(f"Max length       : {args.max_length}")
    print(f"CUDA available   : {torch.cuda.is_available()}")
    print("Unsloth          : enabled (FastLanguageModel)")

    # ── Load model with Unsloth ──
    max_seq_length = getattr(args, "unsloth_max_seq_length", 2048)
    print(f"Loading model via FastLanguageModel (max_seq={max_seq_length})...")

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.base_model,
        max_seq_length=max_seq_length,
        load_in_4bit=getattr(args, "load_in_4bit", True),
        dtype=None,  # Auto-detect: bfloat16 if supported, else float16
        trust_remote_code=True,
        token=getattr(args, "hf_token", None) or None,
    )

    # ── Apply LoRA via Unsloth's optimized method ──
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_rank,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        lora_alpha=args.lora_alpha,
        lora_dropout=0,  # Unsloth recommends 0 for best performance
        bias="none",
        use_gradient_checkpointing=args.gradient_checkpointing,
        random_state=args.seed,
        max_seq_length=max_seq_length,
    )
    model.print_trainable_parameters()

    # ── Callbacks ──
    callbacks = []
    throughput_cb = ThroughputCallback(max_length=args.max_length)
    callbacks.append(throughput_cb)

    curves_cb = None
    if args.save_training_curves or args.viz:
        if args.viz:
            curves_cb = EnhancedTrainingCurvesCallback(args.output_dir)
        else:
            curves_cb = TrainingCurvesCallback(args.output_dir)
        callbacks.append(curves_cb)

    _viz_base_model = args.base_model if hasattr(args, "base_model") else ""
    _viz_dataset_version = args.dataset_version if hasattr(args, "dataset_version") else ""

    # ── Training arguments ──
    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        max_steps=args.max_steps,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.learning_rate,
        warmup_ratio=0.03,
        logging_steps=1,
        save_strategy=args.save_strategy,
        save_steps=args.save_steps,
        save_total_limit=args.save_total_limit,
        eval_strategy=args.eval_strategy,
        eval_steps=args.eval_steps,
        report_to=["wandb"] if args.wandb else [],
        remove_unused_columns=False,
        fp16=not is_bfloat16_supported() if torch.cuda.is_available() else False,
        bf16=is_bfloat16_supported() if torch.cuda.is_available() else False,
        gradient_checkpointing=args.gradient_checkpointing,
        max_grad_norm=args.gradient_clip if args.gradient_clip > 0 else 1.0,
        lr_scheduler_type=args.lr_scheduler_type or "linear",
        load_best_model_at_end=args.early_stopping_patience > 0,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
    )

    if curves_cb and isinstance(curves_cb, EnhancedTrainingCurvesCallback):
        curves_cb.metrics.base_model = _viz_base_model
        curves_cb.metrics.dataset_version = _viz_dataset_version

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=default_data_collator,
        callbacks=callbacks,
    )

    print(f"Training examples: {len(train_dataset)}")
    print(f"Validation examples: {len(eval_dataset)}")
    print(f"LR scheduler: {args.lr_scheduler_type or 'linear'}")
    if args.early_stopping_patience > 0:
        print(f"Early stopping patience: {args.early_stopping_patience}")

    train_result = trainer.train(resume_from_checkpoint=args.resume_from_checkpoint or None)

    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

    metrics = train_result.metrics
    metrics["train_examples"] = len(train_dataset)
    metrics["validation_examples"] = len(eval_dataset)
    trainer.save_metrics("train", metrics)

    if curves_cb:
        if isinstance(curves_cb, EnhancedTrainingCurvesCallback):
            curves_cb.finalize(training_args)
        else:
            curves_cb.save_plot()

    print(f"\n{'=' * 60}")
    print("  ✅ UNSLOTH TRAINING COMPLETE")
    print(f"  Model saved: {args.output_dir}")
    print(f"{'=' * 60}\n")


def train(args: argparse.Namespace) -> None:
    random.seed(args.seed)
    torch.manual_seed(args.seed)

    if getattr(args, "test_mode", False):
        args.max_steps = 2
        args.max_examples = 4
        print("[Test mode] Overriding: --max-steps 2 --max-examples 4")

    if args.base_model.startswith("ollama:"):
        raise ValueError(
            "Ollama/GGUF models cannot be PEFT fine-tuned by this Trainer. "
            "Use an HF-format Qwen path/model id for LoRA training, and use Ollama for RAG/inference."
        )

    # ══════════════════════════════════════════════
    # Route to Unsloth if enabled and available
    # ══════════════════════════════════════════════
    use_unsloth = getattr(args, "use_unsloth", False)
    if use_unsloth:
        if not _HAS_UNSLOTH:
            print("[WARN] Unsloth not installed. Falling back to standard training.")
            print("  Install: pip install 'unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git'")
        else:
            train_with_unsloth(args)
            return

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    use_cache = bool(getattr(args, "dataset_cache_dir", "")) and not getattr(args, "no_dataset_cache", False)
    cache_root = Path(getattr(args, "dataset_cache_dir", "checkpoints/token_cache")) if use_cache else None
    cache_key = build_dataset_cache_key(args, tokenizer) if use_cache else ""
    cached = None

    if use_cache and cache_root is not None:
        cache_root.mkdir(parents=True, exist_ok=True)
        cached = load_cached_datasets(cache_root, cache_key)
        if cached:
            print(f"Loaded cached datasets: {cache_root / cache_key}")

    if cached:
        train_dataset, eval_dataset = cached
    else:
        examples = load_examples(args.source_files, args.max_examples)
        if not args.test_mode and len(examples) < 8:
            raise RuntimeError(f"Not enough training examples: {len(examples)}")

        random.shuffle(examples)
        split_index = max(1, int(len(examples) * (1 - args.validation_split)))
        train_examples = examples[:split_index]
        eval_examples = examples[split_index:] or examples[: min(8, len(examples))]

        train_dataset = make_dataset(train_examples, tokenizer, args.max_length, args.use_indra_prompt)
        eval_dataset = make_dataset(eval_examples, tokenizer, args.max_length, args.use_indra_prompt)

        if use_cache and cache_root is not None:
            meta = {
                "source_files": [str(s) for s in args.source_files],
                "max_examples": args.max_examples,
                "max_length": args.max_length,
                "validation_split": args.validation_split,
                "dataset_version": args.dataset_version,
                "tokenizer": getattr(tokenizer, "name_or_path", ""),
            }
            save_cached_datasets(cache_root, cache_key, train_dataset, eval_dataset, meta)
            print(f"Saved tokenized datasets: {cache_root / cache_key}")

    print(f"Base model       : {args.base_model}")
    print(f"Output directory : {args.output_dir}")
    print(f"Max length       : {args.max_length}")
    print(f"CUDA available   : {torch.cuda.is_available()}")

    # Prepare model kwargs
    model_kwargs: dict[str, Any] = {
        "trust_remote_code": True,
        "torch_dtype": torch.float16 if torch.cuda.is_available() else torch.float32,
    }

    # 4-bit QLoRA support
    if args.load_in_4bit:
        if not torch.cuda.is_available():
            print("Warning: 4-bit requires CUDA; falling back to fp32.")
        else:
            print("Enabling 4-bit QLoRA quantization...")
            model_kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
            )
            model_kwargs["device_map"] = "auto"

    model = AutoModelForCausalLM.from_pretrained(args.base_model, **model_kwargs)
    model.config.use_cache = False

    lora_config = LoraConfig(
        r=args.lora_rank,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=choose_lora_targets(model),
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Custom callbacks
    callbacks = []
    throughput_cb = ThroughputCallback(max_length=args.max_length)
    callbacks.append(throughput_cb)

    curves_cb = None
    if args.save_training_curves or args.viz:
        if args.viz:
            curves_cb = EnhancedTrainingCurvesCallback(args.output_dir)
        else:
            curves_cb = TrainingCurvesCallback(args.output_dir)
        callbacks.append(curves_cb)

        # Capture base_model and dataset_version for visualization metadata
    _viz_base_model = args.base_model if hasattr(args, "base_model") else ""
    _viz_dataset_version = args.dataset_version if hasattr(args, "dataset_version") else ""

    deepspeed_config = resolve_deepspeed_config(args, args.output_dir)

    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        max_steps=args.max_steps,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.learning_rate,
        warmup_ratio=0.03,
        logging_steps=1,
        save_strategy=args.save_strategy,
        save_steps=args.save_steps,
        save_total_limit=args.save_total_limit,
        eval_strategy=args.eval_strategy,
        eval_steps=args.eval_steps,
        report_to=["wandb"] if args.wandb else [],
        remove_unused_columns=False,
        fp16=torch.cuda.is_available(),
        bf16=False,
        gradient_checkpointing=args.gradient_checkpointing,
        max_grad_norm=args.gradient_clip if args.gradient_clip > 0 else 1.0,
        lr_scheduler_type=args.lr_scheduler_type or "linear",
        load_best_model_at_end=args.early_stopping_patience > 0,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        deepspeed=deepspeed_config,
    )

    # Update EnhancedTrainingCurvesCallback metadata
    if curves_cb and isinstance(curves_cb, EnhancedTrainingCurvesCallback):
        curves_cb.metrics.base_model = _viz_base_model
        curves_cb.metrics.dataset_version = _viz_dataset_version

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=default_data_collator,
        callbacks=callbacks,  # type: ignore[arg-type]
    )

    print(f"Training examples: {len(train_dataset)}")
    print(f"Validation examples: {len(eval_dataset)}")
    print(f"LR scheduler: {args.lr_scheduler_type or 'linear'}")
    if args.early_stopping_patience > 0:
        print(f"Early stopping patience: {args.early_stopping_patience}")

    train_result = trainer.train(resume_from_checkpoint=args.resume_from_checkpoint or None)

    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

    metrics = train_result.metrics
    metrics["train_examples"] = len(train_dataset)
    metrics["validation_examples"] = len(eval_dataset)
    trainer.save_metrics("train", metrics)

    # Save training visualization
    if curves_cb:
        if isinstance(curves_cb, EnhancedTrainingCurvesCallback):
            curves_cb.finalize(training_args)
        else:
            curves_cb.save_plot()

    if args.airllm_model:
        probe_prompt = "Explain Python list comprehensions with a practical example."
        maybe_enable_airllm_probe(args.airllm_model, probe_prompt, args.max_length)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap and train the GOD MODE Python model.")
    parser.add_argument("--base-model", default="sshleifer/tiny-gpt2")
    parser.add_argument("--source-files", nargs="*", default=DEFAULT_SOURCE_FILES)
    parser.add_argument("--output-dir", default="checkpoints/god_mode_model")
    parser.add_argument("--max-examples", type=int, default=256)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--validation-split", type=float, default=0.1)
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--lora-rank", type=int, default=8)
    parser.add_argument("--lora-alpha", type=int, default=16)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--airllm-model", default="")
    parser.add_argument("--save-strategy", default="steps", choices=["no", "steps", "epoch"])
    parser.add_argument("--save-steps", type=int, default=25)
    parser.add_argument("--save-total-limit", type=int, default=3)
    parser.add_argument("--eval-strategy", default="steps", choices=["no", "steps", "epoch"])
    parser.add_argument("--eval-steps", type=int, default=25)
    parser.add_argument("--resume-from-checkpoint", default="")
    parser.add_argument("--gradient-checkpointing", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--gradient-clip", type=float, default=0.0, help="Gradient clipping max norm")
    parser.add_argument("--dataset-version", default="")
    parser.add_argument("--wandb", action="store_true", help="Enable W&B logging")
    parser.add_argument("--early-stopping-patience", type=int, default=0)
    parser.add_argument("--lr-scheduler-type", choices=["cosine", "linear", "constant"], default=None)
    parser.add_argument("--save-training-curves", action="store_true", help="Save basic training loss curve plot")
    parser.add_argument(
        "--viz",
        action="store_true",
        help="Save comprehensive training visualization (dashboard, LR, throughput, HTML, JSON)",
    )
    parser.add_argument("--load-in-4bit", action="store_true", help="Enable 4-bit QLoRA")
    parser.add_argument(
        "--use-unsloth", action="store_true", help="Use Unsloth for 2x faster QLoRA training (70%% less VRAM)"
    )
    parser.add_argument(
        "--unsloth-max-seq-length", type=int, default=2048, help="Max sequence length for Unsloth (default: 2048)"
    )
    parser.add_argument("--hf-token", default="", help="HuggingFace token for gated models")
    parser.add_argument("--test-mode", action="store_true", help="Run a quick validation (2 steps, 4 examples)")
    parser.add_argument(
        "--use-indra-prompt", action="store_true", help="Inject INDRA system prompt into training examples"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    train(args)


if __name__ == "__main__":
    main()
