"""
KNOWLEDGE INTELLIGENCE ENGINE
===============================
The Unified Knowledge Intelligence Engine — the brain of the project.

This module orchestrates ALL knowledge sources into a single,
cross-referenced intelligence system:

1. RESEARCH PAPERS — arXiv, Semantic Scholar, PapersWithCode
2. BOOKS — Python/programming books, textbooks
3. TUTORIALS & COURSES — Online educational resources
4. DOCUMENTATION — Official Python docs, library references
5. CONTINUOUS LEARNING — Scheduled updates, trend detection

The engine:
- Automatically collects from all sources
- Extracts structured knowledge (findings, methods, concepts)
- Cross-references between sources
- Generates RAG-compatible chunks
- Provides a unified query interface
- Tracks what's been learned and what's new

Usage:
    from src.data.discovery.knowledge_harvester import KnowledgeIntelligence
    ki = KnowledgeIntelligence()
    ki.harvest_all()                 # Run full harvest
    ki.query("attention mechanism")  # Query across all knowledge
    ki.export_chunks()               # Export for RAG ingestion
"""

from __future__ import annotations

import json
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from collections import defaultdict

from src.data.discovery.research_papers import ResearchPaperKnowledgeBase, PaperKnowledge
from src.data.discovery.book_knowledge import BookKnowledgeBase, BookKnowledge

# ── Paths ───────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent.parent
KNOWLEDGE_DIR = ROOT / "data" / "research_knowledge"
MERGED_INDEX_FILE = KNOWLEDGE_DIR / "merged_knowledge_index.json"
MERGED_CHUNKS_FILE = KNOWLEDGE_DIR / "merged_knowledge_chunks.json"
HARVEST_LOG_FILE = KNOWLEDGE_DIR / "harvest_log.json"

# ── Data Models ─────────────────────────────────────────────────────


@dataclass
class KnowledgeSource:
    """A source of knowledge in the intelligence system."""

    source_type: str  # "paper", "book", "tutorial", "concept", "finding"
    source_id: str  # Unique ID within its type
    title: str
    text: str
    relevance_score: float = 0.5
    category: str = ""
    tags: list[str] = field(default_factory=list)
    citations: int = 0
    url: str = ""
    cross_refs: list[str] = field(default_factory=list)  # IDs of related sources

    @property
    def full_id(self) -> str:
        return f"{self.source_type}_{self.source_id}"


@dataclass
class HarvestReport:
    """Report of a harvest operation."""

    timestamp: str = ""
    papers_collected: int = 0
    books_indexed: int = 0
    total_sources: int = 0
    new_sources: int = 0
    total_chunks: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


