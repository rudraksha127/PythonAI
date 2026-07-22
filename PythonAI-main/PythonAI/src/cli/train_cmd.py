from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.auth.decorators import requires_auth
from src.cli.common import project_python, run


@requires_auth
def train(args: argparse.Namespace) -> int:
    cmd = [
        str(project_python()),
        "-m",
        "src.training.run",
        "--mode",
        args.mode,
        "--max-steps",
        str(args.max_steps),
        "--max-examples",
        str(args.max_examples),
        "--max-length",
        str(args.max_length),
        "--output-dir",
        args.output_dir,
        "--dataset-path",
        args.dataset_path,
    ]
    if getattr(args, "unsloth", False):
        cmd.append("--unsloth")
    if args.skip_train:
        cmd.append("--skip-train")
    return run(cmd)


@requires_auth
def evaluate(args: argparse.Namespace) -> int:
    return run(
        [
            str(project_python()),
            "-m",
            "src.training.evaluator",
            "--adapter-path",
            args.adapter_path,
            "--output-json",
            args.output_json,
        ]
    )


def export_cmd(args: argparse.Namespace) -> int:
    """Export adapter to GGUF / ONNX format."""

    adapter_path = Path(args.adapter_path)
    if not adapter_path.exists():
        print(f"[Error] Adapter path not found: {adapter_path}")
        return 1
    if not (adapter_path / "adapter_config.json").exists():
        print(f"[Error] No adapter_config.json found in {adapter_path}")
        return 1

    print(f"[Export] Exporting adapter from: {adapter_path}")
    print()

    if args.format == "gguf":
        print("  GGUF export guide:")
        print("  1. Merge LoRA weights into base model:")
        print(f"     python -m transformers-cli merge --peft {adapter_path} --output ./merged_model")
        print("  2. Convert to GGUF:")
        print("     git clone https://github.com/ggerganov/llama.cpp")
        print("     python llama.cpp/convert.py ./merged_model --outfile model.gguf")
        print()
        print(f"  Output would be: {adapter_path.parent / (adapter_path.name + '.gguf')}")

    elif args.format == "onnx":
        print("  ONNX export guide:")
        print("  1. Install optimum:")
        print("     pip install optimum[onnxruntime]")
        print("  2. Export:")
        print(f"     optimum-cli export onnx --model {adapter_path} ./onnx_output")
        print()
        print(f"  Output would be: {adapter_path.parent / 'onnx_output'}")

    else:
        print(f"  Unknown format: {args.format}")
        print("  Supported formats: gguf, onnx")
        return 1

    print()
    print("[Tip] For production deployment, consider using:")
    print("  - llama.cpp for GGUF (CPU/GPU inference)")
    print("  - ONNX Runtime for cross-platform deployment")
    print("  - vLLM for high-throughput serving")
    return 0


