"""
Pydantic models for Code Review Agent.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ReviewSeverity(str, Enum):
    """Severity level for a review finding."""

    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    STYLE = "style"


class ReviewCategory(str, Enum):
    """Category of code review finding."""

    CORRECTNESS = "correctness"
    SECURITY = "security"
    PERFORMANCE = "performance"
    STYLE = "style"
    BEST_PRACTICE = "best_practice"
    EDGE_CASE = "edge_case"
    ERROR_HANDLING = "error_handling"
    TYPE_SAFETY = "type_safety"
    DUPLICATION = "duplication"
    DOCUMENTATION = "documentation"
    COMPATIBILITY = "compatibility"
    MAINTAINABILITY = "maintainability"


class ReviewIssue(BaseModel):
    """A single issue found during code review."""

    line: int | None = Field(default=None, description="Line number where the issue occurs")
    column: int | None = Field(default=None, description="Column number")
    severity: ReviewSeverity = Field(default=ReviewSeverity.INFO)
    category: ReviewCategory = Field(default=ReviewCategory.BEST_PRACTICE)
    message: str = Field(..., min_length=1, max_length=1000)
    suggestion: str | None = Field(default=None, max_length=2000)
    code_snippet: str | None = Field(default=None, max_length=500)


class ReviewResult(BaseModel):
    """Complete code review result."""

    summary: str = Field(..., min_length=1, max_length=5000)
    score: float = Field(default=0.0, ge=0.0, le=10.0, description="Overall code quality score (0-10)")
    issues: list[ReviewIssue] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    language: str = Field(default="python")
    file_path: str | None = Field(default=None)
    commit_sha: str | None = Field(default=None)
    token_count: int = Field(default=0, ge=0)


class ReviewRequest(BaseModel):
    """Request to review code."""

    code: str = Field(..., min_length=1, max_length=100000)
    language: str = Field(default="python", max_length=50)
    file_path: str | None = Field(default=None, max_length=500)
    context: str | None = Field(default=None, max_length=5000)
    focus_areas: list[ReviewCategory] | None = Field(default=None)
    max_issues: int = Field(default=20, ge=1, le=100)


class BatchReviewRequest(BaseModel):
    """Review multiple files at once."""

    files: list[ReviewRequest] = Field(..., min_length=1, max_length=50)
    project_context: str | None = Field(default=None, max_length=10000)


class BatchReviewResult(BaseModel):
    """Results from reviewing multiple files."""

    reviews: list[ReviewResult] = Field(default_factory=list)
    overall_score: float = Field(default=0.0, ge=0.0, le=10.0)
    total_issues: int = Field(default=0)
    critical_count: int = Field(default=0)
    error_count: int = Field(default=0)
    summary: str = Field(default="", max_length=5000)
