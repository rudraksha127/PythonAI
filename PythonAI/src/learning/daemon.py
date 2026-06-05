"""
Autonomous Learning Daemon for PythonAI OMNISCIENT
Runs periodically to collect new data, ingest it, and evaluate performance.

Usage:
    python -m src.learning.daemon --interval 24
"""

import time
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

def run_cmd(cmd: list[str]) -> bool:
    """Run a command and print output."""
    print(f"\n[{time.strftime('%H:%M:%S')}] RUNNING: {' '.join(cmd)}")
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), check=True)
        return proc.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="PythonAI Learning Daemon")
    parser.add_argument("--interval", type=int, default=24, help="Interval in hours (default: 24)")
    args = parser.parse_args()

    python_exe = sys.executable

    print("=" * 60)
    print(f"  🤖 PythonAI OMNISCIENT - Autonomous Learning Daemon")
    print(f"  Interval: Every {args.interval} hours")
    print("=" * 60)

    try:
        while True:
            print(f"\n[DAEMON] Starting learning cycle at {time.strftime('%Y-%m-%d %H:%M:%S')}")

            # 1. Collect Data to D: Drive
            run_cmd([python_exe, "-m", "src.data.d_drive_collector", "--all", "--so-pages", "2", "--github-pages", "1"])

            # 2. Ingest New Data into God Mode DB
            run_cmd([python_exe, "-m", "src.data.ingestor"])

            print(f"\n[DAEMON] Cycle complete. Sleeping for {args.interval} hours...")
            time.sleep(args.interval * 3600)

    except KeyboardInterrupt:
        print("\n[DAEMON] Stopped by user.")

if __name__ == "__main__":
    main()
