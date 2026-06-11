"""
ForgeAI Pricing Tiers
======================
Plan definitions, features, and entitlement checking for ForgeAI subscriptions.

Maps Stripe price IDs to ForgeAI plan tiers and their feature sets.
"""

from __future__ import annotations

from dataclasses import dataclass


class PlanTier:
    """Constant plan tier identifiers."""

    FREE = "free"
    PRO = "pro"
    TEAM = "team"
    ENTERPRISE = "enterprise"


@dataclass
class PlanFeatures:
    """Feature set for a pricing tier."""

    # Training
    max_training_runs_per_month: int = 0
    max_signals_per_month: int = 0
    max_adapters: int = 0

    # Agent
    agent_chat_allowed: bool = False
    max_agent_messages_per_day: int = 0
    streaming_allowed: bool = False

    # RAG
    max_projects: int = 0
    max_rag_queries_per_day: int = 0
    rag_indexing_allowed: bool = False

    # Sync
    cloud_sync_allowed: bool = False
    realtime_updates: bool = False
    team_collaboration: bool = False

    # Enterprise
    sso_enabled: bool = False
    audit_logs: bool = False
    dedicated_support: bool = False
    custom_training_schedule: bool = False

    # Rate limits
    api_rate_limit_per_minute: int = 10
    max_concurrent_training: int = 0


# ─── Tier Definitions ────────────────────────────────────────────

PRICING_TIERS: dict[str, dict] = {
    PlanTier.FREE: {
        "name": "Free",
        "description": "Personal use, local only",
        "price_monthly_usd": 0,
        "stripe_price_id": None,  # Free tier has no Stripe price
        "features": PlanFeatures(
            max_training_runs_per_month=5,
            max_signals_per_month=500,
            max_adapters=2,
            agent_chat_allowed=True,
            max_agent_messages_per_day=50,
            streaming_allowed=True,
            max_projects=2,
            max_rag_queries_per_day=100,
            rag_indexing_allowed=True,
            cloud_sync_allowed=True,
            realtime_updates=True,
            api_rate_limit_per_minute=20,
            max_concurrent_training=1,
        ),
        "limits_display": {
            "Training runs": "5/mo",
            "Signals": "500/mo",
            "Projects": "2",
            "Agent messages": "50/day",
            "RAG queries": "100/day",
        },
    },
    PlanTier.PRO: {
        "name": "Pro",
        "description": "Serious developers, cloud features",
        "price_monthly_usd": 20,
        "stripe_price_id": None,  # Set via env var or Stripe lookup
        "features": PlanFeatures(
            max_training_runs_per_month=100,
            max_signals_per_month=10000,
            max_adapters=20,
            agent_chat_allowed=True,
            max_agent_messages_per_day=500,
            streaming_allowed=True,
            max_projects=20,
            max_rag_queries_per_day=1000,
            rag_indexing_allowed=True,
            cloud_sync_allowed=True,
            realtime_updates=True,
            team_collaboration=False,
            api_rate_limit_per_minute=60,
            max_concurrent_training=2,
        ),
        "limits_display": {
            "Training runs": "100/mo",
            "Signals": "10,000/mo",
            "Projects": "20",
            "Agent messages": "500/day",
            "RAG queries": "1,000/day",
        },
    },
    PlanTier.TEAM: {
        "name": "Team",
        "description": "Small teams, shared training",
        "price_monthly_usd": 50,
        "stripe_price_id": None,
        "features": PlanFeatures(
            max_training_runs_per_month=500,
            max_signals_per_month=50000,
            max_adapters=100,
            agent_chat_allowed=True,
            max_agent_messages_per_day=2000,
            streaming_allowed=True,
            max_projects=100,
            max_rag_queries_per_day=5000,
            rag_indexing_allowed=True,
            cloud_sync_allowed=True,
            realtime_updates=True,
            team_collaboration=True,
            api_rate_limit_per_minute=120,
            max_concurrent_training=5,
        ),
        "limits_display": {
            "Training runs": "500/mo",
            "Signals": "50,000/mo",
            "Projects": "100",
            "Agent messages": "2,000/day",
            "RAG queries": "5,000/day",
        },
    },
    PlanTier.ENTERPRISE: {
        "name": "Enterprise",
        "description": "Custom deployment, SSO, audit logs",
        "price_monthly_usd": None,  # Custom pricing
        "stripe_price_id": None,
        "features": PlanFeatures(
            max_training_runs_per_month=99999,
            max_signals_per_month=999999,
            max_adapters=9999,
            agent_chat_allowed=True,
            max_agent_messages_per_day=99999,
            streaming_allowed=True,
            max_projects=9999,
            max_rag_queries_per_day=99999,
            rag_indexing_allowed=True,
            cloud_sync_allowed=True,
            realtime_updates=True,
            team_collaboration=True,
            sso_enabled=True,
            audit_logs=True,
            dedicated_support=True,
            custom_training_schedule=True,
            api_rate_limit_per_minute=500,
            max_concurrent_training=20,
        ),
        "limits_display": {
            "Training runs": "Unlimited",
            "Signals": "Unlimited",
            "Projects": "Unlimited",
            "Agent messages": "Unlimited",
            "SSO": "Included",
        },
    },
}


def get_plan_features(plan_tier: str) -> PlanFeatures:
    """Get the feature set for a given plan tier (defaults to Free)."""
    tier_data = PRICING_TIERS.get(plan_tier, PRICING_TIERS[PlanTier.FREE])
    return tier_data["features"]


def get_plan_info(plan_tier: str) -> dict:
    """Get the full plan info dict for a tier."""
    return PRICING_TIERS.get(plan_tier, PRICING_TIERS[PlanTier.FREE])


def check_entitlement(plan_tier: str, feature: str) -> bool:
    """Check if a plan tier has access to a specific feature.

    Args:
        plan_tier: The user's plan tier (e.g. "free", "pro")
        feature: Feature to check (e.g. "agent_chat_allowed")

    Returns:
        bool: Whether the feature is available
    """
    features = get_plan_features(plan_tier)
    return getattr(features, feature, False)


def get_rate_limit(plan_tier: str) -> int:
    """Get rate limit per minute for a plan tier."""
    features = get_plan_features(plan_tier)
    return features.api_rate_limit_per_minute


def format_limits_display(plan_tier: str) -> dict[str, str]:
    """Get human-readable limit descriptions for a tier."""
    tier_data = PRICING_TIERS.get(plan_tier, PRICING_TIERS[PlanTier.FREE])
    return tier_data["limits_display"]
