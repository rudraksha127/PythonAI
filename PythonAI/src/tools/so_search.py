from __future__ import annotations

from typing import Any

from src.data.api_dataset_gen import StackOverflowClient
from src.utils.swarm import MCPTool

# Global lazy-loaded SO client
_so_client: StackOverflowClient | None = None

def handle_so_search(query: str, tags: str = "python", max_results: int = 3) -> dict[str, Any]:
    """Search Stack Overflow for answers."""
    global _so_client
    if _so_client is None:
        _so_client = StackOverflowClient()

    items = _so_client.search(query, max_results=max_results)

    # Fetch top answer for each result
    results = []
    for item in items[:max_results]:
        answers = _so_client.fetch_answers(item.get("question_id", 0))
        results.append({
            "title": item.get("title", ""),
            "score": item.get("score", 0),
            "link": item.get("link", ""),
            "body": item.get("body", ""),
            "top_answer": answers[0].get("body", "") if answers else "",
        })

    if not results:
        return {"success": False, "error": f"No Stack Overflow answers found for '{query}'"}

    return {"success": True, "results": results}

so_search_tool = MCPTool(
    name="so_search",
    description="Search Stack Overflow for top-voted answers to Python programming questions.",
    handler=handle_so_search,
    parameters={
        "query": {"type": "string", "description": "The programming question to search for (e.g., 'how to reverse a list')"},
        "tags": {"type": "string", "description": "Tags to filter by, semicolon separated", "default": "python"},
        "max_results": {"type": "integer", "description": "Maximum number of answers to return", "default": 3}
    }
)
