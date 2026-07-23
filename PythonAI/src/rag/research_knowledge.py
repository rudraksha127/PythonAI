"""
RESEARCH-AWARE RAG AUGMENTATION
================================
Enhances the existing RAG engine with research paper and book knowledge.

This module provides:
1. Knowledge Intelligence RAG integration - uses the KnowledgeIntelligence engine
2. Paper-cited answer generation - includes citations to papers
3. Contextual concept linking - links concepts to their sources
4. Hot topic awareness - highlights trending research areas

Usage:
    from src.rag.research_knowledge import ResearchRAGAugmenter
    augmenter = ResearchRAGAugmenter()
    context = augmenter.augment_context("What is attention mechanism?")
    # context now includes research paper findings + book knowledge
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

try:
    from src.data.discovery.knowledge_harvester import KnowledgeIntelligence
except ImportError:
    KnowledgeIntelligence = None

try:
    from src.data.discovery.research_papers import PaperKnowledge
except ImportError:
    PaperKnowledge = None

try:
    from src.data.discovery.book_knowledge import BookKnowledge
except ImportError:
    BookKnowledge = None

# ── Paths ───────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent
MERGED_CHUNKS_FILE = ROOT / "data" / "research_knowledge" / "merged_knowledge_chunks.json"


class ResearchRAGAugmenter:
    """
    Augments RAG queries with research paper and book knowledge.

    Features:
    - Automatically loads the latest knowledge chunks
    - Provides contextual augmentation for any query
    - Supports citation formatting for papers
    - Links concepts to their knowledge sources
    """

    def __init__(self, knowledge_engine: KnowledgeIntelligence | None = None):
        self._engine = knowledge_engine
        self._knowledge_chunks: list[dict[str, Any]] = []
        self._load_chunks()

    def _load_chunks(self) -> None:
        """Load knowledge chunks from disk."""
        if MERGED_CHUNKS_FILE.exists():
            try:
                self._knowledge_chunks = json.loads(
                    MERGED_CHUNKS_FILE.read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, Exception):
                self._knowledge_chunks = []
        else:
            # Try loading book chunks as fallback
            book_chunks_file = MERGED_CHUNKS_FILE.parent / "book_chunks.json"
            if book_chunks_file.exists():
                try:
                    self._knowledge_chunks = json.loads(
                        book_chunks_file.read_text(encoding="utf-8")
                    )
                except (json.JSONDecodeError, Exception):
                    self._knowledge_chunks = []

    @property
    def engine(self) -> KnowledgeIntelligence | None:
        """Lazy-load the knowledge intelligence engine."""
        if self._engine is None and KnowledgeIntelligence is not None:
            self._engine = KnowledgeIntelligence(auto_load=True)
        return self._engine

    # ── Context Augmentation ──────────────────────────────────

    def augment_context(
        self,
        query: str,
        max_paper_results: int = 5,
        max_book_results: int = 3,
        include_hot_topics: bool = True,
    ) -> str:
        """
        Augment a RAG query with research paper and book knowledge context.

        Args:
            query: The user's question/query.
            max_paper_results: Max paper findings to include.
            max_book_results: Max book concepts to include.
            include_hot_topics: Whether to include trending research topics.

        Returns:
            Augmented context string ready to be inserted into the RAG prompt.
        """
        parts: list[str] = []

        # 1. Get research paper findings
        if self.engine:
            results = self.engine.query(query, max_results=max_paper_results + max_book_results)

            papers = [r for r in results if r["type"] == "paper"]
            books = [r for r in results if r["type"] in ("book", "concept")]

            if papers:
                parts.append("=" * 60)
                parts.append("RESEARCH PAPER KNOWLEDGE:")
                parts.append("=" * 60)
                for i, p in enumerate(papers[:max_paper_results], 1):
                    parts.append(f"\n[Paper {i}] {p['title']}")
                    parts.append(f"  Relevance: {p['relevance']:.2f} | Citations: {p['citations']}")
                    parts.append(f"  {p['text_preview'][:500]}")
                    if p.get("url"):
                        parts.append(f"  Source: {p['url']}")

            if books:
                parts.append("\n" + "=" * 60)
                parts.append("BOOK & EDUCATIONAL KNOWLEDGE:")
                parts.append("=" * 60)
                for i, b in enumerate(books[:max_book_results], 1):
                    parts.append(f"\n[Resource {i}] {b['title']}")
                    parts.append(f"  {b['text_preview'][:300]}")

            # Hot topics if available
            if include_hot_topics:
                try:
                    hot_topics = self.engine.get_hot_topics(top_n=5)
                    if hot_topics:
                        parts.append("\n" + "=" * 60)
                        parts.append("TRENDING RESEARCH TOPICS:")
                        parts.append("=" * 60)
                        for topic in hot_topics:
                            parts.append(f"  🔥 {topic['topic']} (score: {topic['score']})")
                except Exception:
                    pass

        # 2. Also include raw knowledge chunks for broader context
        if self._knowledge_chunks:
            query_lower = query.lower()
            query_words = set(w for w in re.findall(r'[a-zA-Z]{3,}', query_lower))
            scored_chunks: list[tuple[dict, float]] = []

            for chunk in self._knowledge_chunks:
                text = (chunk.get("text", "") + chunk.get("title", "")).lower()
                # Full phrase match (high score)
                phrase_score = 2.0 if query_lower in text else 0.0
                # Word-level match
                word_matches = sum(1 for w in query_words if w in text)
                word_score = (word_matches / max(len(query_words), 1)) * 0.5
                total_score = phrase_score + word_score
                if total_score > 0:
                    scored_chunks.append((chunk, total_score))

            if scored_chunks:
                scored_chunks.sort(key=lambda x: x[1], reverse=True)
                parts.append("=" * 60)
                parts.append("KNOWLEDGE BASE CONTEXT (from books & research):")
                parts.append("=" * 60)
                for chunk, score in scored_chunks[:5]:
                    parts.append(f"\n• [{score:.1f}] {chunk.get('title', 'Untitled')}")
                    parts.append(f"  {chunk.get('text', '')[:300]}")

        return "\n".join(parts)

    # ── Citation Formatting ───────────────────────────────────

    def format_citations(self, results: list[dict[str, Any]]) -> str:
        """
        Format retrieval results as citations.

        Args:
            results: List of results from KnowledgeIntelligence.query().

        Returns:
            Formatted citation string.
        """
        if not results:
            return ""

        lines = ["\n[Docs] Sources:"]
        for i, r in enumerate(results[:10], 1):
            source_type = r.get("type", "unknown").upper()
            title = r.get("title", "")[:60]
            tags = ", ".join(r.get("tags", [])[:3])
            citations = r.get("citations", 0)
            line = f"  [{i}] ({source_type}) {title}"
            if citations:
                line += f" [cited {citations}x]"
            if tags:
                line += f" — {tags}"
            lines.append(line)

        return "\n".join(lines)

    # ── Concept Deep Dive ─────────────────────────────────────

    def concept_explanation(
        self,
        concept: str,
        max_sources: int = 5,
    ) -> str:
        """
        Generate a deep-dive explanation of a concept from multiple knowledge sources.

        Args:
            concept: The concept to explain (e.g., "transformer attention").
            max_sources: Maximum sources to include.

        Returns:
            Multi-source explanation string.
        """
        parts = [f"📖 KNOWLEDGE DEEP DIVE: '{concept}'"]
        parts.append("=" * 60)

        if self.engine:
            results = self.engine.query(concept, max_results=max_sources)

            if not results:
                parts.append("\nNo knowledge sources found for this concept.")

            for r in results:
                parts.append(f"\n📌 [{r['type'].upper()}] {r['title']}")
                parts.append(f"   {r['text_preview'][:400]}")
                if r.get("url"):
                    parts.append(f"   🔗 {r['url']}")

                # Include related knowledge
                if r.get("related"):
                    parts.append("   Related:")
                    for rel in r["related"][:3]:
                        parts.append(f"     ↳ {rel['title']}")

        else:
            parts.append("\nKnowledge engine not available. Load knowledge first.")

        return "\n".join(parts)


# ── RAG System Prompt Enhancement ───────────────────────────────────


def enhance_system_prompt(base_prompt: str) -> str:
    """
    Enhance the RAG system prompt to include research-awareness.

    Args:
        base_prompt: The existing system prompt.

    Returns:
        Enhanced system prompt with research instructions.
    """
    research_instructions = """

