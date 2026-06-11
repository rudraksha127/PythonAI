"""
ForgeAI Stripe Billing
=======================
Stripe Checkout session creation, Customer Portal integration,
and subscription management for ForgeAI.

Manages the flow:
  1. User clicks "Upgrade" → create_checkout_session() → redirect to Stripe
  2. Stripe sends webhook → sync_subscription_from_stripe() → update DB
  3. User manages billing → create_portal_session() → redirect to Stripe Portal
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import stripe

from src.cloud.config import get_cloud_config
from src.cloud.supabase_client import get_supabase_service_client
from src.cloud.tiers import PlanTier, PRICING_TIERS

logger = logging.getLogger("forgeai.cloud.stripe")


class StripeBillingError(Exception):
    """Raised when a Stripe operation fails."""
    pass


def _init_stripe() -> None:
    """Ensure Stripe API key is set."""
    cfg = get_cloud_config()
    if cfg.stripe_secret_key:
        stripe.api_key = cfg.stripe_secret_key
    else:
        raise StripeBillingError("Stripe secret key not configured")


# ─── Price Management ────────────────────────────────────────────


def _sync_prices_from_stripe() -> dict[str, str]:
    """Fetch price IDs from Stripe for each plan tier.

    This allows users to define prices in the Stripe Dashboard
    and have them automatically discovered by ForgeAI.
    Returns dict of {plan_tier: price_id}.
    """
    _init_stripe()
    price_map = {}

    try:
        prices = stripe.Price.list(
            active=True,
            expand=["data.product"],
            limit=100,
        )
        for price in prices.auto_paging_iter():
            product = price.product if isinstance(price.product, dict) else None
            if product is None:
                continue
            product_name = product.get("name", "").lower()
            metadata = product.get("metadata", {})

            # Map Stripe product names to plan tiers
            for tier_key, tier_data in PRICING_TIERS.items():
                if tier_key == PlanTier.FREE:
                    continue  # Free has no price
                tier_name = tier_data["name"].lower()
                if tier_name in product_name or metadata.get("forgeai_tier") == tier_key:
                    price_map[tier_key] = price.id
                    # Also update the local config cache
                    PRICING_TIERS[tier_key]["stripe_price_id"] = price.id
                    break

            # Also check lookup key
            lookup_key = price.lookup_key
            if lookup_key and lookup_key.startswith("forgeai_"):
                tier = lookup_key.replace("forgeai_", "")
                if tier in PRICING_TIERS:
                    price_map[tier] = price.id
                    PRICING_TIERS[tier]["stripe_price_id"] = price.id

    except stripe.error.StripeError as e:
        logger.warning(f"Failed to sync prices from Stripe: {e}")

    return price_map


def get_prices() -> list[dict]:
    """Get all active prices from Stripe.

    Returns a list of price dicts suitable for display.
    Falls back to configured defaults if Stripe is unreachable.
    """
    _init_stripe()

    prices = []
    try:
        stripe_prices = list(stripe.Price.list(active=True, limit=100, expand=["data.product"]).auto_paging_iter())
        for price in stripe_prices:
            product = price.product if isinstance(price.product, dict) else {}
            unit_amount = price.unit_amount or 0
            prices.append({
                "id": price.id,
                "product_id": product.get("id", ""),
                "name": product.get("name", ""),
                "description": product.get("description", ""),
                "amount": unit_amount / 100,
                "currency": price.currency.upper(),
                "interval": price.recurring.get("interval", "month") if price.recurring else "month",
                "lookup_key": price.lookup_key,
                "metadata": price.metadata,
            })
    except stripe.error.StripeError as e:
        logger.warning(f"Failed to fetch Stripe prices: {e}")
        # Fall back to local definition
        for tier_key, tier_data in PRICING_TIERS.items():
            if tier_data["price_monthly_usd"]:
                prices.append({
                    "id": tier_data["stripe_price_id"] or f"price_{tier_key}",
                    "name": tier_data["name"],
                    "description": tier_data["description"],
                    "amount": tier_data["price_monthly_usd"],
                    "currency": "USD",
                    "interval": "month",
                    "lookup_key": f"forgeai_{tier_key}",
                    "metadata": {},
                })

    return prices


def _get_price_id_for_tier(plan_tier: str) -> str:
    """Get the Stripe price ID for a plan tier."""
    # Check local config first
    tier_data = PRICING_TIERS.get(plan_tier)
    if tier_data and tier_data["stripe_price_id"]:
        return tier_data["stripe_price_id"]

    # Try to sync from Stripe
    price_map = _sync_prices_from_stripe()
    if plan_tier in price_map:
        return price_map[plan_tier]

    raise StripeBillingError(f"No Stripe price configured for tier '{plan_tier}'")


# ─── Checkout & Portal ───────────────────────────────────────────


def create_checkout_session(
    user_id: str,
    email: str,
    plan_tier: str = PlanTier.PRO,
    success_url: Optional[str] = None,
    cancel_url: Optional[str] = None,
) -> dict:
    """Create a Stripe Checkout session for a subscription upgrade.

    Args:
        user_id: The ForgeAI user ID (will be stored as client_reference_id)
        email: User's email for pre-filling
        plan_tier: Target plan tier ("pro" or "team")
        success_url: Redirect URL after successful payment
        cancel_url: Redirect URL if user cancels

    Returns:
        dict: {"session_id": ..., "url": ...} for redirecting the user
    """
    _init_stripe()
    cfg = get_cloud_config()

    price_id = _get_price_id_for_tier(plan_tier)

    success_url = success_url or f"{cfg.app_url}/settings/billing?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = cancel_url or f"{cfg.app_url}/settings/billing"

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            client_reference_id=user_id,
            customer_email=email,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "forgeai_user_id": user_id,
                "forgeai_plan_tier": plan_tier,
            },
            subscription_data={
                "metadata": {
                    "forgeai_user_id": user_id,
                    "forgeai_plan_tier": plan_tier,
                },
            },
        )

        logger.info(f"Created checkout session for user {user_id} (tier={plan_tier})")

        return {
            "session_id": session.id,
            "url": session.url,
            "plan_tier": plan_tier,
        }

    except stripe.error.StripeError as e:
        logger.error(f"Stripe checkout failed: {e}")
        raise StripeBillingError(f"Failed to create checkout session: {e}")


def create_portal_session(
    customer_id: str,
    return_url: Optional[str] = None,
) -> dict:
    """Create a Stripe Billing Portal session for self-serve management.

    Args:
        customer_id: The Stripe customer ID
        return_url: URL to redirect to after leaving the portal

    Returns:
        dict: {"url": ...} for redirecting the user
    """
    _init_stripe()
    cfg = get_cloud_config()

    return_url = return_url or f"{cfg.app_url}/settings/billing"

    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )

        return {"url": session.url}

    except stripe.error.StripeError as e:
        logger.error(f"Stripe portal session failed: {e}")
        raise StripeBillingError(f"Failed to create portal session: {e}")


# ─── Webhook Handler ─────────────────────────────────────────────


def construct_webhook_event(payload: bytes, sig_header: str) -> Any:
    """Verify and construct a Stripe webhook event.

    Args:
        payload: Raw request body bytes
        sig_header: The Stripe-Signature header value

    Returns:
        Stripe Event object

    Raises:
        StripeBillingError: If signature verification fails
    """
    _init_stripe()
    cfg = get_cloud_config()

    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            cfg.stripe_webhook_secret,
        )
        return event
    except stripe.error.SignatureVerificationError as e:
        logger.warning(f"Stripe webhook signature verification failed: {e}")
        raise StripeBillingError("Invalid webhook signature")
    except ValueError as e:
        logger.warning(f"Stripe webhook payload parsing failed: {e}")
        raise StripeBillingError("Invalid webhook payload")


def sync_subscription_from_stripe(subscription_id: str) -> dict:
    """Sync a Stripe subscription to the local database.

    Called by the webhook handler on:
      - checkout.session.completed
      - customer.subscription.updated
      - customer.subscription.deleted
      - invoice.paid

    Returns the updated profile dict.
    """
    _init_stripe()
    service = get_supabase_service_client()
    if service is None:
        raise StripeBillingError("Database not configured")

    try:
        # Fetch subscription from Stripe
        subscription = stripe.Subscription.retrieve(subscription_id)

        customer_id = subscription.customer
        status = subscription.status
        plan_tier = subscription.metadata.get("forgeai_plan_tier", PlanTier.PRO)
        user_id = subscription.metadata.get("forgeai_user_id", "")

        # Try to find user from customer ID if not in metadata
        if not user_id:
            user_id = _find_user_by_customer(customer_id)

        if not user_id:
            logger.warning(f"No ForgeAI user found for customer {customer_id}")
            return {}

        # Map Stripe status to ForgeAI subscription status
        status_map = {
            "active": "active",
            "trialing": "active",
            "past_due": "past_due",
            "canceled": "canceled",
            "unpaid": "unpaid",
            "incomplete": "incomplete",
            "incomplete_expired": "expired",
            "paused": "paused",
        }

        subscription_status = status_map.get(status, "inactive")
        current_period_end = None
        if subscription.current_period_end:
            current_period_end = datetime.fromtimestamp(
                subscription.current_period_end, tz=timezone.utc
            ).isoformat()

        # Update profile in database
        now = datetime.now(timezone.utc).isoformat()
        updates = {
            "stripe_customer_id": customer_id if isinstance(customer_id, str) else customer_id,
            "stripe_subscription_id": subscription.id,
            "plan_tier": plan_tier,
            "subscription_status": subscription_status,
            "current_period_end": current_period_end,
            "updated_at": now,
        }

        service.table("profiles").update(updates).eq("id", user_id).execute()
        logger.info(f"Synced subscription for user {user_id}: {plan_tier}/{subscription_status}")

        # Return the updated state
        return {
            "user_id": user_id,
            "plan_tier": plan_tier,
            "subscription_status": subscription_status,
            "stripe_customer_id": updates["stripe_customer_id"],
            "current_period_end": current_period_end,
        }

    except stripe.error.StripeError as e:
        logger.error(f"Failed to sync subscription {subscription_id}: {e}")
        raise StripeBillingError(f"Failed to sync subscription: {e}")


def cancel_subscription(subscription_id: str) -> dict:
    """Cancel an active subscription at period end."""
    _init_stripe()

    try:
        subscription = stripe.Subscription.update(
            subscription_id,
            cancel_at_period_end=True,
        )
        return {"subscription_id": subscription.id, "cancel_at_period_end": True}
    except stripe.error.StripeError as e:
        raise StripeBillingError(f"Failed to cancel subscription: {e}")


def _find_user_by_customer(stripe_customer_id: str) -> Optional[str]:
    """Find a ForgeAI user ID from their Stripe customer ID."""
    service = get_supabase_service_client()
    if service is None:
        return None

    try:
        resp = (
            service.table("profiles")
            .select("id")
            .eq("stripe_customer_id", stripe_customer_id)
            .limit(1)
            .execute()
        )
        if resp.data:
            return resp.data[0]["id"]
        return None
    except Exception as e:
        logger.warning(f"Failed to find user by customer: {e}")
        return None
