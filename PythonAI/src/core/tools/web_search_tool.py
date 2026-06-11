"""
PythonAI Tool — WebSearchTool
===============================
Search the web using DuckDuckGo and return results.
Inspired by Claude Code's WebSearchTool.
"""

from __future__ import annotations

from typing import Any

from ..tool import (
    InputSchema,
    Parameter,
    ToolResult,
    ToolUseContext,
    ValidationResult,
    build_tool,
)

WebSearchTool = build_tool(
    type("WebSearchToolDef", (), {
        "name": "web_search",
        "description": "Search the web for information. Returns relevant snippets and URLs.",
        "search_hint": "search web, find information, google",
        "input_schema": InputSchema(
            query=Parameter(
                type="string",
                description="Search query",
                required=True,
            ),
            max_results=Parameter(
                type="integer",
                description="Maximum number of search results (default: 5)",
                default=5,
            ),
        ),
        "is_readonly": True,
        "is_concurrency_safe": True,
        "max_result_size_chars": 20000,
        "call": lambda input_data, context: _search_call(input_data, context),
        "validate_input": lambda input_data, context: _search_validate(input_data, context),
        "get_activity_description": lambda input_data: f"Searching for {input_data.get('query', '')[:40]}..." if input_data else None,
    })
)


def _search_validate(input_data: dict[str, Any],
                     context: ToolUseContext) -> ValidationResult:
    query = input_data.get("query", "")
    if not query:
        return ValidationResult(success=False, message="query is required", error_code=1)
    if len(query) > 500:
        return ValidationResult(success=False, message="Query too long (max 500 chars)", error_code=2)
    return ValidationResult(success=True)


def _search_call(input_data: dict[str, Any],
                 context: ToolUseContext) -> ToolResult:
    query = input_data.get("query", "")
    max_results = min(input_data.get("max_results", 5), 20)

    try:
        # Try DuckDuckGo search
        results = _search_duckduckgo(query, max_results)

        if results:
            return ToolResult(data={
                "query": query,
                "total_results": len(results),
                "results": results,
                "message": f"Found {len(results)} results",
            })

        # Fallback: try a simple HTTP-based search
        results = _search_fallback(query, max_results)

        if results:
            return ToolResult(data={
                "query": query,
                "total_results": len(results),
                "results": results,
                "note": "Using fallback search engine",
                "message": f"Found {len(results)} results (fallback)",
            })

        return ToolResult(data={
            "query": query,
            "total_results": 0,
            "results": [],
            "message": "No results found. Try a different query.",
        })

    except ImportError as e:
        return ToolResult(
            data={"error": f"Missing dependency: {e}. Install with: pip install duckduckgo-search requests"},
            error=f"Missing dependency: {e}",
        )
    except Exception as e:
        return ToolResult(data={
            "query": query,
            "error": str(e),
            "results": [],
            "message": f"Search failed: {e}",
        })


def _search_duckduckgo(query: str, max_results: int) -> list[dict[str, str]]:
    """Search using DuckDuckGo."""
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for i, r in enumerate(ddgs.text(query, max_results=max_results)):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
                if i >= max_results:
                    break
        return results
    except Exception:
        return []


def _search_fallback(query: str, max_results: int) -> list[dict[str, str]]:
    """Fallback search using a simple web scrape approach."""
    try:
        import re
        from urllib.parse import quote_plus

        import requests

        encoded = quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return []

        results = []
        # Simple scraping of result links
        for match in re.finditer(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            resp.text, re.DOTALL
        ):
            href = match.group(1).strip()
            title = re.sub(r'<[^>]+>', '', match.group(2)).strip()
            results.append({
                "title": title,
                "url": href,
                "snippet": "",
            })
            if len(results) >= max_results:
                break

        return results
    except Exception:
        return []
