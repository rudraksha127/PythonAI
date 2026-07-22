"""Dedicated unit tests for the Model Battle Arena module."""

from __future__ import annotations


class TestBattleModels:
    """Tests for battle Pydantic models."""

    def test_battle_config_defaults(self) -> None:
        from src.battle import BattleConfig
        config = BattleConfig(provider="openai", model="gpt-4o")
        assert config.provider == "openai"
        assert config.model == "gpt-4o"
        assert config.temperature == 0.7
        assert config.max_tokens == 2048
        assert config.label is None

    def test_battle_config_with_label(self) -> None:
        from src.battle import BattleConfig
        config = BattleConfig(
            provider="anthropic",
            model="claude-sonnet-4",
            label="Claude",
            temperature=0.5,
            max_tokens=4096,
        )
        assert config.label == "Claude"
        assert config.temperature == 0.5
        assert config.max_tokens == 4096

    def test_provider_result_defaults(self) -> None:
        from src.battle import ProviderResult
        result = ProviderResult(provider="openai", model="gpt-4o", label="test")
        assert result.content == ""
        assert result.latency_ms == 0.0
        assert result.token_count_total == 0
        assert result.cost_usd == 0.0
        assert result.error is None

    def test_provider_result_with_values(self) -> None:
        from src.battle import ProviderResult
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        result = ProviderResult(
            provider="anthropic",
            model="claude-3-haiku",
            label="Haiku",
            content="Hello!",
            latency_ms=150.0,
            token_count_input=50,
            token_count_output=100,
            token_count_total=150,
            cost_usd=0.0025,
            finished_at=now,
        )
        assert result.content == "Hello!"
        assert result.latency_ms == 150.0
        assert result.cost_usd == 0.0025

    def test_battle_request_validation(self) -> None:
        from src.battle import BattleRequest, BattleConfig
        configs = [BattleConfig(provider="openai", model="gpt-4o")]
        req = BattleRequest(prompt="Test prompt", providers=configs)
        assert req.prompt == "Test prompt"
        assert len(req.providers) == 1

    def test_battle_request_auto_select(self) -> None:
        from src.battle import BattleRequest
        req = BattleRequest(prompt="Test", auto_select=True, auto_count=4)
        assert req.auto_select is True
        assert req.auto_count == 4

    def test_battle_result_defaults(self) -> None:
        from src.battle import BattleResult
        result = BattleResult(prompt="test")
        assert result.prompt == "test"
        assert result.results == []
        assert result.winner is None
        assert result.error is None

    def test_battle_entry(self) -> None:
        from src.battle import BattleEntry
        entry = BattleEntry(
            id="abc123",
            prompt="test prompt",
            provider_count=2,
        )
        assert entry.id == "abc123"
        assert entry.provider_count == 2
        assert entry.winner is None

    def test_battle_response_success(self) -> None:
        from src.battle import BattleResponse
        resp = BattleResponse(success=True)
        assert resp.success is True
        assert resp.error is None

    def test_battle_response_error(self) -> None:
        from src.battle import BattleResponse
        resp = BattleResponse(success=False, error="Provider unavailable")
        assert resp.success is False
        assert resp.error == "Provider unavailable"


class TestBattleEngine:
    """Tests for the battle engine."""

    def test_engine_init(self) -> None:
        from src.battle import BattleEngine
        engine = BattleEngine()
        assert engine.history == []

    def test_estimate_cost_exact_model(self) -> None:
        from src.battle import BattleEngine
        engine = BattleEngine()
        cost = engine._estimate_cost("openai", "gpt-4o", 1000, 500)
        # gpt-4o: $2.50/1M input, $10.00/1M output
        expected = (1000 / 1_000_000 * 2.50) + (500 / 1_000_000 * 10.00)
        assert abs(cost - expected) < 0.0001

    def test_estimate_cost_prefix_model(self) -> None:
        from src.battle import BattleEngine
        engine = BattleEngine()
        cost = engine._estimate_cost("openai", "gpt-4o-2024-08-06", 500, 200)
        # Should match gpt-4o pricing via prefix match
        assert cost > 0

    def test_estimate_cost_unknown_model(self) -> None:
        from src.battle import BattleEngine
        engine = BattleEngine()
        cost = engine._estimate_cost("unknown", "unknown-model", 1000, 500)
        # Should use default pricing
        expected = (1000 / 1_000_000 * 1.00) + (500 / 1_000_000 * 3.00)
        assert abs(cost - expected) < 0.0001

    def test_get_history_empty(self) -> None:
        from src.battle import BattleEngine
        engine = BattleEngine()
        history = engine.get_history()
        assert history == []

    def test_get_history_limit(self) -> None:
        from src.battle import BattleEngine
        engine = BattleEngine()
        # Add some history entries
        from src.battle import BattleEntry
        for i in range(10):
            engine.history.append(
                BattleEntry(id=str(i), prompt=f"Prompt {i}", provider_count=2)
            )
        assert len(engine.get_history(limit=5)) == 5
        assert len(engine.get_history(limit=20)) == 10

    def test_pricing_table_structure(self) -> None:
        from src.battle import BattleEngine
        engine = BattleEngine()
        providers = engine._PRICING
        assert "openai" in providers
        assert "anthropic" in providers
        assert "deepseek" in providers
        assert "gemini" in providers
        assert "mistral" in providers
        assert "groq" in providers

    def test_pricing_values(self) -> None:
        from src.battle import BattleEngine
        engine = BattleEngine()
        # Check specific pricing
        openai = engine._PRICING["openai"]
        assert "gpt-4o" in openai
        input_price, output_price = openai["gpt-4o"]
        assert input_price > 0
        assert output_price > 0
        assert output_price > input_price  # Output always costs more
