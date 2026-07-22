"""
═══════════════════════════════════════════════════════════════
ForgeAI — Arsenal Integrations Health Check & Lazy Loader
Source: Readme/git.txt (300+ tools, unified status system)
═══════════════════════════════════════════════════════════════

Provides:
  - check_arsenal_status()  → dict of all tools and their install status
  - get_tool(name)          → lazy-import any arsenal tool
  - ARSENAL_REGISTRY        → complete tool manifest
"""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger


# ── Status Enum ──────────────────────────────────────────────

class ToolStatus(str, Enum):
    INSTALLED = "[+] installed"
    MISSING = "[-] missing"
    OPTIONAL = "[?] optional (GPU)"
    BUILTIN = "[*] builtin"


# ── Tool Entry ───────────────────────────────────────────────

@dataclass
class ArsenalTool:
    """Represents a single tool from the GitHub Arsenal."""
    id: int
    name: str
    pip_package: str | None         # pip package name (None = not pip-installable)
    import_name: str | None         # Python import name
    category: str
    priority: str                   # "P1-immediate", "P2-short", "P3-medium", "P4-advanced", "optional"
    description: str
    github_url: str = ""
    stars: str = ""
    status: ToolStatus = ToolStatus.MISSING
    _module: Any = field(default=None, repr=False)


# ── Complete Arsenal Registry ────────────────────────────────
# Organized by the priority system from git.txt

