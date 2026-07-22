"""Two-phase smoke test runner.

Phase 1 -- Mock-based tests: runs all existing pytest tests.
Phase 2 -- Real Ollama RAG query: runs the RAG engine with --question and --no-exec.

Usage:
    python tests/run_smoke_rag.py [-h] [--skip-pytest] [--skip-rag]
                                   [--timeout 300] [--question "..."]

Exit code: 0 if all phases pass, 1 if any phase fails.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Ensure the project root is on sys.path so src.* imports work
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _get_python_exe() -> str:
    """Return the project's Python executable path (lazy import to avoid startup issues)."""
    from src.utils.models import project_python

    return str(project_python())


# -----------------------------------------------------------------------
# Phase 1 -- existing pytest tests
# -----------------------------------------------------------------------


def phase_pytest(verbose: bool = False) -> dict[str, object]:
    """Run all existing pytest tests and return a summary dict."""
    python = _get_python_exe()

    cmd = [python, "-m", "pytest", "tests/", "-v"]
    start = time.time()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    result = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=120,
    )

    elapsed = time.time() - start
    output = (result.stdout or "") + (result.stderr or "")

    # Parse output for summary counts
    passed = failed = skipped = 0
    tested_files: set[str] = set()
    for line in output.splitlines():
        if "::" in line and ("PASSED" in line or "FAILED" in line or "SKIPPED" in line):
            parts = line.split("::")
            if len(parts) >= 2:
                test_file = parts[0].strip()
                if test_file.endswith(".py"):
                    tested_files.add(test_file)
        # Parse summary line like "63 passed, 1 failed in 12.34s" or "63 passed in 12.34s"
        if " passed" in line:
            m = re.search(r"(\d+) passed", line)
            if m:
                passed = int(m.group(1))
            m = re.search(r"(\d+) failed", line)
            if m:
                failed = int(m.group(1))
            m = re.search(r"(\d+) skipped", line)
            if m:
                skipped = int(m.group(1))

    success = result.returncode == 0

    summary: dict[str, object] = {
        "success": success,
        "returncode": result.returncode,
        "elapsed_s": round(elapsed, 2),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "test_files": sorted(tested_files),
        "output": output if verbose else "",
    }
    return summary


# -----------------------------------------------------------------------
# Phase 2 -- Real RAG engine with Ollama
# -----------------------------------------------------------------------


def phase_rag(
    question: str,
    timeout: int = 300,
    verbose: bool = False,
) -> dict[str, object]:
    """Run the RAG engine with --question --no-exec and a real Ollama call."""
    python_bin = _get_python_exe()
    cmd = [
        python_bin,
        "-m",
        "src.rag.rag_engine",
        "--question",
        question,
        "--no-exec",
    ]

    start = time.time()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    try:
        result = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        return {
            "success": False,
            "elapsed_s": round(elapsed, 2),
            "error": f"Timed out after {timeout}s",
            "output": "",
        }

    elapsed = time.time() - start
    output = (result.stdout or "") + (result.stderr or "")

    # Validate output
    checks = {
        "db_loaded": "[GOD MODE" in output or "Loading" in output or "GOD MODE DB" in output,
        "ollama_responded": "PYTHON MASTER" in output or "---" in output,
        "has_answer_text": len(output.strip()) > 500,
        "no_exceptions": "Traceback" not in output,
        "sources_shown": "[1]" in output or "Sources" in output,
    }

    # Extract answer snippet for display
    answer_snippet = ""
    if "PYTHON MASTER" in output:
        idx = output.index("PYTHON MASTER")
        answer_snippet = output[idx : idx + 300].replace("\n", " ")

    success = result.returncode == 0 and checks["ollama_responded"] and checks.get("no_exceptions", True)

    summary: dict[str, object] = {
        "success": success,
        "returncode": result.returncode,
        "elapsed_s": round(elapsed, 2),
        "checks": checks,
        "answer_snippet": answer_snippet,
        "error": "",
        "output": output if verbose else "",
    }

    # If something went wrong, capture error details
    if not success:
        error_lines = []
        for check, ok in checks.items():
            if not ok:
                error_lines.append(f"  [FAIL] Check '{check}' failed")
        if result.stderr:
            error_lines.append(f"  stderr: {result.stderr.strip()[:300]}")
        summary["error"] = "\n".join(error_lines) if error_lines else "Unknown error"

    return summary


