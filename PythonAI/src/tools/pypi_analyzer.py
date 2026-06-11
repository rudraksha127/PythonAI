from __future__ import annotations

import json
import urllib.request
from typing import Any

from src.utils.swarm import MCPTool


def handle_pypi_analyzer(package_name: str) -> dict[str, Any]:
    """Query PyPI JSON API for package info."""
    url = f"https://pypi.org/pypi/{package_name}/json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PythonAI-Agent/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                info = data.get("info", {})
                return {
                    "success": True,
                    "name": info.get("name"),
                    "version": info.get("version"),
                    "summary": info.get("summary"),
                    "author": info.get("author"),
                    "home_page": info.get("home_page"),
                    "project_urls": info.get("project_urls"),
                    "requires_python": info.get("requires_python"),
                    "requires_dist": info.get("requires_dist")
                }
            return {"success": False, "error": f"Failed to fetch PyPI data for {package_name}"}
    except Exception as e:
        return {"success": False, "error": f"PyPI API Error: {e}"}

pypi_analyzer_tool = MCPTool(
    name="pypi_analyzer",
    description="Query the PyPI JSON API for Python package metadata, dependencies, and versions.",
    handler=handle_pypi_analyzer,
    parameters={
        "package_name": {"type": "string", "description": "The name of the PyPI package to analyze"}
    }
)
