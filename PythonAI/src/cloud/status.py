"""
ForgeAI Cloud Status
=====================
Health and connectivity checks for Supabase and Stripe backends.
"""

from __future__ import annotations

import logging
from typing import Any

from src.cloud.config import get_cloud_config
from src.cloud.supabase_client import get_supabase_client

logger = logging.getLogger("forgeai.cloud.status")


def get_cloud_status() -> dict:
    """Get the overall cloud backend status.

    Returns a dict with connectivity info for all services.
    """
    cfg = get_cloud_config()
    status: dict[str, Any] = {
        "cloud_enabled": cfg.cloud_enabled,
        "services": {
            "supabase": {"configured": False, "connected": False, "error": None},
            "stripe": {"configured": False, "connected": False, "error": None},
        },
        "features": {
            "allow_signups": cfg.allow_signups,
            "require_subscription": cfg.require_subscription,
        },
        "config": cfg.to_dict(),
    }

    # Check Supabase connectivity
    if cfg.is_supabase_configured:
        status["services"]["supabase"]["configured"] = True
        try:
            client = get_supabase_client()
            if client:
                # Lightweight health check — just verify the URL is reachable
                # by making a simple API request that doesn't require auth
                import requests
                resp = requests.get(f"{cfg.supabase_url}/rest/v1/", timeout=5)
                status["services"]["supabase"]["connected"] = resp.status_code < 500
            else:
                status["services"]["supabase"]["error"] = "Client initialization failed"
        except Exception as e:
            status["services"]["supabase"]["connected"] = False
            status["services"]["supabase"]["error"] = str(e)

    # Check Stripe connectivity
    if cfg.is_stripe_configured:
        status["services"]["stripe"]["configured"] = True
        try:
            import stripe
            stripe.api_key = cfg.stripe_secret_key
            stripe.Balance.retrieve()
            status["services"]["stripe"]["connected"] = True
        except Exception as e:
            status["services"]["stripe"]["connected"] = False
            status["services"]["stripe"]["error"] = str(e)

    return status


def get_stripe_status() -> dict:
    """Get detailed Stripe connectivity and product info."""
    cfg = get_cloud_config()
    result = {
        "configured": False,
        "connected": False,
        "products": [],
        "error": None,
    }

    if not cfg.is_stripe_configured:
        result["error"] = "Stripe not configured"
        return result

    result["configured"] = True

    try:
        import stripe
        stripe.api_key = cfg.stripe_secret_key

        # Check balance (confirms API key works)
        stripe.Balance.retrieve()

        # List active products with prices
        products = []
        for product in stripe.Product.list(active=True, limit=50, expand=["data.default_price"]):
            prices = []
            for price in stripe.Price.list(product=product.id, active=True, limit=5):
                prices.append({
                    "id": price.id,
                    "amount": (price.unit_amount or 0) / 100,
                    "currency": price.currency.upper(),
                    "interval": price.recurring.get("interval", "one_time") if price.recurring else "one_time",
                    "lookup_key": price.lookup_key,
                })
            products.append({
                "id": product.id,
                "name": product.name,
                "description": product.description,
                "prices": prices,
                "metadata": product.metadata,
            })

        result["connected"] = True
        result["products"] = products

    except Exception as e:
        result["error"] = str(e)

    return result
