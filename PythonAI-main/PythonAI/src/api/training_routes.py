"""
ForgeAI Training & SEAL Cycle API Routes
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger("forgeai.api.training")
router = APIRouter(tags=["Training"])

_capture_engine: Any = None
_sdft_trainer: Any = None
_grpo_trainer: Any = None
_active_training_run: dict[str, Any] | None = None
_broadcast_fn: Any = None

_schedule_config: dict[str, Any] = {
    "enabled": False,
    "cron": "0 2 * * 0",
    "description": "Weekly on Sunday at 02:00",
    "last_run": None,
    "next_run": None,
    "total_runs": 0,
}


def set_training_backends(capture: Any, sdft: Any, grpo: Any, broadcast_fn: Any = None) -> None:
    global _capture_engine, _sdft_trainer, _grpo_trainer, _broadcast_fn
    _capture_engine = capture
    _sdft_trainer = sdft
    _grpo_trainer = grpo
    _broadcast_fn = broadcast_fn


@router.get("/api/training/status")
async def get_training_status(project_id: str | None = None) -> dict[str, Any]:
    """Get current training status and history."""
    if _capture_engine is None:
        raise HTTPException(status_code=503, detail="Capture engine not initialized")

    history = _capture_engine.get_training_runs(limit=10)

    return {
        "active_run": _active_training_run,
        "history": history,
    }


@router.post("/api/training/trigger")
async def trigger_training(project_id: str | None = None) -> dict[str, Any]:
    """Manually trigger a training run."""
    global _active_training_run

    if _capture_engine is None or _sdft_trainer is None:
        raise HTTPException(status_code=503, detail="Training system not initialized")

    if _active_training_run is not None:
        raise HTTPException(status_code=409, detail="Training run already in progress")

    run_id = str(uuid.uuid4())
    _active_training_run = {
        "run_id": run_id,
        "status": "queued",
        "started_at": time.time(),
        "progress": 0.0,
    }

    if _broadcast_fn:
        await _broadcast_fn({"type": "training_started", "run_id": run_id})

    return {"run_id": run_id, "status": "queued"}


@router.get("/api/training/schedule")
async def get_training_schedule() -> dict[str, Any]:
    """Get the current automated training schedule configuration."""
    return {
        "enabled": _schedule_config["enabled"],
        "cron": _schedule_config["cron"],
        "description": _schedule_config["description"],
        "last_run": _schedule_config["last_run"],
        "next_run": _schedule_config["next_run"],
        "total_runs": _schedule_config["total_runs"],
    }


class ScheduleUpdate(BaseModel):
    enabled: bool | None = None
    cron: str | None = Field(
        default=None,
        pattern=r"^\S+ \S+ \S+ \S+ \S+$",
        description="5-field cron expression: minute hour day month day_of_week",
    )


@router.put("/api/training/schedule")
async def update_training_schedule(body: ScheduleUpdate) -> dict[str, Any]:
    """Update the automated training schedule."""
    global _schedule_config

    if body.enabled is not None:
        _schedule_config["enabled"] = body.enabled

    if body.cron is not None:
        _schedule_config["cron"] = body.cron

    return {
        "enabled": _schedule_config["enabled"],
        "cron": _schedule_config["cron"],
        "description": _schedule_config["description"],
        "next_run": _schedule_config["next_run"],
        "message": "Schedule updated",
    }


@router.post("/api/seal/cycle")
async def trigger_seal_cycle(
    dry_run: bool = Query(False, description="Generate curriculum only, skip training"),
):
    """Execute a single SEAL autonomous self-improvement cycle."""
    try:
        from src.training.phase3_seal import SealOrchestrator
        from src.training.seal_types import SealConfig

        seal = SealOrchestrator(config=SealConfig(), capture_engine=_capture_engine)
        seal.load_state()
        result = await asyncio.to_thread(seal.run_cycle, dry_run=dry_run)

        return {"seal": result}
    except ImportError as e:
        raise HTTPException(status_code=501, detail=f"SEAL not available: {e}")
    except Exception as e:
        logger.error(f"SEAL cycle error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/seal/status")
async def get_seal_status():
    """Get SEAL Phase 3 system status."""
    try:
        from src.training.phase3_seal import SealOrchestrator
        from src.training.seal_types import SealConfig

        seal = SealOrchestrator(config=SealConfig(), capture_engine=_capture_engine)
        seal.load_state()
        return seal.status()
    except ImportError as e:
        raise HTTPException(status_code=501, detail=f"SEAL not available: {e}")
    except Exception as e:
        logger.error(f"SEAL status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
