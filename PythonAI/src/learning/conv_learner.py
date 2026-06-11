"""
Conversation Learner — Extract Knowledge from Q&A Interactions
===============================================================

Captures question-answer pairs from user conversations and transforms them
into RAG-compatible documents for the knowledge base.

Architecture:
- Accepts list of Q&A dicts (question + answer)
- Normalizes text (whitespace, encoding)
- Hash-based deduplication against existing stored conversations
- Extracts key concepts via lightweight NLP heuristics
- Persists as JSONL in data/conversations/
- Returns ingestion stats

Usage:
    from src.learning.conv_learner import learn_from_conversation, ConversationLearner

    stats = learn_from_conversation([
        {"question": "What is async/await?", "answer": "..."},
    ])
    print(stats)  # {"learned": 1, "duplicates_skipped": 0, ...}
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("pythonai.learning.conv_learner")

# Project root (PythonAI/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_CONV_DIR = _PROJECT_ROOT / "data" / "conversations"


@dataclass
class ConversationEntry:
    """A single learned Q&A entry."""

    question: str
    answer: str
    content_hash: str
    timestamp: float
    source: str = "conversation"
    category: str = "general"
    concepts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def _normalize_text(text: str) -> str:
    """Normalize whitespace, strip control characters, lowercase for hashing."""
    if not text:
        return ""
    # Strip control characters except newlines
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Normalize whitespace runs
    text = re.sub(r"[ \t]+", " ", text)
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


def _compute_hash(question: str, answer: str) -> str:
    """Compute a content hash for deduplication."""
    combined = f"{question.lower().strip()}||{answer.lower().strip()}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:24]


def _extract_concepts(text: str) -> list[str]:
    """
    Extract key programming concepts from text using heuristic patterns.

    Looks for:
    - Python keywords and builtins
    - Library/module names (dotted identifiers)
    - Common programming terms
    """
    concepts: set[str] = set()

    # Python keywords and builtins
    python_keywords = {
        "async", "await", "class", "def", "import", "from", "return",
        "yield", "lambda", "decorator", "generator", "iterator",
        "exception", "context manager", "metaclass", "descriptor",
        "property", "staticmethod", "classmethod", "abc",
        "dataclass", "namedtuple", "enum", "typing", "protocol",
    }
    text_lower = text.lower()
    for kw in python_keywords:
        if kw in text_lower:
            concepts.add(kw)

    # Dotted module names (e.g., os.path, asyncio.gather)
    module_pattern = re.compile(r"\b([a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)+)\b")
    for match in module_pattern.finditer(text_lower):
        concepts.add(match.group(1))

    # Code identifiers in backticks
    backtick_pattern = re.compile(r"`([^`]{2,60})`")
    for match in backtick_pattern.finditer(text):
        concept = match.group(1).strip()
        if concept and not concept.startswith("http"):
            concepts.add(concept)

    return sorted(concepts)[:20]  # Cap at 20 concepts


def _categorize_question(question: str) -> str:
    """Categorize a question based on keywords."""
    q_lower = question.lower()

    categories = {
        "howto": ["how to", "how do i", "how can i", "how would"],
        "debugging": ["error", "exception", "traceback", "bug", "fix", "crash"],
        "explanation": ["what is", "what are", "explain", "why", "difference between"],
        "performance": ["faster", "optimize", "performance", "slow", "speed"],
        "best_practice": ["best practice", "recommended", "should i", "pattern"],
        "library": ["library", "package", "module", "pip", "install"],
        "syntax": ["syntax", "write", "correct way"],
    }

    for category, keywords in categories.items():
        if any(kw in q_lower for kw in keywords):
            return category

    return "general"


class ConversationLearner:
    """
    Manages the conversation learning pipeline.

    Handles persistence, deduplication, and formatting of Q&A knowledge.
    """

    def __init__(
        self,
        output_dir: str | Path | None = None,
        max_answer_length: int = 10_000,
        min_answer_length: int = 20,
    ):
        self.output_dir = Path(output_dir) if output_dir else _DEFAULT_CONV_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.max_answer_length = max_answer_length
        self.min_answer_length = min_answer_length

        # Load existing hashes for dedup
        self._known_hashes: set[str] = set()
        self._load_existing_hashes()

    def _load_existing_hashes(self) -> None:
        """Load content hashes from existing conversation files."""
        for jsonl_file in self.output_dir.glob("conversations_*.jsonl"):
            try:
                with open(jsonl_file, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            if "content_hash" in entry:
                                self._known_hashes.add(entry["content_hash"])
                        except json.JSONDecodeError:
                            continue
            except OSError as e:
                logger.warning("Failed to read %s: %s", jsonl_file, e)

        logger.info("Loaded %d existing conversation hashes", len(self._known_hashes))

    def _get_output_file(self) -> Path:
        """Get the current output file (rotate daily)."""
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        return self.output_dir / f"conversations_{date_str}.jsonl"

    def learn(
        self,
        qa_pairs: list[dict[str, str]],
        source: str = "conversation",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Learn from a batch of Q&A pairs.

        Args:
            qa_pairs: List of dicts with 'question' and 'answer' keys.
            source: Source identifier (e.g., 'cli', 'webui', 'api').
            metadata: Extra metadata to attach to each entry.

        Returns:
            Stats dict: {learned, duplicates_skipped, invalid_skipped, total_concepts}
        """
        stats = {
            "learned": 0,
            "duplicates_skipped": 0,
            "invalid_skipped": 0,
            "total_concepts": 0,
            "categories": {},
        }

        entries_to_write: list[dict[str, Any]] = []

        for pair in qa_pairs:
            question = pair.get("question", "").strip()
            answer = pair.get("answer", "").strip()

            # Validate
            if not question or not answer:
                stats["invalid_skipped"] += 1
                logger.debug("Skipping empty Q&A pair")
                continue

            if len(answer) < self.min_answer_length:
                stats["invalid_skipped"] += 1
                logger.debug("Skipping short answer (%d chars): %s", len(answer), question[:50])
                continue

            # Normalize
            question = _normalize_text(question)
            answer = _normalize_text(answer)

            # Truncate excessively long answers
            if len(answer) > self.max_answer_length:
                answer = answer[: self.max_answer_length] + "\n\n[truncated]"

            # Deduplicate
            content_hash = _compute_hash(question, answer)
            if content_hash in self._known_hashes:
                stats["duplicates_skipped"] += 1
                continue

            # Extract concepts
            combined_text = f"{question}\n{answer}"
            concepts = _extract_concepts(combined_text)
            category = _categorize_question(question)

            # Build entry
            entry = ConversationEntry(
                question=question,
                answer=answer,
                content_hash=content_hash,
                timestamp=time.time(),
                source=source,
                category=category,
                concepts=concepts,
                metadata=metadata or {},
            )

            entry_dict = {
                "question": entry.question,
                "answer": entry.answer,
                "content_hash": entry.content_hash,
                "timestamp": entry.timestamp,
                "source": entry.source,
                "category": entry.category,
                "concepts": entry.concepts,
                "metadata": entry.metadata,
                # RAG-compatible fields
                "instruction": entry.question,
                "input": "",
                "output": entry.answer,
            }

            entries_to_write.append(entry_dict)
            self._known_hashes.add(content_hash)
            stats["learned"] += 1
            stats["total_concepts"] += len(concepts)
            stats["categories"][category] = stats["categories"].get(category, 0) + 1

        # Write to JSONL
        if entries_to_write:
            output_file = self._get_output_file()
            try:
                with open(output_file, "a", encoding="utf-8") as f:
                    for entry_dict in entries_to_write:
                        f.write(json.dumps(entry_dict, ensure_ascii=False) + "\n")
                logger.info(
                    "Wrote %d conversation entries to %s",
                    len(entries_to_write),
                    output_file.name,
                )
            except OSError as e:
                logger.error("Failed to write conversations: %s", e)
                raise

        return stats

    def get_stats(self) -> dict[str, Any]:
        """Get overall conversation learning statistics."""
        total_entries = 0
        categories: dict[str, int] = {}
        files_count = 0

        for jsonl_file in sorted(self.output_dir.glob("conversations_*.jsonl")):
            files_count += 1
            try:
                with open(jsonl_file, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            total_entries += 1
                            cat = entry.get("category", "general")
                            categories[cat] = categories.get(cat, 0) + 1
                        except json.JSONDecodeError:
                            continue
            except OSError:
                continue

        return {
            "total_entries": total_entries,
            "unique_hashes": len(self._known_hashes),
            "files_count": files_count,
            "categories": categories,
            "output_dir": str(self.output_dir),
        }


def learn_from_conversation(
    qa_pairs: list[dict[str, str]],
    output_dir: str | Path | None = None,
    source: str = "conversation",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Convenience function: learn from Q&A pairs and return stats.

    Args:
        qa_pairs: List of {"question": str, "answer": str} dicts.
        output_dir: Override output directory.
        source: Source identifier.
        metadata: Extra metadata.

    Returns:
        Stats dict with learned/skipped counts.
    """
    learner = ConversationLearner(output_dir=output_dir)
    return learner.learn(qa_pairs, source=source, metadata=metadata)