ARSENAL_REGISTRY: list[ArsenalTool] = [
    # ═══ PRIORITY 1: IMMEDIATE ═══
    ArsenalTool(9, "Outlines", "outlines", "outlines", "AI Foundations", "P1-immediate",
                "Guaranteed JSON from any LLM", "https://github.com/dottxt-ai/outlines", "11K+"),
    ArsenalTool(93, "Distilabel", "distilabel", "distilabel", "Dataset Tools", "P1-immediate",
                "Synthetic data generation pipeline", "https://github.com/argilla-io/distilabel", "5K+"),
    ArsenalTool(138, "RAGAS", "ragas", "ragas", "Evaluation", "P1-immediate",
                "RAG evaluation framework", "https://github.com/explodinggradients/ragas", "8K+"),
    ArsenalTool(139, "DeepEval", "deepeval", "deepeval", "Evaluation", "P1-immediate",
                "pytest for LLMs", "https://github.com/confident-ai/deepeval", "6K+"),

    # ═══ PRIORITY 2: SHORT TERM ═══
    ArsenalTool(66, "LightRAG", "lightrag-hku", "lightrag", "RAG Frameworks", "P2-short",
                "Graph + Vector hybrid RAG", "https://github.com/HKUDS/LightRAG", "20K+"),
    ArsenalTool(119, "mem0", "mem0ai", "mem0", "Memory Systems", "P2-short",
                "Persistent AI memory layer", "https://github.com/mem0ai/mem0", "25K+"),
    ArsenalTool(148, "Langfuse", "langfuse", "langfuse", "Observability", "P2-short",
                "LLM observability platform", "https://github.com/langfuse/langfuse", "8K+"),
    ArsenalTool(196, "Crawl4AI", "crawl4ai", "crawl4ai", "Browser & Web", "P2-short",
                "Async web crawler for LLMs", "https://github.com/unclecode/crawl4ai", "30K+"),
    ArsenalTool(269, "DuckDuckGo Search", "duckduckgo-search", "duckduckgo_search", "Search", "P2-short",
                "Free web search API", "https://github.com/deedy5/duckduckgo_search", "3K+"),

    # ═══ PRIORITY 3: MEDIUM TERM ═══
    ArsenalTool(44, "CrewAI", "crewai", "crewai", "Agent Frameworks", "P3-medium",
                "Role-based multi-agent framework", "https://github.com/crewAIInc/crewAI", "30K+"),
    ArsenalTool(109, "Graphiti", "graphiti-core", "graphiti_core", "Knowledge Graphs", "P3-medium",
                "Temporal knowledge graph", "https://github.com/getzep/graphiti", "8K+"),
    ArsenalTool(94, "Argilla", "argilla", "argilla", "Dataset Tools", "P3-medium",
                "Data labeling for AI", "https://github.com/argilla-io/argilla", "4K+"),

    # ═══ PRIORITY 4: ADVANCED ═══
    ArsenalTool(6, "DSPy", "dspy", "dspy", "AI Foundations", "P4-advanced",
                "Programming (not prompting) LMs", "https://github.com/stanfordnlp/dspy", "30K+"),
    ArsenalTool(5, "LlamaIndex", "llama-index", "llama_index", "AI Foundations", "P4-advanced",
                "Data framework for LLM apps", "https://github.com/run-llama/llama_index", "40K+"),
    ArsenalTool(251, "Guardrails AI", "guardrails-ai", "guardrails", "Safety", "P4-advanced",
                "Input/output validation", "https://github.com/guardrails-ai/guardrails", "5K+"),
    ArsenalTool(195, "Firecrawl", "firecrawl-py", "firecrawl", "Browser & Web", "P4-advanced",
                "LLM-optimized web crawling", "https://github.com/mendableai/firecrawl", "25K+"),

    # ═══ ADDITIONAL (lightweight / already satisfied) ═══
    ArsenalTool(112, "NetworkX", "networkx", "networkx", "Knowledge Graphs", "P4-advanced",
                "Pure Python graph library", "https://github.com/networkx/networkx", "15K+"),
    ArsenalTool(132, "Cleanlab", "cleanlab", "cleanlab", "Dataset Tools", "P4-advanced",
                "Fix data quality issues", "https://github.com/cleanlab/cleanlab", "10K+"),
    ArsenalTool(199, "Trafilatura", "trafilatura", "trafilatura", "Browser & Web", "P4-advanced",
                "Web content extraction", "https://github.com/adbar/trafilatura", "3K+"),

    # ═══ ALREADY INSTALLED (verify) ═══
    ArsenalTool(99, "ChromaDB", "chromadb", "chromadb", "Vector Databases", "builtin",
                "AI-native embedding database", "https://github.com/chroma-core/chroma", "16K+"),
    ArsenalTool(1, "Transformers", "transformers", "transformers", "AI Foundations", "builtin",
                "State-of-art ML", "https://github.com/huggingface/transformers", "161K+"),
    ArsenalTool(13, "Sentence Transformers", "sentence-transformers", "sentence_transformers", "AI Foundations", "builtin",
                "Text embeddings", "https://github.com/UKPLab/sentence-transformers", "16K+"),
    ArsenalTool(167, "FastAPI", "fastapi", "fastapi", "API & Deployment", "builtin",
                "Modern Python API framework", "https://github.com/fastapi/fastapi", "80K+"),
    ArsenalTool(158, "Streamlit", "streamlit", "streamlit", "Web UI", "builtin",
                "Data app framework", "https://github.com/streamlit/streamlit", "37K+"),
    ArsenalTool(14, "FAISS", "faiss-cpu", "faiss", "Vector Databases", "builtin",
                "Similarity search by Meta", "https://github.com/facebookresearch/faiss", "33K+"),
    ArsenalTool(10, "HF PEFT", "peft", "peft", "Fine-tuning", "builtin",
                "Parameter-efficient fine-tuning", "https://github.com/huggingface/peft", "17K+"),
    ArsenalTool(12, "TRL", "trl", "trl", "Fine-tuning", "builtin",
                "RLHF, DPO, PPO training", "https://github.com/huggingface/trl", "12K+"),
    ArsenalTool(11, "Accelerate", "accelerate", "accelerate", "AI Foundations", "builtin",
                "Distributed training made easy", "https://github.com/huggingface/accelerate", "8K+"),

    # ═══ GPU-OPTIONAL ═══
    ArsenalTool(23, "vLLM", "vllm", "vllm", "Inference Engines", "optional",
                "High-throughput LLM serving", "https://github.com/vllm-project/vllm", "45K+"),
    ArsenalTool(24, "SGLang", "sglang", "sglang", "Inference Engines", "optional",
                "5x faster than vLLM", "https://github.com/sgl-project/sglang", "15K+"),
    ArsenalTool(81, "Unsloth", "unsloth", "unsloth", "Fine-tuning", "optional",
                "2x faster, 50% less memory", "https://github.com/unslothai/unsloth", "50K+"),
]


def _check_import(import_name: str) -> bool:
    """Try importing a module, return True if successful."""
    if import_name is None:
        return False
    try:
        importlib.import_module(import_name)
        return True
    except Exception:
        return False


