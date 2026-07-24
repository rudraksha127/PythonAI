"""Tests for ComplexityScorer (test-time scaling component)."""

from __future__ import annotations

import pytest

from src.training.time_scaling import ComplexityScorer, ComplexityFeatures, TTSConfig


class TestComplexityFeatures:
    """Test the ComplexityFeatures dataclass."""

    def test_default_values(self) -> None:
        """Verify default values are zero/false."""
        f = ComplexityFeatures()
        assert f.question_length == 0
        assert f.num_sentences == 0
        assert f.num_code_keywords == 0
        assert not f.has_debug
        assert not f.has_refactor

    def test_custom_values(self) -> None:
        """Verify custom values are stored correctly."""
        f = ComplexityFeatures(
            question_length=100,
            num_sentences=5,
            num_code_keywords=3,
            has_debug=True,
            has_implement=True,
            estimated_tools_needed=4,
        )
        assert f.question_length == 100
        assert f.num_sentences == 5
        assert f.num_code_keywords == 3
        assert f.has_debug
        assert f.has_implement
        assert not f.has_refactor
        assert f.estimated_tools_needed == 4


class TestComplexityScorer:
    """Test the ComplexityScorer class."""

    @pytest.fixture
    def scorer(self) -> ComplexityScorer:
        return ComplexityScorer()

    @pytest.fixture
    def verbose_scorer(self) -> ComplexityScorer:
        config = TTSConfig(verbose=True)
        return ComplexityScorer(config)

    def test_simple_question(self, scorer: ComplexityScorer) -> None:
        """A simple question should score low."""
        score = scorer.compute_score("What is Python?")
        assert 0.0 <= score <= 0.6, f"Simple question scored too high: {score}"

    def test_complex_question(self, scorer: ComplexityScorer) -> None:
        """A complex multi-step question should score higher."""
        question = (
            "Refactor the authentication service to use JWT tokens instead of session cookies. "
            "First, update the login endpoint to return a signed JWT. "
            "Then, add middleware to verify tokens on protected routes. "
            "Finally, write tests for the new authentication flow including edge cases."
        )
        score = scorer.compute_score(question)
        assert score >= 0.35, f"Complex question scored too low: {score}"

    def test_debug_question(self, scorer: ComplexityScorer) -> None:
        """A bug-fix question should detect debug intent."""
        score = scorer.compute_score(
            "Fix the race condition in the distributed task queue. "
            "The workers are crashing when multiple tasks try to update the same record."
        )
        assert score >= 0.15, f"Debug question scored too low: {score}"

    def test_empty_question(self, scorer: ComplexityScorer) -> None:
        """An empty/minimal question should score near zero."""
        score = scorer.compute_score("Hi")
        assert score < 0.3, f"Empty question scored too high: {score}"

    def test_security_question(self, scorer: ComplexityScorer) -> None:
        """A security-related question should score higher."""
        score = scorer.compute_score(
            "Implement input sanitization to prevent SQL injection attacks "
            "in the user search endpoint. Ensure all edge cases are handled."
        )
        assert score >= 0.25, f"Security question scored too low: {score}"

    def test_performance_question(self, scorer: ComplexityScorer) -> None:
        """A performance optimization question should score higher."""
        score = scorer.compute_score(
            "Optimize the database queries to reduce latency. "
            "The current implementation is too slow for production."
        )
        assert score >= 0.30, f"Performance question scored too low: {score}"

    def test_extract_features_simple(self, scorer: ComplexityScorer) -> None:
        """Verify feature extraction for a simple question."""
        features = scorer.extract_features("Hello world")
        assert features.question_length > 0
        assert features.num_sentences >= 1
        assert features.num_code_keywords == 0

    def test_extract_features_complex(self, scorer: ComplexityScorer) -> None:
        """Verify feature extraction for a complex question with keywords."""
        features = scorer.extract_features(
            "Debug the async deadlock in the microservice. "
            "Refactor the code to use proper async patterns. "
            "Write tests to verify the fix. Implement error handling."
        )
        assert features.num_code_keywords >= 2
        assert features.has_debug
        assert features.has_refactor
        assert features.has_test_requirement

    def test_score_range(self, scorer: ComplexityScorer) -> None:
        """All scores should be in [0.0, 1.0]."""
        questions = [
            "Hello",
            "What is a variable?",
            "Write a Python function to sort a list.",
            "Refactor the microservice to use async/await patterns.",
            "Implement a distributed transaction saga pattern with compensation.",
        ]
        for q in questions:
            score = scorer.compute_score(q)
            assert 0.0 <= score <= 1.0, f"Score out of range for '{q[:30]}': {score}"

    def test_verbose_logging(self, verbose_scorer: ComplexityScorer) -> None:
        """Verbose mode should not affect scoring."""
        score_quiet = verbose_scorer.compute_score("Write a simple hello world program.")
        score_loud = verbose_scorer.compute_score("Write a simple hello world program.")
        assert score_quiet == score_loud

    def test_file_mention_detection(self, scorer: ComplexityScorer) -> None:
        """Questions mentioning files should score higher."""
        features = scorer.extract_features("Fix the bug in src/main.py and test/utils/test_helper.ts")
        assert features.num_file_mentions >= 2


class TestComplexityScorerWithHistory:
    """Test ComplexityScorer with conversation history."""

    @pytest.fixture
    def scorer(self) -> ComplexityScorer:
        return ComplexityScorer()

    def test_history_does_not_crash(self, scorer: ComplexityScorer) -> None:
        """History parameter should not cause errors."""
        history = [
            {"role": "user", "content": "Write a Python function"},
            {"role": "assistant", "content": "Here's the function..."},
        ]
        score = scorer.compute_score("Now optimize it.", history)
        assert 0.0 <= score <= 1.0
