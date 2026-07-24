"""
Test-Time Scaling — PDR+RTV for Hard Task Routing
====================================================

Implements the PDR (Parallel-Distill-Refine) + RTV (Recursive Tournament Voting)
framework from "Scaling Test-Time Compute for Agentic Coding" (arXiv:2604.16529).

The core insight: for complex coding tasks (complexity_score > 0.7), the model
benefits from generating multiple parallel rollouts, comparing them via recursive
tournament voting, and then conditioning new rollouts on the distilled winner.

Pipeline:
  1. ComplexityScorer determines if a task is "hard" (score > 0.7 threshold)
  2. For hard tasks, RolloutGenerator spawns N=5 parallel LLM calls
  3. Each rollout is summarized (hypotheses + progress + failure modes)
  4. RecursiveTournamentVoting compares summaries in pairs → selects winner
  5. PDRConditioning: 2 new rollouts conditioned on winner's summary → pick best
  6. Final answer returned with quality metadata

Research: "Scaling Test-Time Compute for Agentic Coding" (arXiv 2604.16529, 2026)
  - Claude Opus 4.5: 70.9% → 77.6% SWE-bench Verified
  - Terminal-Bench v2.0: 46.9% → 59.1%
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("forgeai.tts")


# ═══════════════════════════════════════════════
# Dataclasses
# ═══════════════════════════════════════════════


@dataclass
class RolloutResult:
    """Result of a single model rollout (parallel generation)."""

    rollout_id: str
    answer: str
    summary: str = ""
    hypotheses: list[str] = field(default_factory=list)
    progress: list[str] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)
    temperature: float = 0.7
    tokens_used: int = 0
    elapsed_ms: float = 0.0
    error: str | None = None


@dataclass
class ComplexityFeatures:
    """Features used by ComplexityScorer to assess task difficulty."""

    question_length: int = 0
    num_sentences: int = 0
    num_code_keywords: int = 0
    num_file_mentions: int = 0
    num_step_indicators: int = 0
    has_debug: bool = False
    has_refactor: bool = False
    has_implement: bool = False
    has_optimize: bool = False
    has_explain_debug: bool = False
    has_multiple_languages: bool = False
    has_test_requirement: bool = False
    has_security_concern: bool = False
    has_performance_constraint: bool = False
    estimated_tools_needed: int = 0


@dataclass
class TTSConfig:
    """Configuration for Test-Time Scaling."""

    enabled: bool = True
    complexity_threshold: float = 0.7
    num_initial_rollouts: int = 5
    num_pdr_rollouts: int = 2
    temperatures: list[float] = field(
        default_factory=lambda: [0.3, 0.5, 0.7, 0.9, 1.1]
    )
    max_tokens_per_rollout: int = 4096
    summary_max_tokens: int = 512
    tournament_judge_model: str = ""
    verbose: bool = False

    # Complexity weightings
    keyword_weight: float = 0.15
    length_weight: float = 0.10
    step_weight: float = 0.20
    constraint_weight: float = 0.25
    tool_weight: float = 0.15
    debug_weight: float = 0.15


# ═══════════════════════════════════════════════
# Complexity Scorer
# ═══════════════════════════════════════════════


class ComplexityScorer:
    """Scores a task's complexity from 0.0 (trivial) to 1.0 (very hard).

    Uses a weighted heuristic based on:
    - Question length and structure
    - Presence of complexity keywords (debug, refactor, implement, etc.)
    - Number of steps or file mentions
    - Constraints (security, performance, testing)
    - Estimated tool requirements
    """

    # Keywords that indicate higher complexity
    _COMPLEX_KEYWORDS: list[str] = [
        "refactor", "refactoring", "restructure", "rewrite",
        "optimize", "optimization", "performance", "slow",
        "debug", "debugging", "fix", "bug", "issue",
        "implement", "implementing", "build", "create",
        "migrate", "migration", "upgrade",
        "secure", "security", "vulnerability", "exploit",
        "parallel", "concurrent", "async", "deadlock",
        "distributed", "microservice", "architecture",
        "test", "testing", "coverage", "integration test",
        "deploy", "deployment", "ci/cd", "pipeline",
        "monitor", "monitoring", "observability", "telemetry",
        "authenticate", "authorize", "oauth", "jwt",
        "database", "query", "transaction", "orm",
        "docker", "kubernetes", "container", "orchestrate",
    ]

    # Step indicators
    _STEP_INDICATORS: list[str] = [
        "first", "then", "next", "finally", "step",
        "phase", "stage", "1.", "2.", "3.",
        "first step", "second step", "third step",
    ]

    # Difficulty boosters
    _DIFFICULTY_PHRASES: list[str] = [
        "e2e", "end-to-end", "production", "edge case",
        "error handling", "rollback", "fault tolerant",
        "high availability", "scalable", "load test",
        "zero downtime", "blue-green", "canary",
        "compliance", "hipaa", "pci", "gdpr", "soc2",
        "multi-threaded", "race condition", "deadlock",
        "distributed transaction", "saga",
        "cross-cutting", "cross cutting",
    ]

    def __init__(self, config: TTSConfig | None = None) -> None:
        self.config = config or TTSConfig()

    def extract_features(self, question: str, history: list[dict[str, str]] | None = None) -> ComplexityFeatures:
        """Extract complexity features from a question and optional history."""
        q_lower = question.lower()
        f = ComplexityFeatures()

        # Length and structure
        f.question_length = len(question)
        f.num_sentences = max(1, len([s for s in re.split(r"[.!?]+", question) if s.strip()]))

        # Code keywords
        f.num_code_keywords = sum(1 for kw in self._COMPLEX_KEYWORDS if kw in q_lower)

        # File mentions (e.g., "src/main.py", "file.ts", "/path/to/file")
        f.num_file_mentions = len(re.findall(r'(?:[\w./-]+\.(?:py|js|ts|jsx|tsx|go|rs|java|cpp|c|h|cs|swift|kt|rb|php))', question))

        # Step indicators
        f.num_step_indicators = sum(1 for si in self._STEP_INDICATORS if si in q_lower)

        # Boolean flags
        f.has_debug = any(w in q_lower for w in ["debug", "fix", "bug", "issue", "error"])
        f.has_refactor = any(w in q_lower for w in ["refactor", "restructure", "rewrite"])
        f.has_implement = any(w in q_lower for w in ["implement", "build", "create", "write a"])
        f.has_optimize = any(w in q_lower for w in ["optimize", "performance", "slow", "speed up"])
        f.has_explain_debug = bool(re.search(r"(why|explain|how.*work|what.*mean)", q_lower))
        f.has_test_requirement = any(w in q_lower for w in ["test", "coverage", "assertion"])
        f.has_security_concern = any(w in q_lower for w in [
            "secure", "security", "vulnerability", "exploit", "sanitize",
            "validate input", "sql injection", "xss", "csrf",
        ])
        f.has_performance_constraint = any(w in q_lower for w in [
            "performance", "latency", "throughput", "scalable", "efficient",
            "fast", "optimize", "memory", "cpu",
        ])

        # Multiple languages hint
        lang_exts = re.findall(r'\.(py|js|ts|jsx|tsx|go|rs|java|cpp)', question)
        f.has_multiple_languages = len(set(lang_exts)) > 1

        # Estimated tools needed
        tool_indicators = [
            "python", "javascript", "typescript",  # language mentions
            "react", "vue", "angular",  # frameworks
            "docker", "kubernetes",  # infra
            "database", "sql", "nosql",  # data
            "api", "rest", "graphql",  # api
            "git", "github",  # vcs
            "npm", "pip", "maven",  # package managers
        ]
        f.estimated_tools_needed = sum(1 for t in tool_indicators if t in q_lower)

        return f

    def compute_score(self, question: str, history: list[dict[str, str]] | None = None) -> float:
        """Compute a complexity score between 0.0 and 1.0.

        Args:
            question: The user's question/task.
            history: Optional conversation history for additional context.

        Returns:
            Float between 0.0 (trivial) and 1.0 (very hard).
        """
        cfg = self.config
        features = self.extract_features(question, history)

        # Component scores (each 0.0-1.0)
        # 1. Keyword density
        max_expected_keywords = 8
        keyword_score = min(1.0, features.num_code_keywords / max_expected_keywords)

        # 2. Length score — longer questions tend to be more complex
        length_score = min(1.0, features.question_length / 800)

        # 3. Step/plan score — multiple steps indicate complexity
        step_score = min(1.0, (features.num_step_indicators + features.num_file_mentions) / 6)

        # 4. Constraint score — security, performance, testing requirements
        constraint_score = 0.0
        if features.has_security_concern:
            constraint_score += 0.4
        if features.has_performance_constraint:
            constraint_score += 0.3
        if features.has_test_requirement:
            constraint_score += 0.3
        constraint_score = min(1.0, constraint_score)

        # 5. Debug/refactor score
        debug_score = 0.0
        if features.has_debug:
            debug_score += 0.3
        if features.has_refactor:
            debug_score += 0.3
        if features.has_implement:
            debug_score += 0.2
        if features.has_optimize:
            debug_score += 0.2
        debug_score = min(1.0, debug_score)

        # 6. Tool diversity score
        tool_score = min(1.0, features.estimated_tools_needed / 8)

        # 7. Difficulty phrase bonus
        difficulty_bonus = 0.0
        q_lower = question.lower()
        for phrase in self._DIFFICULTY_PHRASES:
            if phrase in q_lower:
                difficulty_bonus += 0.08
        difficulty_bonus = min(0.4, difficulty_bonus)

        # Weighted combination
        score = (
            cfg.keyword_weight * keyword_score
            + cfg.length_weight * length_score
            + cfg.step_weight * step_score
            + cfg.constraint_weight * constraint_score
            + cfg.debug_weight * debug_score
            + cfg.tool_weight * tool_score
            + difficulty_bonus
        )

        # Clamp to [0.0, 1.0]
        score = max(0.0, min(1.0, score))

        if cfg.verbose:
            logger.info(
                f"[TTS-Complexity] score={score:.2f} "
                f"(keyword={keyword_score:.2f}, length={length_score:.2f}, "
                f"step={step_score:.2f}, constraint={constraint_score:.2f}, "
                f"debug={debug_score:.2f}, tool={tool_score:.2f}, "
                f"difficulty_bonus={difficulty_bonus:.2f})"
            )

        return score


# ═══════════════════════════════════════════════
# Rollout Generator
# ═══════════════════════════════════════════════

# Type for LLM call: async fn(question, history, system_prompt, temperature, max_tokens) -> str
LLMCallable = Callable[
    [str, list[dict[str, str]], str, float, int],
    Any,  # Coroutine that returns str
]


class RolloutGenerator:
    """Generates N parallel LLM rollouts with temperature diversity.

    Each rollout uses a different temperature to explore the solution space.
    After generation, each rollout is summarized into hypotheses, progress,
    and failure modes for comparison.
    """

    def __init__(
        self,
        llm_call: LLMCallable | None = None,
        config: TTSConfig | None = None,
    ) -> None:
        self.llm_call = llm_call
        self.config = config or TTSConfig()
        self._stats: dict[str, Any] = {
            "total_rollouts": 0,
            "total_tokens": 0,
            "total_elapsed_ms": 0.0,
        }

    def set_llm_call(self, llm_call: LLMCallable) -> None:
        """Set the LLM call function (injected by the server)."""
        self.llm_call = llm_call

    async def generate_rollouts(
        self,
        question: str,
        history: list[dict[str, str]] | None = None,
        system_prompt: str = "",
        num_rollouts: int | None = None,
        temperatures: list[float] | None = None,
    ) -> list[RolloutResult]:
        """Generate N parallel rollouts with different temperatures.

        Args:
            question: The task/question.
            history: Optional conversation history.
            system_prompt: System prompt to use.
            num_rollouts: Number of rollouts (default: config.num_initial_rollouts).
            temperatures: Temperature values to use (default: config.temperatures).

        Returns:
            List of RolloutResult objects.
        """
        if self.llm_call is None:
            raise ValueError("LLM call function not set. Call set_llm_call() first.")

        n = num_rollouts or self.config.num_initial_rollouts
        temps = temperatures or self.config.temperatures

        # Ensure we have enough temperatures by cycling if needed
        if len(temps) < n:
            temps = (temps * (n // len(temps) + 1))[:n]
        else:
            temps = temps[:n]

        history = history or []
        tasks: list[asyncio.Task] = []

        async def _run_rollout(temp: float) -> RolloutResult:
            rollout_id = str(uuid.uuid4())[:8]
            start = time.time()
            try:
                answer = await self.llm_call(
                    question=question,
                    history=history,
                    system_prompt=system_prompt,
                    temperature=temp,
                    max_tokens=self.config.max_tokens_per_rollout,
                )
                elapsed_ms = (time.time() - start) * 1000
                tokens_used = len(answer.split())

                result = RolloutResult(
                    rollout_id=rollout_id,
                    answer=answer,
                    temperature=temp,
                    tokens_used=tokens_used,
                    elapsed_ms=elapsed_ms,
                )

                # Generate structured summary
                result.summary, result.hypotheses, result.progress, result.failure_modes = (
                    self._summarize_rollout(answer)
                )

                self._stats["total_rollouts"] += 1
                self._stats["total_tokens"] += tokens_used
                self._stats["total_elapsed_ms"] += elapsed_ms

                if self.config.verbose:
                    logger.info(
                        f"[TTS-Rollout] {rollout_id}: temp={temp:.1f}, "
                        f"tokens={tokens_used}, elapsed={elapsed_ms:.0f}ms"
                    )

                return result

            except Exception as e:
                elapsed_ms = (time.time() - start) * 1000
                logger.warning(f"[TTS-Rollout] {rollout_id} failed: {e}")
                return RolloutResult(
                    rollout_id=rollout_id,
                    answer="",
                    temperature=temp,
                    error=str(e),
                    elapsed_ms=elapsed_ms,
                )

        for temp in temps:
            tasks.append(asyncio.create_task(_run_rollout(temp)))

        results = await asyncio.gather(*tasks)

        # Sort by temperature for deterministic ordering
        results.sort(key=lambda r: r.temperature)

        # Filter out errors
        valid = [r for r in results if r.error is None and r.answer.strip()]
        if not valid and results:
            # All failed — return best effort (first error result)
            logger.warning("[TTS] All rollouts failed, returning first error")
            return results[:1]

        valid_count = len(valid)
        failed_count = len(results) - valid_count
        if failed_count > 0 and self.config.verbose:
            logger.info(f"[TTS] {valid_count}/{len(results)} rollouts succeeded")

        return valid

    @staticmethod
    def _summarize_rollout(answer: str) -> tuple[str, list[str], list[str], list[str]]:
        """Extract structured summary from a rollout answer.

        Returns:
            Tuple of (summary_text, hypotheses, progress, failure_modes).
        """
        lines = answer.split("\n")

        # Summary: first substantive paragraph (skip code blocks)
        summary_parts: list[str] = []
        in_code_block = False
        for line in lines:
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                continue
            if not in_code_block and line.strip():
                summary_parts.append(line.strip())

        summary = " ".join(summary_parts[:8])[:500] if summary_parts else answer[:300]

        # Hypotheses: detect explanation/analysis patterns
        hypotheses: list[str] = []
        in_code_block = False
        for i, line in enumerate(lines):
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                continue
            if not in_code_block and re.search(
                r"(i think|maybe|perhaps|could be|might be|likely|probably|possible|cause|because|reason)",
                line.lower(),
            ):
                hypotheses.append(line.strip()[:150])

        # Progress: code blocks, concrete steps
        progress: list[str] = []
        in_code_block = False
        for i, line in enumerate(lines):
            if line.strip().startswith("```"):
                code_content = []
                in_code_block = True
                continue
            if in_code_block:
                if line.strip().startswith("```"):
                    in_code_block = False
                    if code_content:
                        # Summarize code block
                        code_preview = " ".join(code_content[:3])[:100]
                        progress.append(f"Code: {code_preview}")
                    continue
                code_content.append(line.strip())

        # Also look for explicit steps/actions
        for line in lines:
            stripped = line.strip()
            if re.match(r"^(?:step|then |finally |next |first|second|third|\d+[.)])", stripped.lower()):
                progress.append(stripped[:150])

        # Failure modes: look for warnings, edge cases, limitations
        failure_modes: list[str] = []
        for line in lines:
            stripped = line.strip()
            if re.search(
                r"(caution|warning|note|be careful|pitfall|gotcha|common mistake|"
                r"edge case|limitation|drawback|trade.?off|however|but be aware|"
                r"not recommended|avoid|don't|shouldn't)",
                stripped.lower(),
            ):
                failure_modes.append(stripped[:150])

        # Truncate to reasonable max
        hypotheses = hypotheses[:5]
        progress = progress[:5]
        failure_modes = failure_modes[:5]

        return summary, hypotheses, progress, failure_modes


# ═══════════════════════════════════════════════
# Recursive Tournament Voting (RTV)
# ═══════════════════════════════════════════════


class RecursiveTournamentVoting:
    """Selects the best rollout via recursive pairwise comparison.

    Algorithm:
      1. Group rollouts into pairs (or triplets for odd counts).
      2. For each group, use a judge prompt to compare summaries.
      3. Advance the winner of each group to the next round.
      4. Repeat until one winner remains.

    The judge uses these criteria:
      - Correctness: Does the solution actually solve the problem?
      - Completeness: Are all requirements addressed?
      - Quality: Is the code well-structured and idiomatic?
      - Safety: Are edge cases and error handling addressed?
    """

    def __init__(
        self,
        llm_call: LLMCallable | None = None,
        config: TTSConfig | None = None,
    ) -> None:
        self.llm_call = llm_call
        self.config = config or TTSConfig()
        self._stats: dict[str, Any] = {
            "rounds": 0,
            "comparisons": 0,
            "judge_tokens": 0,
        }

    def set_llm_call(self, llm_call: LLMCallable) -> None:
        self.llm_call = llm_call

    async def select_winner(
        self,
        rollouts: list[RolloutResult],
        question: str,
    ) -> RolloutResult:
        """Run recursive tournament voting to select the best rollout.

        Args:
            rollouts: List of RolloutResults to compare.
            question: The original question (used for judging context).

        Returns:
            The winning RolloutResult.
        """
        if len(rollouts) == 1:
            return rollouts[0]

        if self.llm_call is None:
            # Fallback: use heuristic scoring
            logger.info("[TTS-RTV] No judge LLM available, using heuristic scoring")
            return self._heuristic_select(rollouts)

        candidates = list(rollouts)
        round_num = 1

        while len(candidates) > 1:
            self._stats["rounds"] += 1
            next_round: list[RolloutResult] = []

            # Pair up candidates
            for i in range(0, len(candidates), 2):
                if i + 1 < len(candidates):
                    winner = await self._compare_pair(
                        candidates[i], candidates[i + 1], question
                    )
                    next_round.append(winner)
                else:
                    # Odd one out advances automatically
                    next_round.append(candidates[i])

            if self.config.verbose:
                logger.info(
                    f"[TTS-RTV] Round {round_num}: {len(candidates)} → "
                    f"{len(next_round)} candidates"
                )

            candidates = next_round
            round_num += 1

        winner = candidates[0]

        if self.config.verbose:
            logger.info(
                f"[TTS-RTV] Winner: {winner.rollout_id} "
                f"(temp={winner.temperature:.1f}, "
                f"tokens={winner.tokens_used}, "
                f"elapsed={winner.elapsed_ms:.0f}ms)"
            )

        return winner

    async def _compare_pair(
        self,
        a: RolloutResult,
        b: RolloutResult,
        question: str,
    ) -> RolloutResult:
        """Compare two rollouts using the judge LLM."""
        self._stats["comparisons"] += 1

        judge_prompt = f"""You are a senior engineer judging two solutions to a coding task.
