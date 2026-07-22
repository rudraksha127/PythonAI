"""
ForgeAI Git Hook Integration — Auto-Capture Signals from Git Events
====================================================================

Installs git hooks that automatically capture training signals from:
  - post-commit: Capture accepted code after each commit
  - post-merge: Capture PR merges as high-confidence positive signals
  - post-checkout: Capture branch context changes

Usage:
    from src.learning.git_hooks import install_hooks, capture_post_commit

    install_hooks("/path/to/repo")
    capture_post_commit("/path/to/repo")
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("forgeai.git_hooks")


# ═══════════════════════════════════════
# Hook Script Templates
# ═══════════════════════════════════════

_POST_COMMIT_HOOK = """#!/bin/sh
# ForgeAI — Post-Commit Hook
# Captures accepted code as a training signal after each commit.

FORGEAI_HOOKS=$(which forgeai 2>/dev/null)
if [ -z "$FORGEAI_HOOKS" ]; then
    FORGEAI_HOOKS="python3"
fi

# Run capture in background (don't block git)
nohup $FORGEAI_HOOKS -c "
import sys, json, subprocess, os
sys.path.insert(0, os.path.expanduser('~/.forgeai'))
# Check if server is running
import urllib.request
try:
    req = urllib.request.Request('http://localhost:7337/api/capture/git-hook')
    req.add_header('Content-Type', 'application/json')

    # Get git info
    diff = subprocess.run(['git', 'diff', 'HEAD~1..HEAD', '--name-only'], capture_output=True, text=True)
    sha = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True)
    branch = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], capture_output=True, text=True)

    files = diff.stdout.strip().split('\\\\n') if diff.stdout.strip() else []
    for f in files[:5]:
        data = json.dumps({{
            'event_type': 'accept',
            'file_path': f,
            'language': f.split('.')[-1] if '.' in f else 'unknown',
            'code_content': '',
            'git_sha': sha.stdout.strip(),
            'branch': branch.stdout.strip(),
        }}).encode()
        urllib.request.urlopen(req, data=data, timeout=3)
except Exception:
    pass
" > /dev/null 2>&1 &
exit 0
"""

_POST_MERGE_HOOK = """#!/bin/sh
# ForgeAI — Post-Merge Hook
# Captures PR merges as high-confidence positive signals.

FORGEAI_HOOKS=$(which forgeai 2>/dev/null)
if [ -z "$FORGEAI_HOOKS" ]; then
    FORGEAI_HOOKS="python3"
fi

nohup $FORGEAI_HOOKS -c "
import sys, json, subprocess, os, urllib.request
try:
    req = urllib.request.Request('http://localhost:7337/api/capture/git-hook')
    req.add_header('Content-Type', 'application/json')

    sha = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True)
    branch = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], capture_output=True, text=True)
    diff = subprocess.run(['git', 'diff', 'HEAD~1..HEAD', '--name-only'], capture_output=True, text=True)
    files = diff.stdout.strip().split('\\\\n') if diff.stdout.strip() else []

    for f in files[:5]:
        data = json.dumps({{
            'event_type': 'pr_merge',
            'file_path': f,
            'language': f.split('.')[-1] if '.' in f else 'unknown',
            'code_content': '',
            'pr_number': 0,
            'branch': branch.stdout.strip(),
            'git_sha': sha.stdout.strip(),
        }}).encode()
        urllib.request.urlopen(req, data=data, timeout=3)
except Exception:
    pass
