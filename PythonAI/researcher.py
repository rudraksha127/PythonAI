#!/usr/bin/env python3
"""
FORGEAI RESEARCHER -- Self-Improving Knowledge Intelligence Agent
================================================================

A self-aware researcher agent that:
  1. Reads online research papers (arXiv, Semantic Scholar)
  2. Scans GitHub trending repos & code implementations
  3. Indexes books, tutorials & educational resources
  4. Analyzes collected knowledge for patterns & gaps
  5. Generates actionable self-improvement suggestions
  6. Optionally runs in continuous background mode

Usage:
    python researcher.py harvest        # Run one full harvest cycle
    python researcher.py analyze        # Analyze harvested knowledge -> suggestions
    python researcher.py full           # Harvest + Analyze (recommended)
    python researcher.py continuous     # Run forever (every 60 min)
    python researcher.py report         # Show latest enhancement report
    python researcher.py query "topic"  # Search harvested knowledge
    python researcher.py self-query     # Self-query KB for improvement tips
    python researcher.py auto-tune      # Extract trending paper topics
    python researcher.py benchmarks     # Scan papers for benchmark scores
    python researcher.py leaderboard    # Show benchmark leaderboard
    python researcher.py align          # Cross-reference codebase against research

Output:
  - Harvested knowledge saved to ~/.forgeai/research_knowledge/
  - Enhancement report at data/research_knowledge/enhancement_report.json
  - Self-query log at data/research_knowledge/self_query_log.json
  - Auto-tune topics at data/research_knowledge/dynamic_topics.json
  - Benchmark leaderboard at data/research_knowledge/benchmark_leaderboard.json
  - RAG-compatible chunks generated automatically
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# -- Boot ---------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))
DATA_DIR = PROJECT_ROOT / "data" / "research_knowledge"
DATA_DIR.mkdir(parents=True, exist_ok=True)



# -- ASCII-safe Output Helpers ------------------------------------------


def banner(title: str, char: str = "=", width: int = 65) -> None:
    print(f"\n{char * width}")
    print(f"  {title}")
    print(f"{char * width}")


def phase(title: str) -> None:
    print(f"\n{'-' * 55}")
    print(f"  [PHASE] {title}")
    print(f"{'-' * 55}")


def ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def info(msg: str) -> None:
    print(f"  [INFO] {msg}")


def err(msg: str) -> None:
    print(f"  [ERROR] {msg}")


# -- Phase 1: Knowledge Harvest -----------------------------------------


def run_harvest(
    paper_limit: int = 100,
    paper_topics: list[str] | None = None,
    use_semantic_scholar: bool = True,
) -> dict[str, Any]:
    """
    Run a full knowledge harvest across ALL sources:
      - Research papers (arXiv + Semantic Scholar)
      - Books & educational resources
      - GitHub trending repos

    Uses the existing KnowledgeIntelligence engine.
    """
    banner("PHASE 1 -- KNOWLEDGE HARVEST")

    try:
        from src.data.discovery.knowledge_harvester import KnowledgeIntelligence
    except ImportError as e:
        err(f"Cannot import KnowledgeIntelligence: {e}")
        return {"error": str(e), "phase": "import"}

    # Create the engine and run full harvest
    ki = KnowledgeIntelligence(auto_load=True)

    report = ki.harvest_all(
        paper_topics=paper_topics or [
            "Large Language Models",
            "Retrieval Augmented Generation",
            "Multi-Agent Systems",
            "Code Generation",
            "Reinforcement Learning from Human Feedback",
            "Transformer Architectures",
            "Knowledge Graphs",
            "Neural Network Training",
            "Model Compression and Quantization",
            "Few-Shot Learning",
        ],
        paper_limit=paper_limit,
        use_semantic_scholar=use_semantic_scholar,
    )

    # Also collect GitHub trending data
    phase("GitHub Trending Scan")
    try:
        from src.data.discovery.github_trending import GitHubTrending

        gh = GitHubTrending()
        gh_records = gh.scan(max_results=30, force_refresh=True)
        ok(f"{len(gh_records)} trending repos scanned")
    except Exception as e:
        warn(f"GitHub scan failed: {e}")
        gh_records = []

    # Get statistics
    stats = ki.get_statistics()

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "papers_collected": report.papers_collected,
        "books_indexed": report.books_indexed,
        "total_sources": report.total_sources,
        "total_chunks": report.total_chunks,
        "by_type": stats.get("by_type", {}),
        "duration_seconds": report.duration_seconds,
        "github_repos_scanned": len(gh_records),
        "errors": report.errors,
    }

    # Save harvest summary
    summary_file = DATA_DIR / "harvest_summary.json"
    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    ok(f"Harvest summary saved to {summary_file}")

    return summary


# -- Phase 2: Knowledge Analysis -> Enhancement Suggestions ----------


class EnhancementAnalyzer:
    """
    Analyzes harvested knowledge and produces actionable
    self-improvement suggestions for the ForgeAI system.
    """

    def __init__(self) -> None:
        self.suggestions: list[dict[str, Any]] = []

    def analyze(self) -> dict[str, Any]:
        """
        Run the full analysis pipeline:
          1. Load harvested knowledge
          2. Detect knowledge gaps
          3. Identify trending topics by citation velocity
          4. Compare against current system capabilities
          5. Generate prioritized enhancement suggestions
        """
        banner("PHASE 2 -- KNOWLEDGE ANALYSIS -> ENHANCEMENT SUGGESTIONS")

        # Load harvest data
        harvest_data = self._load_harvest_data()
        if not harvest_data:
            warn("No harvest data found. Run 'harvest' first.")
            return {"error": "No harvest data"}

        # Load knowledge base stats
        kb_stats = self._load_kb_stats()

        # Run analysis
        phase("Analyzing Knowledge Patterns")
        self._detect_knowledge_gaps(harvest_data, kb_stats)

        phase("Identifying Trending Research Topics")
        self._identify_trends(kb_stats)

        phase("Generating Enhancement Suggestions")
        self._generate_suggestions(harvest_data, kb_stats)

        # Build the report
        report = self._build_report(harvest_data, kb_stats)

        # Save report
        report_file = DATA_DIR / "enhancement_report.json"
        report_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        ok(f"Enhancement report saved to {report_file}")

        return report

    def _load_harvest_data(self) -> dict[str, Any]:
        """Load the most recent harvest summary."""
        summary_file = DATA_DIR / "harvest_summary.json"
        if not summary_file.exists():
            # Try parent directory (legacy)
            summary_file = DATA_DIR.parent / "research_knowledge" / "harvest_summary.json"
            if not summary_file.exists():
                warn("No harvest_summary.json found. Run a harvest first via `python researcher.py harvest`.")
                return {}

        try:
            return json.loads(summary_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _load_kb_stats(self) -> dict[str, Any]:
        """Load knowledge base statistics from the KnowledgeIntelligence engine."""
        try:
            from src.data.discovery.knowledge_harvester import get_knowledge_stats

            stats = get_knowledge_stats()
            return stats if isinstance(stats, dict) else {}
        except Exception:
            return {}

    def _detect_knowledge_gaps(
        self, harvest_data: dict[str, Any], kb_stats: dict[str, Any]
    ) -> None:
        """Detect areas where the knowledge base is weak or missing."""

        # Check paper coverage
        paper_count = harvest_data.get("papers_collected", 0)
        if paper_count < 10:
            self.suggestions.append({
                "category": "knowledge_gap",
                "priority": "high",
                "area": "Research Paper Coverage",
                "finding": f"Only {paper_count} papers collected. Need 50+ for effective RAG.",
                "action": "Increase paper_limit or expand search topics.",
                "impact": "Improves answer accuracy and breadth of knowledge.",
            })

        # Check book coverage
        book_count = harvest_data.get("books_indexed", 0)
        if book_count < 5:
            self.suggestions.append({
                "category": "knowledge_gap",
                "priority": "medium",
                "area": "Educational Resource Coverage",
                "finding": f"Only {book_count} books/resources indexed.",
                "action": "Add more books to ESSENTIAL_BOOKS in book_knowledge.py.",
                "impact": "Better foundational knowledge for training data generation.",
            })

        # Check if any errors occurred
        errors = harvest_data.get("errors", [])
        if errors:
            self.suggestions.append({
                "category": "operational",
                "priority": "high",
                "area": "Harvest Errors",
                "finding": f"{len(errors)} errors occurred during harvest.",
                "action": f"Review and fix: {errors[0][:100] if errors else 'unknown'}",
                "impact": "Ensures complete knowledge coverage.",
            })

        # Check KB stats for more gaps
        if kb_stats:
            by_type = kb_stats.get("by_type", {})
            if by_type.get("paper", 0) < 10:
                self.suggestions.append({
                    "category": "knowledge_gap",
                    "priority": "medium",
                    "area": "Paper Knowledge Base",
                    "finding": "Paper knowledge base is sparse.",
                    "action": "Run harvest with broader topics or increase limits.",
                    "impact": "Better research-backed answers.",
                })

    def _identify_trends(self, kb_stats: dict[str, Any]) -> None:
        """Identify trending topics from citation velocity and paper volume."""
        papers = kb_stats.get("papers", {})
        if not papers or not isinstance(papers, dict):
            warn("No paper statistics available for trend analysis.")
            return

        # Extract trending terms from paper titles/topics
        # (citation velocity is a proxy for trendiness)
        top_topics = papers.get("top_topics", [])
        if isinstance(top_topics, list) and len(top_topics) > 3:
            trending = [t for t in top_topics[:5] if isinstance(t, (list, tuple)) and len(t) > 1]
            if trending:
                info(f"Top trending topics: {', '.join(f'{t[0]} ({t[1]})' for t in trending)}")

    def _generate_suggestions(
        self, harvest_data: dict[str, Any], kb_stats: dict[str, Any]
    ) -> None:
        """
        Generate actionable enhancement suggestions for the system
        based on harvested knowledge analysis.
        """

        # -- Suggestion: Expand arXiv categories --
        # NOTE: cs.RO, cs.MA, cs.GT were added in Oct 2026.
        self.suggestions.append({
            "category": "enhancement",
            "priority": "medium",
            "area": "arXiv Category Coverage",
            "finding": "Monitoring 15 arXiv categories (cs.RO, cs.MA, cs.GT added).",
            "action": "Categories already expanded — cs.RO (robotics), cs.MA (multi-agent), cs.GT (game theory).",
            "impact": "Broader research coverage -> more diverse training data.",
            "effort": "Done",
        })

        # -- Suggestion: Add PapersWithCode integration --
        # NOTE: PapersWithCodeClient was implemented in Oct 2026.
        self.suggestions.append({
            "category": "enhancement",
            "priority": "medium",
            "area": "Code Implementation Links",
            "finding": "PapersWithCodeClient implemented using archive + GitHub search fallback.",
            "action": "PapersWithCodeClient already implemented — see research_papers.py. Links papers to code via archive + GitHub search.",
            "impact": "Enables code-aware RAG answers with live implementations.",
            "effort": "Done",
        })

        # -- Suggestion: Crawl more free book sources --
        # NOTE: Web crawlers were added in Oct 2026 (GitHub + Google Books).
        self.suggestions.append({
            "category": "enhancement",
            "priority": "low",
            "area": "Free Book Sources",
            "finding": "Web crawlers added for GitHub free-programming-books and Google Books API.",
            "action": "Crawlers already implemented — see crawl_free_sources() in book_knowledge.py.",
            "impact": "Automatically discovers free programming resources from the web.",
            "effort": "Done",
        })

        # -- Suggestion: Self-query mechanism --
        self.suggestions.append({
            "category": "enhancement",
            "priority": "high",
            "area": "Self-Query Knowledge Retrieval",
            "finding": "Knowledge is harvested but not automatically queried for self-improvement.",
            "action": (
                "Add a scheduled job that queries the knowledge base daily with "
                "prompts like 'What latest techniques can improve my training?' "
                "and logs the answers for review."
            ),
            "impact": "Continuous self-improvement without manual intervention.",
            "effort": "Low (add scheduled query)",
        })

        # -- Suggestion: Trending topic auto-tuning --
        self.suggestions.append({
            "category": "enhancement",
            "priority": "high",
            "area": "Auto-Tune Paper Topics",
            "finding": "Paper search topics are static. Should auto-adjust based on what's trending.",
            "action": (
                "Automatically extract trending keywords from recent papers and "
                "use them as search topics for the next harvest cycle."
            ),
            "impact": "Always harvesting the most relevant & current research.",
            "effort": "Medium (trend extraction + feedback loop)",
        })

        # -- Suggestion: Cross-reference with codebase --
        # NOTE: CodebaseAlignmentAnalyzer was implemented in Oct 2026.
        self.suggestions.append({
            "category": "enhancement",
            "priority": "medium",
            "area": "Codebase-Knowledge Alignment",
            "finding": "CodebaseAlignmentAnalyzer implemented. Run 'python researcher.py align' to generate report.",
            "action": "CodebaseAlignmentAnalyzer already implemented — see src/research/codebase_alignment.py. Run alignment via CLI: 'python researcher.py align'.",
            "impact": "Directly actionable code improvements from research.",
            "effort": "Done",
        })

        # -- Suggestion: Add citation graph --
        self.suggestions.append({
            "category": "enhancement",
            "priority": "low",
            "area": "Paper Citation Graph",
            "finding": "Citation data is collected (from Semantic Scholar) but not visualized as a graph.",
            "action": (
                "Build a citation graph visualization showing which papers "
                "cite each other. Highlight heavily cited works as key references."
            ),
            "impact": "Quick identification of seminal papers and research trends.",
            "effort": "Medium (graph + visualization)",
        })

        # -- Suggestion: Benchmark integration --
        self.suggestions.append({
            "category": "enhancement",
            "priority": "high",
            "area": "Benchmark & Dataset Tracking",
            "finding": "Papers mention benchmarks and datasets but they're not tracked systematically.",
            "action": (
                "Create a benchmark leaderboard that tracks which models achieve "
                "what scores on which benchmarks. Auto-extract from papers."
            ),
            "impact": "Always know the SOTA for any task.",
            "effort": "Medium (extraction + DB)",
        })

    def _build_report(
        self,
        harvest_data: dict[str, Any],
        kb_stats: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the final enhancement report."""
        # Prioritize suggestions
        by_priority: dict[str, list[dict[str, Any]]] = {"high": [], "medium": [], "low": []}
        for s in self.suggestions:
            by_priority.setdefault(s.get("priority", "medium"), []).append(s)

        # Summarize
        paper_count = harvest_data.get("papers_collected", 0)
        book_count = harvest_data.get("books_indexed", 0)
        chunk_count = harvest_data.get("total_chunks", 0)
        source_count = harvest_data.get("total_sources", 0)
        duration = harvest_data.get("duration_seconds", 0)

        if isinstance(kb_stats, dict):
            by_type = kb_stats.get("by_type", {})
            paper_kb_count = by_type.get("paper", paper_count)
        else:
            paper_kb_count = paper_count

        report = {
            "report_timestamp": datetime.now(timezone.utc).isoformat(),
            "report_version": "1.0",
            "system": "ForgeAI Researcher Agent",

            # Knowledge snapshot
            "knowledge_snapshot": {
                "papers_collected": paper_count,
                "books_indexed": book_count,
                "total_sources": source_count,
                "total_rag_chunks": chunk_count,
                "harvest_duration_seconds": duration,
            },

            # Enhancement suggestions (prioritized)
            "enhancement_suggestions": {
                "total": len(self.suggestions),
                "high_priority": len(by_priority.get("high", [])),
                "medium_priority": len(by_priority.get("medium", [])),
                "low_priority": len(by_priority.get("low", [])),
                "items": self.suggestions,
            },

            # Quick actionable items
            "quick_wins": [
                s for s in self.suggestions
                if s.get("priority") in ("high",) and s.get("effort", "").startswith("Low")
            ],

            # Harvest metadata
            "harvest_metadata": {
                "errors": harvest_data.get("errors", []),
                "github_repos_scanned": harvest_data.get("github_repos_scanned", 0),
            },

            # Stats
            "statistics": {
                "paper_kb_count": paper_kb_count,
                **({} if not isinstance(kb_stats, dict) else {
                    k: v for k, v in kb_stats.items()
                    if k in ("total_sources", "by_type", "cross_references", "total_citations")
                }),
            },
        }

        return report


