"""
═══════════════════════════════════════════════════════════════
ForgeAI — Arsenal Filesystem Scanner
Scans the physical arsenal/ directory to report all 252+ cloned repos
═══════════════════════════════════════════════════════════════

Provides:
  - scan_arsenal_directory()  → Full inventory of cloned GitHub tools
  - get_arsenal_categories()  → List of all 26 categories
  - get_category_tools()      → Tools within a specific category
  - get_arsenal_stats()       → Summary statistics
"""

from __future__ import annotations

import os
import json
import time
from pathlib import Path
from typing import Any
from dataclasses import dataclass, asdict

import logging

logger = logging.getLogger("forgeai.arsenal_scanner")

# Default arsenal path (relative to project root)
ARSENAL_BASE = Path(__file__).resolve().parent.parent.parent.parent / "arsenal"


@dataclass
class ClonedTool:
    """Represents a cloned tool in the arsenal directory."""
    name: str
    category: str
    category_id: str
    path: str
    has_git: bool
    has_readme: bool
    has_requirements: bool
    has_setup_py: bool
    has_pyproject: bool
    has_dockerfile: bool
    has_package_json: bool
    language: str  # "python", "javascript", "rust", "mixed", "unknown"
    size_mb: float
    file_count: int


def _detect_language(repo_path: Path) -> str:
    """Detect the primary language of a repository."""
    indicators = {
        "python": 0,
        "javascript": 0,
        "typescript": 0,
        "rust": 0,
        "go": 0,
        "cpp": 0,
    }
    
    for item in repo_path.rglob("*"):
        if item.is_file():
            suffix = item.suffix.lower()
            if suffix in (".py", ".pyx", ".pyi"):
                indicators["python"] += 1
            elif suffix in (".js", ".jsx", ".mjs"):
                indicators["javascript"] += 1
            elif suffix in (".ts", ".tsx"):
                indicators["typescript"] += 1
            elif suffix == ".rs":
                indicators["rust"] += 1
            elif suffix == ".go":
                indicators["go"] += 1
            elif suffix in (".cpp", ".cc", ".cxx", ".c", ".h", ".hpp"):
                indicators["cpp"] += 1
    
    if not any(indicators.values()):
        return "unknown"
    
    # Merge typescript into javascript
    indicators["javascript"] += indicators.pop("typescript", 0)
    
    top = max(indicators, key=indicators.get)
    total = sum(indicators.values())
    
    if indicators[top] / max(total, 1) < 0.5 and total > 10:
        return "mixed"
    
    return top


def _count_files(repo_path: Path) -> int:
    """Count files in a repository (excluding .git)."""
    count = 0
    try:
        for item in repo_path.rglob("*"):
            if ".git" not in item.parts and item.is_file():
                count += 1
    except (PermissionError, OSError):
        pass
    return count


def _dir_size_mb(repo_path: Path) -> float:
    """Calculate directory size in MB (excluding .git)."""
    total = 0
    try:
        for item in repo_path.rglob("*"):
            if ".git" not in item.parts and item.is_file():
                try:
                    total += item.stat().st_size
                except (OSError, PermissionError):
                    pass
    except (PermissionError, OSError):
        pass
    return round(total / (1024 * 1024), 2)


