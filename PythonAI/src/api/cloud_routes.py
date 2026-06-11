"""
ForgeAI Cloud API Routes
=========================
FastAPI router for cloud authentication, billing management, and
subscription gating. Mounted at /api/cloud/* in the main server.

Endpoints:
  POST   /api/cloud/auth/signup        — Register new account
  POST   /api/cloud/auth/signin        — Sign in with email/password
  POST   /api/cloud/auth/signout       — Sign out (revoke session)
  POST   /api/cloud/auth/refresh       — Refresh expired token
  GET    /api/cloud/auth/me            — Get current user profile
  GET    /api/cloud/billing/prices     — List available pricing plans
  POST   /api/cloud/billing/checkout   — Create checkout session
  POST   /api/cloud/billing/portal     — Create customer portal session
  POST   /api/cloud/webhooks/stripe    — Stripe webhook receiver
  GET    /api/cloud/status             — Cloud backend health status
  GET    /api/cloud/projects           — List user's projects
  POST   /api/cloud/projects           — Sync a project to cloud
  GET    /api/cloud/training-runs      — List training runs
  GET    /api/cloud/signals/count      — Get signal count
  POST   /api/cloud/sync/signals       — Sync captured signals to cloud
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field

from src.cloud.auth import (
    CloudAuthError,
    CloudUser,
    refresh_session,
    sign_in,
    sign_out,
    sign_up,
    verify_token,
)
from src.cloud.config import get_cloud_config
from src.cloud.db import CloudDB
from src.cloud.status import get_cloud_status, get_stripe_status
from src.cloud.stripe_billing import (
    StripeBillingError,
    construct_webhook_event,
    create_checkout_session,
    create_portal_session,
    get_prices,
    sync_subscription_from_stripe,
)
from src.cloud.supabase_client import is_cloud_enabled

logger = logging.getLogger("forgeai.api.cloud")

router = APIRouter(prefix="/api/cloud", tags=["cloud"])


# ═══════════════════════════════════════
# Pydantic Models
# ═══════════════════════════════════════

class SignUpRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    username: str = Field(..., min_length=2, max_length=50)


class SignInRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class CheckoutRequest(BaseModel):
    plan_tier: str = Field(default="pro", pattern="^(pro|team)$")
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class PortalRequest(BaseModel):
    return_url: Optional[str] = None


class ProjectSyncRequest(BaseModel):
    project_id: str
    name: str
    repo_path: str
    languages: list[str] = []
    training_phase: int = 0
    base_model: str = ""
    training_schedule: str = "weekly"


class SignalSyncRequest(BaseModel):
    signals: list[dict]


# ═══════════════════════════════════════
# Auth Dependency
# ═══════════════════════════════════════

async def _get_user(authorization: str = Header(default="")) -> CloudUser:
    """FastAPI dependency to extract authenticated user from Bearer token."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    try:
        return await verify_token(parts[1])
    except CloudAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))


# ═══════════════════════════════════════
# Auth Endpoints
# ═══════════════════════════════════════

@router.get("/auth/status")
async def cloud_auth_status():
    """Check if cloud auth is configured and available."""
    return {
        "cloud_enabled": is_cloud_enabled(),
        "allow_signups": get_cloud_config().allow_signups,
    }


@router.post("/auth/signup")
async def cloud_signup(request: SignUpRequest):
    """Register a new cloud account."""
    if not is_cloud_enabled():
        raise HTTPException(status_code=503, detail="Cloud backend not configured")

    try:
        result = await sign_up(request.email, request.password, request.username)
        return result
    except CloudAuthError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/auth/signin")
async def cloud_signin(request: SignInRequest):
    """Sign in with email and password."""
    if not is_cloud_enabled():
        raise HTTPException(status_code=503, detail="Cloud backend not configured")

    try:
        result = await sign_in(request.email, request.password)
        return result
    except CloudAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/auth/signout")
async def cloud_signout(authorization: str = Header(default="")):
    """Sign out and revoke the current session."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    access_token = parts[1]

    try:
        result = await sign_out(access_token)
        return result
    except CloudAuthError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/auth/refresh")
async def cloud_refresh(request: RefreshRequest):
    """Refresh an expired access token."""
    if not is_cloud_enabled():
        raise HTTPException(status_code=503, detail="Cloud backend not configured")

    try:
        result = await refresh_session(request.refresh_token)
        return result
    except CloudAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/auth/me")
async def cloud_me(user: CloudUser = Depends(_get_user)):
    """Get the currently authenticated user's profile."""
    return user.to_dict()


# ═══════════════════════════════════════
# Billing Endpoints
# ═══════════════════════════════════════

@router.get("/billing/prices")
async def billing_prices():
    """List all available pricing plans with prices."""
    try:
        prices = get_prices()
        return {"prices": prices}
    except StripeBillingError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/billing/checkout")