def run_analysis() -> dict[str, Any]:
    """Run the knowledge analysis and generate enhancement report."""
    analyzer = EnhancementAnalyzer()
    return analyzer.analyze()


# -- Phase 3: Full Pipeline --------------------------------------------


def run_full_pipeline() -> dict[str, Any]:
    """Run Harvest + Analysis + Report in one shot."""
    banner("FORGEAI RESEARCHER -- FULL PIPELINE", char="#")

    start_time = time.time()

    # Phase 1: Harvest
    harvest_result = run_harvest(
        paper_limit=100,
        use_semantic_scholar=True,
    )

    # Phase 2: Analyze
    report = run_analysis()

    # Summary
    elapsed = time.time() - start_time
    suggestions = report.get("enhancement_suggestions", {})

    banner("PIPELINE COMPLETE", char="#")
    ok(f"Total time: {elapsed:.1f}s")
    ok(f"Papers collected: {harvest_result.get('papers_collected', 0)}")
    ok(f"Books indexed: {harvest_result.get('books_indexed', 0)}")
    ok(f"RAG chunks: {harvest_result.get('total_chunks', 0)}")
    ok(f"Enhancement suggestions: {suggestions.get('total', 0)}")
    info(f"High priority: {suggestions.get('high_priority', 0)}")
    info(f"Medium priority: {suggestions.get('medium_priority', 0)}")
    info(f"Low priority: {suggestions.get('low_priority', 0)}")

    return report


