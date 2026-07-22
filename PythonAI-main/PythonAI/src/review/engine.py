"""
Code Review Engine — the main orchestrator that runs reviews using
LLM-based analysis.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from .git_analyzer import GitAnalyzer, GitChange
from .models import (
    BatchReviewRequest,
    BatchReviewResult,
    ReviewCategory,
    ReviewIssue,
    ReviewRequest,
    ReviewResult,
    ReviewSeverity,
)


class ReviewEngine:
    """
    Code Review Engine that uses an LLM provider to analyze code and
    produce structured review reports.
    """

    def __init__(
        self,
        provider: str = "auto",
        model: str = "",
        call_llm_fn: Any = None,
    ):
        self.provider = provider
        self.model = model
        self._call_llm_fn = call_llm_fn

    def review_code(self, request: ReviewRequest) -> ReviewResult:
        """Review a single code snippet or file."""
        start = time.time()

        # Build the review prompt
        prompt = self._build_review_prompt(request)

        # Call LLM
        response = self._call_llm(prompt)
        tokens_used = len(response) // 4  # rough estimate

        # Parse the structured response
        try:
            parsed = self._parse_response(response)
        except Exception:
            parsed = {
                "summary": response[:2000],
                "score": 5.0,
                "issues": [],
                "strengths": [],
                "suggestions": [],
            }

        result = ReviewResult(
            summary=parsed.get("summary", "Review completed."),
            score=parsed.get("score", 5.0),
            issues=[ReviewIssue(**i) for i in parsed.get("issues", [])],
            strengths=parsed.get("strengths", []),
            suggestions=parsed.get("suggestions", []),
            language=request.language,
            file_path=request.file_path,
            token_count=tokens_used,
        )

        elapsed = time.time() - start

        return result

    def review_batch(self, request: BatchReviewRequest) -> BatchReviewResult:
        """Review multiple files in batch."""
        reviews = []
        for file_req in request.files:
            result = self.review_code(file_req)
            reviews.append(result)

        # Aggregate results
        total_issues = sum(len(r.issues) for r in reviews)
        critical_count = sum(
            sum(1 for i in r.issues if i.severity == ReviewSeverity.CRITICAL)
            for r in reviews
        )
        error_count = sum(
            sum(1 for i in r.issues if i.severity == ReviewSeverity.ERROR)
            for r in reviews
        )

        avg_score = sum(r.score for r in reviews) / len(reviews) if reviews else 0.0

        # Generate summary
        lang_counts: dict[str, int] = {}
        for r in reviews:
            lang_counts[r.language] = lang_counts.get(r.language, 0) + 1

        summary = (
            f"Reviewed {len(reviews)} files across {len(lang_counts)} languages. "
            f"Overall quality score: {avg_score:.1f}/10. "
            f"Found {total_issues} issues ({critical_count} critical, {error_count} errors)."
        )

        return BatchReviewResult(
            reviews=reviews,
            overall_score=round(avg_score, 1),
            total_issues=total_issues,
            critical_count=critical_count,
            error_count=error_count,
            summary=summary,
        )

    def review_git_changes(
        self,
        git_analyzer: GitAnalyzer,
        changes: list[GitChange] | None = None,
    ) -> BatchReviewResult:
        """Review changes from a git diff."""
        if changes is None:
            changes = git_analyzer.get_uncommitted_changes()

        # Filter out binary/deleted files
        valid_changes = [
            c for c in changes
            if c.change_type != "deleted"
            and c.language != "unknown"
            and c.language in ("python", "javascript", "typescript", "go", "rust", "java", "c", "cpp", "csharp", "ruby", "php", "swift", "kotlin", "scala")
        ]

        if not valid_changes:
            return BatchReviewResult(
                reviews=[],
                overall_score=10.0,
                total_issues=0,
                summary="No code changes to review (all files are binary, deleted, or unknown language).",
            )

        file_requests = []
        for change in valid_changes:
            content = git_analyzer.get_new_content(change)
            if not content.strip():
                continue

            file_requests.append(
                ReviewRequest(
                    code=content,
                    language=change.language,
                    file_path=change.file_path,
                    context=(
                        f"Change type: {change.change_type}. "
                        f"Additions: {change.additions}, Deletions: {change.deletions}. "
                        f"File: {change.file_path}"
                    ),
                )
            )

        if not file_requests:
            return BatchReviewResult(
                reviews=[],
                overall_score=10.0,
                total_issues=0,
                summary="No reviewable changes found (all changes are empty).",
            )

        return self.review_batch(
            BatchReviewRequest(
                files=file_requests,
                project_context=f"Reviewing {len(valid_changes)} changed files from git diff.",
            )
        )

    def _build_review_prompt(self, request: ReviewRequest) -> str:
        """Build the LLM prompt for code review."""
        focus = ""
        if request.focus_areas:
            focus = f"\nFocus on these areas: {', '.join(f.value for f in request.focus_areas)}"

        context = ""
        if request.context:
            context = f"\nContext: {request.context}"

        file_info = ""
        if request.file_path:
            file_info = f"\nFile: {request.file_path}"

        return f"""You are a senior code reviewer AI. Review the following {request.language} code carefully.

