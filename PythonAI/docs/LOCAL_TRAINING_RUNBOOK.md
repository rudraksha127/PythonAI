# Local Training Runbook

This project now has a local-first path for audit, dataset validation, LoRA smoke training, and evaluation.

## What Is Already Present

- `raw_chunks_godmode.json` and `cleaned_chunks.json`: Python documentation chunks.
- `training_dataset.json`: current supervised training pairs.
- `python_brain_godmode/`: local Chroma RAG database.
- `checkpoints/full_pipeline_model/`: previous PEFT LoRA adapter trained from `sshleifer/tiny-gpt2`.
- Ollama model detected locally: `qwen2.5-coder:14b`.

## Important Model Boundary

`qwen2.5-coder:14b` in Ollama is a local inference model, not an HF-format training checkpoint. Use it for RAG answers and evaluation probes.

For PEFT/LoRA fine-tuning, use an HF-format model id or folder such as:

```powershell
.\.venv\Scripts\python.exe forge_run_all.py --test   # Quick test pipeline (2 steps)
```

If no CUDA GPU is available, the runner automatically falls back to a CPU-safe smoke model so the pipeline can still be verified.

## Step By Step

0. Check the whole project from one entrypoint:

```powershell
.\.venv\Scripts\python.exe scripts/python_ai.py status
```

1. Audit project, inspect dataset, detect models, and train a safe local adapter:

```powershell
.\.venv\Scripts\python.exe forge_run_all.py --test   # Quick test pipeline (2 training steps)
```

2. Evaluate the saved adapter:

```powershell
.\.venv\Scripts\python.exe forge_step6_evaluate.py  # Benchmark evaluation
```

3. Probe local Ollama Qwen:

```powershell
.\.venv\Scripts\python.exe forge_audit.py          # Audit hardware + project
```

4. Use local Qwen/Ollama to generate additional grounded supervised rows:

```powershell
.\.venv\Scripts\python.exe scripts/python_ai.py augment --dry-run
.\.venv\Scripts\python.exe scripts/python_ai.py augment --limit 1 --output training_dataset_ollama_sample.json
.\.venv\Scripts\python.exe scripts/python_ai.py merge --add training_dataset_ollama_sample.json --output training_dataset_augmented.json
.\.venv\Scripts\python.exe scripts/python_ai.py augment --limit 5 --pairs-per-chunk 1 --merge --output training_dataset_augmented.json
```

5. If you have an HF-format Qwen folder, point the trainer at it:

```powershell
$env:QWEN_MODEL_PATH="C:\path\to\hf-qwen-model"
.\.venv\Scripts\python.exe forge_step5_train.py     # Full training
```

## Outputs

- `checkpoints/local_training_plan.json`: audit, dataset profile, hardware, detected models, and selected base model.
- `checkpoints/local_auto_model/`: latest local PEFT adapter from the runner.
- `checkpoints/local_eval_outputs.json`: fixed-prompt evaluation outputs.
- `training_dataset_ollama_sample.json` or `training_dataset_augmented.json`: optional local-Qwen generated rows.

## Notes

- AirLLM is wired as an inference probe through `scripts/local_qwen_probe.py`; it is not used as the trainer.
- Current machine reports no CUDA GPU, so real Qwen LoRA training will be very slow locally unless CUDA becomes available.
- If Ollama reports that Qwen 14B needs more system memory than is available, retry with `--num-ctx 512` or close memory-heavy apps before probing.
- The trainer now keeps response tokens trainable even when prompts are long, avoiding all-masked labels and `nan` evaluation loss.
