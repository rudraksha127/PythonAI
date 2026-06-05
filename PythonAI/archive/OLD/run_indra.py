"""
INDRA Master Orchestrator
=========================
Single entry point for the entire INDRA pipeline.
"""

import argparse
import sys
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def run_collection():
    logger.info("Starting Phase 1 Data Collection...")
    subprocess.run([sys.executable, "-m", "src.data.phase1_orchestrator"], check=True)

def run_format():
    logger.info("Starting Data Formatting...")
    subprocess.run([sys.executable, "-m", "src.data.indra_data_formatter"], check=True)

def run_synthetic():
    logger.info("Starting Synthetic Data Generation...")
    subprocess.run([sys.executable, "-m", "src.data.indra_synthetic_generator"], check=True)

def run_train(demo: bool = False):
    logger.info("Starting INDRA Fine-Tuning...")
    cmd = [
        sys.executable, "-m", "src.training.trainer", 
        "--use-indra-prompt",
        "--source-files", "data/training/formatted/indra_training_base.jsonl"
    ]
    
    if demo:
        cmd.extend([
            "--base-model", "sshleifer/tiny-gpt2",
            "--test-mode",
            "--output-dir", "checkpoints/indra_demo"
        ])
    else:
        # We would ideally load the mistral config here, but for brevity:
        cmd.extend([
            "--base-model", "mistralai/Mistral-7B-v0.3",
            "--load-in-4bit",
            "--output-dir", "checkpoints/indra_mistral_7b",
            "--max-steps", "50"
        ])
        
    subprocess.run(cmd, check=True)

def run_evaluate(demo: bool = False):
    logger.info("Starting INDRA Benchmarking...")
    model_path = "checkpoints/indra_demo" if demo else "checkpoints/indra_mistral_7b"
    subprocess.run([sys.executable, "-m", "src.training.indra_benchmark", "--model-path", model_path], check=True)

def run_dashboard():
    logger.info("Starting Dashboard Server...")
    subprocess.run([sys.executable, "-m", "src.webui.indra_dashboard_server"], check=True)

def main():
    parser = argparse.ArgumentParser(description="INDRA Pipeline Orchestrator")
    parser.add_argument("--collect", action="store_true", help="Run data collection")
    parser.add_argument("--format", action="store_true", help="Run data formatting")
    parser.add_argument("--generate-synthetic", action="store_true", help="Generate synthetic data")
    parser.add_argument("--train", action="store_true", help="Run training")
    parser.add_argument("--evaluate", action="store_true", help="Run evaluation")
    parser.add_argument("--dashboard", action="store_true", help="Run dashboard")
    parser.add_argument("--full", action="store_true", help="Run full pipeline")
    parser.add_argument("--demo", action="store_true", help="Run quick demo end-to-end")
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    
    if args.demo:
        logger.info("--- RUNNING INDRA DEMO PIPELINE ---")
        run_format()
        run_train(demo=True)
        run_evaluate(demo=True)
        return

    if args.full:
        run_collection()
        run_format()
        run_synthetic()
        run_train()
        run_evaluate()
        run_dashboard()
        return

    if args.collect: run_collection()
    if args.format: run_format()
    if args.generate_synthetic: run_synthetic()
    if args.train: run_train()
    if args.evaluate: run_evaluate()
    if args.dashboard: run_dashboard()
    
    if not any(vars(args).values()):
        parser.print_help()

if __name__ == "__main__":
    main()
