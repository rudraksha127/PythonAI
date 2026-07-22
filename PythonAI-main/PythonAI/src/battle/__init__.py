"""
Model Battle Arena — Compare LLM Providers Side-by-Side
==========================================================
Send the same prompt to multiple providers/models and compare
responses with latency, token usage, and cost metrics.
"""

from .models import (
    BattleConfig,
    BattleResult,
    BattleEntry,
    BattleRequest,
    BattleResponse,
    ProviderResult,
)
from .engine import BattleEngine

__all__ = [
    "BattleConfig",
    "BattleResult",
    "BattleEntry",
    "BattleRequest",
    "BattleResponse",
    "ProviderResult",
    "BattleEngine",
]