{file_info}{context}{focus}

LANGUAGE: {request.language}
MAX ISSUES: {request.max_issues}

Provide your review as STRICT JSON with this exact structure:
{{
  "summary": "A concise summary of the code quality (2-3 sentences)",
  "score": <0.0-10.0 overall quality score>,
  "issues": [
    {{
      "line": <line_number or null>,
      "column": <column_number or null>,
      "severity": "critical|error|warning|info|style",
      "category": "correctness|security|performance|style|best_practice|edge_case|error_handling|type_safety|duplication|documentation|compatibility|maintainability",
      "message": "Description of the issue",
      "suggestion": "How to fix it",
      "code_snippet": "Relevant code (max 200 chars)"
    }}
  ],
  "strengths": ["What the code does well"],
  "suggestions": ["Actionable improvement suggestions"]
}}

Consider:
1. CORRECTNESS: Does it work correctly in all cases? Any bugs?
2. SECURITY: Are there any security vulnerabilities (injection, XSS, etc.)?
3. PERFORMANCE: Are there performance bottlenecks?
4. STYLE: Does it follow language best practices and conventions?
5. EDGE CASES: Are edge cases handled (empty input, None, boundaries)?
6. ERROR HANDLING: Are errors properly caught and handled?
7. TYPE SAFETY: Are types used correctly? Any type confusion?
8. DUPLICATION: Is there repeated code that should be abstracted?

CODE TO REVIEW:
```{request.language}
{request.code}
```