Analyze each solution carefully and choose the better one.

TASK:
{question[:500]}

SOLUTION A (Temperature {a.temperature:.1f}):
{a.summary[:500]}

Hypotheses: {', '.join(a.hypotheses[:3]) if a.hypotheses else 'None listed'}
Progress: {', '.join(a.progress[:3]) if a.progress else 'None listed'}
Failure modes: {', '.join(a.failure_modes[:3]) if a.failure_modes else 'None listed'}

SOLUTION B (Temperature {b.temperature:.1f}):
{b.summary[:500]}

Hypotheses: {', '.join(b.hypotheses[:3]) if b.hypotheses else 'None listed'}
Progress: {', '.join(b.progress[:3]) if b.progress else 'None listed'}
Failure modes: {', '.join(b.failure_modes[:3]) if b.failure_modes else 'None listed'}

Evaluate on:
1. **Correctness** — does it solve the actual problem?
2. **Completeness** — are all requirements addressed?
3. **Code Quality** — is it well-structured and idiomatic?
4. **Safety** — are edge cases and error handling considered?

Respond with ONLY "A" or "B" — the letter of the better solution."""

        try:
            result = await self.llm_call(
                question=judge_prompt,
                history=[],
                system_prompt="You are a precise, critical code reviewer. Respond with only a single letter.",
                temperature=0.2,
                max_tokens=16,
            )
            self._stats["judge_tokens"] += len(result.split())

            decision = result.strip().upper()
            if "B" in decision and "A" not in decision:
                if self.config.verbose:
                    logger.debug(f"[TTS-RTV] Pair: {a.rollout_id} vs {b.rollout_id} → B wins")
                # Copy metadata from winner
                b.summary = b.summary + f"\n\n(RTV winner vs {a.rollout_id})"
                return b
            else:
                if self.config.verbose:
                    logger.debug(f"[TTS-RTV] Pair: {a.rollout_id} vs {b.rollout_id} → A wins")
                a.summary = a.summary + f"\n\n(RTV winner vs {b.rollout_id})"
                return a
        except Exception as e:
            logger.warning(f"[TTS-RTV] Judge comparison failed: {e}, using heuristic")
            return self._heuristic_compare(a, b)

    @staticmethod
    def _heuristic_select(rollouts: list[RolloutResult]) -> RolloutResult:
        """Select best rollout using heuristics (fallback when no judge LLM)."""
        return max(rollouts, key=lambda r: RecursiveTournamentVoting._heuristic_score(r))

    @staticmethod
    def _heuristic_compare(a: RolloutResult, b: RolloutResult) -> RolloutResult:
        """Compare two rollouts using heuristics."""
        score_a = RecursiveTournamentVoting._heuristic_score(a)
        score_b = RecursiveTournamentVoting._heuristic_score(b)
        return a if score_a >= score_b else b

    @staticmethod
    def _heuristic_score(r: RolloutResult) -> float:
        """Compute a heuristic quality score for a rollout.

        Prefers:
        - Moderate temperature (0.5-0.7: balanced creativity)
        - Longer answers (more thorough)
        - Answers with code blocks (concrete solutions)
        - Answers with safety/edge case awareness
        """
        score = 0.0

        # Temperature preference: 0.5-0.7 is ideal
        temp = r.temperature
        if 0.5 <= temp <= 0.7:
            score += 0.3
        elif 0.3 <= temp <= 0.9:
            score += 0.2
        else:
            score += 0.1

        # Length bonus (but penalize excessively long)
        word_count = len(r.answer.split())
        if 100 <= word_count <= 3000:
            score += 0.2
        elif word_count > 3000:
            score += 0.1
        elif word_count < 50:
            score -= 0.1

        # Code block presence
        if "```" in r.answer:
            score += 0.3

        # Safety awareness
        if any(w in r.answer.lower() for w in ["error", "exception", "edge case", "handle"]):
            score += 0.1

        # Failure mode awareness
        if r.failure_modes:
            score += 0.1

        return score


# ═══════════════════════════════════════════════
# PDR Conditioning (Parallel-Distill-Refine)
# ═══════════════════════════════════════════════


class PDRConditioning:
    """Parallel-Distill-Refine: conditions new rollouts on the RTV winner's summary.

    After RTV selects the best rollout, PDR:
      1. Distills the winner's approach into a conditioning prompt
      2. Generates N new rollouts *conditioned* on this distilled approach
      3. Returns the best refined answer
    """

    def __init__(
        self,
        llm_call: LLMCallable | None = None,
        config: TTSConfig | None = None,
    ) -> None:
        self.llm_call = llm_call
        self.config = config or TTSConfig()
        self._stats: dict[str, Any] = {
            "pdr_rounds": 0,
            "pdr_tokens": 0,
        }

    def set_llm_call(self, llm_call: LLMCallable) -> None:
        self.llm_call = llm_call

    async def refine(
        self,
        question: str,
        winner: RolloutResult,
        history: list[dict[str, str]] | None = None,
        system_prompt: str = "",
    ) -> RolloutResult:
        """Run PDR refinement: generate new rollouts conditioned on the winner.

        Args:
            question: The original question.
            winner: The RTV-selected best rollout.
            history: Optional conversation history.
            system_prompt: System prompt.

        Returns:
            The best refined RolloutResult.
        """
        if self.llm_call is None:
            logger.info("[TTS-PDR] No LLM available, returning winner as-is")
            return winner

        history = history or []
        n = self.config.num_pdr_rollouts

        # Build conditioning prompt from winner's approach
        conditioning = self._build_conditioning_prompt(winner, question)

        # Generate conditioned rollouts
        conditioned_prompt = f"""{conditioning}

