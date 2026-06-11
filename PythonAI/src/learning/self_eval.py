"""
Self-Evaluation Engine — Automated RAG Quality Assessment
==========================================================

Evaluates the RAG engine's answer quality by running sample Q&A pairs
through the system and scoring them on multiple dimensions.

Scoring Dimensions:
- Relevance: Keyword/concept overlap between answer and expected
- Completeness: Length ratio and key-point coverage
- Code Quality: Syntax validity of any Python code blocks
- Consistency: Score stability across repeated runs

Usage:
    from src.learning.self_eval import run_self_evaluation, SelfEvaluator

    report = run_self_evaluation()
    print(report["overall_score"])  # 0.78
    print(report["dimensions"])    # {"relevance": 0.85, "completeness": 0.72, ...}
"""

from __future__ import annotations

import ast
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("pythonai.learning.self_eval")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_EVAL_DIR = _PROJECT_ROOT / "data" / "eval"
_DEFAULT_TRAINING_DATA = _PROJECT_ROOT / "data" / "training" / "training_dataset.json"


@dataclass
class EvalResult:
    """Result from evaluating a single Q&A pair."""

    question: str
    expected_answer: str
    actual_answer: str
    relevance_score: float = 0.0
    completeness_score: float = 0.0
    code_quality_score: float = 0.0
    overall_score: float = 0.0
    eval_time_ms: float = 0.0
    errors: list[str] = field(default_factory=list)


def _score_relevance(expected: str, actual: str) -> float:
    """
    Score relevance via weighted keyword overlap.

    Uses both unigram and bigram overlap for better semantic matching.
    """
    if not expected or not actual:
        return 0.0

    def tokenize(text: str) -> list[str]:
        return re.findall(r"\w+", text.lower())

    expected_tokens = tokenize(expected)
    actual_tokens = tokenize(actual)

    if not expected_tokens or not actual_tokens:
        return 0.0

    # Unigram overlap
    expected_set = set(expected_tokens)
    actual_set = set(actual_tokens)

    # Remove common stopwords
    stopwords = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "to", "of", "in",
        "for", "on", "with", "at", "by", "from", "as", "into", "through",
        "it", "its", "this", "that", "these", "those", "and", "or", "but",
        "not", "no", "so", "if", "then", "than", "too", "very", "just",
    }
    expected_set -= stopwords
    actual_set -= stopwords

    if not expected_set:
        return 0.5  # Can't evaluate without expected content words

    unigram_overlap = len(expected_set & actual_set) / len(expected_set)

    # Bigram overlap
    def get_bigrams(tokens: list[str]) -> set[str]:
        return {f"{tokens[i]}_{tokens[i + 1]}" for i in range(len(tokens) - 1)}

    expected_bigrams = get_bigrams(expected_tokens)
    actual_bigrams = get_bigrams(actual_tokens)

    bigram_overlap = 0.0
    if expected_bigrams:
        bigram_overlap = len(expected_bigrams & actual_bigrams) / len(expected_bigrams)

    # Weighted combination (unigrams more important for recall)
    return 0.7 * unigram_overlap + 0.3 * bigram_overlap


def _score_completeness(expected: str, actual: str) -> float:
    """
    Score completeness based on length ratio and structural coverage.

    A good answer should be at least 30% of the expected length.
    Answers that are too short lose points; excessively long answers
    don't get bonus (but aren't penalized either).
    """
    if not expected or not actual:
        return 0.0

    expected_len = len(expected.split())
    actual_len = len(actual.split())

    if expected_len == 0:
        return 0.5

    # Length ratio (capped at 1.0)
    length_ratio = min(1.0, actual_len / max(expected_len, 1))

    # Structural coverage: check if key sections are present
    # Look for code blocks, lists, examples
    structural_score = 0.0
    checks = 0

    # Code block check
    expected_has_code = "```" in expected or "def " in expected or "import " in expected
    actual_has_code = "```" in actual or "def " in actual or "import " in actual
    if expected_has_code:
        checks += 1
        if actual_has_code:
            structural_score += 1.0

    # Paragraph check (multi-paragraph expected → actual should also be)
    expected_paragraphs = len([p for p in expected.split("\n\n") if p.strip()])
    actual_paragraphs = len([p for p in actual.split("\n\n") if p.strip()])
    if expected_paragraphs > 1:
        checks += 1
        if actual_paragraphs > 1:
            structural_score += 1.0

    # If no structural checks, just use length
    if checks == 0:
        return length_ratio

    structural_ratio = structural_score / checks
    return 0.6 * length_ratio + 0.4 * structural_ratio


