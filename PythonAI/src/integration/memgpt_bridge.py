"""
MemGPT/Letta Bridge — Persistent Memory Agents
===============================================

Wraps the `letta-client` SDK to provide AI agents with long-term,
self-managing memory. MemGPT (now Letta) uses an OS-inspired memory
architecture where agents automatically manage their context window
by separating core memory (always visible) from archival memory
(stored in a vector database, retrieved on demand).

Architecture:
    - Lazy initialization of Letta client on first use
    - Agents created with structured memory blocks (human + persona)
    - Core memory for always-visible context
    - Archival memory for large-scale semantic storage
    - Graceful fallback when letta-client is not installed

Usage:
    from src.integration.memgpt_bridge import MemGPTBridge

    bridge = MemGPTBridge()
    agent = bridge.create_agent(
        name="code-assistant",
        human_block="Name: Alice. Uses Python 3.12.",
        persona_block="You are a senior Python engineer.",
    )
    response = bridge.send_message(agent["id"], "What does Alice prefer?")
    # => {"messages": [...], "memory_updates": [...]}

Environment:
    LETTA_API_KEY       : API key for Letta server
    LETTA_BASE_URL      : Server URL (default: https://api.letta.com)
    LETTA_DEFAULT_MODEL : Default model for agents (default: openai/gpt-4o-mini)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any

logger = logging.getLogger("forgeai.integration.memgpt")

# ── Configuration ────────────────────────────────────────────────

DEFAULT_BASE_URL = "https://api.letta.com"
DEFAULT_MODEL = "openai/gpt-4o-mini"


class MemGPTBridge:
    """Persistent memory agent management via Letta.

    Provides:
    - create_agent with structured memory blocks
    - send_message with automatic memory management
    - Core memory CRUD (list, retrieve, update, attach)
    - Archival memory insert/search
    - Agent status and health checks

    Lazy-initializes the Letta client on first use.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
        enabled: bool = True,
    ) -> None:
        self._api_key = api_key or os.environ.get("LETTA_API_KEY", "")
        self._base_url = base_url or os.environ.get("LETTA_BASE_URL", DEFAULT_BASE_URL)
        self._default_model = default_model or os.environ.get("LETTA_DEFAULT_MODEL", DEFAULT_MODEL)
        self._enabled = enabled

        self._client = None
        self._initialized = False
        self._init_error: str | None = None

        self._stats = {
            "agents_created": 0,
            "messages_sent": 0,
            "memory_updates": 0,
            "archival_inserts": 0,
            "archival_searches": 0,
            "errors": 0,
            "last_error": None,
            "avg_response_ms": 0.0,
        }

    # ── Lazy Initialization ──────────────────────────────────────

    def _ensure_initialized(self) -> bool:
        """Initialize Letta client on first use."""
        if self._initialized:
            return self._client is not None

        if not self._enabled:
            self._initialized = True
            self._init_error = "MemGPT bridge disabled"
            logger.info("MemGPTBridge is disabled")
            return False

        if not self._api_key:
            self._initialized = True
            self._init_error = "LETTA_API_KEY not set"
            logger.warning("MemGPTBridge: LETTA_API_KEY not configured")
            return False

        try:
            from letta_client import Letta

            self._client = Letta(api_key=self._api_key, base_url=self._base_url)
            self._initialized = True
            logger.info(f"MemGPT/Letta client initialized: {self._base_url}")
            return True

        except ImportError:
            self._init_error = "letta-client not installed. Run: pip install letta-client"
            logger.warning(self._init_error)
        except Exception as e:
            self._init_error = str(e)
            logger.warning(f"MemGPTBridge init failed: {e}")

        self._initialized = True
        return False

    # ── Agent Management ─────────────────────────────────────────

    def create_agent(
        self,
        name: str | None = None,
        human_block: str = "",
        persona_block: str = "",
        model: str | None = None,
    ) -> dict[str, Any]:
        """Create a new agent with persistent memory.

        Args:
            name: Optional agent name.
            human_block: Information about the human user (always in context).
            persona_block: Instructions for the agent's persona (always in context).
            model: Model to use (e.g., "openai/gpt-4o").

        Returns:
            Dict with agent "id", "name", "memory_blocks", and status.
        """
        if not self._ensure_initialized() or self._client is None:
            return {"error": self._init_error or "MemGPT not available"}

        try:
            agent_model = model or self._default_model
            memory_blocks = []

            if human_block:
                memory_blocks.append({"label": "human", "value": human_block})
            if persona_block:
                memory_blocks.append({"label": "persona", "value": persona_block})

            kwargs: dict[str, Any] = {"model": agent_model}
            if memory_blocks:
                kwargs["memory_blocks"] = memory_blocks

            agent = self._client.agents.create(**kwargs)
            self._stats["agents_created"] += 1

            return {
                "id": getattr(agent, "id", ""),
                "name": name or f"agent_{getattr(agent, 'id', '')[:8]}",
                "model": agent_model,
                "memory_blocks": len(memory_blocks),
                "status": "created",
            }

        except Exception as e:
            self._stats["errors"] += 1
            self._stats["last_error"] = str(e)
            return {"error": str(e)}

    def list_agents(self) -> list[dict[str, Any]]:
        """List all agents."""
        if not self._ensure_initialized() or self._client is None:
            return []

        try:
            agents = self._client.agents.list()
            return [
                {"id": getattr(a, "id", ""), "name": getattr(a, "name", "") or "",
                 "model": getattr(a, "model", ""), "created": str(getattr(a, "created_at", ""))}
                for a in agents
            ]
        except Exception as e:
            self._stats["errors"] += 1
            return []

    def delete_agent(self, agent_id: str) -> bool:
        """Delete an agent by ID."""
        if not self._ensure_initialized() or self._client is None:
            return False

        try:
            self._client.agents.delete(agent_id)
            return True
        except Exception:
            return False

    # ── Messaging ────────────────────────────────────────────────

    def send_message(
        self,
        agent_id: str,
        message: str,
        stream: bool = False,
    ) -> dict[str, Any]:
        """Send a message to an agent and get response.

        Letta automatically manages the context window — core memory
        is always visible, while archival memories are retrieved as
        needed. The agent may also autonomously update its own memory.

        Args:
            agent_id: Agent to message.
            message: User message text.
            stream: Enable streaming (not yet supported in sync mode).

        Returns:
            Dict with "messages" (list of response messages),
            "usage" (token counts), "memory_updates" (if any).
        """
        if not self._ensure_initialized() or self._client is None:
            return {"messages": [], "error": self._init_error or "MemGPT not available"}

        try:
            start = time.time()

            response = self._client.agents.messages.create(
                agent_id=agent_id,
                input=message,
            )

            elapsed = time.time() - start
            self._stats["messages_sent"] += 1
            self._stats["avg_response_ms"] = (
                (self._stats["avg_response_ms"] * (self._stats["messages_sent"] - 1) + elapsed * 1000)
                / self._stats["messages_sent"]
            )

            # Extract messages and memory updates
            msg_list = []
            memory_updates = []
            for msg in getattr(response, "messages", []):
                msg_dict = {}
                if hasattr(msg, "model_dump"):
                    msg_dict = msg.model_dump()
                elif isinstance(msg, dict):
                    msg_dict = msg
                else:
                    msg_dict = {"content": str(msg)}

                msg_list.append(msg_dict)
                # Check for memory updates in message
                if msg_dict.get("message_type") == "memory_update":
                    memory_updates.append(msg_dict)

            return {
                "messages": msg_list,
                "memory_updates": memory_updates,
                "num_messages": len(msg_list),
                "elapsed_seconds": round(elapsed, 2),
            }

        except Exception as e:
            self._stats["errors"] += 1
            self._stats["last_error"] = str(e)
            return {"messages": [], "error": str(e)}

    # ── Core Memory Management ──────────────────────────────────

    def list_memory_blocks(self, agent_id: str) -> list[dict[str, Any]]:
        """List all core memory blocks for an agent.

        Memory blocks are always visible to the LLM and contain
        structured information like human profile and agent persona.
        """
        if not self._ensure_initialized() or self._client is None:
            return []

        try:
            blocks = self._client.agents.blocks.list(agent_id=agent_id)
            return [
                {"id": getattr(b, "id", ""), "label": getattr(b, "label", ""),
                 "value": getattr(b, "value", "")[:200]}
                for b in blocks
            ]
        except Exception as e:
            self._stats["errors"] += 1
            return []

    def update_memory_block(
        self, agent_id: str, label: str, value: str
    ) -> dict[str, Any]:
        """Update a core memory block for an agent.

        Args:
            agent_id: Agent to update.
            label: Block label (e.g., "human" or "persona").
            value: New block content.

        Returns:
            Dict with update status.
        """
        if not self._ensure_initialized() or self._client is None:
            return {"error": self._init_error or "MemGPT not available"}

        try:
            result = self._client.agents.blocks.update(
                agent_id=agent_id,
                label=label,
                value=value,
            )
            self._stats["memory_updates"] += 1
            return {"label": label, "status": "updated",
                    "value_preview": value[:100]}
        except Exception as e:
            self._stats["errors"] += 1
            return {"error": str(e)}

    def attach_memory_block(
        self, agent_id: str, block_id: str
    ) -> dict[str, Any]:
        """Attach an existing memory block to an agent for shared access."""
        if not self._ensure_initialized() or self._client is None:
            return {"error": self._init_error or "MemGPT not available"}

        try:
            self._client.agents.blocks.attach(agent_id=agent_id, block_id=block_id)
            return {"block_id": block_id, "status": "attached"}
        except Exception as e:
            return {"error": str(e)}

    # ── Archival Memory Management ───────────────────────────────

    def insert_archival_memory(
        self, agent_id: str, content: str, tags: list[str] | None = None
    ) -> dict[str, Any]:
        """Insert content into an agent's archival memory.

        Archival memory is stored in a vector database and retrieved
        on-demand via semantic search. Unlike core memory, it is not
        "pinned" to the context window.

        Args:
            agent_id: Agent to update.
            content: Text content to store.
            tags: Optional tags for filtering.

        Returns:
            Dict with insertion status.
        """
        if not self._ensure_initialized() or self._client is None:
            return {"error": self._init_error or "MemGPT not available"}

        try:
            kwargs: dict[str, Any] = {"content": content}
            if tags:
                kwargs["tags"] = tags

            result = self._client.agents.passages.insert(
                agent_id=agent_id, **kwargs
            )
            self._stats["archival_inserts"] += 1
            return {"content_preview": content[:100], "tags": tags or [],
                    "status": "inserted"}
        except Exception as e:
            self._stats["errors"] += 1
            return {"error": str(e)}

    def search_archival_memory(
        self, agent_id: str, query: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Semantically search an agent's archival memory.

        Returns passages that are semantically similar to the query.
        """
        if not self._ensure_initialized() or self._client is None:
            return []

        try:
            results = self._client.agents.passages.search(
                agent_id=agent_id, input=query, limit=limit
            )
            self._stats["archival_searches"] += 1

            passages = []
            for r in results:
                if hasattr(r, "model_dump"):
                    passages.append(r.model_dump())
                elif isinstance(r, dict):
                    passages.append(r)
                else:
                    passages.append({"content": str(r)})
            return passages[:limit]

        except Exception as e:
            self._stats["errors"] += 1
            return []

    def delete_archival_memory(self, agent_id: str, passage_id: str) -> bool:
        """Delete a specific passage from archival memory."""
        if not self._ensure_initialized() or self._client is None:
            return False

        try:
            self._client.agents.passages.delete(
                agent_id=agent_id, passage_id=passage_id
            )
            return True
        except Exception:
            return False

    # ── Info ─────────────────────────────────────────────────────

    def available(self) -> bool:
        """Check if Letta client is available and configured."""
        self._ensure_initialized()
        return self._client is not None

    def get_stats(self) -> dict[str, Any]:
        """Return adapter statistics."""
        return {
            **self._stats,
            "base_url": self._base_url,
            "has_api_key": bool(self._api_key),
            "default_model": self._default_model,
            "initialized": self._initialized,
            "init_error": self._init_error,
            "enabled": self._enabled,
        }

    def health_check(self) -> dict[str, Any]:
        """Check Letta server connectivity and client availability."""
        checks = []

        try:
            from letta_client import Letta  # noqa: F401
            checks.append({"name": "import", "status": "ok"})
        except ImportError:
            checks.append({"name": "import", "status": "fail"})

        if self._api_key:
            checks.append({"name": "api_key", "status": "ok"})
        else:
            checks.append({"name": "api_key", "status": "fail", "detail": "LETTA_API_KEY not set"})

        if self._ensure_initialized():
            try:
                agents = self._client.agents.list()
                checks.append({"name": "server", "status": "ok",
                               "detail": f"Connected, {len(agents)} agents found"})
            except Exception as e:
                checks.append({"name": "server", "status": "fail", "detail": str(e)})
        else:
            checks.append({"name": "server", "status": "fail", "detail": self._init_error})

        return {"healthy": all(c["status"] == "ok" for c in checks),
                "checks": checks, "timestamp": time.time()}


# ── Factory ──────────────────────────────────────────────────────


def create_memgpt_bridge() -> MemGPTBridge | None:
    """Create a MemGPTBridge if letta-client is installed."""
    try:
        from letta_client import Letta  # noqa: F401
        return MemGPTBridge()
    except ImportError:
        logger.info("letta-client not installed — MemGPT memory agents unavailable")
        return None


# ── CLI ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MemGPT Bridge CLI")
    parser.add_argument("--create-agent", help="Name for new agent")
    parser.add_argument("--human", default="", help="Human memory block content")
    parser.add_argument("--persona", default="", help="Persona memory block content")
    parser.add_argument("--send", help="Send message to agent")
    parser.add_argument("--agent-id", help="Agent ID for message/block ops")
    parser.add_argument("--list-agents", action="store_true", help="List agents")
    parser.add_argument("--list-blocks", action="store_true", help="List memory blocks")
    parser.add_argument("--update-block", help="Update a memory block (use --label --value)")
    parser.add_argument("--label", help="Memory block label (human/persona)")
    parser.add_argument("--value", help="New value for memory block")
    parser.add_argument("--insert-archival", help="Insert into archival memory")
    parser.add_argument("--search-archival", help="Search archival memory")
    parser.add_argument("--health", action="store_true", help="Run health check")
    parser.add_argument("--model", help="Model to use for agent creation")
    args = parser.parse_args()

    bridge = MemGPTBridge()

    if args.health:
        result = bridge.health_check()
    elif args.list_agents:
        result = bridge.list_agents()
    elif args.list_blocks and args.agent_id:
        result = bridge.list_memory_blocks(args.agent_id)
    elif args.update_block and args.agent_id and args.label and args.value:
        result = bridge.update_memory_block(args.agent_id, args.label, args.value)
    elif args.insert_archival and args.agent_id:
        result = bridge.insert_archival_memory(args.agent_id, args.insert_archival)
    elif args.search_archival and args.agent_id:
        result = bridge.search_archival_memory(args.agent_id, args.search_archival)
    elif args.send and args.agent_id:
        result = bridge.send_message(args.agent_id, args.send)
    elif args.create_agent:
        result = bridge.create_agent(
            name=args.create_agent,
            human_block=args.human or "User name: Developer.",
            persona_block=args.persona or "You are a helpful AI assistant.",
            model=args.model,
        )
    else:
        result = {"status": bridge.available(), "stats": bridge.get_stats()}

    print(json.dumps(result, indent=2, default=str))