" > /dev/null 2>&1 &
exit 0
"""


# ═══════════════════════════════════════
# Hook Management
# ═══════════════════════════════════════


def install_hooks(repo_path: str | Path) -> dict[str, Any]:
    """Install ForgeAI git hooks into a repository.

    Creates post-commit and post-merge hooks that auto-capture
    training signals.

    Args:
        repo_path: Path to git repository

    Returns:
        Dict with installation results
    """
    repo_path = Path(repo_path)
    hooks_dir = repo_path / ".git" / "hooks"

    if not hooks_dir.exists():
        return {
            "success": False,
            "error": f"Not a git repository: {repo_path}",
            "installed": [],
        }

    hooks = {
        "post-commit": _POST_COMMIT_HOOK,
        "post-merge": _POST_MERGE_HOOK,
    }

    installed = []
    for hook_name, hook_script in hooks.items():
        hook_path = hooks_dir / hook_name

        # Backup existing hook if present
        if hook_path.exists() and not hook_path.read_text().startswith("# ForgeAI"):
            backup = hook_path.with_suffix(f".bak.{int(time.time())}")
            hook_path.rename(backup)
            logger.info(f"Backed up existing hook: {backup}")

        hook_path.write_text(hook_script)
        hook_path.chmod(0o755)  # Make executable
        installed.append(hook_name)
        logger.info(f"Installed {hook_name} hook in {repo_path}")

    return {
        "success": True,
        "repo_path": str(repo_path),
        "installed": installed,
        "count": len(installed),
    }


def uninstall_hooks(repo_path: str | Path) -> dict[str, Any]:
    """Remove ForgeAI git hooks from a repository.

    Restores any backed-up original hooks.

    Args:
        repo_path: Path to git repository

    Returns:
        Dict with uninstallation results
    """
    repo_path = Path(repo_path)
    hooks_dir = repo_path / ".git" / "hooks"

    if not hooks_dir.exists():
        return {
            "success": False,
            "error": f"Not a git repository: {repo_path}",
            "removed": [],
        }

    removed = []
    for hook_name in ["post-commit", "post-merge"]:
        hook_path = hooks_dir / hook_name

        if not hook_path.exists():
            continue

        if hook_path.read_text().startswith("# ForgeAI"):
            # Check for backup
            backups = sorted(hooks_dir.glob(f"{hook_name}.bak.*"))
            if backups:
                backups[-1].rename(hook_path)
                logger.info(f"Restored backup: {backups[-1]}")
            else:
                hook_path.unlink()
            removed.append(hook_name)
            logger.info(f"Removed {hook_name} hook")

    return {
        "success": True,
        "repo_path": str(repo_path),
        "removed": removed,
        "count": len(removed),
    }


def list_hooks(repo_path: str | Path) -> list[dict[str, Any]]:
    """List git hooks and their ForgeAI status.

    Args:
        repo_path: Path to git repository

    Returns:
        List of hook info dicts
    """
    repo_path = Path(repo_path)
    hooks_dir = repo_path / ".git" / "hooks"

    results = []
    if not hooks_dir.exists():
        return results

    for hook_name in ["post-commit", "post-merge", "pre-commit", "prepare-commit-msg"]:
        hook_path = hooks_dir / hook_name
        if hook_path.exists():
            content = hook_path.read_text()
            results.append({
                "name": hook_name,
                "forgeai": content.startswith("# ForgeAI"),
                "path": str(hook_path),
                "size": hook_path.stat().st_size,
            })

    return results


def capture_post_commit(repo_path: str | Path) -> dict[str, Any] | None:
    """Capture a post-commit signal from the last commit.

    Returns the signal data that would be sent to the server,
    or None if there's nothing to capture.

    This can be called from a post-commit hook.
    """
    repo_path = Path(repo_path)
    if not (repo_path / ".git").exists():
        return None

    try:
        # Get last commit info
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=str(repo_path),
        ).stdout.strip()

        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=str(repo_path),
        ).stdout.strip()

        # Get changed files
        diff = subprocess.run(
            ["git", "diff", "HEAD~1..HEAD", "--name-only"],
            capture_output=True, text=True, cwd=str(repo_path),
        )
        files = [f.strip() for f in diff.stdout.split("\n") if f.strip()]

        if not files:
            return None

        # Get diff content for the first file
        first_file = files[0]
        content = subprocess.run(
            ["git", "show", f"HEAD:{first_file}"],
            capture_output=True, text=True, cwd=str(repo_path),
        ).stdout[:5000]  # Limit size

        return {
            "event_type": "pr_merge" if "merge" in branch.lower() else "accept",
            "file_path": first_file,
            "language": first_file.split(".")[-1] if "." in first_file else "unknown",
            "code_content": content,
            "git_sha": sha,
            "branch": branch,
        }
    except Exception as e:
        logger.debug(f"Failed to capture post-commit signal: {e}")
        return None


def compute_signal_weight(
    signal_type: str,
    edit_distance: float = 0.0,
    context_length: int = 0,
    test_passed: bool | None = None,
) -> float:
    """Compute the weight of a training signal based on quality factors.

    Signal weights determine how much influence a signal has during training.

    Args:
        signal_type: Type of signal (accept, reject, edit, etc.)
        edit_distance: Normalized edit distance (0-1) for edit signals
        context_length: Length of context provided with the signal
        test_passed: Whether the signal was verified by tests

    Returns:
        Weight multiplier (0.0 to 3.0)
    """
    base_weights = {
        "accept": 1.0,
        "reject": -0.5,
        "edit": 0.7,
        "test_pass": 2.0,
        "test_fail": -1.0,
        "pr_merge": 1.5,
        "implicit_accept": 0.3,
    }

    weight = base_weights.get(signal_type, 0.5)

    # Edit distance boost: closer to original = higher weight
    if signal_type == "edit" and edit_distance > 0:
        weight += (1.0 - edit_distance) * 0.3

    # Context length boost: more context = higher confidence
    if context_length > 100:
        weight += min(context_length / 10000, 0.2)

    # Test verification boost
    if test_passed is True:
        weight += 1.0
    elif test_passed is False:
        weight -= 0.5

    return round(max(0.0, weight), 2)


__all__ = [
    "install_hooks",
    "uninstall_hooks",
    "list_hooks",
    "capture_post_commit",
    "compute_signal_weight",
]
