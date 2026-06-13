"""
ForgeAIMemory — Persistent User Memory via mem0
================================================

Provides cross-session memory for developers using the ForgeAI platform.
Stores user preferences, code patterns, language choices, and context
so the agent can personalize responses over time.

Architecture:
- Wraps mem0ai's Memory class with graceful fallback
- Lazy initialization on first use (never blocks server startup)
- Per-developer memory via `developer_id` → `user_id`
- Auto-extracts signals from CaptureEngine events
- Configurable via env vars and JSON config file

Environment:
    FORGEAI_MEMORY_ENABLED  : "true" (default) or "false"
    FORGEAI_MEMORY_DIR      : custom storage path for Chroma
    FORGEAI_LLM_MODEL       : Ollama model for LLM (default: qwen2.5-coder:14b)
    FORGEAI_EMBED_MODEL     : Ollama embedding model (default: nomic-embed-text)

Usage:
    from src.memory.mem0_wrapper import ForgeAIMemory

    mem = ForgeAIMemory()
    mem.add("User prefers Python 3.12", user_id="dev123")
    results = mem.search("Python version", user_id="dev123")
    all_memories = mem.get_all(user_id="dev123")
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("forgeai.memory")

# ── Configuration ────────────────────────────────────────────────

DEFAULT_MEMORY_DIR = Path.home() / ".forgeai" / "memory"
DEFAULT_LLM_MODEL = os.environ.get("FORGEAI_LLM_MODEL", "qwen2.5-coder:14b")
DEFAULT_EMBED_MODEL = os.environ.get("FORGEAI_EMBED_MODEL", "nomic-embed-text")

# ── Adapter ──────────────────────────────────────────────────────


class ForgeAIMemory:
    """Persistent user memory adapter wrapping mem0 (with graceful fallback).

    All operations are safe to call even if mem0 is not installed or
    fails to initialize — methods return empty results gracefully.

    Thread-safe: uses a lock for initialization.
    """

    def __init__(
        self,
        storage_dir: str | Path | None = None,
        llm_model: str = DEFAULT_LLM_MODEL,
        embed_model: str = DEFAULT_EMBED_MODEL,
        enabled: bool = True,
    ) -> None:
        self._storage_dir = Path(storage_dir or DEFAULT_MEMORY_DIR)
        self._storage_dir.mkdir(parents=True, exist_ok=True)

        self._llm_model = llm_model
        self._embed_model = embed_model
        self._enabled = enabled

        self._memory = None
        self._initialized = False
        self._init_error: str | None = None
        self._lock = threading.Lock()

        self._stats = {
            "total_adds": 0,
            "total_searches": 0,
            "total_get_all": 0,
            "total_deletes": 0,
            "errors": 0,
            "last_error": None,
            "last_activity": None,
        }

    # ── Lazy Initialization ──────────────────────────────────────

    def _ensure_initialized(self) -> bool:
        """Lazy-init mem0 on first use. Returns True if available."""
        if self._initialized:
            return self._memory is not None

        if not self._enabled:
            self._initialized = True
            self._init_error = "Memory disabled via FORGEAI_MEMORY_ENABLED=false"
            logger.info("ForgeAIMemory is disabled")
            return False

        with self._lock:
            if self._initialized:
                return self._memory is not None

            try:
                from mem0 import Memory

                config = self._build_config()
                self._memory = Memory.from_config(config)
                self._initialized = True
                logger.info(
                    f"ForgeAIMemory initialized (dir={self._storage_dir}, "
                    f"llm={self._llm_model}, embed={self._embed_model})"
                )
                return True

            except ImportError:
                self._init_error = "mem0 not installed. Run: pip install mem0ai"
                logger.warning(self._init_error)
            except Exception as e:
                self._init_error = str(e)
                logger.warning(f"ForgeAIMemory init failed: {e}")

            self._initialized = True
            self._memory = None
            return False

    def _build_config(self) -> dict[str, Any]:
        """Build mem0 configuration dict."""
        chroma_path = str(self._storage_dir / "chroma_db")
        return {
            "llm": {
                "provider": "ollama",
                "config": {
                    "model": self._llm_model,
                    "ollama_base_url": os.environ.get(
                        "OLLAMA_HOST", "http://localhost:11434"
                    ),
                    "temperature": 0.2,
                    "max_tokens": 256,
                },
            },
            "embedder": {
                "provider": "ollama",
                "config": {
                    "model": self._embed_model,
                    "ollama_base_url": os.environ.get(
                        "OLLAMA_HOST", "http://localhost:11434"
                    ),
                },
            },
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "forgeai_memories",
                    "path": chroma_path,
                },
            },
            "version": "v1.1",
            "history_db_path": str(self._storage_dir / "history.db"),
        }

    # ── Public API ───────────────────────────────────────────────

    def add(self, message: str, user_id: str = "default") -> dict[str, Any]:
        """Store a memory for a developer.

        Args:
            message: The memory text (e.g., "User prefers Python 3.12").
            user_id: Developer identifier. Use the developer_id from signals.

        Returns:
            Dict with result info, or {"error": ...} on failure.
        """
        if not self._ensure_initialized() or self._memory is None:
            self._stats["errors"] += 1
            error_msg = self._init_error or "Memory not available"
            self._stats["last_error"] = error_msg
            return {"error": error_msg}

        try:
            result = self._memory.add(message, user_id=user_id)
            self._stats["total_adds"] += 1
            self._stats["last_activity"] = time.time()
            return result
        except Exception as e:
            self._stats["errors"] += 1
            self._stats["last_error"] = str(e)
            logger.warning(f"ForgeAIMemory.add failed: {e}")
            return {"error": str(e)}

    def search(
        self, query: str, user_id: str = "default", limit: int = 5
    ) -> list[dict[str, Any]]:
        """Semantically search memories for a developer.

        Args:
            query: Natural language query.
            user_id: Developer identifier.
            limit: Max results.

        Returns:
            List of memory dicts with keys like "id", "memory", "score".
        """
        self._stats["total_searches"] += 1
        self._stats["last_activity"] = time.time()

        if not self._ensure_initialized() or self._memory is None:
            return []

        try:
            raw = self._memory.search(query, user_id=user_id)
            results = raw.get("results", [])[:limit]
            return results
        except Exception as e:
            self._stats["errors"] += 1
            self._stats["last_error"] = str(e)
            logger.warning(f"ForgeAIMemory.search failed: {e}")
            return []

    def get_all(self, user_id: str = "default") -> list[dict[str, Any]]:
        """Retrieve all stored memories for a developer.

        Returns:
            List of memory dicts with keys like "id", "memory", etc.
        """
        self._stats["total_get_all"] += 1
        self._stats["last_activity"] = time.time()

        if not self._ensure_initialized() or self._memory is None:
            return []

        try:
            raw = self._memory.get_all(user_id=user_id)
            return raw.get("results", [])
        except Exception as e:
            self._stats["errors"] += 1
            self._stats["last_error"] = str(e)
            logger.warning(f"ForgeAIMemory.get_all failed: {e}")
            return []

    def delete(self, memory_id: str) -> bool:
        """Delete a specific memory by ID."""
        self._stats["total_deletes"] += 1

        if not self._ensure_initialized() or self._memory is None:
            return False

        try:
            self._memory.delete(memory_id)
            return True
        except Exception as e:
            self._stats["errors"] += 1
            self._stats["last_error"] = str(e)
            logger.warning(f"ForgeAIMemory.delete failed: {e}")
            return False

    def delete_all(self, user_id: str = "default") -> int:
        """Delete all memories for a developer.

        Returns:
            Number of memories deleted, or -1 on error.
        """
        memories = self.get_all(user_id=user_id)
        if not memories:
            return 0

        count = 0
        for mem in memories:
            mem_id = mem.get("id")
            if mem_id and self.delete(mem_id):
                count += 1
        return count

    def available(self) -> bool:
        """Check if mem0 is available and initialized."""
        self._ensure_initialized()
        return self._memory is not None

    def get_stats(self) -> dict[str, Any]:
        """Return adapter and mem0 statistics."""
        stats = {**self._stats}

        if self._memory is not None:
            try:
                mem0_stats = getattr(self._memory, "get_stats", lambda: {})()
                if isinstance(mem0_stats, dict):
                    stats["mem0"] = mem0_stats
            except Exception:
                pass

        stats.update({
            "available": self._memory is not None,
            "initialized": self._initialized,
            "init_error": self._init_error,
            "enabled": self._enabled,
            "storage_dir": str(self._storage_dir),
            "llm_model": self._llm_model,
            "embed_model": self._embed_model,
        })
        return stats

    def format_for_context(self, user_id: str = "default", max_memories: int = 5) -> str:
        """Format memories as a context string for LLM prompts.

        Useful for injecting into agent system prompts so the LLM
        knows the developer's preferences and history.

        Args:
            user_id: Developer identifier.
            max_memories: Max memories to include.

        Returns:
            Formatted string like:
            "Developer context:\n- User prefers Python 3.12\n- ..."
        """
        memories = self.get_all(user_id=user_id)[:max_memories]
        if not memories:
            return ""

        lines = ["Developer context:"]
        for mem in memories:
            text = mem.get("memory", "")
            if text:
                lines.append(f"- {text}")
        return "\n".join(lines)


# ── Factory ──────────────────────────────────────────────────────


def create_memory_backend() -> ForgeAIMemory | None:
    """Create a ForgeAIMemory instance.

    Returns None if FORGEAI_MEMORY_ENABLED is set to "false".
    Always returns a ForgeAIMemory instance otherwise (lazy init).
    """
    enabled = os.environ.get("FORGEAI_MEMORY_ENABLED", "true").lower() != "false"
    storage_dir = os.environ.get("FORGEAI_MEMORY_DIR")

    try:
        return ForgeAIMemory(
            storage_dir=storage_dir,
            enabled=enabled,
        )
    except Exception as e:
        logger.warning(f"Failed to create ForgeAIMemory: {e}")
        return None


# ── CLI ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ForgeAIMemory CLI")
    parser.add_argument("--add", help="Store a memory for a user")
    parser.add_argument("--user", default="default", help="Developer/user ID")
    parser.add_argument("--search", help="Search memories")
    parser.add_argument("--list", action="store_true", help="List all memories")
    parser.add_argument("--delete", help="Delete a memory by ID")
    parser.add_argument("--delete-all", action="store_true", help="Delete all for user")
    args = parser.parse_args()

    mem = ForgeAIMemory()

    if args.add:
        result = mem.add(args.add, user_id=args.user)
        print(json.dumps(result, indent=2))
    elif args.search:
        results = mem.search(args.search, user_id=args.user)
        print(json.dumps(results, indent=2))
    elif args.list:
        results = mem.get_all(user_id=args.user)
        print(json.dumps(results, indent=2))
    elif args.delete:
        ok = mem.delete(args.delete)
        print(f"Deleted: {ok}")
    elif args.delete_all:
        count = mem.delete_all(user_id=args.user)
        print(f"Deleted {count} memories")
    else:
        print(f"Status: available={mem.available()}")
        print(json.dumps(mem.get_stats(), indent=2, default=str))
