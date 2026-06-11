"""
Provider Router — Route LLM Requests to Best Provider
=======================================================
Inspired by OpenClaude's buildLaunchEnv() and provider profile system.
Determines which provider/model to use based on:
- User preference (--provider flag)
- Model capabilities required (vision, streaming, reasoning)
- Provider availability (API key exists, not rate-limited)
- Task type (coding, chat, reasoning)
- Cost optimization
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .registry import (
    ModelDescriptor,
    ModelRegistry,
    ProviderDescriptor,
    get_registry,
)


class RouteStrategy(str, Enum):
    """Strategy for selecting a provider."""
    AUTO = "auto"                    # Best available
    FASTEST = "fastest"              # Lowest latency
    CHEAPEST = "cheapest"            # Lowest cost
    BEST_QUALITY = "best_quality"    # Highest quality (reasoning models)
    LOCAL_ONLY = "local_only"        # Local models only
    CODING = "coding"                # Best for coding tasks


@dataclass
class RouteResult:
    """Result of a routing decision."""
    provider: str
    model: str
    base_url: str
    api_key: str | None = None
    api_type: str = "openai"          # "openai", "anthropic", "gemini"
    strategy_used: RouteStrategy = RouteStrategy.AUTO
    resolved_from_profile: bool = False
    is_local: bool = False
    model_info: ModelDescriptor | None = None
    provider_info: ProviderDescriptor | None = None
    error: str | None = None


class ProviderRouter:
    """
    Routes LLM requests to the best available provider.

    Supports:
    - Automatic provider selection based on task
    - Explicit provider/model override
    - Profile-based persistence
    - Capability-based filtering
    - Key availability checking
    """

    def __init__(
        self,
        registry: ModelRegistry | None = None,
        key_resolver: Callable[[str], str | None] | None = None,
    ):
        self.registry = registry or get_registry()
        self._key_resolver = key_resolver or self._default_key_resolver

    # == Key Resolution =======================================

    @staticmethod
    def _default_key_resolver(provider_id: str) -> str | None:
        """Default key resolver: checks env vars and apikeys storage."""
        # First check environment variables
        provider_env_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "mistral": "MISTRAL_API_KEY",
            "groq": "GROQ_API_KEY",
            "xai": "XAI_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "sambanova": "SAMBANOVA_API_KEY",
            "cerebras": "CEREBRAS_API_KEY",
            "together": "TOGETHER_API_KEY",
            "huggingface": "HF_TOKEN",
            "fireworks": "FIREWORKS_API_KEY",
            "deepinfra": "DEEPINFRA_API_KEY",
            "novita": "NOVITA_API_KEY",
        }
        env_key = provider_env_map.get(provider_id)
        if env_key:
            key = os.environ.get(env_key, "").strip()
            if key:
                return key

        # Then check PythonAI's apikeys storage
        try:
            from src.data.apikeys import resolve_key
            return resolve_key(provider_id)  # type: ignore[no-any-return]
        except ImportError:
            pass

        return None

    def resolve_key(self, provider_id: str) -> str | None:
        """Resolve API key for a provider."""
        return self._key_resolver(provider_id)

    def has_key(self, provider_id: str) -> bool:
        """Check if we have a key for a provider."""
        if provider_id == "ollama":
            return True  # Local, no key needed
        return self.resolve_key(provider_id) is not None

    # == Provider Availability ================================

    def get_available_providers(self) -> list[ProviderDescriptor]:
        """Get all providers that have API keys available."""
        available = []
        for provider in self.registry.list_providers():
            if not provider.requires_key or self.has_key(provider.id):
                available.append(provider)
        return sorted(available, key=lambda p: p.priority)

    def get_provider_status(self) -> list[dict[str, Any]]:
        """Get status of all providers with key availability."""
        statuses = []
        for provider in self.registry.list_providers():
            has_key = self.has_key(provider.id) if provider.requires_key else True
            default = self.registry.get_default_model(provider.id)
            statuses.append({
                "id": provider.id,
                "label": provider.label,
                "available": has_key,
                "has_key": has_key,
                "is_local": provider.is_local,
                "default_model": default.id if default else provider.default_model,
                "priority": provider.priority,
                "base_url": provider.base_url,
            })
        return sorted(statuses, key=lambda s: (not s["available"], s["priority"]))

    # == Routing Logic ========================================

    def route(
        self,
        provider: str = "auto",
        model: str = "",
        task: str = "coding",
        strategy: RouteStrategy = RouteStrategy.AUTO,
        require_vision: bool = False,
        require_reasoning: bool = False,
        require_streaming: bool = True,
        require_function_calling: bool = True,
    ) -> RouteResult:
        """
        Route a request to the best provider/model.

        Args:
            provider: Specific provider ID, or "auto" for automatic selection.
            model: Specific model ID. Empty = use provider's default.
            task: Task type: "coding", "chat", "reasoning".
            strategy: Selection strategy.
            require_vision: Must support vision.
            require_reasoning: Must support reasoning.
            require_streaming: Must support streaming.
            require_function_calling: Must support function calling.

        Returns:
            RouteResult with provider, model, base_url, api_key.
        """
        # If explicit provider + model, use that
        if provider != "auto":
            return self._route_explicit(provider, model, task)

        # Auto-select based on requirements and availability
        return self._route_auto(
            task=task,
            strategy=strategy,
            require_vision=require_vision,
            require_reasoning=require_reasoning,
            require_streaming=require_streaming,
            require_function_calling=require_function_calling,
        )

    def _route_explicit(self, provider: str, model: str, task: str) -> RouteResult:
        """Route using explicitly specified provider."""
        provider_info = self.registry.get_provider(provider)
        if not provider_info:
            return RouteResult(
                provider=provider, model=model, base_url="",
                api_type="openai",
                error=f"Unknown provider: {provider}. Use 'python -m src.cli provider list' to see available providers.",
            )

        # Resolve model
        model_id = model or provider_info.default_model
        model_info = self.registry.get_model(model_id)

        # Resolve key
        api_key = self.resolve_key(provider) if provider_info.requires_key else None
        if provider_info.requires_key and not api_key:
            return RouteResult(
                provider=provider, model=model_id, base_url=provider_info.base_url,
                api_type=provider_info.api_type,
                error=f"No API key found for provider '{provider}'. Set {provider_info.env_key} env var or use 'python -m src.cli apikeys set {provider} <key>'.",
            )

        return RouteResult(
            provider=provider,
            model=model_id,
            base_url=provider_info.base_url,
            api_key=api_key,
            api_type=provider_info.api_type,
            is_local=provider_info.is_local,
            model_info=model_info,
            provider_info=provider_info,
            strategy_used=RouteStrategy.AUTO,
        )

    def _route_auto(
        self,
        task: str = "coding",
        strategy: RouteStrategy = RouteStrategy.AUTO,
        require_vision: bool = False,
        require_reasoning: bool = False,
        require_streaming: bool = True,
        require_function_calling: bool = True,
    ) -> RouteResult:
        """Auto-select the best available provider."""
        available = self.get_available_providers()

        if not available:
            # Fallback to Ollama if nothing else is available
            return RouteResult(
                provider="ollama",
                model="qwen2.5-coder:14b",
                base_url="http://localhost:11434/v1",
                api_key=None,
                api_type="openai",
                is_local=True,
                strategy_used=RouteStrategy.LOCAL_ONLY,
                error="No cloud providers with keys available. Using local Ollama.",
            )

        # Find the best provider for this task
        candidates = []
        for p in available:
            # Get provider's default model
            model_desc = self.registry.get_default_model(p.id)
            if not model_desc:
                continue

            # Check capability requirements
            caps = model_desc.capabilities
            if require_vision and not caps.vision:
                continue
            if require_reasoning and not caps.reasoning:
                continue
            if require_streaming and not caps.streaming:
                continue
            if require_function_calling and not caps.function_calling:
                continue

            # Check task fit
            if task == "coding" and "coding" not in model_desc.classification:
                continue
            if task == "vision" and "vision" not in model_desc.classification:
                continue
            if task == "reasoning" and "reasoning" not in model_desc.classification:
                continue

            # Score based on strategy
            score = self._score_provider(p, model_desc, strategy)
            candidates.append((score, p, model_desc))

        if not candidates:
            # Fallback to first available
            p = available[0]
            model_desc = self.registry.get_default_model(p.id)
            model_id = model_desc.id if model_desc else p.default_model
            api_key = self.resolve_key(p.id) if p.requires_key else None
            return RouteResult(
                provider=p.id, model=model_id, base_url=p.base_url,
                api_key=api_key, api_type=p.api_type,
                is_local=p.is_local,
                strategy_used=strategy,
            )

        # Pick highest scored
        candidates.sort(key=lambda x: -x[0])
        _, best_provider, best_model = candidates[0]
        api_key = self.resolve_key(best_provider.id) if best_provider.requires_key else None

        return RouteResult(
            provider=best_provider.id,
            model=best_model.id,
            base_url=best_provider.base_url,
            api_key=api_key,
            api_type=best_provider.api_type,
            is_local=best_provider.is_local,
            model_info=best_model,
            provider_info=best_provider,
            strategy_used=strategy,
        )

    def _score_provider(
        self,
        provider: ProviderDescriptor,
        model: ModelDescriptor,
        strategy: RouteStrategy,
    ) -> float:
        """Score a provider for a given strategy."""
        score = 0.0

        if strategy == RouteStrategy.FASTEST:
            # Lower priority = faster (usually)
            score = 100 - provider.priority * 10
            # Local is slower
            if provider.is_local:
                score -= 50
        elif strategy == RouteStrategy.CHEAPEST:
            # Free / local = best
            if provider.is_local:
                score = 100
            elif model.pricing_per_million_input == 0:
                score = 90
            else:
                score = 100 - model.pricing_per_million_input * 5
        elif strategy == RouteStrategy.BEST_QUALITY:
            # Reasoning models = best quality
            if model.capabilities.reasoning:
                score = 100
            else:
                score = 50 + (model.context_window / 1_000_000) * 20
        elif strategy == RouteStrategy.LOCAL_ONLY:
            score = 100 if provider.is_local else -100
        else:
            # AUTO: balance priority + capability fit
            score = 100 - provider.priority * 5
            if "coding" in model.classification:
                score += 20
            if model.default_model:
                score += 15
            if model.context_window >= 128_000:
                score += 10
            if provider.is_local:
                score -= 30

        return score

    # == Multi-Provider Racing ================================

    def get_racing_providers(
        self,
        count: int = 3,
        task: str = "coding",
    ) -> list[RouteResult]:
        """Get top N providers for parallel racing (first to respond wins)."""
        available = self.get_available_providers()

        # Score all available providers
        scored = []
        for p in available:
            model_desc = self.registry.get_default_model(p.id)
            if not model_desc:
                continue
            score = self._score_provider(p, model_desc, RouteStrategy.AUTO)
            scored.append((score, p, model_desc))

        # Sort by score descending
        scored.sort(key=lambda x: -x[0])

        results = []
        for _, p, m in scored[:count]:
            api_key = self.resolve_key(p.id) if p.requires_key else None
            results.append(RouteResult(
                provider=p.id, model=m.id, base_url=p.base_url,
                api_key=api_key, api_type=p.api_type,
                is_local=p.is_local, model_info=m, provider_info=p,
            ))

        return results
