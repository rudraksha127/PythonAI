"""
Unit tests for the multi-agent API key management system.

Tests:
  - Provider registry completeness
  - MultiAgentKeyManager basic operations
  - Rate limit tracking
  - Provider selection & fair scheduling
  - Concurrent acquire/release
  - Usage reporting
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from src.data.apikeys import (
    ALL_PROVIDERS,
    PROVIDER_LABELS,
    PROVIDER_TIERS,
    PROVIDER_MAX_CONCURRENCY,
    RateLimitState,
    MultiAgentKeyManager,
    resolve_key,
    resolve_all,
    get_available_providers,
    get_provider_info,
    _load,
)


class TestProviderRegistry:
    """Verify the provider registry is complete and consistent."""

    def test_all_providers_have_labels(self):
        """Every provider in ALL_PROVIDERS must have a label."""
        for prov in ALL_PROVIDERS:
            assert prov in PROVIDER_LABELS, f"{prov} missing from PROVIDER_LABELS"

    def test_all_providers_have_tiers(self):
        """Every provider in ALL_PROVIDERS must have a tier."""
        for prov in ALL_PROVIDERS:
            assert prov in PROVIDER_TIERS, f"{prov} missing from PROVIDER_TIERS"

    def test_all_providers_have_concurrency(self):
        """Every provider in ALL_PROVIDERS must have a concurrency limit."""
        for prov in ALL_PROVIDERS:
            assert prov in PROVIDER_MAX_CONCURRENCY, f"{prov} missing from PROVIDER_MAX_CONCURRENCY"

    def test_premium_providers(self):
        """Verify premium-tier providers."""
        premium = {p for p, t in PROVIDER_TIERS.items() if t == "premium"}
        expected = {"anthropic", "openai", "google", "xai", "deepseek", "cohere"}
        assert premium == expected, f"Expected {expected}, got {premium}"

    def test_provider_count(self):
        """Should have at least 16 providers (10 standard + 6 premium)."""
        assert len(ALL_PROVIDERS) >= 16, f"Expected >=16 providers, got {len(ALL_PROVIDERS)}"


class TestRateLimitState:
    """Test the per-provider rate limit tracker."""

    def test_initial_not_limited(self):
        state = RateLimitState()
        assert not state.is_rate_limited()

    def test_after_429_is_limited(self):
        state = RateLimitState()
        state.record_429()
        assert state.is_rate_limited()

    def test_exponential_backoff(self):
        state = RateLimitState()
        state.record_429()  # 2^1 = 2 seconds
        assert state.backoff_until > time.time()
        assert state.backoff_until <= time.time() + 2 + 0.5  # small tolerance

    def test_backoff_caps_at_120s(self):
        """Consecutive 429s should cap at 120s."""
        state = RateLimitState()
        for _ in range(10):
            state.record_429()
        remaining = state.backoff_until - time.time()
        assert remaining <= 121  # cap at 120s + tolerance

    def test_success_reduces_backoff(self):
        state = RateLimitState()
        state.record_429()
        state.record_success()
        assert state.consecutive_429s == 0

    def test_minute_counter_resets(self):
        state = RateLimitState()
        state.minute_calls = 100
        state.last_reset = time.time() - 61  # Over a minute ago
        state.is_rate_limited()  # Triggers reset
        assert state.minute_calls == 0


class TestMultiAgentKeyManager:
    """Test the core key manager."""

    def test_init_empty(self):
        """Should handle no keys gracefully."""
        km = MultiAgentKeyManager(providers={})
        assert km.count() == 0
        assert km.active_providers == []

    def test_init_with_keys(self):
        km = MultiAgentKeyManager(providers={"groq": "test_key_12345", "openai": "sk-test12345678"})
        assert km.count() == 2
        assert "groq" in km.active_providers
        assert "openai" in km.active_providers

    def test_get_key(self):
        km = MultiAgentKeyManager(providers={"groq": "gsk_test_key_xyz"})
        assert km.get_key("groq") == "gsk_test_key_xyz"
        assert km.get_key("nonexistent") is None

    def test_premium_providers_filter(self):
        km = MultiAgentKeyManager(providers={
            "groq": "test_key_1", "openai": "sk-test-key-12345678",
            "anthropic": "sk-ant-test-key-123", "together": "test_key_2",
        })
        premium = km.premium_providers
        assert "openai" in premium
        assert "anthropic" in premium
        assert "groq" not in premium
        assert "together" not in premium

    def test_standard_providers_filter(self):
        km = MultiAgentKeyManager(providers={
            "groq": "test_key_1", "openai": "sk-test-key-12345678",
        })
        standard = km.standard_providers
        assert "groq" in standard
        assert "openai" not in standard

    def test_add_key_at_runtime(self):
        km = MultiAgentKeyManager(providers={"groq": "old_key"})
        assert km.count() == 1
        km.add_key("openai", "new_key")
        assert km.count() == 2
        assert km.get_key("openai") == "new_key"

    def test_remove_key(self):
        km = MultiAgentKeyManager(providers={"groq": "key1", "openai": "key2"})
        assert km.count() == 2
        km.remove_key("groq")
        assert km.count() == 1
        assert "groq" not in km.active_providers

    def test_acquire_release(self):
        km = MultiAgentKeyManager(providers={"groq": "test_key"})
        assert km.acquire("groq", timeout=1) is True
        km.release("groq")

    def test_acquire_rate_limited(self):
        km = MultiAgentKeyManager(providers={"groq": "test_key"})
        km.record_429("groq")  # Puts it in backoff
        # After a 429, acquire should be denied for non-rate-limited providers
        # Actually let's make the backoff expire immediately by setting it to past
        state = km._rate_states["groq"]
        state.backoff_until = time.time() + 100  # Still in backoff
        assert km.acquire("groq", timeout=1) is False

    def test_concurrent_semaphore_limit(self):
        """Should limit concurrency per provider."""
        km = MultiAgentKeyManager(providers={"groq": "test_key"})
        # Max concurrency for groq is 10
        acquired_count = 0
        for _ in range(12):
            if km.acquire("groq", timeout=0.1):
                acquired_count += 1
            else:
                break
        # Should only acquire up to the semaphore limit (10)
        assert acquired_count == PROVIDER_MAX_CONCURRENCY.get("groq", 10)
        # Release all
        for _ in range(acquired_count):
            km.release("groq")

    def test_select_providers_no_keys(self):
        km = MultiAgentKeyManager(providers={})
        selected = km.select_providers(n=3)
        assert selected == []

    def test_select_providers_returns_available(self):
        km = MultiAgentKeyManager(providers={
            "groq": "key1", "cerebras": "key2",
        })
        selected = km.select_providers(n=2)
        assert len(selected) == 2
        assert "groq" in selected
        assert "cerebras" in selected

    def test_select_providers_premium_only(self):
        km = MultiAgentKeyManager(providers={
            "groq": "key1", "openai": "sk-test-12345678",
            "anthropic": "sk-ant-test-12345",
        })
        selected = km.select_providers(n=2, preferred_tier="premium")
        assert len(selected) == 2
        assert "groq" not in selected
        assert "openai" in selected
        assert "anthropic" in selected

    def test_select_providers_exclude(self):
        km = MultiAgentKeyManager(providers={
            "groq": "key1", "cerebras": "key2", "together": "key3",
        })
        selected = km.select_providers(n=2, exclude={"groq"})
        assert "groq" not in selected
        assert len(selected) == 2

    def test_select_providers_fair_scheduling(self):
        """Providers with fewer calls should be preferred."""
        km = MultiAgentKeyManager(providers={
            "groq": "key1", "cerebras": "key2",
        })
        # Give groq more usage
        km._usage["groq"]["calls"] = 100

        # Select 2 — should prefer cerebras first
        selected = km.select_providers(n=2)
        assert selected[0] == "cerebras"  # Fewer calls

    def test_usage_report(self):
        km = MultiAgentKeyManager(providers={"groq": "key1", "openai": "sk-test-12345678"})
        km.record_success("groq", tokens_used=500)
        km.record_success("openai", tokens_used=1000)
        km.record_429("groq")

        report = km.get_usage_report()
        assert report["total_providers"] == 2
        assert report["summary"]["total_calls"] == 2
        assert report["summary"]["total_429s"] == 1
        assert report["providers"]["groq"]["calls"] == 1
        assert report["providers"]["groq"]["429s"] == 1
        assert report["providers"]["groq"]["tokens"] == 500
        assert report["providers"]["openai"]["tokens"] == 1000

    def test_next_openai_compatible(self):
        km = MultiAgentKeyManager(providers={
            "groq": "key1", "cerebras": "key2", "anthropic": "key3",
        })
        # Should return groq or cerebras, never anthropic
        result = km.next_openai_compatible()
        assert result in ("groq", "cerebras")

    def test_parallel_map_basic(self):
        """Test parallel_map with a simple worker function."""
        km = MultiAgentKeyManager(providers={"groq": "key1", "cerebras": "key2"})

        def worker(provider: str, task_data: int) -> int:
            return task_data * 2

        results = km.parallel_map([1, 2, 3, 4, 5], worker, max_workers=3)
        assert len(results) == 5
        # Some may be None if no provider was available
        valid = [r for r in results if r is not None]
        assert len(valid) > 0

    def test_print_report_doesnt_crash(self):
        """print_report should not throw."""
        km = MultiAgentKeyManager(providers={"groq": "key1"})
        km.record_success("groq")
        km.print_report()  # Just ensure it doesn't crash

    def test_repr(self):
        km = MultiAgentKeyManager(providers={"groq": "key1", "cerebras": "key2"})
        r = repr(km)
        assert "MultiAgentKeyManager" in r
        assert "groq" in r
        assert "cerebras" in r


class TestIntegration:
    """Integration-like tests that exercise the full system."""

    @patch("src.data.apikeys._load", return_value={})
    @patch.dict(os.environ, {
        "GROQ_API_KEY": "gsk_test_key_12345678",
        "OPENAI_API_KEY": "sk-test-key-1234567890",
        "ANTHROPIC_API_KEY": "sk-ant-test-key-123456789",
    }, clear=True)
    def test_resolve_all_from_env(self, mock_load):
        """resolve_all should find keys from environment variables."""
        keys = resolve_all()
        assert "groq" in keys
        assert "openai" in keys
        assert "anthropic" in keys
        assert keys["groq"] == "gsk_test_key_12345678"

    @patch("src.data.apikeys._load", return_value={})
    @patch.dict(os.environ, {
        "GROQ_API_KEY": "gsk_test_key_12345678",
    }, clear=True)
    def test_get_available_providers(self, mock_load):
        """get_available_providers should return only providers with keys."""
        available = get_available_providers()
        assert "groq" in available
        assert "openai" not in available

    @patch("src.data.apikeys._load", return_value={})
    @patch.dict(os.environ, {
        "ANTHROPIC_API_KEY": "sk-ant-test-key-12345",
        "OPENAI_API_KEY": "sk-test-key-1234567890",
    }, clear=True)
    def test_get_available_providers_premium(self, mock_load):
        available = get_available_providers(min_tier="premium")
        assert "anthropic" in available
        assert "openai" in available
        assert "groq" not in available

    @patch("src.data.apikeys._load", return_value={})
    @patch.dict(os.environ, {
        "GROQ_API_KEY": "gsk_test_key_12345678",
    }, clear=True)
    def test_get_provider_info(self, mock_load):
        info = get_provider_info("groq")
        assert info["name"] == "groq"
        assert info["has_key"] is True
        assert info["tier"] == "standard"
        assert info["max_concurrency"] == 10

    @patch("src.data.apikeys._load", return_value={})
    def test_get_provider_info_no_key(self, mock_load):
        info = get_provider_info("openai")
        assert info["name"] == "openai"
        assert info["has_key"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
