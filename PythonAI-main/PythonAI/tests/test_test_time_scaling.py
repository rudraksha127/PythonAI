"""
Unit tests for Test-Time Scaling (PDR+RTV) — test_time_scaling.py
==================================================================

Tests cover:
  - ComplexityScorer: feature extraction, scoring, edge cases
  - RolloutGenerator: parallel generation, summarization, error handling
  - RecursiveTournamentVoting: pairwise comparison, heuristic fallback
  - PDRConditioning: conditioning prompt construction, refinement
  - TestTimeScalingPipeline: full pipeline orchestration, routing
  - TTSConfig: configuration defaults

All tests use mocked LLM calls to avoid requiring actual model inference.
"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from src.training.time_scaling import (
    ComplexityScorer,
    ComplexityFeatures,
    TTSConfig,
    RolloutGenerator,
    RolloutResult,
    RecursiveTournamentVoting,
    PDRConditioning,
    TestTimeScalingPipeline,
    create_ollama_llm_call,
)


# ═══════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════


@pytest.fixture
def default_config() -> TTSConfig:
    return TTSConfig()


@pytest.fixture
def scorer(default_config: TTSConfig) -> ComplexityScorer:
    return ComplexityScorer(default_config)


@pytest.fixture
def mock_llm_call() -> AsyncMock:
    """Mock LLM call that returns a fixed answer."""
    async def _llm_call(
        question: str,
        history: list | None = None,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        return f"Here is a solution to: {question[:50]}...\n```python\ndef solve():\n    pass\n```\nEdge cases: handle empty input."

    return AsyncMock(side_effect=_llm_call)


@pytest.fixture
def mock_varying_llm_call() -> AsyncMock:
    """Mock LLM call that returns different answers based on temperature."""
    async def _varying_call(
        question: str,
        history: list | None = None,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        if temperature < 0.4:
            return "Conservative solution using simple approach.\n```python\nx = 1\n```\nIt works."
        elif temperature < 0.8:
            return "Balanced solution with error handling.\n```python\ndef solve(input):\n    if not input:\n        return None\n    return input\n```\nHandles edge cases."
        else:
            return "Creative but risky solution.\n```python\ndef solve(input):\n    import sys\n    return sys.maxsize\n```\nMay have overflow issues."

    return AsyncMock(side_effect=_varying_call)


@pytest.fixture
def mock_judge_llm() -> AsyncMock:
    """Mock judge LLM that always prefers solution B."""
    async def _judge(
        question: str,
        history: list | None = None,
        system_prompt: str = "",
        temperature: float = 0.2,
        max_tokens: int = 16,
    ) -> str:
        return "B"

    return AsyncMock(side_effect=_judge)


@pytest.fixture
def sample_rollouts() -> list[RolloutResult]:
    return [
        RolloutResult(
            rollout_id="r1",
            answer="Solution A with code.\n```python\nprint('a')\n```\nWorks well.",
            summary="Solution A approach is simple.",
            hypotheses=["Maybe use recursion"],
            progress=["Implemented base case"],
            failure_modes=["Stack overflow for large input"],
            temperature=0.3,
            tokens_used=50,
            elapsed_ms=1000.0,
        ),
        RolloutResult(
            rollout_id="r2",
            answer="Solution B with tests.\n```python\nprint('b')\n```\nTested and verified.",
            summary="Solution B is more thorough.",
            hypotheses=["Iterative approach is better"],
            progress=["Added unit tests", "Handled edge cases"],
            failure_modes=["None identified"],
            temperature=0.7,
            tokens_used=80,
            elapsed_ms=1500.0,
        ),
        RolloutResult(
            rollout_id="r3",
            answer="Solution C creative.\n```python\nprint('c')\n```\nInnovative but risky.",
            summary="Solution C is experimental.",
            hypotheses=["Could use metaprogramming"],
            progress=["Prototype works"],
            failure_modes=["Not production ready", "Memory issues"],
            temperature=1.1,
            tokens_used=60,
            elapsed_ms=2000.0,
        ),
    ]


# ═══════════════════════════════════════════
# TTSConfig Tests
# ═══════════════════════════════════════════


class TestTTSConfig:
    def test_default_values(self) -> None:
        config = TTSConfig()
        assert config.enabled is True
        assert config.complexity_threshold == 0.7
        assert config.num_initial_rollouts == 5
        assert config.num_pdr_rollouts == 2
        assert len(config.temperatures) == 5
        assert config.temperatures[0] == 0.3
        assert config.temperatures[-1] == 1.1

    def test_custom_values(self) -> None:
        config = TTSConfig(
            enabled=False,
            complexity_threshold=0.5,
            num_initial_rollouts=3,
            num_pdr_rollouts=1,
        )
        assert config.enabled is False
        assert config.complexity_threshold == 0.5
        assert config.num_initial_rollouts == 3
        assert config.num_pdr_rollouts == 1

    def test_verbose_default_off(self) -> None:
        config = TTSConfig()
        assert config.verbose is False


# ═══════════════════════════════════════════
# ComplexityScorer Tests
# ═══════════════════════════════════════════


class TestComplexityScorer:
    def test_trivial_question_scores_low(self, scorer: ComplexityScorer) -> None:
        """Short, simple questions should score below 0.4."""
        score = scorer.compute_score("What is Python?")
        assert score < 0.4, f"Expected low score, got {score}"

    def test_empty_question_scores_minimum(self, scorer: ComplexityScorer) -> None:
        """Edge case: very short input should still produce valid score."""
        score = scorer.compute_score("hi")
        assert 0.0 <= score <= 1.0

    def test_complex_refactor_scores_high(self, scorer: ComplexityScorer) -> None:
        """Complex refactoring tasks with security concerns should score high."""
        question = (
            "Refactor the authentication module to use JWT instead of sessions. "
            "The system handles 10K concurrent users. Must be PCI-DSS compliant. "
            "Need to handle edge cases like token expiry and refresh. "
            "Implement thorough testing including integration tests for all endpoints."
        )
        score = scorer.compute_score(question)
        assert score > 0.5, f"Expected high score for complex refactor, got {score}"

    def test_debug_task_scores_moderate(self, scorer: ComplexityScorer) -> None:
        """Debug/fix tasks should score moderately higher."""
        score = scorer.compute_score(
            "Fix the race condition in the async data pipeline. "
            "Multiple workers are writing to the same file simultaneously. "
            "Need a distributed lock solution."
        )
        assert score > 0.2, f"Expected moderate score for debug task, got {score}"

    def test_multi_step_task(self, scorer: ComplexityScorer) -> None:
        """Tasks with multiple explicit steps should score higher."""
        score = scorer.compute_score(
            "First, create the database schema. Then, implement the API endpoints. "
            "Next, add authentication middleware. Finally, deploy to production."
        )
        assert score > 0.3, f"Expected moderate score for multi-step, got {score}"

    def test_feature_extraction(self, scorer: ComplexityScorer) -> None:
        """Verify feature extraction accuracy."""
        question = "Fix the bug in src/main.py and add tests for security"
        features = scorer.extract_features(question)

        assert features.has_debug is True
        assert features.has_security_concern is True
        assert features.has_test_requirement is True
        assert features.num_file_mentions >= 1
        assert features.num_code_keywords >= 2

    def test_score_bounds_clamped(self, scorer: ComplexityScorer) -> None:
        """Score should always be within [0.0, 1.0]."""
        extremes = [
            "",
            "a",
            "x" * 5000,  # Very long input
            "debug " * 100,  # Lots of keywords
            "security performance test implement fix refactor " * 50,
        ]
        for q in extremes:
            score = scorer.compute_score(q)
            assert 0.0 <= score <= 1.0, f"Score {score} out of bounds for: {q[:50]}"

    def test_history_not_required(self, scorer: ComplexityScorer) -> None:
        """Scorer should work without history."""
        score = scorer.compute_score("Write a function")
        assert 0.0 <= score <= 1.0


# ═══════════════════════════════════════════
# RolloutGenerator Tests
# ═══════════════════════════════════════════


class TestRolloutGenerator:
    @pytest.mark.asyncio
    async def test_generate_rollouts_success(self, mock_varying_llm_call: AsyncMock, default_config: TTSConfig) -> None:
        """Should generate the requested number of rollouts."""
        generator = RolloutGenerator(llm_call=mock_varying_llm_call, config=default_config)
        results = await generator.generate_rollouts(
            question="Write a sort function",
            num_rollouts=3,
        )
        assert len(results) == 3
        assert all(r.error is None for r in results)
        assert all(r.answer for r in results)

    @pytest.mark.asyncio
    async def test_rollouts_have_different_temperatures(self, mock_varying_llm_call: AsyncMock, default_config: TTSConfig) -> None:
        """Rollouts should use different temperatures."""
        generator = RolloutGenerator(llm_call=mock_varying_llm_call, config=default_config)
        results = await generator.generate_rollouts(
            question="Write a function",
            temperatures=[0.3, 0.7, 1.1],
            num_rollouts=3,
        )
        temps = [r.temperature for r in results]
        assert len(set(temps)) == 3, f"Expected 3 different temperatures, got {temps}"

    @pytest.mark.asyncio
    async def test_error_handling(self, default_config: TTSConfig) -> None:
        """Should handle LLM failures gracefully."""
        async def failing_call(**kwargs) -> str:
            raise RuntimeError("LLM unavailable")

        generator = RolloutGenerator(llm_call=failing_call, config=default_config)
        results = await generator.generate_rollouts(
            question="Test",
            num_rollouts=2,
        )
        # Should return at least the first error result
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_error_when_no_llm(self, default_config: TTSConfig) -> None:
        """Should raise ValueError when no LLM call is set."""
        generator = RolloutGenerator(llm_call=None, config=default_config)
        with pytest.raises(ValueError, match="LLM call function not set"):
            await generator.generate_rollouts(question="Test")

    def test_summarize_rollout(self) -> None:
        """Test the rollout summarization logic."""
        answer = """I think we should use a recursive approach.
