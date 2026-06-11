"""
ForgeAI Cloud Realtime
======================
Supabase Realtime integration for live training progress, signal events,
and dashboard updates.

Uses the Supabase async client's channel subscription system.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

from src.cloud.supabase_client import get_async_supabase_client, get_supabase_service_client

logger = logging.getLogger("forgeai.cloud.realtime")


class RealTimeChannel:
    """Manages a Supabase Realtime channel subscription."""

    def __init__(self, channel_name: str, table: str, event: str = "*"):
        self.channel_name = channel_name
        self.table = table
        self.event = event
        self._callback: Optional[Callable] = None
        self._channel: Any = None

    async def subscribe(self, callback: Callable) -> bool:
        """Subscribe to a Realtime channel.

        Args:
            callback: Function to call with each event payload

        Returns:
            bool: Whether subscription was successful
        """
        client = await get_async_supabase_client()
        if client is None:
            logger.warning("Realtime subscription skipped: cloud not configured")
            return False

        try:
            self._callback = callback

            self._channel = client.channel(self.channel_name)

            def _handle_event(payload: Any) -> None:
                try:
                    if self._callback:
                        self._callback(payload)
                except Exception as e:
                    logger.error(f"Realtime callback error: {e}")

            self._channel.on(
                "postgres_changes",
                {
                    "event": self.event,
                    "schema": "public",
                    "table": self.table,
                },
                _handle_event,
            )

            await self._channel.subscribe()
            logger.info(f"Subscribed to Realtime channel: {self.channel_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to subscribe to Realtime: {e}")
            return False

    async def unsubscribe(self) -> None:
        """Unsubscribe from the Realtime channel."""
        if self._channel:
            try:
                await self._channel.unsubscribe()
                logger.info(f"Unsubscribed from Realtime channel: {self.channel_name}")
            except Exception as e:
                logger.warning(f"Failed to unsubscribe: {e}")
            self._channel = None
            self._callback = None


# ─── Global Channels ────────────────────────────────────────────

_training_channel: Optional[RealTimeChannel] = None
_signals_channel: Optional[RealTimeChannel] = None


async def subscribe_training_progress(callback: Callable) -> bool:
    """Subscribe to training progress updates."""
    global _training_channel
    _training_channel = RealTimeChannel("training-progress", "training_runs")
    return await _training_channel.subscribe(callback)


async def subscribe_signals(callback: Callable) -> bool:
    """Subscribe to signal capture events."""
    global _signals_channel
    _signals_channel = RealTimeChannel("capture-signals", "capture_signals")
    return await _signals_channel.subscribe(callback)


async def unsubscribe_all() -> None:
    """Unsubscribe from all Realtime channels."""
    global _training_channel, _signals_channel
    if _training_channel:
        await _training_channel.unsubscribe()
    if _signals_channel:
        await _signals_channel.unsubscribe()


# ─── Broadcasting (Service-side) ────────────────────────────────


async def broadcast_training_progress(
    user_id: str,
    run_id: str,
    progress: float,
    loss: Optional[float] = None,
    step: Optional[int] = None,
) -> bool:
    """Broadcast training progress update to Realtime subscribers.

    Uses the service_role client to insert/update the training_runs table,
    which triggers Realtime broadcasts to all subscribed dashboard clients.
    """
    service = get_supabase_service_client()
    if service is None:
        return False

    try:
        from datetime import datetime, timezone

        service.table("training_runs").upsert({
            "run_id": run_id,
            "user_id": user_id,
            "status": "running",
            "progress": progress,
            "loss": loss,
            "step": step,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="run_id").execute()
        return True
    except Exception as e:
        logger.warning(f"Failed to broadcast training progress: {e}")
        return False


async def broadcast_signal_event(
    user_id: str,
    signal_type: str,
    signal_id: str,
    metadata: Optional[dict] = None,
) -> bool:
    """Broadcast a signal capture event to Realtime subscribers."""
    service = get_supabase_service_client()
    if service is None:
        return False

    try:
        from datetime import datetime, timezone

        service.table("capture_signals").insert({
            "id": signal_id,
            "user_id": user_id,
            "signal_type": signal_type,
            "metadata": json.dumps(metadata or {}),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        return True
    except Exception as e:
        logger.warning(f"Failed to broadcast signal event: {e}")
        return False
