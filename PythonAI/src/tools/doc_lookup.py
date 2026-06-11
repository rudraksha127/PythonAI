from __future__ import annotations

from typing import Any

from src.rag.knowledge_graph import KnowledgeGraph
from src.utils.swarm import MCPTool

# Global lazy-loaded KG
_kg: KnowledgeGraph | None = None

def handle_doc_lookup(query: str, version: str = "") -> dict[str, Any]:
    """Look up documentation or function signatures from the Knowledge Graph."""
    global _kg
    if _kg is None:
        _kg = KnowledgeGraph()
        _kg.load()

    results = _kg.query(query, hops=1, max_results=3)
    if version:
        results = [r for r in results if not r.get("version") or r.get("version") == version]

    if not results:
        return {"success": False, "error": f"No documentation found for '{query}'"}

    return {"success": True, "results": results}

doc_lookup_tool = MCPTool(
    name="doc_lookup",
    description="Look up Python function signatures, module details, and version changes from the offline knowledge graph.",
    handler=handle_doc_lookup,
    parameters={
        "query": {"type": "string", "description": "The function, class, or module to look up (e.g., 'itertools.chain')"},
        "version": {"type": "string", "description": "Optional Python version to filter by (e.g., '3.10')", "default": ""}
    }
)
