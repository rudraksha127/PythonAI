"""
ForgeAI Integration Routes — Connect PythonAI to Rudra-bots Dashboard
======================================================================

Endpoints:
  GET  /api/forgeai/health     — Health check for cross-project connectivity
  POST /api/forgeai/metrics    — Receive metrics from PythonAI
  GET  /api/forgeai/status     — Full ecosystem status from PythonAI

Integration:
  - Rudra-bots acts as a visualization layer for ForgeAI's self-improvement data
  - Accepts push metrics from PythonAI's CaptureEngine
  - Provides a unified status view for the ecosystem
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger("forgeai.routes")

# In-memory store for received metrics
_metrics_store: dict[str, list[dict[str, Any]]] = {
    "acceptance_rate": [],
    "training_run": [],
    "capture_stats": [],
    "forgeai_sync": [],
}

router = APIRouter(prefix="/api/forgeai", tags=["ForgeAI Integration"])


@router.get("/health")
async def forgeai_health():
    """Health check for cross-project connectivity.

    Returns the status of this ForgeAI integration endpoint.
    """
    return {
        "status": "healthy",
        "service": "Rudra-bots ForgeAI Integration",
        "version": "1.0.0",
        "timestamp": time.time(),
        "metrics_received": sum(len(v) for v in _metrics_store.values()),
    }


@router.post("/metrics")
async def receive_metrics(request: Request):
    """Receive metrics pushed from PythonAI's CaptureEngine.

    Accepts various metric types:
      - acceptance_rate: Daily acceptance/reject/edit stats
      - training_run: Training pipeline run results
      - capture_stats: Overall capture engine statistics
      - forgeai_sync: Full data sync from PythonAI
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    metric_type = body.get("type", "unknown")
    source = body.get("source", "unknown")

    logger.info(f"Received {metric_type} metrics from {source}")

    # Store in appropriate bucket
    if metric_type in _metrics_store:
        bucket = _metrics_store[metric_type]
        bucket.append(body)
        # Keep only last 1000 entries per type
        if len(bucket) > 1000:
            bucket[:] = bucket[-500:]
    else:
        # Unknown type — store in a general bucket
        _metrics_store.setdefault("other", []).append(body)

    return {"received": True, "type": metric_type, "stored": len(_metrics_store.get(metric_type, []))}


@router.get("/metrics")
async def get_metrics(limit: int = 100):
    """Get stored ForgeAI metrics for dashboard display.

    Args:
        limit: Max entries per metric type
    """
    result = {}
    for metric_type, entries in _metrics_store.items():
        if metric_type == "other":
            continue
        result[metric_type] = entries[-limit:] if entries else []

    return {
        "metrics": result,
        "total": sum(len(v) for v in result.values()),
        "last_updated": time.time(),
    }


@router.get("/status")
async def get_ecosystem_status():
    """Get a summarized view of the ForgeAI ecosystem status.

    Combines locally stored metrics into a dashboard-friendly response.
    """
    # Compute summary from stored metrics
    total_signals = 0
    latest_rate = 0.0
    total_runs = 0

    # Check for forgeai_sync data
    sync_entries = _metrics_store.get("forgeai_sync", [])
    if sync_entries:
        latest_sync = sync_entries[-1]
        data = latest_sync.get("data", {})
        stats = data.get("statistics", {})
        signals_by_type = stats.get("signals_by_type", {})
        total_signals = sum(signals_by_type.values())
        latest_rate = stats.get("overall_acceptance_rate", 0)

        runs = data.get("training_runs", [])
        total_runs = len(runs)

    # Check acceptance_rate entries
    rate_entries = _metrics_store.get("acceptance_rate", [])
    if rate_entries:
        latest_rate = rate_entries[-1].get("rate", latest_rate)

    return {
        "status": "connected",
        "last_sync": sync_entries[-1].get("timestamp") if sync_entries else None,
        "total_signals": total_signals,
        "acceptance_rate": latest_rate,
        "training_runs": total_runs,
        "pythonai": {
            "connected": len(sync_entries) > 0 or len(rate_entries) > 0,
            "last_contact": sync_entries[-1].get("timestamp", 0) if sync_entries else 0,
        },
    }


@router.get("/fetch")
async def fetch_from_pythonai():
    """Fetch the latest ForgeAI ecosystem metrics from PythonAI server.

    This acts as a proxy/cache: pulls data from PythonAI (port 7337),
    stores it locally, and returns the result for dashboard display.
    """
    pythonai_url = os.environ.get("PYTHONAI_URL", "http://localhost:7337")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{pythonai_url}/api/forgeai/ecosystem-metrics")
            if response.status_code == 200:
                data = response.json()
                # Store in local metrics store
                _metrics_store["forgeai_sync"].append({
                    "type": "forgeai_sync",
                    "source": "PythonAI",
                    "timestamp": time.time(),
                    "data": data,
                })
                # Trim to last 100
                if len(_metrics_store["forgeai_sync"]) > 100:
                    _metrics_store["forgeai_sync"] = _metrics_store["forgeai_sync"][-50:]
                return {"success": True, "data": data, "cached": False}
            return {"success": False, "error": f"PythonAI returned HTTP {response.status_code}"}
    except httpx.ConnectError:
        # Return cached data if available
        cache = _metrics_store.get("forgeai_sync", [])
        if cache:
            return {"success": True, "data": cache[-1]["data"], "cached": True}
        return {"success": False, "error": "PythonAI server unreachable", "hint": "Start PythonAI server on port 7337"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/metrics")
async def clear_metrics():
    """Clear all stored ForgeAI metrics."""
    for key in _metrics_store:
        _metrics_store[key].clear()
    return {"cleared": True}


