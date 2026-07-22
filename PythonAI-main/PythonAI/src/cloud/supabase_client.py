"""
ForgeAI Supabase Client
========================
Thin wrapper around supabase-py for authentication, database queries,
and realtime subscriptions.

Gracefully handles missing credentials — all cloud features are optional.
"""

from __future__ import annotations

import logging
from typing import Any

from supabase import create_async_client, create_client

from src.cloud.config import get_cloud_config

logger = logging.getLogger("forgeai.cloud.supabase")


# Lazy-loaded clients
_sync_client: Any = None
_async_client: Any = None
_service_client: Any = None


def get_supabase_client() -> Any:
    """Get the Supabase sync client (anon key).

    Returns None if cloud is not configured.
    Suitable for server-side operations in non-async contexts.
    """
    global _sync_client
    if _sync_client is not None:
        return _sync_client

    cfg = get_cloud_config()
    if not cfg.is_supabase_configured:
        return None

    try:
        _sync_client = create_client(cfg.supabase_url, cfg.supabase_anon_key)
        logger.info("Supabase sync client initialized")
        return _sync_client
    except Exception as e:
        logger.error(f"Failed to initialize Supabase sync client: {e}")
        return None


async def get_async_supabase_client() -> Any:
    """Get the Supabase async client (anon key).

    Preferred for FastAPI async endpoints.
    """
    global _async_client
    if _async_client is not None:
        return _async_client

    cfg = get_cloud_config()
    if not cfg.is_supabase_configured:
        return None

    try:
        _async_client = await create_async_client(cfg.supabase_url, cfg.supabase_anon_key)
        logger.info("Supabase async client initialized")
        return _async_client
    except Exception as e:
        logger.error(f"Failed to initialize Supabase async client: {e}")
        return None


def get_supabase_service_client() -> Any:
    """Get the Supabase service_role client (admin).

    CAREFUL: this bypasses RLS. Only use for admin operations
    (webhook processing, profile creation during signup).
    Returns None if service_role_key is not set.
    """
    global _service_client
    if _service_client is not None:
        return _service_client

    cfg = get_cloud_config()
    if not cfg.supabase_service_role_key:
        logger.warning("Supabase service_role key not configured — admin operations disabled")
        return None

    try:
        _service_client = create_client(cfg.supabase_url, cfg.supabase_service_role_key)
        logger.info("Supabase service_role client initialized")
        return _service_client
    except Exception as e:
        logger.error(f"Failed to initialize Supabase service client: {e}")
        return None


def is_cloud_enabled() -> bool:
    """Check if cloud features are available."""
    cfg = get_cloud_config()
    return cfg.cloud_enabled and cfg.is_supabase_configured


def reset_clients():
    """Reset all cached clients (for testing / config reload)."""
    global _sync_client, _async_client, _service_client
    _sync_client = None
    _async_client = None
    _service_client = None
    logger.info("Supabase clients reset")