# -- Continuous Mode ---------------------------------------------------


# -- Phase 4: Self-Query Knowledge Retrieval (Enhancement #1) ---------

SELF_QUERY_PROMPTS = [
    "What latest techniques can improve my training pipeline?",
    "What are the most cited papers on LLM fine-tuning from my collection?",
    "Which new architectures could replace my current model?",
    "What are the top training optimizations discovered recently?",
    "What evaluation benchmarks should I track for code generation?",
    "Which datasets are most relevant to my training domain?",
]

SELF_QUERY_LOG = DATA_DIR / "self_query_log.json"


def _get_llm_response(prompt: str) -> str:
    """Get a response from the configured LLM.

    Tries available providers (OpenAI, Groq, Ollama local) in order.
    Returns a fallback message if no provider is available.
    """
    try:
        from src.utils.llm import generate_with_provider
        return generate_with_provider(prompt, system_prompt="You are a helpful research assistant.")
    except Exception as e:
        info(f"Provider API call failed: {e}")
    try:
        # Try local Ollama as fallback
        import ollama as _ollama
        r = _ollama.chat(
            model="qwen2.5-coder:7b",
            messages=[
                {"role": "system", "content": "You are a helpful research assistant."},
                {"role": "user", "content": prompt},
            ],
            options={"temperature": 0.3},
        )
        return r["message"]["content"]
    except ImportError:
        return "[No LLM available] Ollama not installed. Install with: pip install ollama"
    except Exception as e:
        return f"[No LLM available] Ollama error: {e}"