class KnowledgeIntelligence:
    """
    Unified Knowledge Intelligence Engine.

    The central orchestrator that:
    1. Coordinates all knowledge sources (papers, books, tutorials)
    2. Cross-references knowledge between sources
    3. Provides intelligent querying across all knowledge
    4. Generates RAG-ready chunks
    5. Tracks knowledge evolution over time
    """

    def __init__(
        self,
        data_dir: str | Path | None = None,
        auto_load: bool = True,
    ):
        self.data_dir = Path(data_dir) if data_dir else KNOWLEDGE_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Sub-knowledge bases
        self.papers_kb = ResearchPaperKnowledgeBase(data_dir=self.data_dir)
        self.books_kb = BookKnowledgeBase(data_dir=self.data_dir)

        # Unified index
        self._sources: dict[str, KnowledgeSource] = {}
        self._cross_refs: dict[str, list[str]] = defaultdict(list)

        # Harvest tracking
        self._last_harvest: dict[str, float] = {}

        if auto_load:
            self._load_merged_index()
            # If no sources loaded from index, initialize from available books
            if not self._sources:
                self._merge_all_sources()

    # ── Persistence ───────────────────────────────────────────

    def _load_merged_index(self) -> None:
        """Load previously merged knowledge index."""
        if MERGED_INDEX_FILE.exists():
            try:
                data = json.loads(MERGED_INDEX_FILE.read_text(encoding="utf-8"))
                for s_data in data.get("sources", []):
                    source = KnowledgeSource(**s_data)
                    self._sources[source.full_id] = source
                self._cross_refs = defaultdict(list, data.get("cross_refs", {}))
                self._last_harvest = data.get("last_harvest", {})
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

    def _save_merged_index(self) -> None:
        """Save merged knowledge index."""
        data = {
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "source_count": len(self._sources),
            "sources": [
                {
                    "source_type": s.source_type,
                    "source_id": s.source_id,
                    "title": s.title,
                    "text": s.text[:200],  # Store truncated version in index
                    "relevance_score": s.relevance_score,
                    "category": s.category,
                    "tags": s.tags[:10],
                    "citations": s.citations,
                    "url": s.url,
                    "cross_refs": s.cross_refs[:20],
                }
                for s in self._sources.values()
            ],
            "cross_refs": dict(self._cross_refs),
            "last_harvest": self._last_harvest,
        }
        MERGED_INDEX_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── Harvest Operations ────────────────────────────────────

    def harvest_all(
        self,
        paper_topics: list[str] | None = None,
        paper_limit: int = 100,
        use_semantic_scholar: bool = True,
    ) -> HarvestReport:
        """
        Run a complete harvest across all knowledge sources.

        Args:
            paper_topics: Topics to search papers for.
            paper_limit: Max papers to collect.
            use_semantic_scholar: Whether to enrich with Semantic Scholar.

        Returns:
            HarvestReport with statistics and errors.
        """
        start_time = time.time()
        report = HarvestReport(timestamp=datetime.now(timezone.utc).isoformat())
        errors: list[str] = []

        print("\n" + "=" * 60)
        print("  KNOWLEDGE INTELLIGENCE ENGINE - FULL HARVEST")
        print("=" * 60)

        # === Phase 1: Research Papers ===
        print("\n" + "-" * 55)
        print("PHASE 1: RESEARCH PAPERS")
        print("-" * 55)
        try:
            self.papers_kb.collect_papers(
                topics=paper_topics or ["Large Language Models", "Python"],
                limit=paper_limit,
                use_semantic_scholar=use_semantic_scholar,
            )
            report.papers_collected = len(self.papers_kb.get_all_papers())
            print(f"  ✅ {report.papers_collected} papers in knowledge base")
        except Exception as e:
            err_msg = f"Paper collection failed: {e}"
            errors.append(err_msg)
            print(f"  ❌ {err_msg}")

        # === Phase 2: Books & Tutorials ===
        print("\n" + "-" * 55)
        print("PHASE 2: BOOKS & EDUCATIONAL RESOURCES")
        print("-" * 55)
        try:
            self.books_kb.scan_free_resources()
            report.books_indexed = len(self.books_kb.get_all_books())
            print(f"  ✅ {report.books_indexed} resources in knowledge base")
        except Exception as e:
            err_msg = f"Book collection failed: {e}"
            errors.append(err_msg)
            print(f"  ❌ {err_msg}")

        # === Phase 3: Merge & Cross-Reference ===
        print("\n" + "-" * 55)
        print("PHASE 3: MERGING & CROSS-REFERENCING")
        print("-" * 55)
        try:
            merge_count = self._merge_all_sources()
            print(f"  ✅ Merged {merge_count} sources")
            cross_ref_count = self._build_cross_references()
            print(f"  ✅ Built {cross_ref_count} cross-references")
        except Exception as e:
            err_msg = f"Merge failed: {e}"
            errors.append(err_msg)
            print(f"  ❌ {err_msg}")

        # === Phase 4: Generate Chunks ===
        print("\n" + "-" * 55)
        print("PHASE 4: GENERATING KNOWLEDGE CHUNKS")
        print("-" * 55)
        try:
            chunk_count = self._export_chunks()
            report.total_chunks = chunk_count
            print(f"  ✅ Generated {chunk_count} chunks for RAG")
        except Exception as e:
            err_msg = f"Chunk generation failed: {e}"
            errors.append(err_msg)
            print(f"  ❌ {err_msg}")

        # === Finalize ===
        duration = time.time() - start_time
        report.duration_seconds = round(duration, 2)
        report.total_sources = len(self._sources)
        report.errors = errors

        self._last_harvest["last_full_harvest"] = time.time()
        self._save_merged_index()

        # Save harvest log
        HARVEST_LOG_FILE.write_text(
            json.dumps({
                "reports": [{
                    "timestamp": report.timestamp,
                    "papers_collected": report.papers_collected,
                    "books_indexed": report.books_indexed,
                    "total_sources": report.total_sources,
                    "total_chunks": report.total_chunks,
                    "duration_seconds": report.duration_seconds,
                    "errors": report.errors,
                }]
            }, indent=2),
            encoding="utf-8",
        )

        # Print summary
        print("\n" + "=" * 60)
        print("  HARVEST COMPLETE")
        print("=" * 60)
        print(f"  Papers collected : {report.papers_collected}")
        print(f"  Books indexed    : {report.books_indexed}")
        print(f"  Total sources    : {report.total_sources}")
        print(f"  Total chunks     : {report.total_chunks}")
        print(f"  Duration         : {report.duration_seconds:.1f}s")
        if errors:
            print(f"  Errors           : {len(errors)}")
            for e in errors:
                print(f"    - {e}")
        print()

        return report

    def _merge_all_sources(self) -> int:
        """Merge all knowledge sources into the unified index."""
        count = 0

        # Merge papers
        for paper in self.papers_kb.get_all_papers():
            if paper.relevance_score < 0.3:
                continue

            source_id = f"paper_{paper.paper_id}"
            if source_id not in self._sources:
                source = KnowledgeSource(
                    source_type="paper",
                    source_id=paper.paper_id,
                    title=paper.title[:200],
                    text=(
                        f"Title: {paper.title}\n"
                        f"Authors: {', '.join(a.name for a in paper.authors[:5])}\n"
                        f"Abstract: {paper.abstract[:1000]}\n"
                        + ("\n".join(f"Finding: {f.finding[:150]}" for f in paper.key_findings[:5]))
                    ),
                    relevance_score=paper.relevance_score,
                    category=paper.categories[0] if paper.categories else "general",
                    tags=paper.keywords[:10] + paper.datasets_introduced[:3],
                    citations=paper.citation_count,
                    url=f"https://arxiv.org/abs/{paper.arxiv_id}" if paper.arxiv_id else "",
                )
                self._sources[source_id] = source
                count += 1

        # Merge books
        for book in self.books_kb.get_all_books():
            if book.relevance_score < 0.4:
                continue

            source_id = f"book_{book.book_id}"
            if source_id not in self._sources:
                source = KnowledgeSource(
                    source_type="book",
                    source_id=book.book_id,
                    title=book.title[:200],
                    text=(
                        f"Title: {book.title}\n"
                        f"Author: {book.author}\n"
                        f"Description: {book.description[:500]}\n"
                        + "\n".join(f"• {c}" for c in book.key_concepts[:10])
                    ),
                    relevance_score=book.relevance_score,
                    category=book.source_type,
                    tags=book.topics[:10] + book.key_concepts[:5],
                    url=book.source_url,
                )
                self._sources[source_id] = source
                count += 1

        return count

    def _build_cross_references(self) -> int:
        """Build cross-references between knowledge sources."""
        cross_ref_count = 0
        source_list = list(self._sources.values())

        for i, source in enumerate(source_list):
            # Find related sources by keyword matching
            source_tags = set(t.lower() for t in source.tags)
            source_text_lower = source.title.lower() + " " + source.text.lower()

            related: list[tuple[str, float]] = []

            for j, other in enumerate(source_list):
                if i == j:
                    continue

                # Skip if already cross-referenced
                other_id = other.full_id
                if other_id in self._cross_refs[source.full_id]:
                    continue

                score = 0.0
                other_tags = set(t.lower() for t in other.tags)

                # Tag overlap
                common_tags = source_tags & other_tags
                score += len(common_tags) * 0.2

                # Title/abstract keyword overlap
                other_text = other.title.lower() + " " + other.text.lower()
                common_words = set(source_text_lower.split()) & set(other_text.split())
                score += len(common_words) * 0.001

                if score >= 0.3:
                    related.append((other_id, score))

            # Sort and add top cross-references
            related.sort(key=lambda x: x[1], reverse=True)
            for rel_id, rel_score in related[:5]:
                self._cross_refs[source.full_id].append(rel_id)
                self._cross_refs[rel_id].append(source.full_id)
                cross_ref_count += 1

        # Update source objects with cross-refs
        for source in self._sources.values():
            source.cross_refs = self._cross_refs.get(source.full_id, [])[:10]

        return cross_ref_count

    def _export_chunks(self) -> int:
        """Export all knowledge as RAG-compatible chunks."""
        chunks: list[dict[str, Any]] = []

        # Get paper chunks
        paper_chunks = self.papers_kb.generate_knowledge_chunks()
        chunks.extend(paper_chunks)

        # Get book chunks
        book_chunks = self.books_kb.generate_knowledge_chunks()
        chunks.extend(book_chunks)

        # Add cross-reference enriched chunks for smart sources
        for source in self._sources.values():
            if source.cross_refs and source.relevance_score >= 0.6:
                ref_titles = []
                for ref_id in source.cross_refs[:5]:
                    ref = self._sources.get(ref_id)
                    if ref:
                        ref_titles.append(ref.title[:80])

                enriched = {
                    "id": f"ref_{source.source_type}_{source.source_id}",
                    "title": source.title[:150],
                    "text": (
                        f"{source.text[:2000]}\n\n"
                        f"RELATED KNOWLEDGE:\n" + "\n".join(f"• {t}" for t in ref_titles)
                    ),
                    "type": f"knowledge_{source.source_type}",
                    "category": source.category,
                    "version": "",
                }
                chunks.append(enriched)

        # Save
        MERGED_CHUNKS_FILE.write_text(
            json.dumps(chunks, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return len(chunks)

    # ── Query Interface ───────────────────────────────────────

    def query(
        self,
        query: str,
        max_results: int = 20,
        min_relevance: float = 0.3,
    ) -> list[dict[str, Any]]:
        """
        Query across all knowledge sources with intelligence features:
        - Full-text search across papers, books, and concepts
        - Cross-reference following
        - Relevance scoring with citation boost

        Args:
            query: The search query.
            max_results: Maximum results to return.
            min_relevance: Minimum relevance score threshold.

        Returns:
            List of result dicts with source info, relevance, and cross-refs.
        """
        query_lower = query.lower()
        scored: list[tuple[KnowledgeSource, float]] = []

        for source in self._sources.values():
            score = 0.0

            # Direct matches
            if query_lower in source.title.lower():
                score += 0.6
            if any(query_lower in tag.lower() for tag in source.tags):
                score += 0.4
            if query_lower in source.text.lower()[:1000]:
                score += 0.3

            # Boost by relevance score
            score *= source.relevance_score

            # Citation boost
            score += min(0.1, source.citations / 5000)

            if score >= min_relevance:
                scored.append((source, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        results: list[dict[str, Any]] = []
        for source, score in scored[:max_results]:
            refs = []
            for ref_id in source.cross_refs[:3]:
                ref = self._sources.get(ref_id)
                if ref:
                    refs.append({"id": ref.full_id, "title": ref.title[:80]})

            results.append({
                "id": source.full_id,
                "type": source.source_type,
                "title": source.title[:150],
                "relevance": round(score, 3),
                "text_preview": source.text[:300],
                "citations": source.citations,
                "tags": source.tags[:8],
                "url": source.url,
                "related": refs,
            })

        return results

    def related_knowledge(self, source_id: str, max_results: int = 5) -> list[dict[str, Any]]:
        """Get knowledge sources related to a given source."""
        source = self._sources.get(source_id)
        if not source:
            return []

        results = []
        for ref_id in source.cross_refs[:max_results]:
            ref = self._sources.get(ref_id)
            if ref:
                results.append({
                    "id": ref.full_id,
                    "type": ref.source_type,
                    "title": ref.title[:120],
                    "relevance": ref.relevance_score,
                    "text_preview": ref.text[:200],
                })

        return results

    def get_hot_topics(self, top_n: int = 10) -> list[dict[str, Any]]:
        """
        Identify trending/hot topics based on citation velocity
        and recency of collected papers.
        """
        # Aggregate tags from recent high-citation papers
        tag_scores: dict[str, float] = defaultdict(float)

        for source in self._sources.values():
            if source.source_type == "paper" and source.citations > 0:
                for tag in source.tags:
                    tag_scores[tag] += source.citations * source.relevance_score

        sorted_tags = sorted(tag_scores.items(), key=lambda x: x[1], reverse=True)

        return [
            {"topic": tag, "score": round(score, 1), "count": int(score / 100) + 1}
            for tag, score in sorted_tags[:top_n]
        ]

    def get_statistics(self) -> dict[str, Any]:
        """Get comprehensive statistics about the knowledge intelligence system."""
        # Get sub-stats
        paper_stats = self.papers_kb.get_statistics()
        book_stats = self.books_kb.get_statistics()

        # Aggregate source types
        type_counts: dict[str, int] = defaultdict(int)
        total_citations = 0
        high_value = 0

        for source in self._sources.values():
            type_counts[source.source_type] += 1
            total_citations += source.citations
            if source.relevance_score >= 0.7:
                high_value += 1

        return {
            "total_sources": len(self._sources),
            "by_type": dict(type_counts),
            "papers": paper_stats,
            "books": book_stats,
            "total_citations": total_citations,
            "high_value_sources": high_value,
            "cross_references": sum(len(refs) for refs in self._cross_refs.values()),
            "last_harvest": datetime.fromtimestamp(
                self._last_harvest.get("last_full_harvest", 0)
            ).isoformat() if self._last_harvest.get("last_full_harvest") else "never",
        }

    # ── Online/Continuous Learning ────────────────────────────

    def continuous_harvest(self, interval_minutes: int = 60) -> None:
        """
        Run continuous harvesting loop. Designed to be run as a background job.

        Args:
            interval_minutes: Minutes between harvests.
        """
        import time as _time

        print(f"\n🔄 Continuous Knowledge Harvesting started (every {interval_minutes} min)")
        print("   Press Ctrl+C to stop.\n")

        run_count = 0
        while True:
            run_count += 1
            print(f"\n{'='*60}")
            print(f"📡 Harvest Run #{run_count} — {datetime.now().isoformat()}")
            print(f"{'='*60}")

            try:
                report = self.harvest_all(paper_limit=50)
                print(f"\n✅ Run #{run_count} complete: {report.total_chunks} chunks generated")
            except Exception as e:
                print(f"\n❌ Run #{run_count} failed: {e}")
                traceback.print_exc()

            # Sleep for interval
            print(f"\n⏳ Sleeping for {interval_minutes} minutes...")
            _time.sleep(interval_minutes * 60)


# ═════════════════════════════════════════════════════════════════════
# Convenience Functions
# ═════════════════════════════════════════════════════════════════════


def harvest_all_knowledge(
    paper_topics: list[str] | None = None,
    paper_limit: int = 100,
) -> HarvestReport:
    """Convenience: run full knowledge harvest."""
    ki = KnowledgeIntelligence()
    return ki.harvest_all(paper_topics=paper_topics, paper_limit=paper_limit)


def query_knowledge(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Convenience: query across all knowledge sources."""
    ki = KnowledgeIntelligence()
    return ki.query(query, max_results=max_results)


def get_knowledge_stats() -> dict[str, Any]:
    """Convenience: get knowledge base statistics."""
    ki = KnowledgeIntelligence()
    return ki.get_statistics()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "harvest":
        report = harvest_all_knowledge()
        print(json.dumps({
            "papers": report.papers_collected,
            "books": report.books_indexed,
            "sources": report.total_sources,
            "chunks": report.total_chunks,
            "duration_sec": report.duration_seconds,
        }, indent=2))

    elif len(sys.argv) > 2 and sys.argv[1] == "query":
        results = query_knowledge(sys.argv[2])
        for r in results[:10]:
            print(f"  [{r['type']:6s}] {r['title'][:80]}")
            print(f"           relevance={r['relevance']:.3f} citations={r['citations']}")
            print()

    elif len(sys.argv) > 1 and sys.argv[1] == "stats":
        stats = get_knowledge_stats()
        print(json.dumps(stats, indent=2))

    else:
        print("Usage:")
        print("  python -m src.data.discovery.knowledge_harvester harvest")
        print("  python -m src.data.discovery.knowledge_harvester query 'LLM attention'")
        print("  python -m src.data.discovery.knowledge_harvester stats")
