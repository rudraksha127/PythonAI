"""
Battle Engine — Orchestrates parallel model comparisons.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from .models import (
    BattleConfig,
    BattleEntry,
    BattleRequest,
    BattleResult,
    ProviderResult,
)


class BattleEngine:
    """
    Sends the same prompt to multiple LLM providers in parallel
    and collects responses with latency, token usage, and cost metrics.
    """

    # Estimated cost per 1M tokens (USD) — approximate pricing
    _PRICING: dict[str, dict[str, tuple[float, float]]] = {
        "openai": {
            "gpt-4o": (2.50, 10.00),
            "gpt-4o-mini": (0.15, 0.60),
            "gpt-4.1": (2.00, 8.00),
            "gpt-4.1-mini": (0.40, 1.60),
            "gpt-4.1-nano": (0.10, 0.40),
            "o3": (10.00, 40.00),
            "o4-mini": (1.10, 4.40),
        },
        "anthropic": {
            "claude-sonnet-4": (3.00, 15.00),
            "claude-sonnet-4-20250514": (3.00, 15.00),
            "claude-opus-4": (15.00, 75.00),
            "claude-3-5-sonnet-20241022": (3.00, 15.00),
            "claude-3-haiku-20240307": (0.25, 1.25),
        },
        "deepseek": {
            "deepseek-chat": (0.27, 1.10),
            "deepseek-reasoner": (0.55, 2.19),
        },
        "gemini": {
            "gemini-2.5-pro": (1.25, 10.00),
            "gemini-2.5-flash": (0.15, 0.60),
            "gemini-2.0-flash": (0.10, 0.40),
        },
        "mistral": {
            "mistral-large": (2.00, 6.00),
            "mistral-small": (0.20, 0.60),
        },
        "groq": {
            "llama-3.3-70b": (0.59, 0.79),
            "mixtral-8x7b": (0.24, 0.24),
        },
    }

    _DEFAULT_INPUT_PRICE = 1.00
    _DEFAULT_OUTPUT_PRICE = 3.00

    def __init__(self):
        self.history: list[BattleEntry] = []

    def run_battle(self, request: BattleRequest) -> BattleResult:
        """Run a battle: send prompt to all providers and collect results."""
        from src.core.providers import ProviderRouter, get_provider_api

        started_at = datetime.now(timezone.utc)
        start_time = time.time()
        router = ProviderRouter()

        # If auto_select, get top providers
        if request.auto_select or not request.providers:
            routes = router.get_racing_providers(count=request.auto_count if request.auto_select else 3)
            configs = [
                BattleConfig(provider=r.provider, model=r.model, label=f"{r.provider}/{r.model}")
                for r in routes
            ]
        else:
            configs = request.providers

        # Build messages
        messages: list[dict[str, Any]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})

        results: list[ProviderResult] = []

        for config in configs:
            label = config.label or f"{config.provider}/{config.model}"
            provider_start = time.time()

            try:
                # Get the API function for this provider
                api_fn = get_provider_api(config.provider)

                # Get route info for base_url and api_key
                route = router.route(
                    provider=config.provider,
                    model=config.model,
                )

                if route.error:
                    results.append(ProviderResult(
                        provider=config.provider,
                        model=config.model,
                        label=label,
                        content="",
                        error=route.error,
                        latency_ms=(time.time() - provider_start) * 1000,
                    ))
                    continue

                # Call the provider
                response = api_fn(
                    messages=messages,
                    model=config.model,
                    base_url=route.base_url,
                    api_key=route.api_key or "",
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                )

                provider_elapsed = (time.time() - provider_start) * 1000

                if response.get("error"):
                    results.append(ProviderResult(
                        provider=config.provider,
                        model=config.model,
                        label=label,
                        content="",
                        error=response["error"],
                        latency_ms=provider_elapsed,
                    ))
                    continue

                content = response.get("content", "")
                usage = response.get("usage", {})

                input_tokens = usage.get("prompt_tokens", usage.get("input_tokens", 0))
                output_tokens = usage.get("completion_tokens", usage.get("output_tokens", 0))
                total_tokens = usage.get("total_tokens", input_tokens + output_tokens)

                # Estimate cost
                cost = self._estimate_cost(config.provider, config.model, input_tokens, output_tokens)

                results.append(ProviderResult(
                    provider=config.provider,
                    model=config.model,
                    label=label,
                    content=content,
                    latency_ms=provider_elapsed,
                    token_count_input=input_tokens,
                    token_count_output=output_tokens,
                    token_count_total=total_tokens,
                    cost_usd=cost,
                    finished_at=datetime.now(timezone.utc),
                ))

            except Exception as e:
                results.append(ProviderResult(
                    provider=config.provider,
                    model=config.model,
                    label=label,
                    content="",
                    error=str(e),
                    latency_ms=(time.time() - provider_start) * 1000,
                ))

        total_elapsed = (time.time() - start_time) * 1000
        completed_at = datetime.now(timezone.utc)

        # Determine winner (best content length + no error)
        successful = [r for r in results if not r.error and r.content.strip()]
        winner = None
        if successful:
            # Winner = longest meaningful response (rough quality heuristic)
            winner = max(successful, key=lambda r: len(r.content))
            winner_label = winner.label

        battle_result = BattleResult(
            prompt=request.prompt[:200],
            system_prompt=request.system_prompt,
            results=results,
            winner=winner_label if winner else None,
            total_latency_ms=total_elapsed,
            started_at=started_at,
            completed_at=completed_at,
        )

        # Save to history
        self.history.append(BattleEntry(
            id=uuid.uuid4().hex[:12],
            prompt=request.prompt[:200],
            provider_count=len(configs),
            results=results,
            winner=winner_label if winner else None,
            created_at=time.time(),
        ))

        return battle_result

    def get_history(self, limit: int = 20) -> list[BattleEntry]:
        """Get battle history."""
        return self.history[-limit:]

    def _estimate_cost(self, provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost in USD for a given provider + model + token counts."""
        provider_pricing = self._PRICING.get(provider, {})
        # Try exact model match, then prefix match
        pricing = provider_pricing.get(model)
        if not pricing:
            for model_key, price in provider_pricing.items():
                if model.startswith(model_key):
                    pricing = price
                    break

        if not pricing:
            pricing = (self._DEFAULT_INPUT_PRICE, self._DEFAULT_OUTPUT_PRICE)

        input_price_per_m, output_price_per_m = pricing
        cost = (input_tokens / 1_000_000 * input_price_per_m) + (output_tokens / 1_000_000 * output_price_per_m)
        return round(cost, 6)
