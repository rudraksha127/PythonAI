"""Unit tests for the ForgeAI review module."""

from __future__ import annotations

import pytest
from src.review import ReviewEngine, ReviewRequest, ReviewResult


class TestReviewEngine:
    """Tests for ReviewEngine core functionality."""

    def setup_method(self) -> None:
        self.engine = ReviewEngine()

    def test_review_code_basic(self) -> None:
        """Test basic code review returns expected structure."""
        code = "def add(a, b):\n    return a + b\n"
        request = ReviewRequest(code=code, language="python")
        result = self.engine.review_code(request)

        assert isinstance(result, ReviewResult)
        assert result.language == "python"
        assert result.score >= 0.0
        assert result.score <= 10.0
        assert isinstance(result.issues, list)
        assert isinstance(result.strengths, list)
        assert isinstance(result.suggestions, list)

    def test_review_empty_code(self) -> None:
        """Test review handles empty code gracefully."""
        request = ReviewRequest(code="", language="python")
        result = self.engine.review_code(request)
        assert result.score == 10.0


class TestReviewRequest:
    """Tests for ReviewRequest validation."""

    def test_valid_request(self) -> None:
        req = ReviewRequest(code="x = 1", language="python")
        assert req.code == "x = 1"
        assert req.language == "python"

    def test_file_path(self) -> None:
        req = ReviewRequest(code="x = 1", language="python", file_path="test.py")
        assert req.file_path == "test.py"