Now, produce the final, polished solution. Build upon the approach above,
addressing all requirements completely. Include well-documented code,
edge case handling, and practical usage examples."""

        # Run a single refined generation (slightly higher quality)
        self._stats["pdr_rounds"] += 1

        try:
            start = time.time()
            refined_answer = await self.llm_call(
                question=conditioned_prompt if history else f"{question}\n\n{conditioning}",
                history=history,
                system_prompt=system_prompt,
                temperature=0.4,  # Lower temp for refinement (precision)
                max_tokens=self.config.max_tokens_per_rollout,
            )
            elapsed_ms = (time.time() - start) * 1000
            tokens_used = len(refined_answer.split())
            self._stats["pdr_tokens"] += tokens_used

            refined = RolloutResult(
                rollout_id=f"pdr-{winner.rollout_id}",
                answer=refined_answer,
                summary=f"PDR-refined from {winner.rollout_id}",
                temperature=0.4,
                tokens_used=tokens_used,
                elapsed_ms=elapsed_ms,
            )

            # Re-extract summary for the refined answer
            refined.summary, refined.hypotheses, refined.progress, refined.failure_modes = (
                RolloutGenerator._summarize_rollout(refined_answer)
            )

            if self.config.verbose:
                logger.info(
                    f"[TTS-PDR] Refined from {winner.rollout_id}: "
                    f"tokens={tokens_used}, elapsed={elapsed_ms:.0f}ms"
                )

            return refined

        except Exception as e:
            logger.warning(f"[TTS-PDR] Refinement failed: {e}, returning original winner")
            return winner

    @staticmethod
    def _build_conditioning_prompt(winner: RolloutResult, question: str) -> str:
        """Build a conditioning prompt from the winning rollout's approach."""
        parts = ["## Previous Best Approach (to build upon)"]

        if winner.hypotheses:
            parts.append("\n### Key Hypotheses / Analysis:")
            for h in winner.hypotheses[:3]:
                parts.append(f"- {h}")

        if winner.progress:
            parts.append("\n### Progress Made:")
            for p in winner.progress[:3]:
                parts.append(f"- {p}")

        if winner.failure_modes:
            parts.append("\n### Important Considerations:")
            for f in winner.failure_modes[:3]:
                parts.append(f"- ⚠ {f}")

        return "\n".join(parts)


