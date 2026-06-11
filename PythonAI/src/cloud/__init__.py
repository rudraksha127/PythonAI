"""
ForgeAI Cloud Backend
=====================
Supabase + Stripe integration for ForgeAI subscriptions & cloud sync.

⚠️ Import note: Only config.py and tiers.py are imported eagerly because
they have NO external dependencies (supabase/stripe). All other modules
are imported at point of use to avoid crashes when cloud dependencies
are not installed.

Usage:
    from src.cloud.config import get_cloud_config
    from src.cloud.tiers import get_plan_features, PRICING_TIERS
    from src.cloud.auth import sign_in, sign_up  # Requires supabase
"""

from __future__ import annotations

# ─── Zero-dependency modules (safe to import eagerly) ──────────
from src.cloud.config import CloudConfig, get_cloud_config
from src.cloud.tiers import (
    PRICING_TIERS,
    PlanTier,
    check_entitlement,
    format_limits_display,
    get_plan_features,
    get_rate_limit,
)

# ─── Modules with external dependencies (import at point of use) ──

__all__ = [
    # Config
    "CloudConfig",
    "get_cloud_config",
    # Tiers
    "PlanTier",
    "PRICING_TIERS",
    "get_plan_features",
    "check_entitlement",
    "get_rate_limit",
    "format_limits_display",
]
