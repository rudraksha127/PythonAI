"""
Rudra-bots Bridge — Connect PythonAI to the Rudra-bots (Odysseus) Dashboard
============================================================================

Pushes ForgeAI metrics, training data, and acceptance rates to Rudra-bots
dashboard so users can see their AI improvement stats alongside chat.

Architecture:
  PythonAI ──HTTP POST──▶ Rudra-bots /api/forgeai/metrics
           ◀──HTTP GET──── Rudra-bots /api/forgeai/health
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger("forgeai.integration.rudra_bots")

# Default Rudra-bots server URL
DEFAULT_RUDRA_BOTS_URL = "http://localhost:7000"


def get_rudra_bots_url() -> str:
    """Get the Rudra-bots URL from config or environment."""
    import os

    return os.environ.get("RUDRA_BOTS_URL", DEFAULT_RUDRA_BOTS_URL)


async def check_health() -> dict[str, Any]:
    """Check if Rudra-bots dashboard is running and healthy."""
    url = f"{get_rudra_bots_url()}/api/health"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                return {"running": True, "status": "healthy"}
            return {"running": True, "status": "degraded", "code": response.status_code}
    except httpx.ConnectError:
        return {"running": False, "status": "unreachable"}
    except Exception as e:
        return {"running": False, "status": "error", "error": str(e)}


async def send_metrics(metrics: dict[str, Any]) -> bool:
    """Send ForgeAI metrics to Rudra-bots dashboard.

    Args:
        metrics: Dict with keys like:
            - type: "acceptance_rate" | "training_run" | "capture_stats"
            - Plus relevant data fields

    Returns:
        True if successfully sent
    """
    url = f"{get_rudra_bots_url()}/api/forgeai/metrics"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=metrics)
            if response.status_code in (200, 201):
                logger.debug(f"Metrics sent to Rudra-bots: {metrics.get('type', 'unknown')}")
                return True
            logger.warning(f"Failed to send metrics: HTTP {response.status_code}")
            return False
    except httpx.ConnectError:
        logger.debug("Rudra-bots not reachable (expected if not running)")
        return False
    except Exception as e:
        logger.warning(f"Error sending metrics to Rudra-bots: {e}")
        return False


async def send_acceptance_rate(date: str, rate: float, accepts: int, rejects: int, edits: int = 0):
    """Send acceptance rate data to Rudra-bots dashboard."""
    metrics = {
        "type": "acceptance_rate",
        "date": date,
        "rate": round(rate, 1),
        "accepts": accepts,
        "rejects": rejects,
        "edits": edits,
        "source": "PythonAI",
        "timestamp": time.time(),
    }
    return await send_metrics(metrics)


async def send_training_run(run_data: dict[str, Any]):
    """Send training run data to Rudra-bots dashboard.

    Args:
        run_data: Dict with run_id, model_name, signals_used,
                  acceptance_rate_before, acceptance_rate_after, etc.
    """
    metrics = {
        "type": "training_run",
        "source": "PythonAI",
        "timestamp": time.time(),
        **run_data,
    }
    return await send_metrics(metrics)


async def send_capture_stats(stats: dict[str, Any]):
    """Send capture engine statistics to Rudra-bots dashboard."""
    metrics = {
        "type": "capture_stats",
        "source": "PythonAI",
        "timestamp": time.time(),
        "data": stats,
    }
    return await send_metrics(metrics)


async def sync_all_to_dashboard():
    """Sync all ForgeAI data to Rudra-bots dashboard in one call."""
    from src.learning.capture_engine import CaptureEngine

    try:
        engine = CaptureEngine()
        stats = engine.get_statistics()
        rates = engine.get_acceptance_rate(days=7)
        runs = engine.get_training_runs(limit=5)

        payload = {
            "type": "forgeai_sync",
            "source": "PythonAI",
            "timestamp": time.time(),
            "data": {
                "statistics": stats,
                "acceptance_rates": rates,
                "training_runs": runs,
            },
        }

        return await send_metrics(payload)
    except Exception as e:
        logger.error(f"Failed to sync all data: {e}")
        return False