# ═══════════════════════════════════════════════
# Test-Time Scaling Pipeline
# ═══════════════════════════════════════════════


class TestTimeScalingPipeline:
    """Orchestrates the complete PDR+RTV pipeline.

    NOTE: __test__ = False prevents pytest from collecting this as a test class
    (pytest treats classes starting with "Test" as test containers).
    """
    __test__ = False
    """Orchestrates the complete PDR+RTV pipeline.

    Complexity routing:
      - score < 0.4: Fast path — single LLM call
      - 0.4 <= score <= 0.7: Balanced path — single LLM call with RAG
      - score > 0.7: Hard path — PDR+RTV with N rollouts + refinement

    Per the paper, this gives approximately:
      - +6.7% quality improvement on hard tasks
      - Negligible overhead on easy/medium tasks
    """

    def __init__(
        self,
        llm_call: LLMCallable | None = None,
        config: TTSConfig | None = None,
    ) -> None:
        self.config = config or TTSConfig()
        self.scorer = ComplexityScorer(self.config)
        self.generator = RolloutGenerator(llm_call, self.config)
        self.tournament = RecursiveTournamentVoting(llm_call, self.config)
        self.pdr = PDRConditioning(llm_call, self.config)
        self.    _stats: dict[str, Any]

        # Initialize stats separately to avoid pytest collection issues
        self._reset_stats()

    def set_llm_call(self, llm_call: LLMCallable) -> None:
        """Set the LLM call function for all sub-components."""
        self.generator.set_llm_call(llm_call)
        self.tournament.set_llm_call(llm_call)
        self.pdr.set_llm_call(llm_call)

    async def run(
        self,
        question: str,
        history: list[dict[str, str]] | None = None,
        system_prompt: str = "",
        force_hard: bool = False,
        complexity_score: float | None = None,
    ) -> dict[str, Any]:
        """Run the TTS pipeline with automatic complexity routing.

        Args:
            question: The user's question/task.
            history: Optional conversation history.
            system_prompt: System prompt for the LLM.
            force_hard: If True, always run the full PDR+RTV pipeline.
            complexity_score: Optional pre-computed complexity score.

        Returns:
            Dict with keys:
              - answer: The final answer text
              - complexity_score: Computed complexity score
              - route: "fast", "balanced", or "hard"
              - pipeline: Pipeline result metadata
              - pdr_applied: Whether PDR was applied
              - rtv_applied: Whether RTV was applied
              - num_rollouts: How many rollouts were generated
              - elapsed_ms: Total elapsed time
              - tokens_used: Total tokens used
              - winner_id: ID of the winning rollout
              - error: Any error that occurred
        """
        if self.generator.llm_call is None:
            raise ValueError("LLM call function not set. Call set_llm_call() first.")

        self._stats["total_pipelines"] += 1
        start = time.time()
        history = history or []

        # 1. Compute complexity
        if complexity_score is None:
            complexity_score = self.scorer.compute_score(question, history)

        # Update moving average
        prev_avg = self._stats["avg_complexity_score"]
        n = self._stats["total_pipelines"]
        self._stats["avg_complexity_score"] = prev_avg + (complexity_score - prev_avg) / n

        result: dict[str, Any] = {
            "answer": "",
            "complexity_score": round(complexity_score, 3),
            "route": "unknown",
            "pipeline": {},
            "pdr_applied": False,
            "rtv_applied": False,
            "num_rollouts": 0,
            "elapsed_ms": 0.0,
            "tokens_used": 0,
            "winner_id": "",
            "error": None,
        }

        # 2. Route based on complexity
        threshold = self.config.complexity_threshold

        if force_hard or complexity_score > threshold:
            # ── HARD PATH (PDR+RTV) ──────────────────────────────
            self._stats["hard_tasks"] += 1
            result["route"] = "hard"

            if self.config.verbose:
                logger.info(
                    f"[TTS] Hard task (score={complexity_score:.2f} > {threshold}): "
                    f"running PDR+RTV pipeline"
                )

            # Step 1: Generate N initial rollouts
            rollouts = await self.generator.generate_rollouts(
                question=question,
                history=history,
                system_prompt=system_prompt,
            )
            result["num_rollouts"] = len(rollouts)

            if not rollouts:
                result["error"] = "All initial rollouts failed"
                result["elapsed_ms"] = (time.time() - start) * 1000
                return result

            if len(rollouts) == 1:
                # Only one succeeded
                winner = rollouts[0]
            else:
                # Step 2: Recursive Tournament Voting
                result["rtv_applied"] = True
                winner = await self.tournament.select_winner(rollouts, question)

                # Step 3: PDR Conditioning — refine from winner
                result["pdr_applied"] = True
                refined = await self.pdr.refine(
                    question=question,
                    winner=winner,
                    history=history,
                    system_prompt=system_prompt,
                )
                # Use the PDR-refined answer as the final result
                if refined.error is None and refined.answer.strip():
                    winner = refined

            result["answer"] = winner.answer
            result["winner_id"] = winner.rollout_id
            result["tokens_used"] = (
                sum(r.tokens_used for r in rollouts)
                + winner.tokens_used
            )
            result["pipeline"] = {
                "num_rollouts": len(rollouts),
                "winner_temp": winner.temperature,
                "winner_tokens": winner.tokens_used,
                "winner_elapsed_ms": round(winner.elapsed_ms, 1),
                "rtv_rounds": self.tournament._stats["rounds"],
                "rtv_comparisons": self.tournament._stats["comparisons"],
                "pdr_rounds": self.pdr._stats["pdr_rounds"],
            }

        elif complexity_score > 0.4:
            # ── BALANCED PATH ────────────────────────────────────
            self._stats["medium_tasks"] += 1
            result["route"] = "balanced"

            # Single high-quality generation with RAG context
            if self.config.verbose:
                logger.info(
                    f"[TTS] Medium task (score={complexity_score:.2f}): single call with RAG"
                )

            try:
                answer = await self.generator.llm_call(
                    question=question,
                    history=history,
                    system_prompt=system_prompt,
                    temperature=0.3,
                    max_tokens=self.config.max_tokens_per_rollout,
                )
                result["answer"] = answer
                result["tokens_used"] = len(answer.split())
                result["winner_id"] = "single"
            except Exception as e:
                result["error"] = str(e)

        else:
            # ── FAST PATH ────────────────────────────────────────
            self._stats["fast_tasks"] += 1
            result["route"] = "fast"

            if self.config.verbose:
                logger.info(
                    f"[TTS] Fast task (score={complexity_score:.2f}): lightweight call"
                )

            try:
                answer = await self.generator.llm_call(
                    question=question,
                    history=history,
                    system_prompt=system_prompt,
                    temperature=0.3,
                    max_tokens=self.config.max_tokens_per_rollout,
                )
                result["answer"] = answer
                result["tokens_used"] = len(answer.split())
                result["winner_id"] = "single"
            except Exception as e:
                result["error"] = str(e)

        result["elapsed_ms"] = round((time.time() - start) * 1000, 1)
        self._stats["total_tokens_used"] += result["tokens_used"]
        self._stats["total_elapsed_ms"] += result["elapsed_ms"]

        return result

    def get_stats(self) -> dict[str, Any]:
        """Return pipeline statistics."""
        s = {**self._stats}
        s.update({
            "config": {
                "enabled": self.config.enabled,
                "complexity_threshold": self.config.complexity_threshold,
                "num_initial_rollouts": self.config.num_initial_rollouts,
                "num_pdr_rollouts": self.config.num_pdr_rollouts,
            },
            "generator": dict(self.generator._stats),
            "tournament": dict(self.tournament._stats),
            "pdr": dict(self.pdr._stats),
        })
        return s

    def _reset_stats(self) -> None:
        """Initialize or reset all statistics."""
        self._stats = {
            "total_pipelines": 0,
            "hard_tasks": 0,
            "medium_tasks": 0,
            "fast_tasks": 0,
            "total_tokens_used": 0,
            "total_elapsed_ms": 0.0,
            "avg_complexity_score": 0.0,
            "complexity_threshold": self.config.complexity_threshold,
        }
        self.generator._stats = {"total_rollouts": 0, "total_tokens": 0, "total_elapsed_ms": 0.0}
        self.tournament._stats = {"rounds": 0, "comparisons": 0, "judge_tokens": 0}
        self.pdr._stats = {"pdr_rounds": 0, "pdr_tokens": 0}

    def reset_stats(self) -> None:
        """Reset all statistics."""
        self._reset_stats()


# ═══════════════════════════════════════════════
# Default LLM Call (using Ollama)
# ═══════════════════════════════════════════════


def create_ollama_llm_call(
    model: str = "qwen2.5-coder:14b",
    ollama_url: str = "http://localhost:11434",
) -> Callable:
    """Create an async LLM call function using Ollama.

    This is the default implementation. Users can provide their own
    callable for different backends (vLLM, SGLang, OpenAI-compatible, etc.).

    Args:
        model: Ollama model name.
        ollama_url: Ollama server URL.

    Returns:
        Async callable suitable for use with TestTimeScalingPipeline.
    """
    import httpx

    async def llm_call(
        question: str,
        history: list[dict[str, str]] | None = None,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Call Ollama generate API and return the response text."""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if history:
            messages.extend(history[-10:])

        messages.append({"role": "user", "content": question})

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "repeat_penalty": 1.1,
            },
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{ollama_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "")

    return llm_call