def scan_arsenal_directory(base_path: Path | None = None, quick: bool = True) -> dict[str, Any]:
    """
    Scan the arsenal directory and return a full inventory.
    
    Args:
        base_path: Override the default arsenal path
        quick: If True, skip expensive operations (file count, size, language detection)
    
    Returns:
        {
            "base_path": str,
            "total_categories": int,
            "total_tools": int,
            "categories": [
                {
                    "id": "01-ai-foundations",
                    "name": "AI Foundations",
                    "tool_count": int,
                    "tools": [...]
                }
            ],
            "scan_time_ms": float,
            "scan_mode": "quick" | "full"
        }
    """
    base = Path(base_path) if base_path else ARSENAL_BASE
    
    if not base.exists():
        return {
            "base_path": str(base),
            "total_categories": 0,
            "total_tools": 0,
            "categories": [],
            "error": "Arsenal directory not found",
            "scan_time_ms": 0,
            "scan_mode": "quick" if quick else "full",
        }
    
    start = time.time()
    categories = []
    total_tools = 0
    
    # Scan each category directory
    for cat_dir in sorted(base.iterdir()):
        if not cat_dir.is_dir() or cat_dir.name.startswith("."):
            continue
        
        cat_id = cat_dir.name
        # Convert "01-ai-foundations" -> "AI Foundations"
        parts = cat_id.split("-", 1)
        cat_name = parts[1].replace("-", " ").title() if len(parts) > 1 else cat_id.title()
        
        tools = []
        for tool_dir in sorted(cat_dir.iterdir()):
            if not tool_dir.is_dir() or tool_dir.name.startswith("."):
                continue
            
            tool = ClonedTool(
                name=tool_dir.name,
                category=cat_name,
                category_id=cat_id,
                path=str(tool_dir),
                has_git=(tool_dir / ".git").exists(),
                has_readme=any((tool_dir / f).exists() for f in ["README.md", "readme.md", "README.rst"]),
                has_requirements=(tool_dir / "requirements.txt").exists(),
                has_setup_py=(tool_dir / "setup.py").exists(),
                has_pyproject=(tool_dir / "pyproject.toml").exists(),
                has_dockerfile=any((tool_dir / f).exists() for f in ["Dockerfile", "docker-compose.yml"]),
                has_package_json=(tool_dir / "package.json").exists(),
                language=_detect_language(tool_dir) if not quick else "unknown",
                size_mb=_dir_size_mb(tool_dir) if not quick else 0,
                file_count=_count_files(tool_dir) if not quick else 0,
            )
            tools.append(asdict(tool))
            total_tools += 1
        
        categories.append({
            "id": cat_id,
            "name": cat_name,
            "tool_count": len(tools),
            "tools": tools,
        })
    
    elapsed_ms = round((time.time() - start) * 1000, 1)
    
    return {
        "base_path": str(base),
        "total_categories": len(categories),
        "total_tools": total_tools,
        "categories": categories,
        "scan_time_ms": elapsed_ms,
        "scan_mode": "quick" if quick else "full",
    }


def get_arsenal_categories(base_path: Path | None = None) -> list[dict[str, Any]]:
    """Get just the category listing with tool counts."""
    result = scan_arsenal_directory(base_path, quick=True)
    return [
        {"id": c["id"], "name": c["name"], "tool_count": c["tool_count"]}
        for c in result["categories"]
    ]


def get_category_tools(category_id: str, base_path: Path | None = None) -> dict[str, Any] | None:
    """Get tools for a specific category."""
    result = scan_arsenal_directory(base_path, quick=True)
    for cat in result["categories"]:
        if cat["id"] == category_id:
            return cat
    return None


def get_arsenal_stats(base_path: Path | None = None) -> dict[str, Any]:
    """Get summary statistics about the arsenal."""
    result = scan_arsenal_directory(base_path, quick=True)
    
    git_repos = sum(
        1 for cat in result["categories"]
        for tool in cat["tools"]
        if tool["has_git"]
    )
    
    with_readme = sum(
        1 for cat in result["categories"]
        for tool in cat["tools"]
        if tool["has_readme"]
    )
    
    python_projects = sum(
        1 for cat in result["categories"]
        for tool in cat["tools"]
        if tool["has_requirements"] or tool["has_setup_py"] or tool["has_pyproject"]
    )
    
    js_projects = sum(
        1 for cat in result["categories"]
        for tool in cat["tools"]
        if tool["has_package_json"]
    )
    
    docker_projects = sum(
        1 for cat in result["categories"]
        for tool in cat["tools"]
        if tool["has_dockerfile"]
    )
    
    return {
        "total_tools": result["total_tools"],
        "total_categories": result["total_categories"],
        "git_repos": git_repos,
        "with_readme": with_readme,
        "python_projects": python_projects,
        "javascript_projects": js_projects,
        "docker_ready": docker_projects,
        "completeness_pct": round(git_repos / max(result["total_tools"], 1) * 100, 1),
        "scan_time_ms": result["scan_time_ms"],
    }


if __name__ == "__main__":
    import json
    stats = get_arsenal_stats()
    print(json.dumps(stats, indent=2))