def check_arsenal_status() -> dict[str, Any]:
    """
    Check the installation status of all arsenal tools.

    Returns:
        {
            "total": int,
            "installed": int,
            "missing": int,
            "optional": int,
            "tools": [
                {"id": 9, "name": "Outlines", "status": "✅ installed", ...},
                ...
            ],
            "by_priority": {
                "P1-immediate": {"installed": 4, "total": 4},
                ...
            }
        }
    """
    results = []
    by_priority: dict[str, dict[str, int]] = {}

    for tool in ARSENAL_REGISTRY:
        if tool.import_name and _check_import(tool.import_name):
            tool.status = ToolStatus.INSTALLED
        elif tool.priority == "optional":
            tool.status = ToolStatus.OPTIONAL
        elif tool.priority == "builtin":
            # Should be installed, check anyway
            if tool.import_name and _check_import(tool.import_name):
                tool.status = ToolStatus.BUILTIN
            else:
                tool.status = ToolStatus.MISSING
        else:
            tool.status = ToolStatus.MISSING

        results.append({
            "id": tool.id,
            "name": tool.name,
            "category": tool.category,
            "priority": tool.priority,
            "status": tool.status.value,
            "description": tool.description,
            "github": tool.github_url,
        })

        # Aggregate by priority
        if tool.priority not in by_priority:
            by_priority[tool.priority] = {"installed": 0, "total": 0}
        by_priority[tool.priority]["total"] += 1
        if tool.status in (ToolStatus.INSTALLED, ToolStatus.BUILTIN):
            by_priority[tool.priority]["installed"] += 1

    installed = sum(1 for r in results if "installed" in r["status"] or "builtin" in r["status"])
    optional = sum(1 for r in results if "optional" in r["status"])

    return {
        "total": len(results),
        "installed": installed,
        "missing": len(results) - installed - optional,
        "optional": optional,
        "tools": results,
        "by_priority": by_priority,
    }


def get_tool(name: str) -> Any:
    """
    Lazy-import an arsenal tool by name.

    Args:
        name: The tool name (case-insensitive) or import name.

    Returns:
        The imported module, or None if not installed.

    Example:
        >>> outlines = get_tool("outlines")
        >>> mem0 = get_tool("mem0")
    """
    # Search by name or import_name
    for tool in ARSENAL_REGISTRY:
        if tool.name.lower() == name.lower() or tool.import_name == name:
            if tool.import_name and _check_import(tool.import_name):
                mod = importlib.import_module(tool.import_name)
                tool._module = mod
                tool.status = ToolStatus.INSTALLED
                return mod
            else:
                logger.warning(f"Arsenal tool '{tool.name}' ({tool.pip_package}) is not installed.")
                logger.info(f"  → Install: pip install {tool.pip_package}")
                return None

    logger.error(f"Arsenal tool '{name}' not found in registry.")
    return None


def print_arsenal_status():
    """Pretty-print the arsenal status table to console."""
    from rich.console import Console
    from rich.table import Table

    console = Console()
    status = check_arsenal_status()

    table = Table(
        title=f"ForgeAI Arsenal Status - {status['installed']}/{status['total']} installed",
        show_lines=False,
    )
    table.add_column("#", style="dim", width=5)
    table.add_column("Name", style="bold cyan", width=25)
    table.add_column("Category", style="dim", width=20)
    table.add_column("Priority", width=14)
    table.add_column("Status", width=18)

    priority_colors = {
        "P1-immediate": "bold red",
        "P2-short": "bold yellow",
        "P3-medium": "bold blue",
        "P4-advanced": "bold magenta",
        "builtin": "bold green",
        "optional": "dim",
    }

    for t in status["tools"]:
        p_style = priority_colors.get(t["priority"], "")
        table.add_row(
            str(t["id"]),
            t["name"],
            t["category"],
            f"[{p_style}]{t['priority']}[/]",
            t["status"],
        )

    console.print(table)
    console.print()

    # Summary by priority
    for p, data in status["by_priority"].items():
        pct = (data["installed"] / data["total"] * 100) if data["total"] else 0
        bar = "#" * int(pct / 5) + "-" * (20 - int(pct / 5))
        console.print(f"  {p:15s} {bar} {data['installed']}/{data['total']} ({pct:.0f}%)")


# ── CLI Entry Point ──────────────────────────────────────────

if __name__ == "__main__":
    print_arsenal_status()
