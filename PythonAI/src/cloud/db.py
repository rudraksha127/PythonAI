"""
ForgeAI Cloud Database
=======================
Supabase-backed database operations for users, projects, training runs,
and signal syncing.

Uses the Supabase Python SDK's fluent query interface.
All functions are async for FastAPI compatibility.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.cloud.supabase_client import get_supabase_service_client

logger = logging.getLogger("forgeai.cloud.db")


class CloudDB:
    """Cloud database operations using Supabase."""

    @staticmethod
    async def get_profile(user_id: str) -> dict | None:
        """Get a user's profile by ID."""
        service = get_supabase_service_client()
        if service is None:
            return None
        try:
            resp = service.table("profiles").select("*").eq("id", user_id).single().execute()
            return resp.data
        except Exception as e:
            logger.warning(f"Failed to get profile {user_id}: {e}")
            return None

    @staticmethod
    async def update_profile(user_id: str, updates: dict) -> bool:
        """Update a user's profile. Returns True on success."""
        service = get_supabase_service_client()
        if service is None:
            return False
        try:
            updates["updated_at"] = datetime.now(timezone.utc).isoformat()
            service.table("profiles").update(updates).eq("id", user_id).execute()
            return True
        except Exception as e:
            logger.warning(f"Failed to update profile {user_id}: {e}")
            return False

    @staticmethod
    async def list_projects(user_id: str) -> list[dict]:
        """List all projects for a user."""
        service = get_supabase_service_client()
        if service is None:
            return []
        try:
            resp = service.table("projects").select("*").eq("user_id", user_id).order("updated_at", desc=True).execute()
            return resp.data or []
        except Exception as e:
            logger.warning(f"Failed to list projects for {user_id}: {e}")
            return []

    @staticmethod
    async def upsert_project(user_id: str, project: dict) -> str | None:
        """Create or update a project. Returns project ID."""
        service = get_supabase_service_client()
        if service is None:
            return None
        try:
            now = datetime.now(timezone.utc).isoformat()
            project["user_id"] = user_id
            project["updated_at"] = now
            if "created_at" not in project:
                project["created_at"] = now

            resp = service.table("projects").upsert(project, on_conflict="id").execute()
            if resp.data:
                return resp.data[0]["id"]
            return None
        except Exception as e:
            logger.warning(f"Failed to upsert project: {e}")
            return None

    @staticmethod
    async def upsert_training_run(user_id: str, run: dict) -> str | None:
        """Record a training run in the cloud."""
        service = get_supabase_service_client()
        if service is None:
            return None
        try:
            now = datetime.now(timezone.utc).isoformat()
            run["user_id"] = user_id
            run["updated_at"] = now
            if "created_at" not in run:
                run["created_at"] = now

            resp = service.table("training_runs").upsert(run, on_conflict="run_id").execute()
            if resp.data:
                return resp.data[0]["run_id"]
            return None
        except Exception as e:
            logger.warning(f"Failed to upsert training run: {e}")
            return None

    @staticmethod
    async def list_training_runs(user_id: str, limit: int = 20) -> list[dict]:
        """Get recent training runs for a user."""
        service = get_supabase_service_client()
        if service is None:
            return []
        try:
            resp = (
                service.table("training_runs")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.warning(f"Failed to list training runs: {e}")
            return []

    @staticmethod
    async def sync_signal(user_id: str, signal: dict) -> str | None:
        """Sync a captured signal to the cloud database."""
        service = get_supabase_service_client()
        if service is None:
            return None
        try:
            signal["user_id"] = user_id
            if "created_at" not in signal:
                signal["created_at"] = datetime.now(timezone.utc).isoformat()

            resp = service.table("capture_signals").insert(signal).execute()
            if resp.data:
                return resp.data[0]["id"]
            return None
        except Exception as e:
            logger.warning(f"Failed to sync signal: {e}")
            return None

    @staticmethod
    async def get_signal_count(user_id: str, days: int = 30) -> int:
        """Count signals captured in the last N days."""
        service = get_supabase_service_client()
        if service is None:
            return 0
        try:
            from datetime import timedelta

            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            resp = (
                service.table("capture_signals")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .gte("created_at", cutoff)
                .execute()
            )
            return resp.count or 0
        except Exception as e:
            logger.warning(f"Failed to count signals: {e}")
            return 0

    @staticmethod
    async def get_acceptance_rate(user_id: str, days: int = 30) -> dict:
        """Get acceptance rate stats from the cloud."""
        service = get_supabase_service_client()
        if service is None:
            return {"accepts": 0, "rejects": 0, "edits": 0, "acceptance_rate": 0.0}
        try:
            from datetime import timedelta

            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            resp = (
                service.table("capture_signals")
                .select("signal_type")
                .eq("user_id", user_id)
                .gte("created_at", cutoff)
                .execute()
            )
            signals = resp.data or []
            accepts = sum(1 for s in signals if s.get("signal_type") == "accept")
            rejects = sum(1 for s in signals if s.get("signal_type") == "reject")
            edits = sum(1 for s in signals if s.get("signal_type") == "edit")
            total = accepts + rejects + edits
            rate = (accepts / total * 100) if total > 0 else 0.0
            return {"accepts": accepts, "rejects": rejects, "edits": edits, "acceptance_rate": round(rate, 1)}
        except Exception as e:
            logger.warning(f"Failed to get acceptance rate: {e}")
            return {"accepts": 0, "rejects": 0, "edits": 0, "acceptance_rate": 0.0}


# ─── Convenience functions ───────────────────────────────────────


async def get_or_create_profile(user_id: str, email: str, username: str) -> dict | None:
    """Get a user profile or create one if it doesn't exist."""
    profile = await CloudDB.get_profile(user_id)
    if profile:
        return profile

    # Create new profile
    service = get_supabase_service_client()
    if service is None:
        return None

    now = datetime.now(timezone.utc).isoformat()
    try:
        resp = (
            service.table("profiles")
            .insert(
                {
                    "id": user_id,
                    "email": email,
                    "username": username,
                    "plan_tier": "free",
                    "subscription_status": "inactive",
                    "created_at": now,
                    "updated_at": now,
                }
            )
            .execute()
        )
        return resp.data[0] if resp.data else None
    except Exception as e:
        logger.warning(f"Failed to create profile: {e}")
        return None


async def upsert_project(user_id: str, project: dict) -> str | None:
    """Convenience wrapper for CloudDB.upsert_project."""
    return await CloudDB.upsert_project(user_id, project)


async def upsert_training_run(user_id: str, run: dict) -> str | None:
    """Convenience wrapper for CloudDB.upsert_training_run."""
    return await CloudDB.upsert_training_run(user_id, run)


async def get_user_subscription(user_id: str) -> dict:
    """Get a user's subscription info from their profile."""
    profile = await CloudDB.get_profile(user_id)
    if not profile:
        return {"plan_tier": "free", "subscription_status": "inactive", "stripe_customer_id": None}

    return {
        "plan_tier": profile.get("plan_tier", "free"),
        "subscription_status": profile.get("subscription_status", "inactive"),
        "stripe_customer_id": profile.get("stripe_customer_id"),
        "current_period_end": profile.get("current_period_end"),
    }
