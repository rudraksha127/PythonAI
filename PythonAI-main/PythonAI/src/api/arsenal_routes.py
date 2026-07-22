"""
ForgeAI Arsenal API Routes — Expose GitHub Arsenal via REST
=============================================================

Endpoints:
  GET /api/arsenal/status     — Full status of all registered tools
  GET /api/arsenal/tools/{name} — Lazy-import check for a specific tool
  GET /api/arsenal/summary     — Quick counts by priority tier

Registered via `app.include_router(arsenal_router)` in server.py.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

logger = logging.getLogger("forgeai.api.arsenal")

router = APIRouter(prefix="/api/arsenal", tags=["Arsenal Tools"])


@router.get("/inventory")
async def arsenal_inventory() -> dict[str, Any]:
    """Get the full scan inventory and summary stats of the arsenal."""
    try:
        from src.integrations.arsenal_scanner import scan_arsenal_directory, get_arsenal_stats

        inventory = scan_arsenal_directory(quick=True)
        stats = get_arsenal_stats()
        return {
            "total_categories": inventory.get("total_categories", 0),
            "total_tools": inventory.get("total_tools", 0),
            "categories": inventory.get("categories", []),
            "stats": stats,
        }
    except Exception as e:
        logger.error(f"Failed to scan arsenal: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def arsenal_status() -> dict[str, Any]:
    """Get installation status of all arsenal tools.

    Returns tool counts, per-priority breakdowns, and individual tool info.
    """
    try:
        from src.integrations.arsenal_integrations import check_arsenal_status

        status = check_arsenal_status()
        return {"success": True, **status}
    except ImportError:
        return {
            "success": False,
            "error": "Arsenal integrations module not found",
            "total": 0,
            "installed": 0,
            "missing": 0,
        }
    except Exception as e:
        logger.error(f"Arsenal status check failed: {e}")
        return {"success": False, "error": str(e)}


@router.get("/summary")
async def arsenal_summary() -> dict[str, Any]:
    """Quick summary — installed/total counts by priority."""
    try:
        from src.integrations.arsenal_integrations import check_arsenal_status

        status = check_arsenal_status()
        return {
            "total": status["total"],
            "installed": status["installed"],
            "missing": status["missing"],
            "optional": status["optional"],
            "by_priority": status["by_priority"],
        }
    except ImportError:
        return {"total": 0, "installed": 0, "missing": 0, "optional": 0}
    except Exception as e:
        return {"error": str(e)}


@router.get("/tools/{name}")
async def arsenal_tool_info(name: str) -> dict[str, Any]:
    """Check a specific tool by name.

    Returns its status, category, description, and import availability.
    """
    try:
        from src.integrations.arsenal_integrations import ARSENAL_REGISTRY, _check_import

        for tool in ARSENAL_REGISTRY:
            if tool.name.lower() == name.lower() or tool.import_name == name:
                installed = (
                    _check_import(tool.import_name) if tool.import_name else False
                )
                return {
                    "found": True,
                    "name": tool.name,
                    "pip_package": tool.pip_package,
                    "import_name": tool.import_name,
                    "category": tool.category,
                    "priority": tool.priority,
                    "description": tool.description,
                    "github_url": tool.github_url,
                    "stars": tool.stars,
                    "installed": installed,
                }

        raise HTTPException(
            status_code=404, detail=f"Tool '{name}' not found in arsenal registry"
        )
    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(
            status_code=503, detail="Arsenal integrations module not available"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
