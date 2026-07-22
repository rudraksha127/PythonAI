"""
Error Pattern Tracker — Learn from Debugging Sessions
======================================================

Tracks error→solution patterns from user debugging sessions.
Stores patterns in a JSON database and provides fuzzy lookup
for future similar errors.

Architecture:
- Accept error traceback + solution text
- Extract error type, module, and message
- Hash-based deduplication
- JSON-based pattern database at data/cache/error_patterns.json
- Fuzzy lookup via text similarity
- Frequency tracking and confidence scoring

Usage:
    from src.learning.error_patterns import log_error_pattern, find_solution

    log_error_pattern(
        error="TypeError: 'NoneType' object is not iterable",
        solution="Check that the function returns a list, not None."
    )

    result = find_solution("TypeError: 'NoneType' object is not iterable")
    print(result)  # {"solution": "...", "confidence": 0.95, "times_seen": 3}
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("pythonai.learning.error_patterns")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_DB_PATH = _PROJECT_ROOT / "data" / "cache" / "error_patterns.json"


@dataclass
class ErrorPattern:
    """A single error→solution pattern."""

    error_hash: str
    error_type: str  # e.g., "TypeError", "ImportError"
    error_message: str  # The error message text
    error_module: str  # Module where error originated (if extractable)
    full_traceback: str  # Complete traceback text
    solution: str  # The solution text
    times_seen: int = 1
    confidence: float = 0.5
    first_seen: float = 0.0
    last_seen: float = 0.0
    tags: list[str] = field(default_factory=list)
    related_hashes: list[str] = field(default_factory=list)


def _extract_error_info(error_text: str) -> dict[str, str]:
    """
    Extract structured information from an error/traceback string.

    Returns:
        Dict with 'error_type', 'error_message', 'error_module'.
    """
    info = {
        "error_type": "Unknown",
        "error_message": error_text.strip()[:200],
        "error_module": "",
    }

    # Try to extract "ErrorType: message" pattern
    # Handles both single-line errors and multi-line tracebacks
    error_line_pattern = re.compile(
        r"^((?:[a-zA-Z_][\w.]*)?(?:Error|Exception|Warning|Fault))\s*:\s*(.+)",
        re.MULTILINE,
    )
    match = error_line_pattern.search(error_text)
    if match:
        info["error_type"] = match.group(1).strip()
        info["error_message"] = match.group(2).strip()[:500]

    # Try to extract the module from traceback
    # Look for 'File "..." in <module>' patterns
    module_pattern = re.compile(r'File\s+"([^"]+)"')
    module_matches = module_pattern.findall(error_text)
    if module_matches:
        # Use the last file in the traceback (closest to the error)
        last_file = module_matches[-1]
        # Extract module name from path
        parts = Path(last_file).parts
        # Try to find src/ or site-packages/ relative path
        for i, part in enumerate(parts):
            if part in ("src", "site-packages", "lib"):
                info["error_module"] = ".".join(parts[i + 1 :]).replace(".py", "")
                break
        if not info["error_module"]:
            info["error_module"] = Path(last_file).stem

    return info


def _compute_error_hash(error_type: str, error_message: str) -> str:
    """
    Compute a deduplication hash for an error.

    Normalizes the message to group similar errors together:
    - Removes file paths and line numbers
    - Removes memory addresses
    - Removes specific variable names from common patterns
    """
    normalized = error_message.lower().strip()

    # Remove file paths
    normalized = re.sub(r'["\']?(/[^\s"\']+|[a-zA-Z]:\\[^\s"\']+)["\']?', "<path>", normalized)
    # Remove line numbers
    normalized = re.sub(r"line\s+\d+", "line <N>", normalized)
    # Remove memory addresses
    normalized = re.sub(r"0x[0-9a-fA-F]+", "<addr>", normalized)
    # Remove specific numbers in common patterns
    normalized = re.sub(r"(\d+) (positional|keyword) argument", "<N> \\2 argument", normalized)

    combined = f"{error_type.lower()}::{normalized}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:24]


def _compute_similarity(text1: str, text2: str) -> float:
    """
    Compute a simple text similarity score (0.0 to 1.0).

    Uses token overlap (Jaccard similarity) for speed.
    """
    if not text1 or not text2:
        return 0.0

    # Tokenize by splitting on non-alphanumeric
    tokens1 = set(re.findall(r"\w+", text1.lower()))
    tokens2 = set(re.findall(r"\w+", text2.lower()))

    if not tokens1 or not tokens2:
        return 0.0

    intersection = tokens1 & tokens2
    union = tokens1 | tokens2

    return len(intersection) / len(union) if union else 0.0


class ErrorPatternDB:
    """
    JSON-based error pattern database with fuzzy lookup.

    Stores patterns as a JSON file and provides methods for
    logging new patterns and finding matching solutions.
    """

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._patterns: dict[str, ErrorPattern] = {}
        self._load()

    def _load(self) -> None:
        """Load patterns from JSON file."""
        if not self.db_path.exists():
            self._patterns = {}
            return

        try:
            with open(self.db_path, encoding="utf-8") as f:
                data = json.load(f)

            for hash_key, entry in data.items():
                self._patterns[hash_key] = ErrorPattern(
                    error_hash=entry.get("error_hash", hash_key),
                    error_type=entry.get("error_type", "Unknown"),
                    error_message=entry.get("error_message", ""),
                    error_module=entry.get("error_module", ""),
                    full_traceback=entry.get("full_traceback", ""),
                    solution=entry.get("solution", ""),
                    times_seen=entry.get("times_seen", 1),
                    confidence=entry.get("confidence", 0.5),
                    first_seen=entry.get("first_seen", 0.0),
                    last_seen=entry.get("last_seen", 0.0),
                    tags=entry.get("tags", []),
                    related_hashes=entry.get("related_hashes", []),
                )
            logger.info("Loaded %d error patterns from %s", len(self._patterns), self.db_path.name)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load error patterns: %s", e)
            self._patterns = {}

    def _save(self) -> None:
        """Persist patterns to JSON file."""
        data = {}
        for hash_key, pattern in self._patterns.items():
            data[hash_key] = asdict(pattern)

        try:
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.error("Failed to save error patterns: %s", e)
            raise

    def _trigger_auto_search(self, error_type: str, error_message: str) -> None:
        """
        Optional: Triggers an asynchronous background search (e.g. StackOverflow or
        Web Search) to proactively find a solution for an unresolved error.
        """
        logger.info(f"Triggering auto-search for unresolved error: {error_type}")
        # In a real implementation, this would queue a task for an agent or sync job
        # to search GitHub issues or StackOverflow.

    def log(
        self,
        error: str,
        solution: str,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Log an error→solution pattern.

        If the error pattern already exists, updates frequency and confidence.
        If new, creates a fresh entry.

        If the solution is missing, triggers an auto-search.

        Args:
            error: Error text or full traceback.
            solution: The solution text (can be empty if unresolved).
            tags: Optional tags for categorization.

        Returns:
            Dict with pattern info: {error_hash, error_type, is_new, times_seen}
        """
        info = _extract_error_info(error)
        error_hash = _compute_error_hash(info["error_type"], info["error_message"])
        now = time.time()

        is_unresolved = not solution or solution.strip().lower() == "unresolved"
        if is_unresolved:
            self._trigger_auto_search(info["error_type"], info["error_message"])

        if error_hash in self._patterns:
            # Update existing pattern
            pattern = self._patterns[error_hash]
            pattern.times_seen += 1
            pattern.last_seen = now
            # Increase confidence with repeated observations
            pattern.confidence = min(1.0, pattern.confidence + 0.1)
            # Update solution if the new one is longer/more detailed
            if len(solution) > len(pattern.solution) and not is_unresolved:
                pattern.solution = solution
            if tags:
                pattern.tags = list(set(pattern.tags + tags))

            self._save()
            return {
                "error_hash": error_hash,
                "error_type": info["error_type"],
                "is_new": False,
                "times_seen": pattern.times_seen,
                "confidence": pattern.confidence,
            }
        else:
            # Create new pattern
            pattern = ErrorPattern(
                error_hash=error_hash,
                error_type=info["error_type"],
                error_message=info["error_message"],
                error_module=info["error_module"],
                full_traceback=error,
                solution=solution,
                times_seen=1,
                confidence=0.5 if not is_unresolved else 0.1,
                first_seen=now,
                last_seen=now,
                tags=tags or [],
            )
            self._patterns[error_hash] = pattern
            self._save()

            logger.info("New error pattern logged: %s (%s)", info["error_type"], error_hash[:8])
            return {
                "error_hash": error_hash,
                "error_type": info["error_type"],
                "is_new": True,
                "times_seen": 1,
                "confidence": pattern.confidence,
            }

    def find(
        self,
        error_text: str,
        threshold: float = 0.3,
        max_results: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Find solutions for a given error text.

        First tries exact hash match, then falls back to fuzzy text similarity.

        Args:
            error_text: The error or traceback to look up.
            threshold: Minimum similarity score (0.0 to 1.0).
            max_results: Maximum number of results to return.

        Returns:
            List of dicts: {solution, confidence, times_seen, error_type, similarity}
        """
        info = _extract_error_info(error_text)
        error_hash = _compute_error_hash(info["error_type"], info["error_message"])

        results: list[dict[str, Any]] = []

        # Exact match
        if error_hash in self._patterns:
            pattern = self._patterns[error_hash]
            results.append(
                {
                    "solution": pattern.solution,
                    "confidence": pattern.confidence,
                    "times_seen": pattern.times_seen,
                    "error_type": pattern.error_type,
                    "similarity": 1.0,
                    "match_type": "exact",
                }
            )
            return results

        # Fuzzy match
        scored: list[tuple[float, ErrorPattern]] = []
        query_text = f"{info['error_type']} {info['error_message']}"

        for pattern in self._patterns.values():
            candidate_text = f"{pattern.error_type} {pattern.error_message}"
            similarity = _compute_similarity(query_text, candidate_text)

            # Boost score if error types match
            if info["error_type"].lower() == pattern.error_type.lower():
                similarity = min(1.0, similarity + 0.2)

            if similarity >= threshold:
                scored.append((similarity, pattern))

        # Sort by similarity descending
        scored.sort(key=lambda x: x[0], reverse=True)

        for similarity, pattern in scored[:max_results]:
            results.append(
                {
                    "solution": pattern.solution,
                    "confidence": pattern.confidence * similarity,
                    "times_seen": pattern.times_seen,
                    "error_type": pattern.error_type,
                    "similarity": round(similarity, 3),
                    "match_type": "fuzzy",
                }
            )

        return results

    def get_stats(self) -> dict[str, Any]:
        """Get database statistics."""
        if not self._patterns:
            return {
                "total_patterns": 0,
                "error_types": {},
                "avg_confidence": 0.0,
                "total_observations": 0,
            }

        error_types: dict[str, int] = {}
        total_confidence = 0.0
        total_observations = 0

        for pattern in self._patterns.values():
            error_types[pattern.error_type] = error_types.get(pattern.error_type, 0) + 1
            total_confidence += pattern.confidence
            total_observations += pattern.times_seen

        return {
            "total_patterns": len(self._patterns),
            "error_types": error_types,
            "avg_confidence": round(total_confidence / len(self._patterns), 3),
            "total_observations": total_observations,
            "db_path": str(self.db_path),
        }


# ─── Module-Level Convenience Functions ──────────────────────────────────

_db: ErrorPatternDB | None = None


def _get_db() -> ErrorPatternDB:
    """Get or create the global error pattern database."""
    global _db
    if _db is None:
        _db = ErrorPatternDB()
    return _db


def log_error_pattern(
    error: str,
    solution: str,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """
    Log an error→solution pattern (convenience function).

    Args:
        error: Error text or traceback.
        solution: The solution text.
        tags: Optional tags.

    Returns:
        Pattern info dict.
    """
    return _get_db().log(error, solution, tags=tags)


def find_solution(
    error_text: str,
    threshold: float = 0.3,
    max_results: int = 3,
) -> dict[str, Any] | None:
    """
    Find the best matching solution for an error (convenience function).

    Returns:
        Best matching result dict, or None if no match found.
    """
    results = _get_db().find(error_text, threshold=threshold, max_results=max_results)
    return results[0] if results else None


def find_all_solutions(
    error_text: str,
    threshold: float = 0.3,
    max_results: int = 3,
) -> list[dict[str, Any]]:
    """Find all matching solutions for an error (convenience function)."""
    return _get_db().find(error_text, threshold=threshold, max_results=max_results)