def self_query() -> list[dict[str, Any]]:
    """
    Query the harvested knowledge base with self-improvement prompts
    and log the answers for review.

    This implements the 'Self-Query Knowledge Retrieval' enhancement:
    Knowledge is harvested -> automatically queried for tips -> logged.

    Returns:
        List of {prompt, answer, timestamp, knowledge_results} dicts.
    """
    banner("PHASE 4 -- SELF-QUERY KNOWLEDGE RETRIEVAL")

    results: list[dict[str, Any]] = []
    previous_logs: list[dict[str, Any]] = []

    # Load previous logs
    if SELF_QUERY_LOG.exists():
        try:
            previous_logs = json.loads(SELF_QUERY_LOG.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            previous_logs = []

    for prompt in SELF_QUERY_PROMPTS:
        phase(f"Query: {prompt[:60]}...")

        # 1. Search harvested knowledge for relevant info
        knowledge_hits = query_knowledge(prompt, max_results=5)
        context = ""
        if knowledge_hits:
            context = "\n".join(
                f"- [{r.get('type','?')}] {r.get('title','')[:100]}"
                for r in knowledge_hits[:3]
            )
            ok(f"Found {len(knowledge_hits)} relevant knowledge items")
        else:
            info("No relevant knowledge found in KB yet")

        # 2. Get LLM insight using the harvested knowledge as context
        llm_prompt = (
            f"Based on the following knowledge base results, answer this question:\n\n"
            f"Question: {prompt}\n\n"
            f"Relevant knowledge from my research database:\n{context or '(no direct knowledge found)'}\n\n"
            f"Provide a concise, actionable answer."
        )
        answer = _get_llm_response(llm_prompt)

        entry = {
            "prompt": prompt,
            "answer": answer[:1000],
            "knowledge_items_found": len(knowledge_hits),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        results.append(entry)

        print(f"    Answer: {answer[:150]}...")
        print()

    # Save log (keep last 30 days worth)
    combined = previous_logs + results
    combined = combined[-500:]  # Keep max 500 entries
    SELF_QUERY_LOG.write_text(json.dumps(combined, indent=2, ensure_ascii=False), encoding="utf-8")

    ok(f"Self-query complete. {len(results)} queries logged to {SELF_QUERY_LOG}")
    return results


# -- Phase 5: Auto-Tune Paper Topics (Enhancement #2) -----------------

TRENDING_TOPICS_FILE = DATA_DIR / "dynamic_topics.json"


def extract_trending_topics(
    kb_stats: dict[str, Any] | None = None,
    top_n: int = 3,
) -> list[str]:
    """
    Extract trending topics from harvested papers to auto-tune
    the next harvest cycle's search queries.

    This implements the 'Auto-Tune Paper Topics' enhancement:
    Paper search topics are dynamically updated based on what's trending
    in the collected papers.

    Args:
        kb_stats: Knowledge base statistics (from get_knowledge_stats).
                  If None, loads fresh stats.
        top_n: Number of trending topics to extract.

    Returns:
        List of trending topic strings for the next harvest.
    """
    banner("PHASE 5 -- AUTO-TUNE PAPER TOPICS")

    # Try to load KB stats
    if kb_stats is None:
        try:
            from src.data.discovery.knowledge_harvester import get_knowledge_stats
            kb_stats = get_knowledge_stats()
        except Exception:
            kb_stats = {}

    # Default topics to fall back on
    default_topics = [
        "Large Language Models",
        "RAG",
        "Code Generation",
        "Multi-Agent Systems",
        "Neural Network Training",
    ]

    dynamic_topics: list[str] = []

    # Extract from paper stats
    papers = kb_stats.get("papers", {})
    if isinstance(papers, dict):
        top_topics = papers.get("top_topics", [])
        if isinstance(top_topics, list):
            for item in top_topics[:top_n * 2]:
                if isinstance(item, (list, tuple)) and len(item) > 1:
                    topic_name = str(item[0])
                    if topic_name not in dynamic_topics:
                        dynamic_topics.append(topic_name)

    # Also extract from harvest by_type
    by_type = kb_stats.get("by_type", {})
    if by_type.get("paper", 0) > 0:
        ok(f"{by_type['paper']} papers in KB — extracting trending keywords")

    # If we have papers, extract keywords from them
    try:
        from src.data.discovery.research_papers import ResearchPaperKnowledgeBase
        rpk = ResearchPaperKnowledgeBase()
        all_papers = rpk.get_all_papers()

        if all_papers:
            # Collect all keywords from papers
            keyword_counts: dict[str, int] = {}
            for p in all_papers:
                for kw in p.keywords:
                    kw_lower = kw.lower()
                    if len(kw_lower) > 2:
                        keyword_counts[kw_lower] = keyword_counts.get(kw_lower, 0) + 1

            # Sort by frequency
            sorted_kw = sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)
            for kw, count in sorted_kw[:top_n * 2]:
                if kw not in dynamic_topics:
                    dynamic_topics.append(kw.capitalize())

            ok(f"Extracted {len(sorted_kw)} unique keywords from {len(all_papers)} papers")
    except Exception as e:
        info(f"Could not extract paper keywords: {e}")

    # Merge with defaults (defaults first, then dynamic on top)
    merged_topics = default_topics[:2] + dynamic_topics[:top_n] + default_topics[2:top_n + 2]
    merged_topics = merged_topics[:top_n * 3]

    # Deduplicate while preserving order
    seen_topics: set[str] = set()
    deduped: list[str] = []
    for t in merged_topics:
        key = t.lower().strip()
        if key not in seen_topics:
            seen_topics.add(key)
            deduped.append(t)
    merged_topics = deduped

    # Save for next harvest
    dynamic_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dynamic_topics": dynamic_topics[:top_n],
        "all_topics": merged_topics,
        "source": "paper_keywords_and_stats",
    }
    TRENDING_TOPICS_FILE.write_text(json.dumps(dynamic_data, indent=2), encoding="utf-8")

    ok(f"Dynamic topics: {dynamic_topics[:top_n]}")
    ok(f"Merged topics for next harvest: {merged_topics}")

    return merged_topics


