"""
ForgeAI Memory API Routes (mem0 integration)
"""
from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, HTTPException

from src.api.models import MemoryAddRequest, MemorySearchRequest

logger = logging.getLogger("forgeai.api.memory")
router = APIRouter(prefix="/api/memory", tags=["Memory"])

_forgeai_memory: Any = None


def set_memory_backend(backend: Any) -> None:
    global _forgeai_memory
    _forgeai_memory = backend


@router.post("/add")
async def memory_add(body: MemoryAddRequest) -> dict[str, Any]:
    """Store a memory for a developer across sessions."""
    if _forgeai_memory is None:
        return {"success": False, "error": "Memory system not initialized"}

    result = _forgeai_memory.add(body.message, user_id=body.user_id)
    return {"success": "error" not in result, **result}


@router.post("/search")
async def memory_search(body: MemorySearchRequest) -> dict[str, Any]:
    """Semantic search across a developer's memories."""
    if _forgeai_memory is None:
        return {"success": False, "results": [], "error": "Memory system not initialized"}

    results = _forgeai_memory.search(body.query, user_id=body.user_id, limit=body.limit)
    return {"success": True, "results": results}


@router.get("/stats")
async def memory_stats() -> dict[str, Any]:
    """Get memory system statistics."""
    if _forgeai_memory is None:
        return {"available": False, "error": "Memory system not initialized"}

    stats = _forgeai_memory.get_stats()
    return {"available": True, **stats}


@router.get("/{user_id}")
async def memory_get_all(user_id: str = "default") -> dict[str, Any]:
    """Get all memories for a developer."""
    if _forgeai_memory is None:
        return {"success": False, "results": [], "error": "Memory system not initialized"}

    results = _forgeai_memory.get_all(user_id=user_id)
    return {"success": True, "results": results}


@router.delete("/{user_id}")
async def memory_delete_all(user_id: str = "default") -> dict[str, Any]:
    """Delete all memories for a developer."""
    if _forgeai_memory is None:
        return {"success": False, "deleted": 0, "error": "Memory system not initialized"}

    count = _forgeai_memory.delete_all(user_id=user_id)
    return {"success": True, "deleted": count}


@router.get("/context/{user_id}")
async def memory_context(user_id: str = "default") -> dict[str, Any]:
    """Get formatted context string for LLM prompts."""
    if _forgeai_memory is None:
        return {"context": ""}

    context = _forgeai_memory.format_for_context(user_id=user_id)
    return {"context": context}
