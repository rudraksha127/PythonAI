"""
ForgeAI TTS (Test-Time Scaling) & Benchmark Routes
====================================================
Handles /api/tts/* configuration and /api/benchmark/* report endpoints.
"""
from __future__ import annotations

import datetime
import json
import logging
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("forgeai.api.tts")
router = APIRouter(tags=["TTS & Benchmark"])

# ── Shared state references (injected at mount time) ────────────
_tts_config = None
_tts_pipeline = None
_BENCHMARK_DIR: Path = Path(__file__).resolve().parent.parent.parent / "data" / "benchmark"


def set_state(*, tts_config, tts_pipeline):
    """Inject shared state from the main server module."""
    global _tts_config, _tts_pipeline
    _tts_config = tts_config
    _tts_pipeline = tts_pipeline


# ── TTS Config Update Model ────────────────────────────────────

class TTSConfigUpdateRequest(BaseModel):
    """Update Test-Time Scaling configuration."""
    enabled: bool | None = None
    complexity_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    num_initial_rollouts: int | None = Field(default=None, ge=1, le=20)
    num_pdr_rollouts: int | None = Field(default=None, ge=1, le=10)


# ── TTS Endpoints ──────────────────────────────────────────────

@router.get("/api/tts/status")
async def tts_status() -> dict[str, Any]:
    """
    Get Test-Time Scaling pipeline status and statistics.

    Returns complexity distribution, number of hard tasks routed,
    pipeline performance stats, and current configuration.
    """
    stats = _tts_pipeline.get_stats() if _tts_pipeline else {}
    return {
        "enabled": _tts_config.enabled if _tts_config else False,
        "pipeline_initialized": _tts_pipeline is not None,
        "config": {
            "complexity_threshold": _tts_config.complexity_threshold,
            "num_initial_rollouts": _tts_config.num_initial_rollouts,
            "num_pdr_rollouts": _tts_config.num_pdr_rollouts,
        } if _tts_config else {},
        "stats": stats,
    }


@router.put("/api/tts/config")
async def tts_update_config(body: TTSConfigUpdateRequest) -> dict[str, Any]:
    """
    Update Test-Time Scaling configuration at runtime.

    Changes take effect on the next agent chat request.
    Restart the server to persist changes to environment variables.
    """
    if _tts_config is None:
        raise HTTPException(status_code=503, detail="TTS not initialized")

    if body.enabled is not None:
        _tts_config.enabled = body.enabled
    if body.complexity_threshold is not None:
        _tts_config.complexity_threshold = body.complexity_threshold
    if body.num_initial_rollouts is not None:
        _tts_config.num_initial_rollouts = body.num_initial_rollouts
    if body.num_pdr_rollouts is not None:
        _tts_config.num_pdr_rollouts = body.num_pdr_rollouts

    logger.info(f"TTS config updated: enabled={_tts_config.enabled}, threshold={_tts_config.complexity_threshold}")

    return {
        "status": "updated",
        "config": {
            "enabled": _tts_config.enabled,
            "complexity_threshold": _tts_config.complexity_threshold,
            "num_initial_rollouts": _tts_config.num_initial_rollouts,
            "num_pdr_rollouts": _tts_config.num_pdr_rollouts,
        },
    }


@router.post("/api/tts/reset-stats")
async def tts_reset_stats() -> dict[str, Any]:
    """Reset Test-Time Scaling pipeline statistics."""
    if _tts_pipeline:
        _tts_pipeline.reset_stats()
        return {"status": "stats_reset"}
    return {"status": "not_initialized"}


# ── Benchmark Report Endpoints ────────────────────────────

@router.get("/api/benchmark/reports")
async def list_benchmark_reports() -> dict[str, Any]:
    """
    List all saved benchmark reports with metadata.
    Returns a list of report files sorted by recency.
    """
    if not _BENCHMARK_DIR.exists():
        return {"success": True, "reports": []}

    reports = []
    for f in sorted(_BENCHMARK_DIR.glob("rag_benchmark_*.json"), reverse=True):
        try:
            stat = f.stat()
            ts_str = f.name.replace("rag_benchmark_", "").replace(".json", "")
            try:
                ts = datetime.datetime.strptime(ts_str, "%Y%m%d_%H%M%S").timestamp()
            except ValueError:
                ts = stat.st_mtime
            reports.append({
                "filename": f.name,
                "path": str(f.relative_to(_BENCHMARK_DIR.parent)),
                "timestamp": ts or stat.st_mtime,
                "size_bytes": stat.st_size,
            })
        except Exception as e:
            logger.warning(f"Error reading benchmark report {f.name}: {e}")

    return {"success": True, "reports": reports}


@router.get("/api/benchmark/report/{filename}")
async def get_benchmark_report(filename: str) -> dict[str, Any]:
    """
    Get a specific benchmark report by filename.
    """
    safe_name = Path(filename).name
    if ".." in safe_name or "/" in safe_name or "\\" in safe_name:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = _BENCHMARK_DIR / safe_name
    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail=f"Report '{safe_name}' not found")

    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
        return {"success": True, "report": data}
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse report: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
