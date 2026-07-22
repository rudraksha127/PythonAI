"""
ForgeAI Agents API Routes
==========================
Exposes the 7 special-purpose agents (code, debug, docs, teacher,
performance, retrieval, orchestrator) via REST endpoints.

Endpoints:
  GET  /api/agents              — List available agents with descriptions
  POST /api/agents/{agent_type} — Run a specific agent
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.agents import ALL_AGENTS
from src.agents.orchestrator import run_orchestrator_agent
from src.utils.swarm import GenerationTask

logger = logging.getLogger("forgeai.api.agents")

router = APIRouter(prefix="/api/agents", tags=["agents"])

# ── Agent Metadata ───────────────────────────────────────────

AGENT_METADATA: dict[str, dict[str, Any]] = {
    "code": {
        "description": "Generates production-ready Python code with type hints, docstrings, and error handling",
        "provider": "parallel (Cerebras, Groq, SambaNova — race to fastest)",
    },
    "debug": {
        "description": "Ruthless code reviewer — finds bugs, edge cases, security vulnerabilities, and returns fixed code",
        "provider": "Mistral",
    },
    "docs": {
        "description": "Explains APIs, libraries, and Python concepts with clear examples and official docs links",
        "provider": "OpenRouter",
    },
    "teacher": {
        "description": "Patient Python educator — explains from first principles with analogies, exercises, and Hinglish support",
        "provider": "Auto (best available)",
    },
    "performance": {
        "description": "Python optimization expert — profiles bottlenecks, suggests algorithmic improvements with benchmarks",
        "provider": "Auto (best available)",
    },
    "retrieval": {
        "description": "Knowledge extraction specialist — searches, ranks, and synthesizes information from multiple sources",
        "provider": "parallel (Groq, Cerebras, SambaNova — race to fastest)",
    },
    "orchestrator": {
        "description": "Central brain — routes coding tasks to Code Agent then verifies with Debug Agent; remembers past context",
        "provider": "parallel + AgentMemory (ChromaDB)",
    },
}

# ── Pydantic Models ──────────────────────────────────────────


class AgentRequest(BaseModel):
    """Request to run an agent."""

    prompt: str = Field(..., min_length=1, max_length=10_000, description="The task/question for the agent")
    session_id: str = Field(default="default", max_length=200, description="Session ID for memory/context tracking")


class AgentResponse(BaseModel):
    """Response from an agent execution."""

    agent_type: str
    output: str
    success: bool
    error: str | None = None


# ── Endpoints ────────────────────────────────────────────────


@router.get("")
async def list_agents() -> dict[str, Any]:
    """List all available agents with descriptions and provider info."""
    agents = {}
    for name in ALL_AGENTS:
        meta = AGENT_METADATA.get(name, {})
        agents[name] = {
            "name": name,
            "description": meta.get("description", ""),
            "provider": meta.get("provider", "unknown"),
        }
    return {
        "success": True,
        "agents": agents,
        "count": len(agents),
    }


@router.get("/{agent_type}")
async def get_agent_info(agent_type: str) -> dict[str, Any]:
    """Get metadata for a specific agent."""
    if agent_type not in ALL_AGENTS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown agent '{agent_type}'. Available: {', '.join(ALL_AGENTS)}",
        )
    meta = AGENT_METADATA.get(agent_type, {})
    return {
        "success": True,
        "agent": {
            "name": agent_type,
            "description": meta.get("description", ""),
            "provider": meta.get("provider", "unknown"),
        },
    }


@router.post("/{agent_type}", response_model=AgentResponse)
async def run_agent(agent_type: str, body: AgentRequest) -> dict[str, Any]:
    """Run a specific agent with the given prompt.

    Args:
        agent_type: One of: code, debug, docs, teacher, performance, retrieval, orchestrator.
        body: Request with `prompt` and optional `session_id`.

    Returns:
        AgentResponse with the agent's output.
    """
    if agent_type not in ALL_AGENTS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown agent '{agent_type}'. Available: {', '.join(ALL_AGENTS)}",
        )

    try:
        # Build the GenerationTask that agents expect
        task = GenerationTask(
            task_id=f"{agent_type}_{uuid.uuid4().hex[:8]}",
            task_type=agent_type,
            prompt=body.prompt,
            timeout=120.0,
        )

        # Run the agent
        if agent_type == "orchestrator":
            result = run_orchestrator_agent(task, session_id=body.session_id)
        else:
            agent_fn = ALL_AGENTS[agent_type]
            result = agent_fn(task)

        output = result.get("output", "")
        if output.startswith(f"[{agent_type.capitalize()} Agent failed]"):
            logger.error(f"Agent '{agent_type}' failed: {output}")
            return {
                "agent_type": agent_type,
                "output": output,
                "success": False,
                "error": output,
            }

        logger.info(f"Agent '{agent_type}' completed: {len(output)} chars")
        return {
            "agent_type": agent_type,
            "output": output,
            "success": True,
            "error": None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Agent '{agent_type}' error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {e}")
