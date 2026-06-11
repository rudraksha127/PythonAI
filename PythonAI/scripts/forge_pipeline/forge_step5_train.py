"""
forge_step5_train.py - PHASE 5: MODEL TRAINING
=============================================
QLoRA fine-tuning with optimal settings.
Auto-detects hardware and adjusts config.
Checkpoints every 100 steps. Resumable.
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
from pathlib import Path

# Fix Windows console encoding
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import torch
from loguru import logger
from rich.console import Console

from forge_config import ForgeConfig

try:
    from datasets import Dataset, load_dataset
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        TrainingArguments,
        EarlyStoppingCallback,
        Trainer,
        default_data_collator,
    )
    from peft import LoraConfig, get_peft_model, TaskType, PeftModel
    from trl import SFTTrainer

    HAS_TRAIN_DEPS = True
except ImportError as _import_err:
    HAS_TRAIN_DEPS = False

console = Console()


def auto_detect_config(cfg: ForgeConfig) -> dict:
    """Return optimal training config based on detected hardware."""
    hw = cfg.hardware_profile
    vram = hw.get("vram_gb", 0)

    if hw.get("has_cuda"):
        if vram >= 40:
            return {"batch": 4, "accum": 4, "dtype": "bf16", "use_4bit": False, "seq": 4096}
        elif vram >= 24:
            return {"batch": 4, "accum": 4, "dtype": "fp16", "use_4bit": False, "seq": 2048}
        elif vram >= 16:
            return {"batch": 2, "accum": 8, "dtype": "fp16", "use_4bit": True, "seq": 2048}
        elif vram >= 10:
            return {"batch": 2, "accum": 8, "dtype": "fp16", "use_4bit": True, "seq": 1024}
        elif vram >= 6:
            return {"batch": 1, "accum": 16, "dtype": "fp16", "use_4bit": True, "seq": 512}
        else:
            return {"batch": 1, "accum": 32, "dtype": "fp16", "use_4bit": True, "seq": 256}
    else:
        # CPU mode: use gradient accumulation to simulate larger batch
        # With 12 cores, accum=8 gives effective batch of 8 without OOM
        return {"batch": 1, "accum": 8, "dtype": "fp32", "use_4bit": False, "seq": 512}


def load_raw_records(cfg: ForgeConfig, test_mode: bool = False) -> list[dict]:
    """Load assembled training data from disk as raw dicts."""
    train_dir = Path(cfg.train_data_dir)
    all_file = train_dir / "all_data.jsonl"

    if not all_file.exists():
        train_file = train_dir / "train.jsonl"
        if train_file.exists():
            all_file = train_file
        else:
            raise FileNotFoundError(f"No training data found in {train_dir}. Run forge_step4_assemble.py first.")

    logger.info(f"Loading training data from: {all_file}")

    records = []
    with open(all_file, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass

    if not records:
        raise ValueError("No valid training examples found!")

    logger.success(f"Loaded {len(records):,} training records")

    if test_mode:
        records = records[:10]
        logger.info(f"TEST MODE: using {len(records)} records")

    return records


def tokenize_record(record: dict, tokenizer, max_length: int) -> dict | None:
    """Tokenize a single ChatML record into input_ids/attention_mask/labels.
    Masks the prompt portion (system + user) with -100 so only assistant
    tokens contribute to the loss."""
    try:
        if "messages" in record:
            msgs = record["messages"]
            # Build full conversation text
            full_text = "\n".join([f"{m.get('role', 'user').upper()}: {m.get('content', '')}" for m in msgs])
            response_idx = len(msgs) - 1
            # Find where assistant response starts
            prompt_text = (
                "\n".join([f"{m.get('role', 'user').upper()}: {m.get('content', '')}" for m in msgs[:-1]])
                + "\nASSISTANT:"
            )
        elif "text" in record and len(record["text"]) > 50:
            full_text = record["text"]
            prompt_text = full_text[: len(full_text) // 2]  # Heuristic split
        else:
            return None

        # Tokenize
        full_ids = tokenizer(full_text, add_special_tokens=False)["input_ids"]
        prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]

        response_ids = full_ids[len(prompt_ids) :]
        if not response_ids:
            return None

        # Truncate to max_length
        if len(response_ids) >= max_length:
            prompt_ids = []
            response_ids = response_ids[:max_length]
        else:
            prompt_budget = max_length - len(response_ids)
            prompt_ids = prompt_ids[:prompt_budget]

        input_ids = prompt_ids + response_ids
        attention_mask = [1] * len(input_ids)
        labels = [-100] * len(prompt_ids) + list(response_ids)

        # Pad to max_length
        pad_id = tokenizer.pad_token_id or 0
        pad_count = max_length - len(input_ids)
        if pad_count > 0:
            input_ids.extend([pad_id] * pad_count)
            attention_mask.extend([0] * pad_count)
            labels.extend([-100] * pad_count)

        if all(l == -100 for l in labels):
            return None

        return {
            "input_ids": input_ids[:max_length],
            "attention_mask": attention_mask[:max_length],
            "labels": labels[:max_length],
        }
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
# UNSLOTH TRAINING (Optional — 2x faster, 70% less VRAM)
# ═══════════════════════════════════════════════════════════════

_HAS_UNSLOTH = False
try:
    from unsloth import FastLanguageModel, is_bfloat16_supported

    _HAS_UNSLOTH = True
except ImportError:
    pass


def train_with_unsloth(cfg: ForgeConfig, test_mode: bool = False):
    """Train using Unsloth FastLanguageModel for 2x speed."""
    if not _HAS_UNSLOTH:
        logger.error("Unsloth not installed. Run: pip install unsloth")
        return None

    # Load records
    try:
        raw_records = load_raw_records(cfg, test_mode=test_mode)
    except (FileNotFoundError, ValueError) as e:
        logger.error(str(e))
        return None

    # Load model via FastLanguageModel
    max_seq_length = 4096 if cfg.hardware_profile.get("vram_gb", 0) >= 24 else 2048
    logger.info(f"Loading via FastLanguageModel (max_seq={max_seq_length})...")

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=cfg.base_model,
        max_seq_length=max_seq_length,
        load_in_4bit=True,
        dtype=None,  # Auto-detect
        trust_remote_code=True,
        token=cfg.hf_token or None,
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r=cfg.lora_rank,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_alpha=cfg.lora_alpha or 16,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing=True,
        random_state=42,
        max_seq_length=max_seq_length,
    )
    model.print_trainable_parameters()

    # Tokenize data
    max_length = 2048 if cfg.hardware_profile.get("vram_gb", 12) < 16 else 4096
    tokenized = []
    for record in raw_records:
        result = tokenize_record(record, tokenizer, max_length)
        if result:
            tokenized.append(result)

    if not tokenized:
        raise ValueError("No records survived tokenization!")

    import random

    random.shuffle(tokenized)
    split_idx = int(len(tokenized) * 0.98)
    train_data = Dataset.from_list(tokenized[:split_idx])
    eval_data = Dataset.from_list(tokenized[split_idx:])

    logger.success(f"Unsloth: {len(tokenized)} records — Train: {len(train_data)}, Eval: {len(eval_data)}")

    # Training args
    hw = auto_detect_config(cfg)
    output_dir = str(Path(cfg.checkpoint_dir) / f"forge_unsloth_{time.strftime('%Y%m%d_%H%M')}")
    max_steps = 2 if test_mode else -1
    num_epochs = 1 if not torch.cuda.is_available() and not test_mode else (cfg.num_epochs or 1)

    use_bf16 = is_bfloat16_supported()
    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=num_epochs,
        max_steps=max_steps,
        per_device_train_batch_size=hw["batch"],
        per_device_eval_batch_size=max(1, hw["batch"] // 2),
        gradient_accumulation_steps=hw["accum"],
        optim="adamw_8bit",
        save_steps=500,
        logging_steps=10,
        eval_steps=500,
        learning_rate=cfg.learning_rate,
        weight_decay=cfg.weight_decay,
        fp16=not use_bf16,
        bf16=use_bf16,
        max_grad_norm=0.3,
        warmup_ratio=cfg.warmup_ratio,
        lr_scheduler_type="cosine",
        eval_strategy="steps",
        save_strategy="steps",
        save_total_limit=2,
        load_best_model_at_end=not test_mode,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        gradient_checkpointing=True,
        report_to="none",
        ddp_find_unused_parameters=False if torch.cuda.device_count() > 1 else None,
        dataloader_num_workers=0,
        remove_unused_columns=True,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_data,
        eval_dataset=eval_data,
        data_collator=default_data_collator,
    )

    # Resume logic
    last_checkpoint = None
    checkpoint_dir = Path(output_dir)
    if checkpoint_dir.exists():
        checkpoints = sorted(checkpoint_dir.glob("checkpoint-*"))
        if checkpoints:
            last_checkpoint = str(checkpoints[-1])
            logger.info(f"Resuming from: {last_checkpoint}")

    effective_batch = hw["batch"] * hw["accum"]
    total_steps = (len(train_data) // effective_batch) * num_epochs
    logger.info(f"""
{"=" * 60}
⚡ UNSLOTH TRAINING START
  Model:      {cfg.base_model}
  Train rows: {len(train_data):,}
  Eval rows:  {len(eval_data):,}
  Epochs:     {num_epochs}
  Batch:      {hw["batch"]} x {hw["accum"]} = {effective_batch}
  Est steps:  {total_steps:,}
  Precision:  {"bf16" if use_bf16 else "fp16"}
  Seq len:    {max_length}
  LoRA rank:  {cfg.lora_rank}
  Output:     {output_dir}
{"=" * 60}
""")

    trainer.train(resume_from_checkpoint=last_checkpoint)

    # Save
    final_dir = Path(cfg.final_model_dir)
    final_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Saving Unsloth model to: {final_dir}")
    trainer.save_model(str(final_dir))
    tokenizer.save_pretrained(str(final_dir))

    metrics = trainer.state.log_history
    train_losses = [m.get("loss") for m in metrics if "loss" in m]
    final_loss = train_losses[-1] if train_losses else None
    eval_losses = [m.get("eval_loss") for m in metrics if "eval_loss" in m]
    final_eval_loss = eval_losses[-1] if eval_losses else None

    summary = {
        "train_loss": final_loss,
        "eval_loss": final_eval_loss,
        "total_steps": trainer.state.global_step,
        "base_model": cfg.base_model,
        "lora_rank": cfg.lora_rank,
        "batch_size": hw["batch"],
        "grad_accum": hw["accum"],
        "max_length": max_length,
        "num_epochs": num_epochs,
        "learning_rate": cfg.learning_rate,
        "hardware": cfg.hardware_profile,
        "engine": "unsloth",
    }
    (final_dir / "training_metrics.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    logger.success(f"""
{"=" * 60}
✅ UNSLOTH TRAINING COMPLETE
  Final train loss: {final_loss or "N/A"}
  Final eval loss:  {final_eval_loss or "N/A"}
  Total steps:      {trainer.state.global_step:,}
  Model saved:      {final_dir}
{"=" * 60}
""")
    return final_dir


def train(cfg: ForgeConfig, test_mode: bool = False):
    """Run the full training pipeline."""
    if not HAS_TRAIN_DEPS:
        logger.error("Missing training dependencies. Install: pip install transformers peft trl datasets")
        return

    hw = auto_detect_config(cfg)

    # ── LOAD & TOKENIZE DATA ──────────────────────────────────────────────
    try:
        raw_records = load_raw_records(cfg, test_mode=test_mode)
    except (FileNotFoundError, ValueError) as e:
        logger.error(str(e))
        return

    logger.info(f"Loading model: {cfg.base_model}")
    tokenizer = AutoTokenizer.from_pretrained(
        cfg.base_model,
        token=cfg.hf_token or None,
        trust_remote_code=True,
        padding_side="right",
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Tokenize all records in parallel (simplified sequential for reliability)
    max_length = hw["seq"]
    tokenized = []
    for record in raw_records:
        result = tokenize_record(record, tokenizer, max_length)
        if result:
            tokenized.append(result)

    if not tokenized:
        raise ValueError("No records survived tokenization!")

    # Shuffle and split into train/eval
    import random

    random.shuffle(tokenized)
    split_idx = int(len(tokenized) * 0.98)
    train_data = Dataset.from_list(tokenized[:split_idx])
    eval_data = Dataset.from_list(tokenized[split_idx:])

    logger.success(f"Tokenized: {len(tokenized)} records — Train: {len(train_data)}, Eval: {len(eval_data)}")

    # ── QUANTIZATION ──────────────────────────────────────────────────────
    bnb_config = None
    if hw["use_4bit"] and torch.cuda.is_available():
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )

    # ── MODEL ──────────────────────────────────────────────────────────────
    model_kwargs = {
        "trust_remote_code": True,
        "torch_dtype": torch.float16
        if hw["dtype"] == "fp16"
        else (torch.bfloat16 if hw["dtype"] == "bf16" else torch.float32),
    }
    if bnb_config:
        model_kwargs["quantization_config"] = bnb_config
        model_kwargs["device_map"] = "auto"

    model = AutoModelForCausalLM.from_pretrained(cfg.base_model, **model_kwargs)
    model.config.use_cache = False
    model.config.pretraining_tp = 1

    # ⚡ Apply torchao INT8 quantization for CPU speedup (2-4x faster)
    try:
        from torchao.quantization import quantize_, int8_dynamic_activation_int8_weight

        quantize_(model, int8_dynamic_activation_int8_weight())
        logger.info("⚡ Applied torchao INT8 dynamic quantization")
    except Exception as e:
        logger.info(f"torchao INT8 not applied (CPU only mode): {e}")

    # ⚡ torch.compile with inductor backend for graph optimization
    try:
        model = torch.compile(model, backend="inductor", mode="max-autotune")
        logger.info("⚡ Applied torch.compile(inductor) for CPU graph optimization")
    except Exception as e:
        logger.info(f"torch.compile not available: {e}")

    n_params = sum(p.numel() for p in model.parameters()) / 1e9
    logger.info(f"Model loaded: {n_params:.1f}B parameters")

    # ── LORA ───────────────────────────────────────────────────────────────
    target_modules = ["q_proj", "v_proj", "k_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
    actual_modules = []
    for name, _ in model.named_modules():
        for target in target_modules:
            if name.endswith(target) and target not in actual_modules:
                actual_modules.append(target)

    if not actual_modules:
        actual_modules = ["c_attn", "c_proj"]  # GPT-2 fallback

    peft_config = LoraConfig(
        r=cfg.lora_rank,
        lora_alpha=cfg.lora_alpha or 16,
        target_modules=actual_modules,
        lora_dropout=cfg.lora_dropout,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters()

    # ── TRAINING ARGUMENTS ─────────────────────────────────────────────────
    output_dir = str(Path(cfg.checkpoint_dir) / f"forge_{time.strftime('%Y%m%d_%H%M')}")
    max_steps = 2 if test_mode else -1

    # For CPU: use 1 epoch for first real run (tunable later)
    num_epochs = 1 if not torch.cuda.is_available() and not test_mode else (cfg.num_epochs or 1)

    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=num_epochs,
        max_steps=max_steps,
        per_device_train_batch_size=hw["batch"],
        per_device_eval_batch_size=max(1, hw["batch"] // 2),
        gradient_accumulation_steps=hw["accum"],
        optim="paged_adamw_8bit" if torch.cuda.is_available() else "adamw_torch",
        save_steps=500,
        logging_steps=10,
        eval_steps=500,
        learning_rate=cfg.learning_rate,
        weight_decay=cfg.weight_decay,
        fp16=(hw["dtype"] == "fp16"),
        bf16=(hw["dtype"] == "bf16"),
        max_grad_norm=0.3,
        warmup_ratio=cfg.warmup_ratio,
        lr_scheduler_type="cosine",
        eval_strategy="steps",
        save_strategy="steps",
        save_total_limit=2,
        load_best_model_at_end=not test_mode,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        gradient_checkpointing=True,
        report_to="none",
        ddp_find_unused_parameters=False if torch.cuda.device_count() > 1 else None,
        dataloader_num_workers=0,  # 0 to avoid multiprocessing issues on Windows
        remove_unused_columns=True,  # Safe now — only tokenized columns remain
    )

    # ── TRAINER (using standard Trainer, not SFTTrainer, for pre-tokenized data) ──
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_data,
        eval_dataset=eval_data,
        data_collator=default_data_collator,
    )

    # ── RESUME FROM CHECKPOINT ─────────────────────────────────────────────
    last_checkpoint = None
    checkpoint_dir = Path(output_dir)
    if checkpoint_dir.exists():
        checkpoints = sorted(checkpoint_dir.glob("checkpoint-*"))
        if checkpoints:
            last_checkpoint = str(checkpoints[-1])
            logger.info(f"Resuming from: {last_checkpoint}")

    # ── START TRAINING ─────────────────────────────────────────────────────
    effective_batch = hw["batch"] * hw["accum"]
    total_steps = (len(train_data) // effective_batch) * num_epochs
    logger.info(f"""
{"=" * 60}
TRAINING START
  Model:      {cfg.base_model}
  Train rows: {len(train_data):,}
  Eval rows:  {len(eval_data):,}
  Epochs:     {num_epochs}
  Batch:      {hw["batch"]} × {hw["accum"]} = {effective_batch} effective
  Est steps:  {total_steps:,}
  Precision:  {hw["dtype"]}
  4-bit:      {hw["use_4bit"]}
  Seq len:    {max_length}
  LoRA rank:  {cfg.lora_rank}
  Output:     {output_dir}
{"=" * 60}
""")

    trainer.train(resume_from_checkpoint=last_checkpoint)

    # ── SAVE ───────────────────────────────────────────────────────────────
    final_dir = Path(cfg.final_model_dir)
    final_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Saving final model to: {final_dir}")

    trainer.save_model(str(final_dir))
    tokenizer.save_pretrained(str(final_dir))

    # Save metrics
    metrics = trainer.state.log_history
    train_losses = [m.get("loss") for m in metrics if "loss" in m]
    final_loss = train_losses[-1] if train_losses else None
    eval_losses = [m.get("eval_loss") for m in metrics if "eval_loss" in m]
    final_eval_loss = eval_losses[-1] if eval_losses else None

    summary = {
        "train_loss": final_loss,
        "eval_loss": final_eval_loss,
        "total_steps": trainer.state.global_step,
        "epoch": trainer.state.epoch if hasattr(trainer.state, "epoch") else None,
        "base_model": cfg.base_model,
        "lora_rank": cfg.lora_rank,
        "batch_size": hw["batch"],
        "grad_accum": hw["accum"],
        "max_length": max_length,
        "num_epochs": num_epochs,
        "learning_rate": cfg.learning_rate,
        "train_records": len(train_data),
        "eval_records": len(eval_data),
        "hardware": {"tier": cfg.hardware_profile.get("tier", "unknown")},
    }
    (final_dir / "training_metrics.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    logger.success(f"""
{"=" * 60}
TRAINING COMPLETE
  Final train loss: {final_loss or "N/A"}
  Final eval loss:  {final_eval_loss or "N/A"}
  Total steps:      {trainer.state.global_step:,}
  Model saved:      {final_dir}
{"=" * 60}
""")

    return final_dir


def run_training(cfg: ForgeConfig, test_mode: bool = False, use_unsloth: bool = False):
    """Entry point for training."""
    engine = "⚡ Unsloth" if use_unsloth else "Standard"
    console.print(f"\n[bold cyan]═══ PHASE 5: MODEL TRAINING [b]{engine}[/b] ═══[/bold cyan]")

    if test_mode:
        console.print("[yellow]Running in TEST MODE (2 steps, 10 examples)[/yellow]")

    try:
        if use_unsloth and _HAS_UNSLOTH:
            model_path = train_with_unsloth(cfg, test_mode=test_mode)
        elif use_unsloth and not _HAS_UNSLOTH:
            console.print("[yellow]Unsloth not installed. Falling back to standard training.[/yellow]")
            console.print("  Install: pip install 'unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git'")
            model_path = train(cfg, test_mode=test_mode)
        else:
            model_path = train(cfg, test_mode=test_mode)

        if model_path:
            console.print(f"\n[bold green]Training complete! Model: {model_path}[/bold green]")
            console.print("Run: python forge_step6_evaluate.py")
    except Exception as e:
        console.print(f"\n[bold red]Training failed: {e}[/bold red]")
        import traceback

        console.print(traceback.format_exc())


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Test mode (2 steps)")
    parser.add_argument(
        "--unsloth", action="store_true", help="Use Unsloth for 2x faster training (requires pip install unsloth)"
    )
    args = parser.parse_args()

    cfg = ForgeConfig.load()
    run_training(cfg, test_mode=args.test, use_unsloth=args.unsloth)
