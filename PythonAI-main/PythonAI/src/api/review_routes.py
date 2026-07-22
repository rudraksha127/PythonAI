"""
ForgeAI Code Review Routes
============================
Handles /api/review/code and /api/review/git endpoints.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("forgeai.api.review")
router = APIRouter(tags=["Code Review"])


class ReviewCodeRequest(BaseModel):
    """Request to review a code snippet."""
    code: str = Field(..., min_length=1, max_length=100000)
    language: str = Field(default="python", max_length=50)
    file_path: str | None = Field(default=None, max_length=500)
    context: str | None = Field(default=None, max_length=5000)


class ReviewGitRequest(BaseModel):
    """Request to review git changes."""
    repo_path: str | None = Field(default=None, max_length=2000)
    commit_range: str | None = Field(default=None, max_length=200)
    staged: bool = Field(default=False)


@router.post("/api/review/code")
async def review_code(body: ReviewCodeRequest) -> dict[str, Any]:
    """
    Review a code snippet for issues, security concerns, and best practices.

    Uses the configured LLM provider for deep analysis. Falls back to
    a basic built-in analyzer if no provider is available.

    Returns structured review with issues, strengths, and a quality score.
    """
    from src.review import ReviewEngine, ReviewRequest

    try:
        engine = ReviewEngine()
        request = ReviewRequest(
            code=body.code,
            language=body.language,
            file_path=body.file_path,
            context=body.context,
        )
        result = engine.review_code(request)

        return {
            "success": True,
            "summary": result.summary,
            "score": result.score,
            "issues": [i.model_dump() for i in result.issues],
            "strengths": result.strengths,
            "suggestions": result.suggestions,
            "language": result.language,
            "file_path": result.file_path,
            "token_count": result.token_count,
        }
    except Exception as e:
        logger.error(f"Code review error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Review failed: {e}")


@router.post("/api/review/git")
async def review_git(body: ReviewGitRequest) -> dict[str, Any]:
    """
    Review uncommitted git changes or a specific commit range.

    Analyzes the diff, extracts changed code, and runs the review
    engine on each modified file.
    """
    from src.review import GitAnalyzer, ReviewEngine

    try:
        repo_path = body.repo_path or os.getcwd()
        analyzer = GitAnalyzer(repo_path=repo_path)

        if body.commit_range:
            changes = analyzer.get_diff(commit_range=body.commit_range)
        elif body.staged:
            changes = analyzer.get_diff(staged=True)
        else:
            changes = analyzer.get_uncommitted_changes()

        if not changes:
            return {
                "success": True,
                "files_reviewed": 0,
                "overall_score": 10.0,
                "total_issues": 0,
                "reviews": [],
                "summary": "No changes to review.",
            }

        engine = ReviewEngine()
        result = engine.review_git_changes(analyzer, changes)

        return {
            "success": True,
            "files_reviewed": len(result.reviews),
            "overall_score": result.overall_score,
            "total_issues": result.total_issues,
            "critical_count": result.critical_count,
            "error_count": result.error_count,
            "reviews": [
                {
                    "file_path": r.file_path,
                    "summary": r.summary,
                    "score": r.score,
                    "issues": [i.model_dump() for i in r.issues],
                    "strengths": r.strengths,
                    "suggestions": r.suggestions,
                    "language": r.language,
                }
                for r in result.reviews
            ],
            "summary": result.summary,
        }
    except Exception as e:
        logger.error(f"Git review error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Git review failed: {e}")