Maybe the base case is when input is empty.
First, handle the base case.
Then, process recursively.
Caution: this can cause stack overflow for large inputs.
```python
def solve(n):
    if n == 0:
        return 0
    return n + solve(n-1)
```
Edge cases: negative numbers not handled."""

        summary, hypotheses, progress, failure_modes = RolloutGenerator._summarize_rollout(answer)

        assert len(hypotheses) >= 1
        assert any("recursive" in h.lower() for h in hypotheses)
        assert len(progress) >= 1
        assert len(failure_modes) >= 1
        assert "caution" in failure_modes[0].lower() or "stack overflow" in failure_modes[0].lower()


# ═══════════════════════════════════════════
# RecursiveTournamentVoting Tests
# ═══════════════════════════════════════════


class TestRecursiveTournamentVoting:
    @pytest.mark.asyncio
    async def test_select_winner_with_judge(
        self, sample_rollouts: list[RolloutResult], mock_judge_llm: AsyncMock, default_config: TTSConfig
    ) -> None:
        """Should select a winner using the judge LLM."""
        tournament = RecursiveTournamentVoting(llm_call=mock_judge_llm, config=default_config)
        winner = await tournament.select_winner(sample_rollouts, question="Test question")
        assert winner is not None
        assert winner.rollout_id in [r.rollout_id for r in sample_rollouts]

    @pytest.mark.asyncio
    async def test_heuristic_fallback(self, sample_rollouts: list[RolloutResult], default_config: TTSConfig) -> None:
        """Should use heuristic scoring when no judge LLM available."""
        tournament = RecursiveTournamentVoting(llm_call=None, config=default_config)
        winner = await tournament.select_winner(sample_rollouts, question="Test")
        assert winner is not None
        # Should prefer the most balanced temperature (0.7)
        assert winner.temperature == 0.7

    def test_single_rollout_returns_immediately(self, default_config: TTSConfig) -> None:
        """Single rollout should be returned without comparison."""
        async def test():
            tournament = RecursiveTournamentVoting(llm_call=None, config=default_config)
            single = [RolloutResult(rollout_id="r1", answer="test", summary="test")]
            winner = await tournament.select_winner(single, question="test")
            assert winner.rollout_id == "r1"
            return winner

        asyncio.run(test())

    def test_heuristic_score_prefers_balanced_temperature(self) -> None:
        """Heuristic should prefer moderate temperatures with code blocks."""
        good = RolloutResult(
            rollout_id="good",
            answer="Solution with code.\n```python\nx = 1\n```\nHandles errors.",
            temperature=0.7,
            tokens_used=100,
        )
        bad = RolloutResult(
            rollout_id="bad",
            answer="Short",
            temperature=1.5,
            tokens_used=10,
        )
        score_good = RecursiveTournamentVoting._heuristic_score(good)
        score_bad = RecursiveTournamentVoting._heuristic_score(bad)
        assert score_good > score_bad


# ═══════════════════════════════════════════
# PDRConditioning Tests
# ═══════════════════════════════════════════


class TestPDRConditioning:
    @pytest.mark.asyncio
    async def test_refine_success(self, mock_llm_call: AsyncMock, default_config: TTSConfig) -> None:
        """PDR refinement should produce a refined rollout."""
        winner = RolloutResult(
            rollout_id="winner1",
            answer="Base solution.",
            summary="Simple approach.",
            hypotheses=["Use caching"],
            progress=["Basic implementation done"],
            failure_modes=["Cache invalidation"],
            temperature=0.7,
        )
        pdr = PDRConditioning(llm_call=mock_llm_call, config=default_config)
        refined = await pdr.refine(
            question="Build a cache",
            winner=winner,
        )
        assert refined is not None
        assert refined.rollout_id.startswith("pdr-")
        assert refined.answer

    @pytest.mark.asyncio
    async def test_refine_fallback_when_no_llm(self, default_config: TTSConfig) -> None:
        """Should return original winner when no LLM available."""
        winner = RolloutResult(rollout_id="w1", answer="test", summary="test")
        pdr = PDRConditioning(llm_call=None, config=default_config)
        refined = await pdr.refine(question="test", winner=winner)
        assert refined is winner

    def test_build_conditioning_prompt(self) -> None:
        """Conditioning prompt should include hypotheses and failure modes."""
        winner = RolloutResult(
            rollout_id="w1",
            answer="test",
            summary="test",
            hypotheses=["Hypothesis 1", "Hypothesis 2"],
            progress=["Step 1 done", "Step 2 done"],
            failure_modes=["Memory issue", "Race condition"],
        )
        prompt = PDRConditioning._build_conditioning_prompt(winner, "Test question")
        assert "Hypothesis 1" in prompt
        assert "Step 1 done" in prompt
        assert "Memory issue" in prompt
        assert "Race condition" in prompt


# ═══════════════════════════════════════════
# TestTimeScalingPipeline Tests
# ═══════════════════════════════════════════


class TestTestTimeScalingPipeline:
    @pytest.mark.asyncio
    async def test_fast_path_for_easy_task(self, mock_llm_call: AsyncMock, default_config: TTSConfig) -> None:
        """Easy tasks should use the fast path (single call)."""
        pipeline = TestTimeScalingPipeline(llm_call=mock_llm_call, config=default_config)
        result = await pipeline.run(
            question="What is 2+2?",
            force_hard=False,
        )
        assert result["route"] == "fast"
        assert result["complexity_score"] < 0.4
        assert result["answer"]
        assert result["pdr_applied"] is False
        assert result["rtv_applied"] is False

    @pytest.mark.asyncio
    async def test_hard_path_for_complex_task(self, mock_varying_llm_call: AsyncMock, default_config: TTSConfig) -> None:
        """Hard tasks should use the full PDR+RTV pipeline."""
        pipeline = TestTimeScalingPipeline(llm_call=mock_varying_llm_call, config=default_config)
        result = await pipeline.run(
            question="Implement a distributed cache with security, performance optimization, "
                     "fault tolerance, thread safety, and comprehensive testing. "
                     "First set up the architecture, then implement the core, then add tests.",
            force_hard=True,
        )
        assert result["route"] == "hard"
        assert result["answer"]
        assert result["num_rollouts"] >= 1
        assert result["winner_id"]
        assert "elapsed_ms" in result

    @pytest.mark.asyncio
    async def test_force_hard_bypasses_threshold(self, mock_varying_llm_call: AsyncMock, default_config: TTSConfig) -> None:
        """force_hard=True should always use the hard path."""
        pipeline = TestTimeScalingPipeline(llm_call=mock_varying_llm_call, config=default_config)
        result = await pipeline.run(
            question="Simple question",
            force_hard=True,
        )
        assert result["route"] == "hard"

    @pytest.mark.asyncio
    async def test_pre_computed_complexity(self, mock_llm_call: AsyncMock, default_config: TTSConfig) -> None:
        """Pre-computed complexity score should be used as-is."""
        pipeline = TestTimeScalingPipeline(llm_call=mock_llm_call, config=default_config)
        result = await pipeline.run(
            question="Any question",
            complexity_score=0.8,  # Should route to hard
        )
        assert result["complexity_score"] == 0.8
        assert result["route"] == "hard"

    def test_get_and_reset_stats(self, default_config: TTSConfig) -> None:
        """Stats tracking should work correctly."""
        async def run_test():
            pipeline = TestTimeScalingPipeline(llm_call=mock_varying_llm_call, config=default_config)

            # Run two pipelines
            await pipeline.run(question="Easy Q", force_hard=False)
            await pipeline.run(question="Complex Q with security, performance, testing, and distributed architecture. Multiple steps required.", force_hard=True)

            stats = pipeline.get_stats()
            assert stats["total_pipelines"] == 2
            assert stats["fast_tasks"] >= 1

            pipeline.reset_stats()
            reset = pipeline.get_stats()
            assert reset["total_pipelines"] == 0

        mock_varying_llm_call = AsyncMock()
        async def _mock_call(**kwargs):
            return "Answer"
        mock_varying_llm_call.side_effect = _mock_call
        asyncio.run(run_test())

    @pytest.mark.asyncio
    async def test_pipeline_error_handling(self, default_config: TTSConfig) -> None:
        """Pipeline should handle LLM failures gracefully."""
        async def failing_call(**kwargs) -> str:
            raise RuntimeError("Server down")

        pipeline = TestTimeScalingPipeline(llm_call=failing_call, config=default_config)
        result = await pipeline.run(question="Test question", force_hard=True)
        # Should either have an error, or still have a route
        assert "error" in result
        assert "route" in result


# ═══════════════════════════════════════════
# create_ollama_llm_call Tests
# ═══════════════════════════════════════════


class TestCreateOllamaLLMCall:
    def test_returns_callable(self) -> None:
        llm_call = create_ollama_llm_call(model="test-model")
        assert callable(llm_call)

    def test_default_model(self) -> None:
        llm_call = create_ollama_llm_call()
        assert callable(llm_call)