Respond ONLY with the JSON object. No markdown, no code fences."""
    def _call_llm(self, prompt: str) -> str:
        """Call the LLM provider to get a review.

        Uses the configured provider. Falls back to a simple
        built-in analysis if no LLM is available.
        """
        if self._call_llm_fn:
            result = self._call_llm_fn(prompt)
            if result:
                return result

        # Try using the provider system
        try:
            from ..core.providers import ProfileManager, ProviderRouter, get_provider_api

            router = ProviderRouter()
            profile = ProfileManager().load()
            provider = profile.provider if profile else "auto"
            model = profile.model if profile else ""

            route = router.route(provider=provider, model=model, task="review")

            if route.error:
                # Try first available provider
                available = router.get_available_providers()
                for p in available:
                    r = router.route(provider=p.id)
                    if not r.error:
                        route = r
                        break
                else:
                    return self._fallback_review(prompt)

            api_fn = get_provider_api(route.provider)
            result = api_fn(
                messages=[
                    {"role": "system", "content": "You are a senior code reviewer. Respond with JSON only."},
                    {"role": "user", "content": prompt},
                ],
                model=route.model,
                base_url=route.base_url,
                api_key=route.api_key or "",
                temperature=0.2,
                max_tokens=4096,
            )

            if result.get("error"):
                return self._fallback_review(prompt)

            return result.get("content", "")

        except ImportError:
            return self._fallback_review(prompt)
        except Exception:
            return self._fallback_review(prompt)

    def _fallback_review(self, prompt: str) -> str:
        """Simple built-in review when no LLM is available."""
        import re

        code_lines = prompt.split("```")[1].split("\n")[1:] if "```" in prompt else []
        code = "\n".join(code_lines)

        issues = []
        strengths = []
        score = 7.0

        # Basic checks
        lines = code.split("\n")
        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # Check for TODOs
            if "TODO" in stripped or "FIXME" in stripped:
                issues.append({
                    "line": i,
                    "severity": "info",
                    "category": "maintainability",
                    "message": f"Incomplete work marker: {stripped.strip()[:60]}",
                    "suggestion": "Complete the implementation and remove the marker.",
                })
                score -= 0.2

            # Check for hardcoded values
            if re.match(r'^\s*(password|secret|api_key|token)\s*=\s*["\']', stripped, re.IGNORECASE):
                issues.append({
                    "line": i,
                    "severity": "critical",
                    "category": "security",
                    "message": "Hardcoded credential detected.",
                    "suggestion": "Use environment variables or a secrets manager instead.",
                })
                score -= 1.0

            # Check for broad exception handlers
            if "except:" in stripped or "except Exception:" in stripped:
                issues.append({
                    "line": i,
                    "severity": "warning",
                    "category": "error_handling",
                    "message": "Broad exception handler may hide unexpected errors.",
                    "suggestion": "Catch specific exceptions instead of using a bare except.",
                })
                score -= 0.3

            # Check for print debugging
            if re.match(r'^\s*print\(', stripped) and len(stripped) < 80:
                issues.append({
                    "line": i,
                    "severity": "style",
                    "category": "best_practice",
                    "message": "Debug print statement found.",
                    "suggestion": "Use proper logging instead of print statements.",
                })
                score -= 0.1

            # Long lines
            if len(line) > 100:
                issues.append({
                    "line": i,
                    "column": 100,
                    "severity": "style",
                    "category": "style",
                    "message": f"Line too long ({len(line)} chars). Consider wrapping.",
                    "suggestion": "Break the line into multiple lines for better readability.",
                })
                score -= 0.05

        # Check for docstrings (Python)
        if code.strip().startswith("def ") or "class " in code:
            has_docstring = '"""' in code or "'''" in code
            if not has_docstring:
                score -= 0.3
                issues.append({
                    "line": None,
                    "severity": "info",
                    "category": "documentation",
                    "message": "Functions/classes may lack docstrings.",
                    "suggestion": "Add docstrings to explain the purpose and behavior.",
                })

        # Some strengths
        if any(len(line) < 80 for line in lines):
            strengths.append("Code generally follows line length conventions.")

        if len([l for l in lines if l.strip() and not l.strip().startswith("#")]) > 0:
            strengths.append("Contains meaningful, non-trivial code.")

        # Clamp score
        score = max(0.0, min(10.0, score))

        result = {
            "summary": f"Basic review completed. Found {len(issues)} issues. Score: {score:.1f}/10.",
            "score": round(score, 1),
            "issues": issues[:20],
            "strengths": strengths or ["Code structure appears reasonable."],
            "suggestions": [
                "Configure a cloud LLM provider (OpenAI, Anthropic, etc.) for deeper AI-powered reviews.",
                "Run 'forgeai config init' to set up your API keys.",
            ],
        }

        return json.dumps(result, ensure_ascii=False)

    def _parse_response(self, response: str) -> dict[str, Any]:
        """Parse the LLM response into structured data."""
        # Try to extract JSON from the response
        import re

        # Find JSON object in response
        json_match = re.search(r"\{[\s\S]*\}", response)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # Try parsing entire response as JSON
        cleaned = response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]

        try:
            return json.loads(cleaned.strip())
        except json.JSONDecodeError:
            pass

        # Fallback: create a basic result from the response text
        return {
            "summary": response[:2000] if response else "Review completed.",
            "score": 5.0,
            "issues": [],
            "strengths": ["Review generated."],
            "suggestions": ["Review the full analysis for details."],
        }