async def billing_checkout(
    request: CheckoutRequest,
    user: CloudUser = Depends(_get_user),
):
    """Create a Stripe Checkout session for subscription upgrade."""
    try:
        session = create_checkout_session(
            user_id=user.id,
            email=user.email,
            plan_tier=request.plan_tier,
            success_url=request.success_url,
            cancel_url=request.cancel_url,
        )
        return session
    except StripeBillingError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/billing/portal")
async def billing_portal(
    request: PortalRequest,
    user: CloudUser = Depends(_get_user),
):
    """Create a Stripe Customer Portal session for subscription management."""
    from src.cloud.db import CloudDB

    profile = await CloudDB.get_profile(user.id)
    if not profile or not profile.get("stripe_customer_id"):
        raise HTTPException(status_code=400, detail="No Stripe customer found")

    try:
        session = create_portal_session(
            customer_id=profile["stripe_customer_id"],
            return_url=request.return_url,
        )
        return session
    except StripeBillingError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/billing/subscription")
async def billing_subscription(user: CloudUser = Depends(_get_user)):
    """Get the current user's subscription details."""
    from src.cloud.db import get_user_subscription

    sub = await get_user_subscription(user.id)
    return sub


# ═══════════════════════════════════════
# Webhook Endpoints
# ═══════════════════════════════════════

@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events (checkout, subscription, invoice)."""
    if not get_cloud_config().is_stripe_configured:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing Stripe signature")

    try:
        event = construct_webhook_event(payload, sig_header)
    except StripeBillingError as e:
        raise HTTPException(status_code=400, detail=str(e))

    event_type = event.type
    logger.info(f"Stripe webhook received: {event_type}")

    try:
        obj = event.data.object

        if event_type == "checkout.session.completed":
            subscription_id = getattr(obj, "subscription", None)
            if subscription_id:
                sync_subscription_from_stripe(subscription_id)

        elif event_type == "customer.subscription.updated":
            sync_subscription_from_stripe(obj.id)

        elif event_type == "customer.subscription.deleted":
            sync_subscription_from_stripe(obj.id)

        elif event_type == "invoice.paid":
            subscription_id = getattr(obj, "subscription", None)
            if subscription_id:
                sync_subscription_from_stripe(subscription_id)

        elif event_type == "invoice.payment_failed":
            subscription_id = getattr(obj, "subscription", None)
            if subscription_id:
                sync_subscription_from_stripe(subscription_id)
                logger.warning(f"Payment failed for subscription {subscription_id}")

        else:
            logger.debug(f"Unhandled Stripe event type: {event_type}")

        return {"received": True, "type": event_type}

    except Exception as e:
        logger.error(f"Error processing Stripe webhook: {e}")
        # Always return 200 to Stripe to prevent retries for non-critical errors
        return {"received": True, "type": event_type, "error": str(e)}


# ═══════════════════════════════════════
# Cloud Data Endpoints
# ═══════════════════════════════════════

@router.get("/projects")
async def cloud_list_projects(user: CloudUser = Depends(_get_user)):
    """List user's cloud-synced projects."""
    projects = await CloudDB.list_projects(user.id)
    return {"projects": projects}


@router.post("/projects")
async def cloud_sync_project(
    request: ProjectSyncRequest,
    user: CloudUser = Depends(_get_user),
):
    """Sync a local project to the cloud."""
    project_id = await CloudDB.upsert_project(user.id, {
        "id": request.project_id,
        "name": request.name,
        "repo_path": request.repo_path,
        "languages": request.languages,
        "training_phase": request.training_phase,
        "base_model": request.base_model,
        "training_schedule": request.training_schedule,
    })
    if not project_id:
        raise HTTPException(status_code=500, detail="Failed to sync project")
    return {"project_id": project_id, "synced": True}


@router.get("/training-runs")
async def cloud_list_training_runs(
    limit: int = 20,
    user: CloudUser = Depends(_get_user),
):
    """List user's training runs from the cloud."""
    runs = await CloudDB.list_training_runs(user.id, limit=limit)
    return {"training_runs": runs}


@router.get("/signals/count")
async def cloud_signal_count(
    days: int = 30,
    user: CloudUser = Depends(_get_user),
):
    """Get the count of signals captured in the last N days."""
    count = await CloudDB.get_signal_count(user.id, days=days)
    return {"count": count, "days": days}


@router.get("/signals/acceptance-rate")
async def cloud_acceptance_rate(
    days: int = 30,
    user: CloudUser = Depends(_get_user),
):
    """Get acceptance rate stats from the cloud."""
    stats = await CloudDB.get_acceptance_rate(user.id, days=days)
    return stats


@router.post("/sync/signals")
async def cloud_sync_signals(
    request: SignalSyncRequest,
    user: CloudUser = Depends(_get_user),
):
    """Sync captured signals to the cloud."""
    synced = 0
    for signal in request.signals:
        signal_id = await CloudDB.sync_signal(user.id, signal)
        if signal_id:
            synced += 1

    return {"synced": synced, "total": len(request.signals)}


# ═══════════════════════════════════════
# Status Endpoint
# ═══════════════════════════════════════

@router.get("/status")
async def cloud_status():
    """Get cloud backend health status."""
    return get_cloud_status()
