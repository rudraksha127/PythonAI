"""Tests for RolloutGenerator (test-time scaling component)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.training.time_scaling import (
    RolloutGenerator,
    RolloutResult,
    TTSConfig,
)


class TestRolloutResult:
    """Test the RolloutResult dataclass."""

    def test_default_values(self) -> None:
        """Verify default values are sensible."""
        r = RolloutResult(rollout_id="test-1", answer="def foo(): pass")
        assert r.rollout_id == "test-1"
        assert r.answer == "def foo(): pass"
        assert r.summary == ""
        assert r.hypotheses == []
        assert r.progress == []
        assert r.failure_modes == []
        assert r.temperature == 0.7
        assert r.tokens_used == 0
        assert r.elapsed_ms == 0.0
        assert r.error is None

    def test_custom_values(self) -> None:
        """Verify custom values are stored."""
        r = RolloutResult(
            rollout_id="test-2",
            answer="optimized code",
            summary="A good solution",
            hypotheses=["Use caching"],
            progress=["Implemented cache"],
            failure_modes=["Memory issue"],
            temperature=0.5,
            tokens_used=100,
            elapsed_ms=500.0,
        )
        assert r.rollout_id == "test-2"
        assert r.summary == "A good solution"
        assert r.hypotheses == ["Use caching"]
        assert r.temperature == 0.5
        assert r.tokens_used == 100
        assert r.elapsed_ms == 500.0


class TestRolloutGenerator:
    """Test the RolloutGenerator class."""

    @pytest.fixture
    def config(self) -> TTSConfig:
        return TTSConfig(
            enabled=True,
            num_initial_rollouts=3,
            temperatures=[0.3, 0.5, 0.7],
            verbose=False,
        )

    @pytest.fixture
    def mock_llm(self) -> Any:
        """Create a mock LLM call function that returns predictable responses."""

        async def llm_call(
            question: str,
            history: list[dict[str, str]] | None = None,
            system_prompt: str = "",
            temperature: float = 0.7,
            max_tokens: int = 4096,
        ) -> str:
            return f"Answer for: {question[:50]} (temp={temperature:.1f})"

        return llm_call

    def test_requires_llm_call(self, config: TTSConfig) -> None:
        """Generator should raise error if no LLM call is set."""
        generator = RolloutGenerator(config=config)
        with pytest.raises(ValueError, match="LLM call function not set"):
            asyncio.run(generator.generate_rollouts("test question"))

    def test_single_rollout(self, config: TTSConfig, mock_llm: Any) -> None:
        """Should generate at least one rollout."""
        generator = RolloutGenerator(llm_call=mock_llm, config=config)
        results = asyncio.run(generator.generate_rollouts("Hello world"))
        assert len(results) >= 1

    def test_multiple_rollouts(self, config: TTSConfig, mock_llm: Any) -> None:
        """Should generate the requested number of rollouts."""
        generator = RolloutGenerator(llm_call=mock_llm, config=config)
        results = asyncio.run(generator.generate_rollouts("Test", num_rollouts=3))
        assert len(results) == 3

    def test_rollout_temperatures(self, config: TTSConfig, mock_llm: Any) -> None:
        """Rollouts should have different temperatures."""
        generator = RolloutGenerator(llm_call=mock_llm, config=config)
        results = asyncio.run(
            generator.generate_rollouts("Test", num_rollouts=3, temperatures=[0.3, 0.5, 0.7])
        )
        temps = [r.temperature for r in results]
        # Should be sorted by temperature
        assert temps == sorted(temps)

    def test_rollout_has_answer(self, config: TTSConfig, mock_llm: Any) -> None:
        """Each rollout should have non-empty answer."""
        generator = RolloutGenerator(llm_call=mock_llm, config=config)
        results = asyncio.run(generator.generate_rollouts("Hello world", num_rollouts=2))
        for r in results:
            assert r.answer, f"Rollout {r.rollout_id} has empty answer"

    def test_stats_tracking(self, config: TTSConfig, mock_llm: Any) -> None:
        """Stats should track rollouts and tokens."""
        generator = RolloutGenerator(llm_call=mock_llm, config=config)
        asyncio.run(generator.generate_rollouts("Test question", num_rollouts=2))
        assert generator._stats["total_rollouts"] >= 2
        assert generator._stats["total_tokens"] > 0

    def test_set_llm_call(self, config: TTSConfig, mock_llm: Any) -> None:
        """set_llm_call should work after construction."""
        generator = RolloutGenerator(config=config)
        generator.set_llm_call(mock_llm)
        results = asyncio.run(generator.generate_rollouts("Hello", num_rollouts=1))
        assert len(results) == 1


class TestSummarizeRollout:
    """Test the static _summarize_rollout method."""

    def test_summary_with_code_block(self) -> None:
        """Should extract summary from non-code text."""
        answer = """Here's a Python function to sort a list.

```python
def sort_list(items):
    return sorted(items)
```

This uses the built-in sorted function which is efficient."""
        summary, hypotheses, progress, failure_modes = RolloutGenerator._summarize_rollout(answer)
        assert len(summary) > 0
        assert "Python function" in summary or "sort" in summary.lower()

    def test_hypothesis_detection(self) -> None:
        """Should detect hypothesis/analysis patterns."""
        answer = """I think the issue might be a caching problem.
Perhaps we should invalidate the cache after writes.
The likely cause is stale data being served."""
        _, hypotheses, _, _ = RolloutGenerator._summarize_rollout(answer)
        assert len(hypotheses) >= 2
        assert any("caching" in h.lower() for h in hypotheses)

    def test_failure_mode_detection(self) -> None:
        """Should detect warnings and edge cases."""
        answer = """Caution: this approach doesn't handle empty lists.
Warning: memory usage grows with input size.
Edge case: what if the user passes None?"""
        _, _, _, failure_modes = RolloutGenerator._summarize_rollout(answer)
        assert len(failure_modes) >= 2
        assert any("empty" in f.lower() for f in failure_modes)

    def test_empty_answer(self) -> None:
        """Should handle empty answers gracefully."""
        summary, hypotheses, progress, failure_modes = RolloutGenerator._summarize_rollout("")
        assert summary == "" or len(summary) <= 300



