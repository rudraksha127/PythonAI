# MODULE M5 — TRAINING PIPELINE (KAGGLE)
## Paste this entire file into Anti-Gravity as the task, but run the actual
## training itself on Kaggle, not the Windows laptop — see environment section.

<role>
You are the engineering agent responsible for producing a genuinely
fine-tuned model from the project's training pipeline. This is module 5 of
13. Modules 2 (data) and 4 (signals) must already be complete — this module
consumes their output, it does not produce its own data.
</role>

<mission_context>
This is where the project's actual differentiation lives: a model that has
learned from this specific codebase's patterns and this specific developer's
accept/reject history, not a generic base model. Everything before this
module builds the ingredients; this module is where they actually get used.
</mission_context>

<verified_facts>
`PythonAI/src/training/run.py` exists with a confirmed, exact CLI:
`--mode` (choices: `auto`, `smoke`, `qwen`, default `auto`),
`--output-dir` (default `checkpoints/local_auto_model`),
`--dataset-path` (default `data/training/training_dataset.json`),
`--max-examples` (default 128), `--max-steps` (default 8),
`--max-length` (default 384), `--batch-size` (default 1),
`--grad-accum` (default 4), `--learning-rate` (default 5e-5),
`--save-steps` (default 4), `--eval-steps` (default 4),
`--resume-from-checkpoint`, `--skip-train`, and `--wandb`.

The training base model is `Qwen/Qwen2.5-Coder-7B-Instruct` per
`src/config.py` — confirm this is still accurate before assuming otherwise.

Sibling files confirmed present: `trainer.py` (core training logic),
`grpo_trainer.py` (alignment from real accept/reject signals),
`sdft_trainer.py` (continual learning across batches without forgetting
earlier training), `seal_meta_learner.py`, `seal_inner_loop.py`,
`phase3_seal.py` (self-generated harder training examples),
`checkpoint_manager.py`, `evaluator.py`, `comparison.py`, and
`indra_benchmark.py`. Read each briefly before assuming its role from the
name alone — several of these implement specific published techniques
(SEAL, GRPO, SDFT) and should be used as intended rather than reinvented.
</verified_facts>

<environment>
The Windows 11 laptop has no dedicated GPU and 16GB of RAM — genuine
fine-tuning of a 7B model is not realistic on it. Use `run.py --mode smoke`
locally only as a wiring check (small step count, quick to fail loudly if
something is broken), then move actual training to Kaggle's free GPU tier
(two T4 GPUs, roughly 30 hours per week). Treat the local run purely as a
"does the pipeline even execute" check, not a real training run.
</environment>

<task>
1. Run `run.py --mode smoke` locally on Windows with a small `--max-steps`
   value, purely to confirm the pipeline executes without error end to end.
   Do not treat its output as a usable model.
2. Prepare a Kaggle notebook that clones the repository, installs
   dependencies, and runs `run.py --mode qwen` against module 2's real
   final dataset, with the sibling training files (SDFT, GRPO) wired in as
   they're designed to be used, not skipped.
3. After supervised fine-tuning completes, run the GRPO alignment step
   using real signal data exported by module 4's `export_for_training`.
4. Export the resulting adapter and bring it back to the Windows machine.
5. Register the fine-tuned model with Ollama and confirm it runs and
   responds to a basic prompt.
6. Run `evaluator.py` or `comparison.py` (whichever is the intended
   entrypoint — check both) to compare the fine-tuned model against the
   unmodified base model on a fixed set of questions, and report the result
   honestly, including if the fine-tuned model does not yet win.
</task>

<constraints>
Use the existing SEAL, GRPO, and SDFT implementations as designed. Do not
write a simplified custom training loop that bypasses them — they exist
specifically to prevent catastrophic forgetting and to align the model to
real usage signal, and skipping them would silently remove those properties.
</constraints>

<reasoning_process>
Before running a full Kaggle training job, re-confirm the smoke test result
was genuinely clean, not just "didn't crash" — check that loss actually
decreased over the smoke run's few steps, since a flat or NaN loss there
will waste a full Kaggle GPU session if it goes unnoticed.
</reasoning_process>

<success_criteria>
- Local smoke test completes without error and shows decreasing loss
- Kaggle training run completes and produces a downloadable adapter
- GRPO alignment step runs against real (not synthetic) exported signal data
- Fine-tuned model registered in Ollama and responds to a test prompt
- Comparison against the base model is reported honestly, win or not
</success_criteria>

<output_format>
Report back in exactly this shape:
DONE: [what was completed]
METRIC: [smoke test loss trend — Kaggle steps run — comparison result]
BLOCKED: [exact blocker, or "none"]
NEXT: [first concrete action for module M10, which automates this]
</output_format>

<if_blocked>
If Kaggle's free GPU quota is exhausted mid-run, checkpoint what exists,
report exactly how far training got, and do not represent a partial
checkpoint as a finished fine-tuned model.
</if_blocked>
