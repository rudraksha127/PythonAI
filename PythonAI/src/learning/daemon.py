"""
Autonomous Learning Daemon for PythonAI OMNISCIENT
Runs periodically to collect new data, ingest it, and evaluate performance.

Usage:
    python -m src.learning.daemon --interval 24
"""

import argparse
import subprocess
import sys
import time
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
    print("  🤖 PythonAI OMNISCIENT - Autonomous Learning Daemon")
    print(f"  Interval: Every {args.interval} hours")
    print("=" * 60)

    try:
        while True:
            print(f"\n[DAEMON] Starting learning cycle at {time.strftime('%Y-%m-%d %H:%M:%S')}")

            # 1. Collect Data to D: Drive
            run_cmd([python_exe, "-m", "src.data.d_drive_collector", "--all", "--so-pages", "2", "--github-pages", "1"])

            # 2. Ingest New Data into God Mode DB
            run_cmd([python_exe, "-m", "src.data.ingestor"])

            # 3. Check for new Python Documentation
            print("\n[DAEMON] Checking for Python documentation updates...")
            run_cmd([python_exe, "-c", "from src.learning.doc_watcher import watch_docs; print(watch_docs())"])

            # 4. Sync Advanced StackOverflow Tags
            print("\n[DAEMON] Syncing trending StackOverflow Q&A...")
            run_cmd(
                [
                    python_exe,
                    "-c",
                    "from src.learning.so_sync import sync_stackoverflow; print(sync_stackoverflow(pages=1))",
                ]
            )

            # 5. Run RAG Self-Evaluation
            print("\n[DAEMON] Running RAG Self-Evaluation...")
            run_cmd(
                [
                    python_exe,
                    "-c",
                    "from src.learning.self_eval import run_self_evaluation; print(run_self_evaluation(sample_size=10))",
                ]
            )

            # 6. Extract developer signals from CaptureEngine
            print("\n[DAEMON] Extracting developer signals from CaptureEngine...")
            run_cmd(
                [
                    python_exe,
                    "-c",
                    "from src.learning.capture_engine import CaptureEngine; "
                    "engine = CaptureEngine(); "
                    "stats = engine.get_statistics(); "
                    "print(f'Signals: {stats}'); "
                    "accepts = stats.get('signals_by_type', {}).get('accept', 0); "
                    "rejects = stats.get('signals_by_type', {}).get('reject', 0); "
                    "rate = stats.get('overall_acceptance_rate', 0); "
                    "print(f'[DAEMON] Signal status: {accepts + rejects} total ({accepts}A / {rejects}R), acceptance rate: {rate:.1f}%')",
                ]
            )

            # 7. Trigger training if enough signals are available
            print("\n[DAEMON] Checking training readiness...")
            run_cmd(
                [
                    python_exe,
                    "-c",
                    "from src.learning.capture_engine import CaptureEngine; "
                    "import urllib.request; import json; "
                    "engine = CaptureEngine(); "
                    "stats = engine.get_statistics(); "
                    "total = sum(stats.get('signals_by_type', {}).values()); "
                    "print(f'[DAEMON] Total signals collected: {total}'); "
                    "if total >= 10: "
                    "    try: "
                    "        req = urllib.request.Request( "
                    "            'http://localhost:7337/api/training/trigger', "
                    "            method='POST', "
                    "            data=b'{}', "
                    "            headers={'Content-Type': 'application/json'} "
                    "        ); "
                    "        with urllib.request.urlopen(req, timeout=10) as resp: "
                    "            result = json.loads(resp.read()); "
                    "            print(f'[DAEMON] Training triggered: {result}') "
                    "    except Exception as e: "
                    "        print(f'[DAEMON] Training trigger failed (server may not be running): {e}'); "
                    "        print(f'[DAEMON] To trigger manually: curl -X POST http://localhost:7337/api/training/trigger') "
                    "else: "
                    "    print(f'[DAEMON] Not enough signals ({total}/10) to trigger training yet')",
                ]
            )

            print(f"\n[DAEMON] Cycle complete. Sleeping for {args.interval} hours...")
            time.sleep(args.interval * 3600)

    except KeyboardInterrupt:
        print("\n[DAEMON] Stopped by user.")


if __name__ == "__main__":
    main()
