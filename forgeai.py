#!/usr/bin/env python3
"""
ForgeAI — Master Orchestration Script
======================================

Single entry point for all ForgeAI operations across the ecosystem.

Usage:
    python forgeai.py capture stats          # View capture statistics
    python forgeai.py rag index ./src        # Index codebase with cAST
    python forgeai.py train --sdft           # Train with SDFT
    python forgeai.py train --grpo           # Train with GRPO
    python forgeai.py agent "fix the bug"    # Run agent
    python forgeai.py dashboard              # Start dashboard
    python forgeai.py config show            # Show configuration
    python forgeai.py config init            # Initialize config

Research Foundation: MIT SEAL · cAST · GRPO · SDFT · Unsloth · vLLM
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def cmd_capture(args):
    """Capture engine commands."""
    from src.learning.capture_engine import CaptureEngine
    
    engine = CaptureEngine()
    
    if args.action == "stats":
        stats = engine.get_statistics()
        print(json.dumps(stats, indent=2))
    elif args.action == "export":
        count = engine.export_for_training(args.output, args.format)
        print(f"Exported {count} training examples to {args.output}")
    elif args.action == "rate":
        rates = engine.get_acceptance_rate(args.days)
        for r in rates:
            print(f"{r['date']}: {r['acceptance_rate']:.1f}% ({r['accepts']}A/{r['rejects']}R/{r['edits']}E)")


def cmd_rag(args):
    """RAG engine commands."""
    from src.rag.cast_chunker import CastChunker
    
    chunker = CastChunker()
    
    if args.action == "index":
        path = Path(args.path)
        if path.is_file():
            chunks = chunker.chunk_file(path)
        elif path.is_dir():
            chunks = chunker.chunk_directory(path)
        else:
            print(f"Error: {path} not found")
            sys.exit(1)
        
        if args.output:
            import json
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            with open(args.output, "w") as f:
                json.dump([c.to_dict() for c in chunks], f, indent=2)
            print(f"Wrote {len(chunks)} chunks to {args.output}")
        else:
            for chunk in chunks:
                print(f"[{chunk.chunk_type}] {chunk.name} ({chunk.token_count} tokens)")
            print(f"\nTotal: {len(chunks)} chunks")


def cmd_train(args):
    """Training commands."""
    from src.config import get_config
    
    config = get_config()
    
    if args.sdft:
        print("Starting SDFT training...")
        from src.training.sdft_trainer import SDFTTrainer
        
        trainer = SDFTTrainer(
            model_name=config.training.base_model,
            lora_rank=config.training.lora_rank,
            learning_rate=config.training.learning_rate,
        )
        
        # Load training data
        if args.data:
            import json
            examples = []
            with open(args.data) as f:
                for line in f:
                    if line.strip():
                        try:
                            examples.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            print(f"Loaded {len(examples)} training examples")
        else:
            print("No training data specified. Use --data <file>")
            sys.exit(1)
        
        # Load replay buffers
        if args.replay:
            trainer.replay_buffer.load_from_disk(
                args.replay,
                args.foundational or (Path(args.replay).parent / "foundational.jsonl"),
            )
        
        metrics = trainer.train(
            current_examples=[],  # Would need TrainingExample conversion
            output_dir=args.output or "checkpoints/forge_model",
            num_epochs=args.epochs,
            batch_size=config.training.batch_size,
        )
        
        print(json.dumps(metrics, indent=2))
    
    elif args.grpo:
        print("Starting GRPO training...")
        from src.training.grpo_trainer import GRPOTrainer, GRPOPair
        
        trainer = GRPOTrainer(
            model_name=args.model or config.training.base_model,
            lora_rank=config.training.lora_rank,
            learning_rate=config.training.grpo_learning_rate,
            kl_coef=config.training.grpo_kl_coef,
        )
        
        if args.data:
            import json
            pairs = []
            with open(args.data) as f:
                for line in f:
                    if line.strip():
                        try:
                            data = json.loads(line)
                            pairs.append(GRPOPair.from_dict(data))
                        except (json.JSONDecodeError, KeyError):
                            pass
            print(f"Loaded {len(pairs)} GRPO pairs")
            
            metrics = trainer.train(
                pairs=pairs,
                output_dir=args.output or "checkpoints/forge_grpo",
                num_epochs=args.epochs,
                batch_size=config.training.batch_size,
            )
            print(json.dumps(metrics, indent=2))
        else:
            print("No training data specified. Use --data <pairs.jsonl>")
            sys.exit(1)


def cmd_agent(args):
    """Agent commands."""
    print(f"Agent mode: {args.task}")
    print("Connecting to Hermes-Agent...")
    
    try:
        from src.integration.hermes_bridge import call_hermes_agent
        result = call_hermes_agent(args.task)
        print(json.dumps(result, indent=2))
    except ImportError:
        print("Warning: hermes-agent not installed")
        print("Install with: pip install -e hermes-agent-main")


def cmd_config(args):
    """Configuration commands."""
    from src.config import ForgeAIConfig, get_config
    
    if args.action == "show":
        config = get_config()
        print(json.dumps(config.to_dict(), indent=2))
    elif args.action == "init":
        config = ForgeAIConfig()
        config.save()
        print(f"Configuration saved to ~/.forgeai/config.json")
        print(json.dumps(config.to_dict(), indent=2))
    elif args.action == "paths":
        config = get_config()
        print("ForgeAI Paths:")
        print(f"  Models: {config.expand_path(config.paths.models_dir)}")
        print(f"  Data: {config.expand_path(config.paths.data_dir)}")
        print(f"  Signals DB: {config.expand_path(config.capture.db_path)}")
        print(f"  Logs: {config.expand_path(config.paths.logs_dir)}")


def cmd_dashboard(args):
    """Dashboard commands."""
    print("Starting ForgeAI Dashboard...")
    print("Opening web interface at http://localhost:8501")
    
    try:
        from src.webui.app import run_dashboard
        run_dashboard()
    except ImportError:
        print("Dashboard not available. Install streamlit: pip install streamlit")


def main():
    parser = argparse.ArgumentParser(
        description="ForgeAI — Self-Improving Developer AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s capture stats                    # View capture statistics
  %(prog)s rag index ./src --output chunks.json
  %(prog)s train --sdft --data training.jsonl --replay replay.jsonl
  %(prog)s train --grpo --data pairs.jsonl
  %(prog)s agent "fix the authentication bug"
  %(prog)s config show
  %(prog)s config init

Research: MIT SEAL · cAST (EMNLP 2025) · GRPO (DeepSeek 2025) · SDFT (MIT 2026)
        """,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Capture command
    capture_parser = subparsers.add_parser("capture", help="Capture engine commands")
    capture_parser.add_argument("action", choices=["stats", "export", "rate"], help="Action")
    capture_parser.add_argument("--output", "-o", help="Output file")
    capture_parser.add_argument("--format", default="jsonl", choices=["jsonl", "json"])
    capture_parser.add_argument("--days", type=int, default=7)
    capture_parser.set_defaults(func=cmd_capture)
    
    # RAG command
    rag_parser = subparsers.add_parser("rag", help="RAG engine commands")
    rag_parser.add_argument("action", choices=["index", "search"], help="Action")
    rag_parser.add_argument("path", nargs="?", help="File or directory to index")
    rag_parser.add_argument("--output", "-o", help="Output file")
    rag_parser.set_defaults(func=cmd_rag)
    
    # Train command
    train_parser = subparsers.add_parser("train", help="Training commands")
    train_parser.add_argument("--sdft", action="store_true", help="Use SDFT training")
    train_parser.add_argument("--grpo", action="store_true", help="Use GRPO training")
    train_parser.add_argument("--data", help="Training data file (JSONL)")
    train_parser.add_argument("--replay", help="Replay buffer file")
    train_parser.add_argument("--foundational", help="Foundational examples file")
    train_parser.add_argument("--output", help="Output directory")
    train_parser.add_argument("--model", help="Base model")
    train_parser.add_argument("--epochs", type=int, default=1)
    train_parser.set_defaults(func=cmd_train)
    
    # Agent command
    agent_parser = subparsers.add_parser("agent", help="Run AI agent")
    agent_parser.add_argument("task", help="Task description")
    agent_parser.set_defaults(func=cmd_agent)
    
    # Config command
    config_parser = subparsers.add_parser("config", help="Configuration commands")
    config_parser.add_argument("action", choices=["show", "init", "paths"], help="Action")
    config_parser.set_defaults(func=cmd_config)
    
    # Dashboard command
    dashboard_parser = subparsers.add_parser("dashboard", help="Start dashboard")
    dashboard_parser.set_defaults(func=cmd_dashboard)
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(0)
    
    args.func(args)


if __name__ == "__main__":
    main()