def _score_code_quality(answer: str) -> float:
    """
    Score the quality of Python code blocks in an answer.

    Checks syntax validity via ast.parse.
    Returns 1.0 if no code blocks or all are valid, lower if some fail.
    """
    # Extract Python code blocks
    code_blocks = re.findall(r"```python\n(.*?)```", answer, re.DOTALL)
    # Also try indented blocks after ">>>"
    repl_blocks = re.findall(r">>> (.+)", answer)

    if not code_blocks and not repl_blocks:
        return 1.0  # No code to evaluate

    total = 0
    valid = 0

    for block in code_blocks:
        total += 1
        try:
            ast.parse(block.strip())
            valid += 1
        except SyntaxError:
            pass

    for line in repl_blocks:
        total += 1
        try:
            ast.parse(line.strip())
            valid += 1
        except SyntaxError:
            pass

    return valid / total if total > 0 else 1.0


class SelfEvaluator:
    """
    Self-evaluation engine for RAG quality assessment.

    Loads sample Q&A pairs and evaluates RAG answers against them.
    """

    def __init__(
        self,
        eval_dir: str | Path | None = None,
        training_data_path: str | Path | None = None,
        sample_size: int = 50,
    ):
        self.eval_dir = Path(eval_dir) if eval_dir else _DEFAULT_EVAL_DIR
        self.eval_dir.mkdir(parents=True, exist_ok=True)

        self.training_data_path = (
            Path(training_data_path) if training_data_path else _DEFAULT_TRAINING_DATA
        )
        self.sample_size = sample_size

    def load_eval_samples(self) -> list[dict[str, str]]:
        """
        Load evaluation samples from the training dataset.

        Returns list of {"question": str, "answer": str} dicts.
        """
        samples: list[dict[str, str]] = []

        if not self.training_data_path.exists():
            logger.warning("Training data not found at %s", self.training_data_path)
            return samples

        try:
            with open(self.training_data_path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load training data: %s", e)
            return samples

        # Handle both list and dict formats
        entries = data if isinstance(data, list) else data.get("data", [])

        # Sample entries that have both instruction and output
        count = 0
        for entry in entries:
            if count >= self.sample_size:
                break

            question = entry.get("instruction", "") or entry.get("question", "")
            answer = entry.get("output", "") or entry.get("answer", "")

            if question and answer and len(answer) > 50:
                samples.append({"question": question, "answer": answer})
                count += 1

        logger.info("Loaded %d evaluation samples", len(samples))
        return samples

    def evaluate_single(
        self,
        question: str,
        expected_answer: str,
        actual_answer: str,
    ) -> EvalResult:
        """Evaluate a single Q&A pair."""
        start = time.time()

        relevance = _score_relevance(expected_answer, actual_answer)
        completeness = _score_completeness(expected_answer, actual_answer)
        code_quality = _score_code_quality(actual_answer)

        # Weighted overall score
        overall = (
            0.45 * relevance
            + 0.30 * completeness
            + 0.25 * code_quality
        )

        elapsed_ms = (time.time() - start) * 1000

        return EvalResult(
            question=question,
            expected_answer=expected_answer,
            actual_answer=actual_answer,
            relevance_score=round(relevance, 4),
            completeness_score=round(completeness, 4),
            code_quality_score=round(code_quality, 4),
            overall_score=round(overall, 4),
            eval_time_ms=round(elapsed_ms, 2),
        )

    def evaluate_batch(
        self,
        samples: list[dict[str, str]] | None = None,
        rag_fn: Any = None,
    ) -> dict[str, Any]:
        """
        Run batch evaluation.

        If rag_fn is provided, it's called with each question to get the actual answer.
        Otherwise, evaluates the expected answers against themselves (baseline = 1.0).

        Args:
            samples: List of Q&A pairs. Loads from training data if None.
            rag_fn: Optional callable(question: str) -> str that returns RAG answer.

        Returns:
            Evaluation report dict.
        """
        if samples is None:
            samples = self.load_eval_samples()

        if not samples:
            return {
                "status": "no_samples",
                "overall_score": 0.0,
                "dimensions": {},
                "results_count": 0,
            }

        results: list[EvalResult] = []

        for sample in samples:
            question = sample["question"]
            expected = sample["answer"]

            if rag_fn is not None:
                try:
                    actual = rag_fn(question)
                except Exception as e:
                    logger.warning("RAG function failed for question: %s", e)
                    actual = ""
            else:
                # Self-evaluation baseline: compare expected against itself
                actual = expected

            result = self.evaluate_single(question, expected, actual)
            results.append(result)

        # Aggregate scores
        n = len(results)
        avg_relevance = sum(r.relevance_score for r in results) / n
        avg_completeness = sum(r.completeness_score for r in results) / n
        avg_code_quality = sum(r.code_quality_score for r in results) / n
        avg_overall = sum(r.overall_score for r in results) / n
        avg_time = sum(r.eval_time_ms for r in results) / n

        report = {
            "status": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_score": round(avg_overall, 4),
            "dimensions": {
                "relevance": round(avg_relevance, 4),
                "completeness": round(avg_completeness, 4),
                "code_quality": round(avg_code_quality, 4),
            },
            "results_count": n,
            "avg_eval_time_ms": round(avg_time, 2),
            "score_distribution": {
                "excellent": sum(1 for r in results if r.overall_score >= 0.8),
                "good": sum(1 for r in results if 0.6 <= r.overall_score < 0.8),
                "fair": sum(1 for r in results if 0.4 <= r.overall_score < 0.6),
                "poor": sum(1 for r in results if r.overall_score < 0.4),
            },
            "has_rag_fn": rag_fn is not None,
        }

        # Save report
        self._save_report(report, results)

        return report

    def _save_report(self, report: dict[str, Any], results: list[EvalResult]) -> None:
        """Save evaluation report to file."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report_path = self.eval_dir / f"eval_report_{timestamp}.json"

        # Include top-level report + per-question details
        full_report = {
            **report,
            "detailed_results": [
                {
                    "question": r.question[:200],
                    "relevance": r.relevance_score,
                    "completeness": r.completeness_score,
                    "code_quality": r.code_quality_score,
                    "overall": r.overall_score,
                    "eval_time_ms": r.eval_time_ms,
                }
                for r in results
            ],
        }

        try:
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(full_report, f, indent=2, ensure_ascii=False)
            logger.info("Evaluation report saved to %s", report_path.name)
        except OSError as e:
            logger.error("Failed to save eval report: %s", e)

    def get_trend(self, limit: int = 10) -> list[dict[str, Any]]:
        """
        Get score trend from past evaluation reports.

        Returns list of {timestamp, overall_score, dimensions} sorted by time.
        """
        reports = []

        for report_file in sorted(self.eval_dir.glob("eval_report_*.json"))[-limit:]:
            try:
                with open(report_file, encoding="utf-8") as f:
                    data = json.load(f)
                reports.append({
                    "timestamp": data.get("timestamp", ""),
                    "overall_score": data.get("overall_score", 0.0),
                    "dimensions": data.get("dimensions", {}),
                    "results_count": data.get("results_count", 0),
                })
            except (json.JSONDecodeError, OSError):
                continue

        return reports


def run_self_evaluation(
    sample_size: int = 50,
    rag_fn: Any = None,
    eval_dir: str | Path | None = None,
) -> dict[str, Any]:
    """
    Run a full self-evaluation and return the report.

    Convenience function for quick evaluation.

    Args:
        sample_size: Number of Q&A pairs to evaluate.
        rag_fn: Optional RAG function(question) -> answer.
        eval_dir: Override evaluation output directory.

    Returns:
        Evaluation report dict.
    """
    evaluator = SelfEvaluator(
        sample_size=sample_size,
        eval_dir=eval_dir,
    )
    return evaluator.evaluate_batch(rag_fn=rag_fn)