def grpo_cmd(args: argparse.Namespace) -> int:
    """
    GRPO: Group Relative Policy Optimization training (DeepSeek-R1 2025).

    Trains a policy model using accept/reject pairs with PPO-style clipped
    surrogate objectives and group-relative advantages. No reward model needed.
    """
    if args.action == "train":
        from src.training.grpo_trainer import GRPOPair, GRPOTrainer

        # Load pairs
        pairs_path = Path(args.data)
        if not pairs_path.exists():
            print(f"[Error] GRPO pairs file not found: {pairs_path}")
            return 1

        pairs = []
        with open(pairs_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        data = json.loads(line)
                        pairs.append(GRPOPair.from_dict(data))
                    except json.JSONDecodeError:
                        pass

        print(f"Loaded {len(pairs)} GRPO pairs from {pairs_path}")

        if not pairs:
            print("[Error] No valid GRPO pairs found.")
            return 1

        trainer = GRPOTrainer(
            model_name=args.model,
            lora_rank=args.lora_rank,
            learning_rate=args.lr,
            kl_coef=args.kl_coef,
            epsilon=args.epsilon,
        )

        metrics = trainer.train(
            pairs=pairs,
            output_dir=args.output,
            num_epochs=args.epochs,
            batch_size=args.batch_size,
        )
        print(json.dumps(metrics, indent=2))
        return 0

    elif args.action == "export-pairs":
        """Export GRPO pairs from CaptureEngine DB."""
        from src.learning.capture_engine import CaptureEngine, SignalType
        from src.training.grpo_trainer import create_grpo_pairs_from_signals

        db_path = Path(args.db).expanduser()
        if not db_path.exists():
            print(f"[Error] CaptureEngine DB not found: {db_path}")
            return 1

        engine = CaptureEngine(db_path=db_path)

        accepts = engine.get_signals(signal_type=SignalType.ACCEPT, limit=args.max_pairs)
        rejects = engine.get_signals(signal_type=SignalType.REJECT, limit=args.max_pairs)
        edits = engine.get_signals(signal_type=SignalType.EDIT, limit=args.max_pairs)

        pairs = create_grpo_pairs_from_signals(
            accept_signals=[s.to_dict() for s in accepts],
            reject_signals=[s.to_dict() for s in rejects],
            edit_signals=[s.to_dict() for s in edits],
        )

        output_path = Path(args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            for pair in pairs:
                f.write(json.dumps(pair.to_dict()) + "\n")

        print(f"Exported {len(pairs)} GRPO pairs to {output_path}")
        print(f"  Source: {len(accepts)} accepts, {len(rejects)} rejects, {len(edits)} edits")
        return 0

    elif args.action == "stats":
        """Show training runs with acceptance rate deltas."""
        from datetime import datetime

        from src.learning.capture_engine import CaptureEngine

        db_path = Path(args.db).expanduser()
        if not db_path.exists():
            print(f"[Error] CaptureEngine DB not found: {db_path}")
            print("  Tip: Run 'python -m src.cli train --capture-db <path>' to start recording training runs.")
            return 1

        engine = CaptureEngine(db_path=db_path)
        runs = engine.get_training_runs(limit=args.limit)

        if not runs:
            print(f"[Empty] No training runs found in {db_path}")
            print("  Run 'python -m src.cli train --capture-db <path>' after some signal data is collected.")
            return 0

        if getattr(args, "json", False):
            print(json.dumps(runs, indent=2, default=str))
            return 0

        # Table header
        print("\n[GRPO] Recent Training Runs")
        print(f"{'=' * 80}")
        print(
            f"  {'Run ID':12s} {'Date':14s} {'Model':20s} {'Signals':>8s} {'Loss':>8s} {'Rate Before':>12s} {'Rate After':>11s} {'Change':>6s}"
        )
        print(f"  {'-' * 12} {'-' * 14} {'-' * 20} {'-' * 8} {'-' * 8} {'-' * 12} {'-' * 11} {'-' * 6}")

        for r in runs:
            ts = datetime.fromtimestamp(r["timestamp"]).strftime("%Y-%m-%d %H:%M")
            model = r["model_name"][:18] + ".." if len(r["model_name"]) > 20 else r["model_name"]
            loss = f"{r['train_loss']:.4f}" if r["train_loss"] else "-"
            rate_before = f"{r['acceptance_rate_before']:.1%}"
            rate_after = f"{r['acceptance_rate_after']:.1%}"
            delta = r["acceptance_delta"]
            delta_str = f"{delta:+.1%}"
            delta_indicator = "[+]" if delta > 0 else ("[-]" if delta < 0 else "[=]")

            print(
                f"  {r['run_id'][:10]:12s} {ts:14s} {model:20s} {r['signals_used']:8d} {loss:>8s} {rate_before:>12s} {rate_after:>11s} {delta_indicator} {delta_str:>4s}"
            )

        total_runs = len(runs)
        positive_deltas = sum(1 for r in runs if r["acceptance_delta"] > 0)
        negative_deltas = sum(1 for r in runs if r["acceptance_delta"] < 0)
        print(f"\n  Summary: {total_runs} runs | {positive_deltas} improved [+] | {negative_deltas} regressed [-]")
        print()
        return 0

    elif args.action == "create-pairs":
        """Create GRPO pairs directly from manual inputs (for testing)."""
        from src.training.grpo_trainer import create_grpo_pairs_from_signals

        accept_signals = []
        reject_signals = []
        edit_signals = []

        if args.accepts:
            acc_path = Path(args.accepts)
            if acc_path.exists():
                with open(acc_path, encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            accept_signals.append(json.loads(line))

        if args.rejects:
            rej_path = Path(args.rejects)
            if rej_path.exists():
                with open(rej_path, encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            reject_signals.append(json.loads(line))

        if args.edits:
            edit_path = Path(args.edits)
            if edit_path.exists():
                with open(edit_path, encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            edit_signals.append(json.loads(line))

        pairs = create_grpo_pairs_from_signals(
            accept_signals=accept_signals,
            reject_signals=reject_signals,
            edit_signals=edit_signals,
        )

        output_path = Path(args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            for pair in pairs:
                f.write(json.dumps(pair.to_dict()) + "\n")

        print(
            f"Created {len(pairs)} GRPO pairs from {len(accept_signals)} accepts, {len(reject_signals)} rejects, {len(edit_signals)} edits"
        )
        print(f"Output: {output_path}")
        return 0

    return 1


def training_cmd(args: argparse.Namespace) -> int:
    """Enhanced training pipeline management."""
    from src.training.checkpoint_manager import CheckpointManager, format_meta
    from src.training.config import (
        TrainingConfig,
        production_config,
        quick_config,
        qwen_config,
        smoke_config,
    )

    if args.action == "config":
        """Show / generate / save training configs."""
        if args.preset == "smoke":
            cfg = smoke_config()
        elif args.preset == "quick":
            cfg = quick_config()
        elif args.preset == "qwen":
            cfg = qwen_config()
        elif args.preset == "production":
            cfg = production_config()
        elif args.preset == "custom" and args.config_file:
            cfg = TrainingConfig.from_file(args.config_file)
        else:
            cfg = TrainingConfig()

        if args.save:
            path = cfg.to_json(args.save)
            print(f"[Training] Config saved to: {path}")
            return 0

        if args.json:
            print(json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2))
            return 0

        print("[Training] Configuration Summary")
        print("=" * 50)
        print(cfg.summary)
        if args.all:
            print("\nFull config (JSON):")
            print(json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2))
        return 0

    if args.action == "checkpoints":
        """List / inspect / clean training checkpoints."""
        mgr = CheckpointManager(base_dir=args.checkpoint_dir)

        if args.checkpoint_list:
            checkpoints = mgr.list(
                sort_by=args.sort_by,
                reverse=not args.ascending,
                max_results=args.limit,
                model_filter=args.model_filter,
                tag_filter=args.tag_filter,
            )
            if not checkpoints:
                print("[Checkpoints] No checkpoints found.")
                return 0
            print(f"[Checkpoints] {len(checkpoints)} found")
            print(mgr.compare([c.name for c in checkpoints[:20]]))
            return 0

        if args.checkpoint_show:
            meta = mgr.get(args.checkpoint_show)
            if not meta:
                print(f"[Checkpoints] '{args.checkpoint_show}' not found.")
                return 1
            print("[Checkpoint]")
            print(format_meta(meta))
            return 0

        if args.checkpoint_delete:
            mgr.delete(args.checkpoint_delete)
            return 0

        if args.checkpoint_best:
            best = mgr.find_best(model_filter=args.model_filter)
            if best:
                print("[Best Checkpoint]")
                print(format_meta(best))
            else:
                print("[Checkpoints] No checkpoints with eval loss found.")
            return 0

        if args.checkpoint_clean:
            deleted = mgr.clean(
                keep_best=args.keep_best,
                keep_last=args.keep_last,
                max_age_days=args.max_age,
                dry_run=args.dry_run,
            )
            if not deleted:
                print("[Checkpoints] Nothing to clean.")
            else:
                print(f"[Checkpoints] Cleaned {len(deleted)} checkpoints.")
            return 0

        checkpoints = mgr.list(max_results=20)
        if not checkpoints:
            print("[Checkpoints] No checkpoints found.")
        else:
            print(mgr.compare([c.name for c in checkpoints]))
        return 0

    return 1