def load_dynamic_topics() -> list[str] | None:
    """Load previously saved dynamic topics. Returns None if not available."""
    if TRENDING_TOPICS_FILE.exists():
        try:
            data = json.loads(TRENDING_TOPICS_FILE.read_text(encoding="utf-8"))
            return data.get("all_topics", None)
        except (json.JSONDecodeError, OSError):
            pass
    return None


# -- Phase 6: Benchmark & Dataset Tracking (Enhancement #3) ----------

BENCHMARK_DB_FILE = DATA_DIR / "benchmark_leaderboard.json"


class BenchmarkTracker:
    """
    Extracts benchmark scores from papers and maintains a leaderboard.

    This implements the 'Benchmark & Dataset Tracking' enhancement:
    Papers mention benchmarks -> auto-extract scores -> leaderboard.

    Usage:
        tracker = BenchmarkTracker()
        tracker.scan_papers()         # Extract from all papers
        tracker.show_leaderboard()    # Display as table
        tracker.get_leaderboard()     # Get as dict
    """

    # Class-level regex pattern (compiled once, not per scan_papers call)
    BENCHMARK_PATTERN = re.compile(
        r"([A-Z][A-Za-z0-9_-]+(?:Bench|Score|Accuracy|F1|BLEU|ROUGE|Perplexity|@\d+|-" + r"\d+)?"
        r")\s*(?::|is|reaches?|achieves?|gets?|=|≈)\s*([\d.]+)",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        self.leaderboard: dict[str, list[dict[str, Any]]] = {}
        self._load()

    def _load(self) -> None:
        """Load previously saved leaderboard."""
        if BENCHMARK_DB_FILE.exists():
            try:
                self.leaderboard = json.loads(BENCHMARK_DB_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self.leaderboard = {}

    def _save(self) -> None:
        """Save leaderboard to disk."""
        BENCHMARK_DB_FILE.write_text(
            json.dumps(self.leaderboard, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def scan_papers(self) -> int:
        """
        Scan all harvested papers for benchmark mentions and
        extract model -> benchmark -> score mappings.

        Returns:
            Number of new benchmark entries found.
        """
        phase("Scanning papers for benchmarks & datasets")

        try:
            from src.data.discovery.research_papers import ResearchPaperKnowledgeBase

            rpk = ResearchPaperKnowledgeBase()
            all_papers = rpk.get_all_papers()
        except Exception as e:
            warn(f"Could not load papers: {e}")
            return 0

        new_entries = 0

        for paper in all_papers:
            text = f"{paper.title} {paper.abstract} {paper.full_text_snippet}"

            # Find benchmark mentions
            matches = self.BENCHMARK_PATTERN.findall(text)
            for benchmark_name, score_str in matches:
                try:
                    score = float(score_str)
                except ValueError:
                    continue

                bm = benchmark_name.strip()[:50]
                if bm not in self.leaderboard:
                    self.leaderboard[bm] = []

                # Check if this entry already exists
                entry_exists = any(
                    e.get("paper_id") == paper.paper_id and abs(e.get("score", 0) - score) < 0.001
                    for e in self.leaderboard[bm]
                )
                if not entry_exists:
                    self.leaderboard[bm].append({
                        "score": round(score, 4),
                        "paper_id": paper.paper_id,
                        "paper_title": paper.title[:120],
                        "arxiv_id": paper.arxiv_id,
                        "year": paper.published_date[:4] if paper.published_date else "",
                        "citation_count": paper.citation_count,
                        "datasets_used": paper.datasets_used[:3],
                    })
                    new_entries += 1

        # Sort each benchmark by score descending
        for bm in self.leaderboard:
            self.leaderboard[bm].sort(key=lambda x: x.get("score", 0), reverse=True)

        self._save()

        # Also scan for dataset mentions
        dataset_count = sum(len(p.datasets_introduced + p.datasets_used) for p in all_papers)

        ok(f"Scanned {len(all_papers)} papers, found {new_entries} benchmark entries")
        info(f"Datasets referenced: {dataset_count}")
        info(f"Unique benchmarks tracked: {len(self.leaderboard)}")

        return new_entries

    def get_leaderboard(self, top_n: int = 20) -> dict[str, list[dict[str, Any]]]:
        """Get the full benchmark leaderboard."""
        return {bm: entries[:top_n] for bm, entries in self.leaderboard.items()}

    def show_leaderboard(self, top_n: int = 10) -> None:
        """Display the benchmark leaderboard."""
        phase("BENCHMARK LEADERBOARD")

        if not self.leaderboard:
            warn("No benchmarks tracked yet. Run scan_papers() first or harvest more papers.")
            return

        for bm in sorted(self.leaderboard.keys())[:20]:
            entries = self.leaderboard[bm][:top_n]
            print(f"\n  {bm}:")
            for i, e in enumerate(entries, 1):
                year = f"({e.get('year', '?')})" if e.get('year') else ""
                cites = f"cited {e['citation_count']}x" if e.get('citation_count', 0) > 0 else ""
                paper_short = e.get('paper_title', '?')[:60]
                print(f"    #{i}: {e['score']:.4f} | {paper_short} {year} {cites}".strip())
            if len(entries) >= top_n:
                print(f"    ... (+ more)")

        print(f"\n  Total benchmarks tracked: {len(self.leaderboard)}")
        print(f"  Total entries: {sum(len(v) for v in self.leaderboard.values())}")


# -- Continuous Mode ---------------------------------------------------

ENHANCEMENT_CYCLE = 1  # Run enhancements every N harvest cycles


def run_continuous(interval_minutes: int = 60) -> None:
    """
    Run the researcher pipeline in a continuous loop.
    Designed to run as a background daemon or scheduled task.

    Each cycle:
      1. Full knowledge harvest
      2. Analysis -> Enhancement suggestions
      3. Sleep for interval_minutes

    Enhancement features run periodically:
      - Self-Query Knowledge Retrieval (every cycle)
      - Auto-Tune Paper Topics (every cycle)
      - Benchmark & Dataset Tracking (every cycle)
    """
    banner("CONTINUOUS RESEARCHER MODE (Ctrl+C to stop)")
    ok(f"Interval: {interval_minutes} minutes")
    ok("Each cycle: Harvest -> Analyze -> Report -> Self-Query -> Auto-Tune -> Benchmarks")

    run_count = 0
    while True:
        run_count += 1
        phase(f"Research Cycle #{run_count} - {datetime.now().isoformat()}")

        try:
            # Core pipeline
            report = run_full_pipeline()

            # Enhancement features (every cycle)
            try:
                self_query()
            except Exception as e:
                warn(f"Self-query failed: {e}")

            try:
                extract_trending_topics()
            except Exception as e:
                warn(f"Auto-tune topics failed: {e}")

            try:
                bt = BenchmarkTracker()
                bt.scan_papers()
            except Exception as e:
                warn(f"Benchmark scan failed: {e}")

            # Codebase-Knowledge Alignment
            try:
                from src.research.codebase_alignment import run_alignment
                run_alignment()
            except Exception as e:
                warn(f"Codebase alignment failed: {e}")

        except KeyboardInterrupt:
            ok("Interrupted by user. Exiting.")
            break
        except Exception as e:
            err(f"Cycle failed: {e}")
            traceback.print_exc()

        info(f"Sleeping for {interval_minutes} minutes...")
        try:
            time.sleep(interval_minutes * 60)
        except KeyboardInterrupt:
            ok("Interrupted. Exiting.")
            break


# -- Query Mode --------------------------------------------------------


# -- Lazy-loaded sentence-transformers model for semantic search ----------
_SEMANTIC_MODEL: Any = None
_SEMANTIC_CHUNKS: list[dict[str, Any]] | None = None
_SEMANTIC_CHUNK_EMBEDDINGS: list[list[float]] | None = None


def _load_semantic_search() -> None:
    """Lazy-load the sentence-transformers model and knowledge chunks."""
    global _SEMANTIC_MODEL, _SEMANTIC_CHUNKS, _SEMANTIC_CHUNK_EMBEDDINGS

    if _SEMANTIC_MODEL is not None:
        return

    try:
        from sentence_transformers import SentenceTransformer
        _SEMANTIC_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    except ImportError:
        _SEMANTIC_MODEL = False  # Sentinel: not available
        return

    # Load merged knowledge chunks
    merged_file = PROJECT_ROOT / "data" / "research_knowledge" / "merged_knowledge_chunks.json"
    if not merged_file.exists():
        # Try alternative location
        merged_file = DATA_DIR / "merged_knowledge_chunks.json"
    if not merged_file.exists():
        warn("No merged knowledge chunks found. Run harvest first.")
        return

    try:
        _SEMANTIC_CHUNKS = json.loads(merged_file.read_text(encoding="utf-8"))
        if not _SEMANTIC_CHUNKS:
            _SEMANTIC_CHUNKS = None
            return
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        warn(f"Failed to load knowledge chunks for semantic search: {e}")
        _SEMANTIC_CHUNKS = None
        return

    # Pre-compute embeddings for all chunks
    texts_to_embed = []
    for chunk in _SEMANTIC_CHUNKS:
        text = chunk.get("text", "")[:1000] or chunk.get("content", "")[:1000]
        title = chunk.get("title", "")
        combined = f"{title}: {text}" if title else text
        texts_to_embed.append(combined)

    if texts_to_embed:
        try:
            embeddings = _SEMANTIC_MODEL.encode(texts_to_embed, show_progress_bar=False)
            _SEMANTIC_CHUNK_EMBEDDINGS = [emb.tolist() for emb in embeddings]
            info(f"Semantic search loaded: {len(_SEMANTIC_CHUNKS)} chunks, {len(_SEMANTIC_CHUNK_EMBEDDINGS)} embeddings")
        except Exception as e:
            warn(f"Embedding computation failed: {e}")
            _SEMANTIC_CHUNKS = None
            _SEMANTIC_CHUNK_EMBEDDINGS = None
    else:
        _SEMANTIC_CHUNKS = None


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _semantic_search(query: str, max_results: int = 10, min_score: float = 0.2) -> list[dict[str, Any]]:
    """
    Semantic search over the merged knowledge chunks using embedding similarity.

    Enables natural-language queries like "What latest techniques can improve
    my training pipeline?" to find relevant papers/books even when the exact
    wording doesn't match any title.

    Returns:
        List of result dicts with type, title, relevance, text_preview, etc.
    """
    _load_semantic_search()

    if _SEMANTIC_MODEL is None or _SEMANTIC_MODEL is False:
        return []
    if not _SEMANTIC_CHUNKS or not _SEMANTIC_CHUNK_EMBEDDINGS:
        return []

    try:
        query_emb = _SEMANTIC_MODEL.encode([query], show_progress_bar=False)[0].tolist()
    except Exception as e:
        warn(f"Query embedding failed: {e}")
        return []

    # Compute similarities
    scored: list[tuple[int, float]] = []
    for i, chunk_emb in enumerate(_SEMANTIC_CHUNK_EMBEDDINGS):
        score = _cosine_similarity(query_emb, chunk_emb)
        if score >= min_score:
            scored.append((i, score))

    scored.sort(key=lambda x: x[1], reverse=True)

    results: list[dict[str, Any]] = []
    for idx, score in scored[:max_results]:
        chunk = _SEMANTIC_CHUNKS[idx]
        chunk_type = chunk.get("type", "knowledge_chunk")
        title = chunk.get("title", "")[:150]
        text = chunk.get("text", "") or chunk.get("content", "")

        # Determine source type for display
        source_type = "paper" if "paper" in chunk_type else "book" if "book" in chunk_type else "chunk"

        results.append({
            "id": chunk.get("id", str(idx)),
            "type": source_type,
            "title": title or text[:80],
            "relevance": round(score, 3),
            "text_preview": text[:300],
            "citations": chunk.get("citation_count", 0) or chunk.get("citations", 0),
            "tags": chunk.get("tags", []) or chunk.get("keywords", []),
        })

    return results



def query_knowledge(query_text: str, max_results: int = 10) -> list[dict[str, Any]]:
    """
    Query the harvested knowledge base using semantic search (preferred)
    with keyword-matching fallback.

    Phase 1: Embedding-based semantic search against the merged knowledge
    chunks (1,102 chunks from 129 papers + 676 books). This handles
    natural-language queries that don't match titles exactly.

    Phase 2: Fall back to keyword matching via KnowledgeIntelligence.query()
    for direct title/keyword lookups.
    """
    banner(f"SEARCH: {query_text}")

    results: list[dict[str, Any]] = []

    # ── Phase 1: Semantic search ──
    phase("Phase 1: Semantic search (embedding-based)")
    try:
        semantic_results = _semantic_search(query_text, max_results=max_results)
        if semantic_results:
            results.extend(semantic_results)
            ok(f"Semantic search found {len(semantic_results)} relevant chunks")
        else:
            info("Semantic search returned no matches")
    except Exception as e:
        info(f"Semantic search unavailable: {e}")

    # ── Phase 2: Keyword fallback ──
    phase("Phase 2: Keyword matching (KnowledgeIntelligence)")
    try:
        from src.data.discovery.knowledge_harvester import query_knowledge as qk

        keyword_results = qk(query_text, max_results=max_results)
        if keyword_results:
            # Merge: add keyword results that aren't already in semantic results
            existing_titles = {r.get("title", "").lower() for r in results}
            for r in keyword_results:
                if r.get("title", "").lower() not in existing_titles:
                    results.append(r)
            ok(f"Keyword matching found {len(keyword_results)} additional sources")
        else:
            info("Keyword matching returned no results")
    except Exception as e:
        info(f"Keyword matching unavailable: {e}")

    # ── Display results ──
    if results:
        # Sort by relevance descending
        results.sort(key=lambda r: r.get("relevance", 0), reverse=True)
        results = results[:max_results]

        ok(f"Total results: {len(results)}")
        print()
        for i, r in enumerate(results, 1):
            rtype = r.get('type', '?').upper()
            title = str(r.get('title', ''))[:100]
            rel = r.get('relevance', 0)
            cites = r.get('citations', 0)
            print(f"  #{i} [{rtype}] rel={rel:.3f} cites={cites}")
            print(f"       {title}")
            if r.get("text_preview"):
                print(f"       {str(r['text_preview'])[:120]}...")
            print()

        return results
    else:
        warn("No results found from any search method.")
        return []


# -- Report Display -----------------------------------------------------


def show_report() -> None:
    """Display the latest enhancement report."""
    report_file = DATA_DIR / "enhancement_report.json"
    if not report_file.exists():
        warn("No report found. Run `python researcher.py full` first.")
        return

    try:
        report = json.loads(report_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        err(f"Failed to read report: {e}")
        return

    banner("LATEST ENHANCEMENT REPORT", char="#")

    # Knowledge snapshot
    ks = report.get("knowledge_snapshot", {})
    print(f"\n  Knowledge Snapshot:")
    print(f"    Papers collected  : {ks.get('papers_collected', '?')}")
    print(f"    Books indexed     : {ks.get('books_indexed', '?')}")
    print(f"    Total sources     : {ks.get('total_sources', '?')}")
    print(f"    RAG chunks        : {ks.get('total_rag_chunks', '?')}")
    print(f"    Harvest duration  : {ks.get('harvest_duration_seconds', 0):.1f}s")

    # Suggestions
    es = report.get("enhancement_suggestions", {})
    items = es.get("items", [])
    print(f"\n  Enhancement Suggestions: {len(items)} total")
    print(f"    High priority   : {es.get('high_priority', 0)}")
    print(f"    Medium priority : {es.get('medium_priority', 0)}")
    print(f"    Low priority    : {es.get('low_priority', 0)}")

    # Print each suggestion
    for i, s in enumerate(items, 1):
        print(f"\n  {'-' * 50}")
        print(f"  [{s.get('priority', '?').upper()}] #{i}: {s.get('area', '?')}")
        print(f"    Finding: {s.get('finding', '?')}")
        print(f"    Action:  {s.get('action', '?')}")
        print(f"    Impact:  {s.get('impact', '?')}")
        if s.get("effort"):
            print(f"    Effort:  {s.get('effort', '?')}")

    print(f"\n  Report timestamp: {report.get('report_timestamp', '?')}")
    print()


# -- CLI ---------------------------------------------------------------


def print_usage() -> None:
    """Print CLI usage information."""
    print(__doc__)


def _fix_stdout_encoding() -> None:
    """Wrap stdout/stderr with UTF-8 encoding for Windows terminals.

    Skips when running under pytest (PYTEST_CURRENT_TEST env var) to avoid
    conflicting with pytest's capture mechanism, which also wraps sys.stdout.
    """
    if sys.platform != "win32" or "PYTEST_CURRENT_TEST" in os.environ:
        return
    import io
    if hasattr(sys.stdout, "buffer") and sys.stdout.buffer is not None:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer") and sys.stderr.buffer is not None:
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def main() -> None:
    """CLI entry point."""
    _fix_stdout_encoding()

    if len(sys.argv) < 2:
        print_usage()
        return

    command = sys.argv[1]

    if command == "harvest":
        run_harvest()

    elif command == "analyze":
        run_analysis()

    elif command == "full":
        run_full_pipeline()

    elif command == "continuous":
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 60
        run_continuous(interval)

    elif command == "report":
        show_report()

    elif command == "query":
        if len(sys.argv) < 3:
            warn("Usage: python researcher.py query '<search text>'")
            return
        query_knowledge(" ".join(sys.argv[2:]))

    elif command == "self-query":
        self_query()

    elif command == "auto-tune":
        extract_trending_topics()

    elif command == "benchmarks":
        bt = BenchmarkTracker()
        count = bt.scan_papers()
        ok(f"Found {count} new benchmark entries")

    elif command == "leaderboard":
        bt = BenchmarkTracker()
        bt.show_leaderboard()

    elif command == "align":
        """Cross-reference codebase against research papers."""
        from src.research.codebase_alignment import run_alignment
        run_alignment()

    elif command in ("--help", "-h", "help"):
        print_usage()

    else:
        warn(f"Unknown command: {command}")
        print_usage()


if __name__ == "__main__":
    main()
