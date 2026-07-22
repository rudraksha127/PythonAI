"""
ForgeAI Cloud Configuration
============================
Environment-variable-driven config for Supabase + Stripe integration.

All cloud features are optional and gracefully degrade when env vars are absent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class CloudConfig:
    """Configuration for ForgeAI Cloud backend."""

    # ─── Supabase ──────────────────────────────────────────────
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_db_schema: str = "public"

    # ─── Stripe ────────────────────────────────────────────────
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_lookup_key_active: str = ""  # Lookup key for monthly subscription price

    # ─── App URLs (for Stripe redirects) ───────────────────────
    app_url: str = "http://localhost:3000"
    api_url: str = "http://localhost:7337"

    # ─── Feature flags ─────────────────────────────────────────
    cloud_enabled: bool = False
    allow_signups: bool = True
    require_subscription: bool = False  # If True, API returns 402 for non-paying users

    @property
    def is_supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_anon_key)

    @property
    def is_stripe_configured(self) -> bool:
        return bool(self.stripe_secret_key and self.stripe_webhook_secret)

    @classmethod
    def from_env(cls) -> CloudConfig:
        """Load configuration from environment variables."""
        cfg = cls()

        # Supabase
        cfg.supabase_url = os.getenv("SUPABASE_URL", "")
        cfg.supabase_anon_key = os.getenv("SUPABASE_ANON_KEY", "")
        cfg.supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

        # Stripe
        cfg.stripe_secret_key = os.getenv("STRIPE_SECRET_KEY", "")
        cfg.stripe_publishable_key = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
        cfg.stripe_webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
        cfg.stripe_price_lookup_key_active = os.getenv("STRIPE_PRICE_LOOKUP_KEY", "")

        # App URLs
        cfg.app_url = os.getenv("FORGEAI_APP_URL", "http://localhost:3000")
        cfg.api_url = os.getenv("FORGEAI_API_URL", "http://localhost:7337")

        # Feature flags
        cfg.cloud_enabled = os.getenv("FORGEAI_CLOUD_ENABLED", "").lower() in ("1", "true", "yes")
        cfg.allow_signups = os.getenv("FORGEAI_ALLOW_SIGNUPS", "true").lower() in ("1", "true", "yes")
        cfg.require_subscription = os.getenv("FORGEAI_REQUIRE_SUBSCRIPTION", "").lower() in ("1", "true", "yes")

        return cfg

    def to_dict(self) -> dict:
        """Return config dict (never expose secrets)."""
        return {
            "cloud_enabled": self.cloud_enabled,
            "allow_signups": self.allow_signups,
            "require_subscription": self.require_subscription,
            "supabase_configured": self.is_supabase_configured,
            "stripe_configured": self.is_stripe_configured,
            "app_url": self.app_url,
            "api_url": self.api_url,
        }


# Global singleton
_cloud_config: CloudConfig | None = None


def get_cloud_config() -> CloudConfig:
    """Get the global cloud configuration (lazy-loaded)."""
    global _cloud_config
    if _cloud_config is None:
        _cloud_config = CloudConfig.from_env()
    return _cloud_config


def reload_cloud_config() -> CloudConfig:
    """Reload cloud configuration from environment variables."""
    global _cloud_config
    _cloud_config = CloudConfig.from_env()
    return _cloud_config