# -----------------------------------------------------------------------
# Main runner
# -----------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Two-phase smoke test runner: pytest + real Ollama RAG query.",
    )
    parser.add_argument("--skip-pytest", action="store_true", help="Skip Phase 1 (pytest)")
    parser.add_argument("--skip-rag", action="store_true", help="Skip Phase 2 (RAG query)")
    parser.add_argument(
        "--timeout", type=int, default=300, help="Timeout in seconds for the Ollama RAG query (default: 300)"
    )
    parser.add_argument(
        "--question",
        default="What is the difference between a list and a tuple in Python?",
        help="Question to ask the RAG engine (default: difference between list and tuple)",
    )
    parser.add_argument("--verbose", action="store_true", help="Show full output from each phase")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    any_failed = False

    # Reconfigure stdout to UTF-8 so Unicode from the RAG engine can be printed
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass

    print()
    print("=" * 60)
    print("   PYTHONAI COMPREHENSIVE SMOKE TEST RUNNER")
    print("   Phase 1: pytest (mock-based, no services needed)")
    print("   Phase 2: RAG engine (real Ollama query)")
    print("=" * 60)
    print()

    # ---- Phase 1: pytest ------------------------------------------
    if args.skip_pytest:
        print("  [SKIP] Phase 1 (pytest) SKIPPED")
        print()
    else:
        print("  [Phase 1] Running all pytest tests...")
        print(f"  {'-' * 55}")
        pytest_result = phase_pytest(verbose=args.verbose)

        p = pytest_result
        if p["success"]:
            print(f"  [PASS] Phase 1 PASSED  ({p['elapsed_s']:.1f}s)")
        else:
            any_failed = True
            print(f"  [FAIL] Phase 1 FAILED  ({p['elapsed_s']:.1f}s)")
            print(f"      Return code: {p['returncode']}")

        print(f"      Tests passed: {p['passed']}  |  failed: {p['failed']}  |  skipped: {p['skipped']}")
        print(f"      Test files: {', '.join(p['test_files'][:10])}")
        if len(p["test_files"]) > 10:
            print(f"      ... and {len(p['test_files']) - 10} more")
        if args.verbose and p.get("output"):
            print(f"\n{p['output'][:2000]}")
        print()

    # ---- Phase 2: RAG engine ---------------------------------------
    if args.skip_rag:
        print("  [SKIP] Phase 2 (RAG query) SKIPPED")
        print()
    else:
        print("  [Phase 2] Running RAG engine with real Ollama query...")
        print(f'      Question: "{args.question}"')
        print(f"      Timeout:  {args.timeout}s")
        print(f"  {'-' * 55}")
        print("  (This may take a while -- the 14B model loads and generates...)")
        print()
        sys.stdout.flush()

        rag_result = phase_rag(
            question=args.question,
            timeout=args.timeout,
            verbose=args.verbose,
        )

        r = rag_result
        if r["success"]:
            print(f"\n  [PASS] Phase 2 PASSED  ({r['elapsed_s']:.1f}s)")
        else:
            any_failed = True
            print(f"\n  [FAIL] Phase 2 FAILED  ({r['elapsed_s']:.1f}s)")
            if r.get("error"):
                print(f"      {r['error']}")

        # Show check results
        checks = r.get("checks", {})
        if checks:
            print("      Checks:")
            for check_name, ok in checks.items():
                print(f"        {'[OK]' if ok else '[--]'}  {check_name}")

        # Show answer snippet (if available) -- sanitize non-ASCII chars for safety
        snippet = r.get("answer_snippet", "")
        if snippet:
            safe_snippet = snippet[:200].encode("ascii", errors="replace").decode("ascii")
            print(f"\n      [Answer preview] {safe_snippet}...")

        if args.verbose and r.get("output"):
            print(f"\n{r['output'][:2000]}")

        # If returncode was nonzero, show stderr
        if not r["success"] and r.get("returncode", 0) != 0:
            if r.get("output"):
                stderr_section = r["output"].split("Traceback")
                if len(stderr_section) > 1:
                    print(f"\n      [stderr] Traceback{stderr_section[1][:400]}")

        print()

    # ---- Summary ---------------------------------------------------
    print("=" * 60)
    if any_failed:
        print("  [FAIL] SMOKE TEST FAILED -- see details above")
    else:
        print("  [PASS] ALL SMOKE TESTS PASSED")
    print("=" * 60)
    print()

    return 1 if any_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