KNOWLEDGE INTELLIGENCE CAPABILITIES:
- You have access to a research paper knowledge base with 1000+ papers
- You have access to a curated book knowledge base (Fluent Python, etc.)
- When answering, cite specific papers when possible
- Mention relevant books or resources that support your answer
- Distinguish between established knowledge (from books) and cutting-edge research (from papers)
- When discussing AI/ML concepts, reference the relevant papers or textbooks
- For Python-specific questions, prioritize official documentation and established books
- Use this format for citations: [Paper: Title] or [Book: Title]

RESEARCH AWARENESS:
- Stay current: reference recent papers when discussing state-of-the-art
- Historical context: cite foundational papers for established concepts
- Practical knowledge: reference books for best practices and patterns
- Cross-reference: connect related concepts across different sources
"""

    if research_instructions not in base_prompt:
        return base_prompt + research_instructions
    return base_prompt


# ═════════════════════════════════════════════════════════════════════
# Convenience Functions
# ═════════════════════════════════════════════════════════════════════


def augment_rag_query(query: str) -> str:
    """Convenience: augment a RAG query with research knowledge."""
    augmenter = ResearchRAGAugmenter()
    return augmenter.augment_context(query)


def explain_concept(concept: str) -> str:
    """Convenience: get a multi-source explanation of a concept."""
    augmenter = ResearchRAGAugmenter()
    return augmenter.concept_explanation(concept)


if __name__ == "__main__":
    # Quick test
    augmenter = ResearchRAGAugmenter()
    context = augmenter.augment_context(
        "How does the transformer attention mechanism work in large language models?",
    )
    print(context)
