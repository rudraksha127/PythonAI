"""
ForgeAI Ecosystem Metrics & Sync Daemon Routes
================================================
Handles /api/forgeai/ecosystem-metrics endpoint and the auto-sync daemon status.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter

from src.cli import VERSION

logger = logging.getLogger("forgeai.api.ecosystem")
router = APIRouter(tags=["Ecosystem"])

# ── Shared state references (injected at mount time) ────────────
_capture_engine = None
_active_training_run = None
_schedule_config = None
_sync_daemon_status = None
_start_time = None
_health_check_fn = None
_rag_backend_info_fn = None


def set_state(
    *,
    capture_engine,
    active_training_run_getter,
    schedule_config,
    sync_daemon_status,
    start_time,
    health_check_fn,
    rag_backend_info_fn,
):
    """Inject shared state from the main server module."""
    global _capture_engine, _active_training_run
    global _schedule_config, _sync_daemon_status
    global _start_time, _health_check_fn, _rag_backend_info_fn
    _capture_engine = capture_engine
    _active_training_run = active_training_run_getter
    _schedule_config = schedule_config
    _sync_daemon_status = sync_daemon_status
    _start_time = start_time
    _health_check_fn = health_check_fn
    _rag_backend_info_fn = rag_backend_info_fn


@router.get("/api/forgeai/ecosystem-metrics")
async def forgeai_ecosystem_metrics() -> dict[str, Any]:
    """Aggregated ecosystem metrics for cross-service consumption.

    This is the endpoint that Rudra-bots' `/api/forgeai/fetch` calls to
    pull live data from PythonAI.  Previously missing — causing the
    dashboard to always show cached data.
    """
    # Server health
    health_data = await _health_check_fn() if _health_check_fn else {}
    server_info = {
        "status": "healthy",
        "version": VERSION,
        "uptime_seconds": round(time.time() - (_start_time or time.time())),
    }

    # Capture statistics
    stats = {}
    if _capture_engine is not None:
        try:
            stats = _capture_engine.get_statistics()
        except Exception:
            pass

    # Acceptance rate time-series
    acceptance_rates = []
    if _capture_engine is not None:
        try:
            acceptance_rates = _capture_engine.get_acceptance_rate(days=84)
        except Exception:
            pass

    # Training info
    active_run = _active_training_run() if callable(_active_training_run) else _active_training_run
    training_info = {
        "active_run": active_run,
        "history": [],
        "schedule": {
            "enabled": _schedule_config["enabled"],
            "cron": _schedule_config["cron"],
            "description": _schedule_config["description"],
            "last_run": _schedule_config["last_run"],
            "next_run": _schedule_config["next_run"],
            "total_runs": _schedule_config["total_runs"],
        } if _schedule_config else {},
    }
    if _capture_engine is not None:
        try:
            training_info["history"] = _capture_engine.get_training_runs(limit=10)
        except Exception:
            pass

    # RAG info
    rag_info = _rag_backend_info_fn() if _rag_backend_info_fn else {}

    # Signal distribution (for charts)
    signal_dist = []
    signal_labels = {
        "accept": "Accept",
        "reject": "Reject",
        "edit": "Edit",
        "pr_merge": "PR Merge",
        "test_pass": "Test Pass",
        "test_fail": "Test Fail",
    }
    sbt = stats.get("signals_by_type", {})
    for name, count in sbt.items():
        signal_dist.append({"name": signal_labels.get(name, name.capitalize()), "value": count})

    # Sync daemon status
    sync_info = {
        "running": _sync_daemon_status.get("running", False),
        "last_sync_time": _sync_daemon_status.get("last_sync_time"),
        "total_syncs": _sync_daemon_status.get("total_syncs", 0),
        "fail_count": _sync_daemon_status.get("fail_count", 0),
        "consecutive_fails": _sync_daemon_status.get("consecutive_fails", 0),
        "last_sync_result": _sync_daemon_status.get("last_sync_result"),
        "started_at": _sync_daemon_status.get("started_at"),
        "interval": _sync_daemon_status.get("interval", 30),
    } if _sync_daemon_status else {}

    # Arsenal tools summary
    arsenal_info = {"total": 0, "installed": 0}
    try:
        from src.integrations.arsenal_integrations import check_arsenal_status
        a = check_arsenal_status()
        arsenal_info = {"total": a["total"], "installed": a["installed"], "missing": a["missing"]}
    except Exception:
        pass

    return {
        "server": server_info,
        "statistics": stats,
        "training": training_info,
        "rag": rag_info,
        "signal_distribution": signal_dist,
        "sync_daemon": sync_info,
        "arsenal": arsenal_info,
        "health": health_data,
        "acceptance_rates": acceptance_rates,
    }
