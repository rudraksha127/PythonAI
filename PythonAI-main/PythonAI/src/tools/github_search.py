from __future__ import annotations

from typing import Any

from src.data.api_dataset_gen import GitHubCodeClient
from src.utils.swarm import MCPTool

# Global lazy-loaded GitHub client
_gh_client: GitHubCodeClient | None = None


def handle_github_search(query: str, max_results: int = 3) -> dict[str, Any]:
    """Search GitHub for real production Python code."""
    global _gh_client
    if _gh_client is None:
        _gh_client = GitHubCodeClient()

    results = _gh_client.search_code(query, max_results=max_results)

    if not results:
        return {"success": False, "error": f"No GitHub code found for '{query}'"}

    return {"success": True, "results": results}


github_search_tool = MCPTool(
    name="github_search",
    description="Search GitHub for real production Python code usage patterns and examples.",
    handler=handle_github_search,
    parameters={
        "query": {"type": "string", "description": "The code pattern to search for (e.g., 'requests.get')"},
        "max_results": {"type": "integer", "description": "Maximum number of code snippets to return", "default": 3},
    },
)
