# 🧠 Training Pipeline — PEFT/LoRA Fine-Tuning

## Overview

Fine-tune causal language models locally using PEFT (Parameter-Efficient Fine-Tuning) with LoRA adapters. Supports auto hardware detection — trains on GPU if available, falls back to CPU-safe models.

```
dataset → training_run.py → trainer.py (PEFT/LoRA) → adapter checkpoints
                                                          ↓
                                                  evaluator.py → outputs.json
```

---

## 📝 Prompt to Continue (Training Pipeline Enhancements)

```
Copy-paste into Codebuff to continue:

Enhance the training pipeline. Here's what I need:

### 1. Training Runner (src/training/run.py)
- Add --wandb flag to log metrics to Weights & Biases
- Add --early-stopping with patience parameter
- Add --lr-scheduler-type (cosine, linear, constant)
- Save training curves plot (loss vs steps) after training
- Add --resume flag that auto-finds latest checkpoint

### 2. Trainer (src/training/trainer.py)
- Support DeepSpeed ZeRO-2/3 for large model training
- Add gradient clipping option
- Support 4-bit QLoRA (quantized LoRA) via bitsandbytes
- Add dataset preprocessing caching to avoid re-tokenizing
- Print per-step token throughput (tokens/sec)

### 3. Evaluator (src/training/evaluator.py)
- Add --num-prompts to specify how many test prompts to run
- Add BLEU/ROUGE score computation against reference outputs
- Support batch evaluation (multiple prompts at once)
- Save generated outputs alongside reference outputs for comparison
- Add --interactive flag to type prompts and see real-time output

### 4. Full Pipeline (src/training/pipeline.py)
- Add --skip-collection and --skip-generation flags for granular control
- Support configurable base model for different runs
- Add pipeline timing report (how long each stage took)
- Add --dataset-version label to tag output checkpoints

### 5. New Features
- Add model export: convert PEFT adapter to standalone merged model
- Add ONNX export option for faster inference
- Add --test-mode that runs 2 steps with 4 examples for quick validation
```

---

## 🧩 Training Components

| Module | File | Purpose |
|--------|------|---------|
| Runner | `src/training/run.py` | Audit + dataset check + launch training |
| Trainer | `src/training/trainer.py` | PEFT/LoRA fine-tuning with HF Transformers |
| Pipeline | `src/training/pipeline.py` | End-to-end: collect → clean → generate → train |
| Evaluator | `src/training/evaluator.py` | Test saved adapters with fixed prompts |

## 🚀 Commands

```powershell
# Full audit + train (auto-detect hardware)
python -m src.cli train --mode auto --max-steps 8

# Smoke test (tiny model, quick validation)
python -m src.cli train --mode smoke --max-steps 4

# Full pipeline: collect → clean → train
python -m src.training.pipeline --max-examples 256

# Evaluate a trained adapter
python -m src.cli eval --adapter-path checkpoints/local_auto_model

# Train directly
python -m src.training.run --mode auto --max-steps 8
```

## 📍 Checkpoints

| Directory | Description |
|-----------|-------------|
| `checkpoints/local_auto_model/` | Auto-detected hardware training output |
| `checkpoints/full_pipeline_model/` | Full pipeline training output |
| `checkpoints/augmented_smoke_model/` | Augmented dataset smoke test |

---

## ✅ Status

[ ] Not started  
[ ] In progress  
[ ] Completed  
