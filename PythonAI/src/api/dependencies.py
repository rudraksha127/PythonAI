"""
ForgeAI API Dependencies
=========================
FastAPI dependency injection for authentication, subscription gating,
and rate limiting.

Used across all API routers to enforce access control consistently.
"""

from __future__ import annotations

import logging

from fastapi import Depends, Header, HTTPException, Request

from src.cloud.auth import CloudAuthError, CloudUser, verify_token
from src.cloud.config import get_cloud_config
from src.cloud.supabase_client import is_cloud_enabled
from src.cloud.tiers import check_entitlement, get_rate_limit

logger = logging.getLogger("forgeai.api.dependencies")


# ═══════════════════════════════════════
# Auth Dependencies
# ═══════════════════════════════════════


async def require_cloud_user(authorization: str = Header(default="")) -> CloudUser:
    """Require a valid cloud authentication token.

    Returns:
        CloudUser if authenticated

    Raises:
        HTTPException 401 if not authenticated
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Include a Bearer token in the Authorization header.",
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization format. Use: Authorization: Bearer <token>",
        )

    try:
        user = await verify_token(parts[1])
        return user
    except CloudAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))


async def optional_cloud_user(authorization: str = Header(default="")) -> CloudUser | None:
    """Optionally resolve a cloud user from the authorization header.

    Returns CloudUser if valid token, None otherwise.
    Never raises — use for endpoints that work in both cloud and local modes.
    """
    if not authorization:
        return None

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    try:
        return await verify_token(parts[1])
    except CloudAuthError:
        return None


# ═══════════════════════════════════════
# Subscription Gating
# ═══════════════════════════════════════


async def require_feature(
    user: CloudUser = Depends(require_cloud_user),
    feature: str = "",
) -> CloudUser:
    """Check if the authenticated user has access to a specific feature.

    Usage:
        @app.post("/api/training/trigger")
        async def trigger_training(
            user: CloudUser = Depends(lambda: require_feature(feature="max_training_runs_per_month"))
        ):
            ...

    Returns the CloudUser if entitled, raises 402 Payment Required otherwise.
    """
    if not feature:
        return user

    if not check_entitlement(user.plan_tier, feature):
        cfg = get_cloud_config()
        detail = f"Feature '{feature}' requires an upgraded plan (current: {user.plan_tier})"

        if cfg.is_stripe_configured:
            detail += ". Visit /settings/billing to upgrade."

        raise HTTPException(
            status_code=402,
            detail=detail,
            headers={
                "X-Plan-Required": "pro",
                "X-Current-Plan": user.plan_tier,
            },
        )

    return user


async def check_tier_limit(request: Request) -> None:
    """Set up rate limit and user info on the request state.

    Intended to be used as a middleware dependency on routes that
    need plan-based rate limiting. Resolves the user from the request
    if a valid Authorization header is present.
    """
    if not is_cloud_enabled():
        return

    # Try to resolve user from header
    auth = request.headers.get("authorization", "")
    try:
        user = await optional_cloud_user(auth)
        if user:
            request.state.rate_limit = get_rate_limit(user.plan_tier)
            request.state.user = user
    except Exception:
        pass


# ═══════════════════════════════════════
# Feature Check Helper
# ═══════════════════════════════════════


def feature_required(feature: str):
    """Create a dependency that checks for a specific feature entitlement.

    Usage:
        @router.post("/api/training/trigger")
        async def trigger_training(
            _: CloudUser = Depends(feature_required("max_training_runs_per_month")),
        ):
            ...
    """
    async def _check(user: CloudUser = Depends(require_cloud_user)) -> CloudUser:
        return await require_feature(user, feature=feature)

    return _check
