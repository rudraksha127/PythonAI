from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from src.utils.models import (
    ROOT,
    audit_project,
    choose_training_base,
    cleanup_dry_run,
    dataset_profile,
    discover_qwen_hf_candidates,
    hardware_profile,
    list_hf_cached_models,
    list_ollama_models,
    project_python,
    save_json,
)


def print_section(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def find_latest_checkpoint(output_dir: Path) -> str | None:
    """Auto-discover the latest checkpoint in output directory."""
    if not output_dir.exists():
        return None
    checkpoints = sorted(output_dir.glob("checkpoint-*"))
    return str(checkpoints[-1]) if checkpoints else None


def run_training(args: argparse.Namespace, base_model: str, python_exe: Path) -> None:
    command = [
        str(python_exe),
        "-m", "src.training.trainer",
        "--base-model", base_model,
        "--source-files", str(ROOT / args.dataset_path),
        "--output-dir", str(ROOT / args.output_dir),
        "--max-examples", str(args.max_examples),
        "--max-steps", str(args.max_steps),
        "--max-length", str(args.max_length),
        "--batch-size", str(args.batch_size),
        "--grad-accum", str(args.grad_accum),
        "--learning-rate", str(args.learning_rate),
        "--save-steps", str(args.save_steps),
        "--eval-steps", str(args.eval_steps),
    ]

    if args.gradient_checkpointing:
        command.append("--gradient-checkpointing")
    else:
        command.append("--no-gradient-checkpointing")

    # New flags
    if args.wandb:
        command.append("--wandb")
    if args.early_stopping_patience > 0:
        command.extend(["--early-stopping-patience", str(args.early_stopping_patience)])
    if args.lr_scheduler_type:
        command.extend(["--lr-scheduler-type", args.lr_scheduler_type])
    if args.save_training_curves:
        command.append("--save-training-curves")
    if args.viz:
        command.append("--viz")
    if args.load_in_4bit:
        command.append("--load-in-4bit")
    if args.gradient_clip:
        command.extend(["--gradient-clip", str(args.gradient_clip)])

    # Auto-resume: find latest checkpoint
    resume_from = args.resume_from_checkpoint
    if args.auto_resume and not resume_from:
        auto_ckpt = find_latest_checkpoint(ROOT / args.output_dir)
        if auto_ckpt:
            resume_from = auto_ckpt
            print(f"Auto-resume detected: {resume_from}")

    if resume_from:
        command.extend(["--resume-from-checkpoint", resume_from])

    if args.dataset_version:
        command.extend(["--dataset-version", args.dataset_version])

    print_section("Training Command")
    print(" ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Local-first audit, dataset check, and model training runner."
    )
    parser.add_argument("--mode", choices=["auto", "smoke", "qwen"], default="auto")
    parser.add_argument("--output-dir", default="checkpoints/local_auto_model")
    parser.add_argument("--dataset-path", default="data/training/training_dataset.json")
    parser.add_argument("--max-examples", type=int, default=128)
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--max-length", type=int, default=384)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=5e-5)
    parser.add_argument("--save-steps", type=int, default=4)
    parser.add_argument("--eval-steps", type=int, default=4)
    parser.add_argument(
        "--gradient-checkpointing",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument("--resume-from-checkpoint", default="")
    parser.add_argument("--skip-train", action="store_true")

    # New training enhancements
    parser.add_argument("--wandb", action="store_true", help="Log metrics to Weights & Biases")
    parser.add_argument("--early-stopping-patience", type=int, default=0,
                        help="Early stopping patience (0 = disabled)")
    parser.add_argument("--lr-scheduler-type", choices=["cosine", "linear", "constant"], default=None,
                        help="Learning rate scheduler type")
    parser.add_argument("--save-training-curves", action="store_true",
                        help="Save basic loss curves plot to output directory")
    parser.add_argument("--viz", action="store_true",
                        help="Save comprehensive training visualization (dashboard, LR, throughput, HTML, JSON)")
    parser.add_argument("--auto-resume", action="store_true",
                        help="Auto-find and resume from latest checkpoint")
    parser.add_argument("--load-in-4bit", action="store_true",
                        help="Enable 4-bit QLoRA quantization")
    parser.add_argument("--gradient-clip", type=float, default=0.0,
                        help="Gradient clipping max norm (0 = disabled)")
    parser.add_argument("--dataset-version", default="",
                        help="Label to tag output checkpoints with")
    parser.add_argument("--test-mode", action="store_true",
                        help="Run a quick validation (2 steps, 4 examples)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    python_exe = project_python()

    if args.test_mode:
        args.max_steps = 2
        args.max_examples = 4
        print("[Test mode] Overriding: --max-steps 2 --max-examples 4")

    print_section("Project Audit")
    audit = audit_project()
    cleanup = cleanup_dry_run()
    print(f"Files       : {audit['total_files']}")
    print(f"Size        : {audit['total_mb']} MB (excluding .venv/.git)")
    print(f"Cleanup dry : {cleanup['candidate_count']} candidates, {cleanup['recoverable_mb']} MB")

    print_section("Dataset")
    profile = dataset_profile()
    print(f"Rows        : {profile['rows']}")
    print(f"Keys        : {', '.join(profile['keys'])}")
    print(f"Length avg  : {profile['length_avg']} chars")
    print(f"Top cats    : {profile['categories_top'][:5]}")

    print_section("Local Models")
    hardware = hardware_profile(python_exe)
    ollama_models = list_ollama_models()
    hf_models = list_hf_cached_models()
    qwen_candidates = discover_qwen_hf_candidates()
    base_model, reason = choose_training_base(args.mode, hardware, qwen_candidates)
    print(f"Python      : {python_exe}")
    print(f"CUDA        : {hardware.get('cuda_available')} ({hardware.get('gpu_name')})")
    print(f"Ollama      : {ollama_models or 'none detected'}")
    print(f"HF cache    : {hf_models or 'none detected'}")
    print(f"Qwen HF     : {qwen_candidates or 'none detected'}")
    print(f"Train base  : {base_model}")
    print(f"Reason      : {reason}")

    run_report = {
        "audit": audit,
        "cleanup_dry_run": cleanup,
        "dataset": profile,
        "hardware": hardware,
        "ollama_models": ollama_models,
        "hf_cached_models": hf_models,
        "qwen_hf_candidates": qwen_candidates,
        "selected_base_model": base_model,
        "selection_reason": reason,
        "output_dir": args.output_dir,
        "dataset_path": args.dataset_path,
        "wandb": args.wandb,
        "early_stopping": args.early_stopping_patience,
        "lr_scheduler": args.lr_scheduler_type,
        "dataset_version": args.dataset_version,
        "test_mode": args.test_mode,
    }
    save_json(ROOT / "checkpoints" / "local_training_plan.json", run_report)
    print("\nWrote checkpoints/local_training_plan.json")

    # Auto-enable 4-bit + gradient checkpointing for Qwen 14B on CPU
    if args.mode == "qwen" and not hardware.get("cuda_available"):
        args.load_in_4bit = True
        args.gradient_checkpointing = True
        print("[Qwen 14B CPU mode] Auto-enabled: --load-in-4bit --gradient-checkpointing")

    if args.skip_train:
        print("Training skipped by --skip-train.")
        return

    run_training(args, base_model, python_exe)


if __name__ == "__main__":
    main()
