from __future__ import annotations

import argparse
import sys
import time
from rich.console import Console

from forge_config import ForgeConfig
import forge_audit
import forge_step1_collect
import forge_step2_process
import forge_step3_synthetic
import forge_step4_assemble
import forge_step5_train
import forge_step6_evaluate
import forge_step7_deploy

console = Console()

def print_header():
    console.print(r"""[bold cyan]
  ___ ___  ___  ___ ___    ___  __  __ ___ ___   _   
 | __/ _ \| _ \/ __| __|  / _ \|  \/  | __/ __| /_\  
 | _| (_) |   / (_ | _|  | (_) | |\/| | _| (_ |/ _ \ 
 |_| \___/|_|_\\___|___|  \___/|_|  |_|___\___/_/ \_\
                                                     
    End-to-End Autonomous AI Training Pipeline
[/bold cyan]""")

def run_all(cfg: ForgeConfig, args: argparse.Namespace):
    start_time = time.time()
    
    # Checkpoint mechanism
    phase = args.start_phase
    
    if phase <= 0:
        forge_audit.scan_project(cfg)
        
    if phase <= 1 and not args.skip_collect:
        forge_step1_collect.run_collection(cfg)
        
    if phase <= 2 and not args.skip_process:
        forge_step2_process.run_processing(cfg)
        
    if phase <= 3 and not args.skip_synthetic:
        forge_step3_synthetic.run_synthetic_gen(cfg, target_count=args.synthetic_count)
        
    if phase <= 4 and not args.skip_assemble:
        forge_step4_assemble.run_assemble(cfg)
        
    if phase <= 5 and not args.skip_train:
        forge_step5_train.run_training(cfg, test_mode=args.test_mode)
        
    if phase <= 6 and not args.skip_evaluate:
        forge_step6_evaluate.run_evaluation(cfg)
        
    if phase <= 7 and not args.skip_deploy:
        forge_step7_deploy.run_server()
        
    elapsed = time.time() - start_time
    console.print(f"\n[bold green]FORGE-OMEGA Pipeline Complete![/bold green] (Time: {elapsed/60:.1f}m)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FORGE-OMEGA Pipeline")
    parser.add_argument("--start-phase", type=int, default=0, help="Phase to start from (0-7)")
    parser.add_argument("--skip-collect", action="store_true", help="Skip Phase 1 (Collection)")
    parser.add_argument("--skip-process", action="store_true", help="Skip Phase 2 (Processing)")
    parser.add_argument("--skip-synthetic", action="store_true", help="Skip Phase 3 (Synthetic Data)")
    parser.add_argument("--skip-assemble", action="store_true", help="Skip Phase 4 (Assembly)")
    parser.add_argument("--skip-train", action="store_true", help="Skip Phase 5 (Training)")
    parser.add_argument("--skip-evaluate", action="store_true", help="Skip Phase 6 (Evaluation)")
    parser.add_argument("--skip-deploy", action="store_true", help="Skip Phase 7 (Deployment)")
    parser.add_argument("--synthetic-count", type=int, default=100, help="Number of synthetic examples to generate")
    parser.add_argument("--test-mode", action="store_true", help="Run training in test mode (fast)")
    
    args = parser.parse_args()
    
    print_header()
    
    # Initialize and save configuration
    cfg = ForgeConfig()
    cfg.save()
    
    run_all(cfg, args)
