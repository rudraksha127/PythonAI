"""
ForgeAI Cloud Auth
===================
Supabase-backed authentication for the ForgeAI cloud backend.

Provides JWT-based auth for API clients and integrates with
the existing local auth as a fallback.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from src.cloud.config import get_cloud_config
from src.cloud.supabase_client import get_async_supabase_client, get_supabase_service_client

logger = logging.getLogger("forgeai.cloud.auth")


@dataclass
class CloudUser:
    """Authenticated cloud user info."""
    id: str
    email: str
    username: str
    plan_tier: str = "free"
    subscription_status: str = "inactive"
    created_at: str = ""
    is_authenticated: bool = True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "username": self.username,
            "plan_tier": self.plan_tier,
            "subscription_status": self.subscription_status,
            "created_at": self.created_at,
        }


class CloudAuthError(Exception):
    """Raised when cloud authentication fails."""
    pass


# ─── Public Auth Functions ───────────────────────────────────────


async def sign_up(email: str, password: str, username: str) -> dict:
    """Register a new user via Supabase Auth.

    Returns {"user_id": ..., "email": ..., "session": ...} on success.
    Raises CloudAuthError on failure.
    """
    client = await get_async_supabase_client()
    if client is None:
        raise CloudAuthError("Cloud backend not configured")

    try:
        resp = await client.auth.sign_up({
            "email": email,
            "password": password,
            "options": {"data": {"username": username}},
        })

        user = resp.user
        if user is None:
            raise CloudAuthError("Sign-up returned no user")

        session = resp.session
        session_data = {
            "access_token": session.access_token if session else "",
            "refresh_token": session.refresh_token if session else "",
        } if session else {}

        # Create profile in public.profiles
        await _ensure_profile_exists(user.id, email, username)

        logger.info(f"Cloud user signed up: {email} (id={user.id})")
        return {
            "user_id": user.id,
            "email": user.email or email,
            "session": session_data,
            "requires_email_confirmation": bool(session is None),
        }

    except Exception as e:
        error_msg = str(e)
        if "already registered" in error_msg.lower():
            raise CloudAuthError("An account with this email already exists")
        raise CloudAuthError(f"Sign-up failed: {error_msg}")


async def sign_in(email: str, password: str) -> dict:
    """Authenticate a user via Supabase Auth.

    Returns {"user_id": ..., "email": ..., "session": ...} on success.
    """
    client = await get_async_supabase_client()
    if client is None:
        raise CloudAuthError("Cloud backend not configured")

    try:
        resp = await client.auth.sign_in_with_password({
            "email": email,
            "password": password,
        })

        user = resp.user
        if user is None:
            raise CloudAuthError("Invalid credentials")

        session = resp.session
        if session is None:
            raise CloudAuthError("No session returned")

        logger.info(f"Cloud user signed in: {email}")
        return {
            "user_id": user.id,
            "email": user.email or email,
            "session": {
                "access_token": session.access_token,
                "refresh_token": session.refresh_token,
                "expires_at": session.expires_at,
            },
        }

    except Exception as e:
        error_msg = str(e)
        if "invalid login credentials" in error_msg.lower():
            raise CloudAuthError("Invalid email or password")
        raise CloudAuthError(f"Sign-in failed: {error_msg}")


async def sign_out(access_token: str) -> dict:
    """Sign out a user by revoking their session via the service-role admin API.

    Uses the service_role client so we can revoke by user identity without
    depending on fragile mock-session workarounds. Falls back to async client
    sign-out if the service role is unavailable.
    """
    try:
        # First verify the token to get the user ID
        user = await verify_token(access_token)

        # Use service-role admin API to sign out
        service = get_supabase_service_client()
        if service is not None:
            try:
                service.auth.admin.sign_out(user.id)
                logger.info(f"Cloud user signed out (admin): {user.id}")
                return {"success": True}
            except Exception:
                pass  # Fall through to next method

        # Fallback: use async client with proper session
        client = await get_async_supabase_client()
        if client is None:
            raise CloudAuthError("Cloud backend not configured")

        # Set the session token on the client and sign out
        await client.auth.set_session(access_token, refresh_token="")
        await client.auth.sign_out()
        logger.info("Cloud user signed out (session)")
        return {"success": True}

    except CloudAuthError:
        raise
    except Exception as e:
        raise CloudAuthError(f"Sign-out failed: {e}")


async def verify_token(access_token: str) -> CloudUser:
    """Verify a JWT access token and return the authenticated user.

    Raises CloudAuthError if the token is invalid/expired.
    """
    client = get_supabase_service_client()
    if client is None:
        raise CloudAuthError("Cloud backend not configured")

    try:
        # Use service client to get user by JWT
        user_data = client.auth.get_user(access_token)
        user = user_data.user
        if user is None:
            raise CloudAuthError("Invalid token")

        user_id = user.id
        email = user.email or ""
        username = user.user_metadata.get("username", email.split("@")[0])

        # Fetch subscription status from profiles
        plan_tier = "free"
        subscription_status = "inactive"

        try:
            profile = (
                client.table("profiles")
                .select("plan_tier, subscription_status")
                .eq("id", user_id)
                .single()
                .execute()
            )
            if profile.data:
                plan_tier = profile.data.get("plan_tier", "free")
                subscription_status = profile.data.get("subscription_status", "inactive")
        except Exception:
            pass  # Non-critical — fall back to defaults

        return CloudUser(
            id=user_id,
            email=email,
            username=username,
            plan_tier=plan_tier,
            subscription_status=subscription_status,
            created_at=user.created_at or "",
        )

    except Exception as e:
        error_msg = str(e)
        if "invalid" in error_msg.lower() or "expired" in error_msg.lower():
            raise CloudAuthError("Token expired or invalid")
        raise CloudAuthError(f"Token verification failed: {error_msg}")


async def refresh_session(refresh_token: str) -> dict:
    """Refresh an expired session using the refresh token."""
    client = await get_async_supabase_client()
    if client is None:
        raise CloudAuthError("Cloud backend not configured")

    try:
        resp = await client.auth.refresh_session(refresh_token)
        session = resp.session
        if session is None:
            raise CloudAuthError("Session refresh failed")

        return {
            "access_token": session.access_token,
            "refresh_token": session.refresh_token,
            "expires_at": session.expires_at,
        }
    except Exception as e:
        raise CloudAuthError(f"Session refresh failed: {e}")


# ─── Internal Helpers ────────────────────────────────────────────


async def _ensure_profile_exists(user_id: str, email: str, username: str) -> None:
    """Create a profile row for a new user (idempotent)."""
    service = get_supabase_service_client()
    if service is None:
        return

    try:
        resp = service.table("profiles").select("id").eq("id", user_id).execute()
        if resp.data:
            return  # Already exists

        now = datetime.now(timezone.utc).isoformat()
        service.table("profiles").insert({
            "id": user_id,
            "email": email,
            "username": username,
            "plan_tier": "free",
            "subscription_status": "inactive",
            "created_at": now,
            "updated_at": now,
        }).execute()
        logger.info(f"Created profile for user {user_id}")
    except Exception as e:
        logger.warning(f"Failed to ensure profile for {user_id}: {e}")
        # Non-fatal — profile can be created later


# ─── Dependency for FastAPI ──────────────────────────────────────


async def get_current_user(authorization: str = "") -> Optional[CloudUser]:
    """FastAPI dependency: extract and verify the Bearer token.

    Usage:
        @app.get("/api/cloud/me")
        async def me(user: CloudUser = Depends(get_current_user)):
            ...
    """
    if not authorization:
        return None

    # Parse Bearer token
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    try:
        return await verify_token(parts[1])
    except CloudAuthError:
        return None
