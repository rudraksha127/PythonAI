"""
Git Analyzer — extracts code changes from git diffs for review.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GitChange:
    """A single changed file from a git diff."""

    file_path: str
    old_path: str | None = None
    change_type: str = "modified"  # added, modified, deleted, renamed
    diff_content: str = ""
    language: str = "unknown"
    additions: int = 0
    deletions: int = 0
    old_content: str = ""
    new_content: str = ""


# Language extension map (shared across methods)
_EXT_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".php": "php",
    ".sql": "sql",
    ".md": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".vue": "vue",
    ".svelte": "svelte",
}


class GitAnalyzer:
    """Analyzes git repositories to extract code changes for review."""

    def __init__(self, repo_path: str | Path | None = None):
        self.repo_path = Path(repo_path).resolve() if repo_path else None

    def get_diff(
        self,
        commit_range: str | None = None,
        staged: bool = False,
        base_ref: str | None = None,
        head_ref: str | None = None,
    ) -> list[GitChange]:
        """Get changes from a git diff.

        Args:
            commit_range: e.g. "abc123..def456" or "HEAD~3..HEAD"
            staged: If True, show staged changes (--cached)
            base_ref: Base git ref for comparison
            head_ref: Head git ref for comparison

        Returns:
            List of GitChange objects
        """
        cmd = ["git", "diff"]

        if staged:
            cmd.append("--cached")

        if commit_range:
            cmd.append(commit_range)
        elif base_ref and head_ref:
            cmd.append(f"{base_ref}..{head_ref}")

        if not commit_range and not (base_ref and head_ref) and not staged:
            cmd.append("HEAD")

        # Add unified context for better review
        cmd.extend(["-U5", "--no-color"])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.repo_path,
                timeout=30,
            )
            diff_output = result.stdout
        except subprocess.TimeoutExpired:
            return [GitChange(file_path="", diff_content="Error: git diff timed out")]
        except FileNotFoundError:
            return [GitChange(file_path="", diff_content="Error: git not found")]
        except Exception as e:
            return [GitChange(file_path="", diff_content=f"Error: {e}")]

        return self._parse_diff(diff_output)

    def get_uncommitted_changes(self) -> list[GitChange]:
        """Get all uncommitted changes (both staged and unstaged)."""
        changes = []

        # Staged changes
        staged = self.get_diff(staged=True)
        changes.extend(staged)

        # Unstaged changes
        unstaged = self.get_diff(commit_range="")
        changes.extend(unstaged)

        # Remove duplicates (same file can be both staged and unstaged)
        seen: set[str] = set()
        unique: list[GitChange] = []
        for c in changes:
            if c.file_path not in seen:
                seen.add(c.file_path)
                unique.append(c)
            elif c.diff_content:
                # Merge diff content from duplicate
                for u in unique:
                    if u.file_path == c.file_path:
                        u.diff_content += c.diff_content
                        u.additions += c.additions
                        u.deletions += c.deletions
                        break

        return unique

    def get_file_content(self, file_path: str | Path, ref: str = "HEAD") -> str:
        """Get file content from a specific git ref."""
        try:
            result = subprocess.run(
                ["git", "show", f"{ref}:{file_path}"],
                capture_output=True,
                text=True,
                cwd=self.repo_path,
                timeout=15,
            )
            return result.stdout
        except Exception:
            return ""

    def _parse_diff(self, diff_output: str) -> list[GitChange]:
        """Parse git diff output into structured changes."""
        changes: list[GitChange] = []
        current_file: GitChange | None = None
        current_lines: list[str] = []

        for line in diff_output.split("\n"):
            if line.startswith("diff --git"):
                # Save previous file
                if current_file and current_lines:
                    current_file.diff_content = "\n".join(current_lines)
                    changes.append(current_file)

                # Parse new file header
                parts = line.split()
                old_path = parts[2].lstrip("a/") if len(parts) > 2 else ""
                new_path = parts[3].lstrip("b/") if len(parts) > 3 else ""
                file_path = new_path or old_path
                ext = Path(file_path).suffix.lower()
                language = EXT_MAP.get(ext, "unknown")

                current_file = GitChange(
                    file_path=file_path,
                    old_path=old_path if old_path != new_path else None,
                    change_type="modified",
                    language=language,
                )
                current_lines = []

            elif line.startswith("new file mode"):
                if current_file:
                    current_file.change_type = "added"

            elif line.startswith("deleted file mode"):
                if current_file:
                    current_file.change_type = "deleted"

            elif line.startswith("rename from"):
                if current_file:
                    current_file.change_type = "renamed"

            elif line.startswith("@@") and current_file:
                # Parse hunk header for additions/deletions
                parts = line.split()
                for part in parts:
                    if part.startswith("+"):
                        try:
                            count = part.lstrip("+").split(",")[0]
                            current_file.additions += int(count) if count else 0
                        except ValueError:
                            pass
                    elif part.startswith("-"):
                        try:
                            count = part.lstrip("-").split(",")[0]
                            current_file.deletions += int(count) if count else 0
                        except ValueError:
                            pass
                current_lines.append(line)

            elif current_file is not None:
                current_lines.append(line)

        # Save last file
        if current_file and current_lines:
            current_file.diff_content = "\n".join(current_lines)
            changes.append(current_file)

        return changes

    def get_new_content(self, change: GitChange) -> str:
        """Extract new (post-change) content from a diff."""
        if change.change_type == "deleted":
            return ""

        if change.change_type == "added":
            # For new files, the diff contains only additions
            lines = []
            for line in change.diff_content.split("\n"):
                if line.startswith("+") and not line.startswith("+++"):
                    lines.append(line[1:])
            return "\n".join(lines)

        # For modified files, extract lines starting with ' ' (unchanged) or '+' (added)
        lines = []
        in_hunk = False
        for line in change.diff_content.split("\n"):
            if line.startswith("@@"):
                in_hunk = True
                continue
            if not in_hunk:
                continue
            if line.startswith("+") and not line.startswith("+++"):
                lines.append(line[1:])
            elif line.startswith(" "):
                lines.append(line[1:])

        return "\n".join(lines)

    def get_changed_line_numbers(self, change: GitChange) -> list[int]:
        """Extract line numbers of changed (added/modified) lines."""
        changed_lines: list[int] = []
        current_line = 0

        for line in change.diff_content.split("\n"):
            if line.startswith("@@"):
                # Extract new file line number: @@ -old,count +new,count @@
                match = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
                if match:
                    current_line = int(match.group(1))
                continue

            if line.startswith("---") or line.startswith("+++"):
                continue

            if line.startswith("+") and not line.startswith("+++"):
                changed_lines.append(current_line)
                current_line += 1
            elif line.startswith(" "):
                current_line += 1
            elif line.startswith("-"):
                continue  # Deleted line, no new content

        return changed_lines

    def get_changed_files(self) -> list[str]:
        """List currently changed (uncommitted) files."""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                capture_output=True,
                text=True,
                cwd=self.repo_path,
                timeout=15,
            )
            staged = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                capture_output=True,
                text=True,
                cwd=self.repo_path,
                timeout=15,
            )
            files = set()
            for f in result.stdout.strip().split("\n"):
                if f.strip():
                    files.add(f.strip())
            for f in staged.stdout.strip().split("\n"):
                if f.strip():
                    files.add(f.strip())
            return sorted(files)
        except Exception:
            return []

    @staticmethod
    def detect_language(file_path: str) -> str:
        """Detect programming language from file extension."""
        ext = Path(file_path).suffix.lower()
        return _EXT_MAP.get(ext, "unknown")
