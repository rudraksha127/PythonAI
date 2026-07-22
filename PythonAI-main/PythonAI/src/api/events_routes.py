"""
ForgeAI Event Capture & Metrics Routes
=======================================
Handles /api/events (accept/reject/edit/pr_merge) and /api/metrics/*.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger("forgeai.api.events")
router = APIRouter(tags=["Events & Metrics"])


# ── Pydantic Models ─────────────────────────────────────────────

class EventPayload(BaseModel):
    """Event from VS Code extension."""

    event_type: str = Field(..., description="accept, reject, edit, pr_merge, test_pass, test_fail")
    session_id: str
    project_id: str
    file_path: str
    line_number: int = 0
    language: str
    framework: str | None = None
    project_type: str = "general"
    suggestion: str
    suggestion_metadata: dict = Field(default_factory=dict)
    context_before: str = ""
    context_after: str = ""
    full_context: str = ""
    final_code: str | None = None
    edit_distance: float = 0.0
    developer_id: str | None = None

    @field_validator("event_type")
    @classmethod
    def _validate_event_type(cls, v: str) -> str:
        valid = {"accept", "reject", "edit", "pr_merge", "test_pass", "test_fail"}
        if v not in valid:
            raise ValueError(f"Invalid event_type. Must be one of: {valid}")
        return v


# ── Shared state references (injected at mount time) ────────────
# These are set by server.py during startup via `set_state()`

_capture_engine = None
_ws_clients: list = []
_broadcast_fn = None


def set_state(*, capture_engine, ws_clients, broadcast_fn):
    """Inject shared state from the main server module."""
    global _capture_engine, _ws_clients, _broadcast_fn
    _capture_engine = capture_engine
    _ws_clients = ws_clients
    _broadcast_fn = broadcast_fn


async def _broadcast_to_dashboards(message: dict[str, Any]):
    """Broadcast to dashboard clients via the injected function."""
    if _broadcast_fn is not None:
        await _broadcast_fn(message)


# ── Event Capture ───────────────────────────────────────────────

@router.post("/api/events")
async def capture_event(payload: EventPayload) -> dict[str, Any]:
    """
    Capture a developer signal (accept/reject/edit).
    Called by VS Code extension via WebSocket or HTTP.
    """
    if _capture_engine is None:
        raise HTTPException(status_code=503, detail="Capture engine not initialized")

    start = time.time()
    signal_id = None

    try:
        if payload.event_type == "accept":
            signal_id = _capture_engine.capture_accept(
                suggestion=payload.suggestion,
                file_path=payload.file_path,
                line_number=payload.line_number,
                language=payload.language,
                context_before=payload.context_before,
                context_after=payload.context_after,
                full_context=payload.full_context,
                suggestion_metadata=payload.suggestion_metadata,
                framework=payload.framework,
                project_type=payload.project_type,
                developer_id=payload.developer_id,
            )
        elif payload.event_type == "reject":
            signal_id = _capture_engine.capture_reject(
                suggestion=payload.suggestion,
                file_path=payload.file_path,
                line_number=payload.line_number,
                language=payload.language,
                context_before=payload.context_before,
                context_after=payload.context_after,
                full_context=payload.full_context,
                suggestion_metadata=payload.suggestion_metadata,
                framework=payload.framework,
                project_type=payload.project_type,
                developer_id=payload.developer_id,
            )
        elif payload.event_type == "edit":
            if not payload.final_code:
                raise HTTPException(status_code=400, detail="final_code required for edit events")
            signal_id = _capture_engine.capture_edit(
                original_suggestion=payload.suggestion,
                final_code=payload.final_code,
                file_path=payload.file_path,
                line_number=payload.line_number,
                language=payload.language,
                context_before=payload.context_before,
                context_after=payload.context_after,
                full_context=payload.full_context,
                suggestion_metadata=payload.suggestion_metadata,
                framework=payload.framework,
                project_type=payload.project_type,
                developer_id=payload.developer_id,
            )
        elif payload.event_type == "pr_merge":
            signal_id = _capture_engine.capture_pr_merge(
                file_path=payload.file_path,
                language=payload.language,
                code_content=payload.suggestion,
                pr_number=payload.suggestion_metadata.get("pr_number", 0),
                branch_name=payload.suggestion_metadata.get("branch", ""),
                git_sha=payload.suggestion_metadata.get("git_sha", ""),
                context_before=payload.context_before,
                context_after=payload.context_after,
                full_context=payload.full_context,
                framework=payload.framework,
                project_type=payload.project_type,
                developer_id=payload.developer_id,
            )

        elapsed_ms = (time.time() - start) * 1000
        logger.info(f"Captured {payload.event_type} event: {signal_id} in {elapsed_ms:.1f}ms")

        # Broadcast to dashboard clients
        await _broadcast_to_dashboards(
            {
                "type": "event_captured",
                "event_type": payload.event_type,
                "signal_id": signal_id,
                "timestamp": time.time(),
            }
        )

        return {"event_id": signal_id, "captured": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error capturing event: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to capture event")


# ── Acceptance Rate Metric ──────────────────────────────────────

@router.get("/api/metrics/acceptance-rate")
async def get_acceptance_rate(project_id: str | None = None, weeks: int = 12) -> dict[str, Any]:
    """Get acceptance rate over time for dashboard chart."""
    if _capture_engine is None:
        raise HTTPException(status_code=503, detail="Capture engine not initialized")

    days = weeks * 7
    rates = _capture_engine.get_acceptance_rate(days=days)

    # Compute training run markers
    runs = _capture_engine.get_training_runs(limit=20)
    markers = [
        {"timestamp": r["timestamp"], "delta": r["acceptance_delta"], "signals": r["signals_used"]} for r in runs
    ]

    return {"data": rates, "training_markers": markers}
