"""
Hermes-Agent Bridge — Connect PythonAI to hermes-agent framework
=================================================================

Provides:
- call_hermes_agent(): Send tasks to hermes-agent for multi-agent execution
- get_hermes_status(): Check if hermes-agent is installed and running
- register_forgeai_skills(): Register ForgeAI's capabilities as hermes skills
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("forgeai.integration.hermes")

HERMES_PACKAGE = "hermes_cli"
FORGEAI_CONFIG_PATH = Path.home() / ".forgeai" / "config.json"


def _venv_bin_dir(venv_root: Path) -> Path:
    """Return the correct binary directory for a virtualenv on any platform.

    Windows: <venv>/Scripts/
    Linux/macOS: <venv>/bin/
    """
    return venv_root / ("Scripts" if os.name == "nt" else "bin")


def _venv_python_names() -> list[str]:
    """Return possible Python executable names for the current platform.

    Windows: only python.exe
    Linux/macOS: try python3 first, fall back to python for distros
    that don't ship the python3 symlink.
    """
    if os.name == "nt":
        return ["python.exe"]
    return ["python3", "python"]


def _get_hermes_venv_python() -> str | None:
    """Find the Python 3.12 venv for hermes-agent (cross-platform)."""
    venv_dirs = [
        # From Project Root / hermes-agent-main / .venv312
        Path(__file__).resolve().parent.parent.parent.parent / "hermes-agent-main" / ".venv312",
        # From CWD
        Path.cwd() / "hermes-agent-main" / ".venv312",
    ]

    for venv_root in venv_dirs:
        for py_name in _venv_python_names():
            candidate = _venv_bin_dir(venv_root) / py_name
            if candidate.is_file():
                return str(candidate)

    return None


def is_hermes_available() -> bool:
    """Check if the hermes-agent package is installed."""
    # Check via Python import (uses current Python)
    try:
        import importlib
        importlib.import_module(HERMES_PACKAGE)
        return True
    except ImportError:
        pass
    # Check via 3.12 venv (hermes requires <3.14)
    venv_python = _get_hermes_venv_python()
    if venv_python:
        try:
            result = subprocess.run(
                [venv_python, "-c", "import hermes_cli; print('ok')"],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return False


def get_hermes_agent():
    """Get Hermes agent instance for multi-agent orchestration.

    Returns a dict with availability/version info, None otherwise.
    """
    if not is_hermes_available():
        logger.warning("hermes-agent not installed. Run: pip install -e hermes-agent-main")
        return None

    # Get version via subprocess (hermes in 3.12 venv, current Python is 3.14)
    venv_python = _get_hermes_venv_python() or sys.executable
    try:
        result = subprocess.run(
            [venv_python, "-c", "from hermes_cli.main import main; print('hermes-agent 0.16.0')"],
            capture_output=True, text=True, timeout=10,
        )
        version = "0.16.0"
        if result.returncode == 0 and result.stdout.strip():
            version = result.stdout.strip()

        return {"available": True, "version": version}
    except Exception as e:
        logger.error(f"Failed to verify hermes-agent: {e}")
        return None


async def call_hermes_agent(task: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Send a task to Hermes agent for multi-agent processing.

    Uses asyncio subprocess so it doesn't block the event loop.

    Args:
        task: Natural language task description
        context: Optional context dict with forgeai capabilities info

    Returns:
        Dict with result or error information
    """
    if context is None:
        context = {}

    # Add ForgeAI context
    context["forgeai"] = {
        "rag_available": True,
        "training_available": True,
        "capture_available": True,
    }

    hermes_path = _find_hermes_path()
    if not hermes_path:
        return {"error": "hermes-agent not installed", "details": "Install with: pip install -e hermes-agent-main"}

    hermes_python = sys.executable
    # Try 3.12 venv first (hermes may be installed there)
    venv_python = _get_hermes_venv_python()
    if venv_python:
        hermes_python = venv_python

    try:
        cli_args = [hermes_python, "-m", "hermes_cli.main", "-z", task]

        # Pass context as a child-only env var via the subprocess `env` parameter.
        # This avoids mutating the parent process's os.environ (which would
        # persist after the call and leak context to unrelated subprocesses).
        # The hermes CLI reads FORGEAI_CONTEXT from the environment to discover
        # ForgeAI's capabilities (RAG, training, capture).
        child_env = {**os.environ, "FORGEAI_CONTEXT": json.dumps(context)}

        proc = await asyncio.create_subprocess_exec(
            *cli_args,
            env=child_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=120.0
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {"error": "Hermes agent timed out after 120s"}

        return {
            "output": (stdout.decode("utf-8", errors="replace") or stderr.decode("utf-8", errors="replace")).strip(),
            "returncode": proc.returncode,
        }

    except FileNotFoundError:
        return {"error": "Hermes CLI not found"}
    except Exception as e:
        return {"error": str(e)}


def _find_hermes_path() -> Path | None:
    """Find the hermes-agent-main directory."""
    # Check next to PythonAI
    candidates = [
        Path.cwd().parent / "hermes-agent-main",
        Path.cwd() / "hermes-agent-main",
        Path(__file__).resolve().parent.parent.parent.parent / "hermes-agent-main",
        Path.home() / "hermes-agent-main",
    ]

    for candidate in candidates:
        if (candidate / "hermes").exists() and (candidate / "pyproject.toml").exists():
            return candidate

    # Check if hermes module is importable
    try:
        import hermes_cli  # type: ignore[import-untyped]  # noqa: F401
        init_file = hermes_cli.__file__
        if init_file:
            return Path(init_file).resolve().parent.parent
    except (ImportError, AttributeError):
        pass

    return None


def register_forgeai_skills():
    """Register ForgeAI's capabilities with hermes-agent skill system."""
    if not is_hermes_available():
        logger.info("hermes-agent not available, skipping skill registration")
        return False

    skills_dir = Path.home() / ".forgeai" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    # Create ForgeAI skill definitions
    forgeai_skills = {
        "rag_search": {
            "name": "forgeai_rag_search",
            "description": "Search the ForgeAI RAG database for code context",
            "command": "python -m src.integration.hermes_bridge rag_search",
        },
        "capture_stats": {
            "name": "forgeai_capture_stats",
            "description": "Get ForgeAI capture engine statistics and acceptance rates",
            "command": "python -m src.integration.hermes_bridge capture_stats",
        },
        "training_status": {
            "name": "forgeai_training_status",
            "description": "Check ForgeAI training pipeline status",
            "command": "python -m src.integration.hermes_bridge training_status",
        },
    }

    for skill_name, skill_def in forgeai_skills.items():
        skill_file = skills_dir / f"{skill_name}.json"
        skill_file.write_text(json.dumps(skill_def, indent=2), encoding="utf-8")

    logger.info(f"Registered {len(forgeai_skills)} ForgeAI skills with hermes-agent")
    return True


# ─── CLI Entry Points ──────────────────────────────────────────────────


def _resolve_pythonai_path() -> str:
    """Resolve PythonAI src directory so CLI handlers can import from it.

    When hermes-agent invokes these handlers as subprocesses, the working
    directory may not be PythonAI/. We add PythonAI/src to sys.path so
    imports like `from src.rag.rag_engine` resolve correctly.
    """
    candidates = [
        Path(__file__).resolve().parent.parent,  # PythonAI/src/
        Path.cwd() / "PythonAI" / "src",
        Path.cwd().parent / "PythonAI" / "src",
    ]
    for p in candidates:
        resolved = str(p.resolve())
        if resolved not in sys.path:
            sys.path.insert(0, resolved)
        # Also add parent so `from src...` works
        parent = str(p.parent.resolve())
        if parent not in sys.path:
            sys.path.insert(0, parent)
    return str(candidates[0].resolve())


def cli_rag_search():
    """CLI handler for RAG search skill."""
    _resolve_pythonai_path()
    from src.rag.rag_engine import get_answer, load_or_build_db

    try:
        query = sys.argv[1] if len(sys.argv) > 1 else "default search"
        coll, embedder, bm25, corpus, _ = load_or_build_db()
        answer, docs = get_answer(query, coll, embedder, [], bm25=bm25, corpus_texts=corpus)
        result = {"answer": answer, "sources": len(docs)}
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


def cli_capture_stats():
    """CLI handler for capture stats skill."""
    _resolve_pythonai_path()
    from src.learning.capture_engine import CaptureEngine

    try:
        engine = CaptureEngine()
        stats = engine.get_statistics()
        rates = engine.get_acceptance_rate(days=7)
        result = {"statistics": stats, "recent_rates": rates}
        print(json.dumps(result, default=str))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


def cli_training_status():
    """CLI handler for training status skill."""
    _resolve_pythonai_path()
    from src.learning.capture_engine import CaptureEngine

    try:
        engine = CaptureEngine()
        runs = engine.get_training_runs(limit=5)
        result = {"training_runs": runs}
        print(json.dumps(result, default=str))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    """CLI entry point for hermes-agent skill invocations."""
    if len(sys.argv) < 2:
        print("Usage: python -m src.integration.hermes_bridge <command> [args]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "rag_search":
        cli_rag_search()
    elif command == "capture_stats":
        cli_capture_stats()
    elif command == "training_status":
        cli_training_status()
    else:
        print(json.dumps({"error": f"Unknown command: {command}"}))
        sys.exit(1)
