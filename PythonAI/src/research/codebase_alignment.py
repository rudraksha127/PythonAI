"""
CODEBASE-KNOWLEDGE ALIGNMENT ANALYZER
=======================================
Cross-references the ForgeAI codebase (src/) against research papers,
books, and methodologies to identify:

1. Which research topics are well-covered by the codebase
2. Where modern research patterns could replace legacy implementations
3. Which classes/functions correspond to which research concepts
4. Gaps where the codebase lacks SOTA techniques

Usage:
    from src.research.codebase_alignment import CodebaseAlignmentAnalyzer
    analyzer = CodebaseAlignmentAnalyzer()
    report = analyzer.analyze()
    analyzer.print_report(report)
"""

from __future__ import annotations

import ast
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SRC_DIR = PROJECT_ROOT / "src"
DATA_DIR = PROJECT_ROOT / "data" / "research_knowledge"
ALIGNMENT_FILE = DATA_DIR / "codebase_alignment.json"

# Research topics that map to codebase modules/patterns
TOPIC_MODULE_MAP: dict[str, list[str]] = {
    # LLM / Transformer patterns
    "transformer": ["attention", "transformer", "llm", "language_model"],
    "attention mechanism": ["attention", "self_attention", "multi_head", "attention_mechanism", "scaled_dot_product", "flash_attention"],
    "large language model": ["llm", "language_model", "chat", "completion"],
    "reinforcement learning": ["rl", "reinforcement", "ppo", "grpo"],
    "RLHF": ["rlhf", "reward", "preference", "feedback"],
    "fine-tuning": ["fine_tune", "sft", "lora", "adapter", "trainer"],
    "RAG": ["rag", "retrieval", "vector", "embedding", "chroma"],
    "knowledge graph": ["knowledge_graph", "kg", "graph"],
    "few-shot learning": ["few_shot", "in_context", "prompt"],
    "chain of thought": ["reasoning", "chain_of_thought", "cot"],
    "distributed training": ["distributed", "parallel", "multi_gpu"],
    "model compression": ["quantization", "pruning", "distill", "compress"],
    "embeddings": ["embedding", "vector", "encoder"],
    "multi-agent": ["agent", "multi_agent", "orchestrat"],
    "code generation": ["code_gen", "program", "synthesi"],
    "dataset": ["dataset", "data_collect", "training_data"],
    "benchmark": ["benchmark", "eval", "metric", "score"],
    "neural network training": ["trainer", "training", "loss", "optimizer"],
    "RAG pipeline": ["retrieval", "generator", "qa", "query"],
    "API server": ["api", "server", "route", "endpoint", "fastapi"],
    "authentication": ["auth", "login", "oauth", "token", "jwt"],
    "caching": ["cache", "redis", "memory"],
    "monitoring": ["monitor", "metric", "logging", "observ"],
    "guardrails": ["guardrail", "safety", "validation", "content_filter"],
    "tool calling": ["tool", "function_call", "mcp"],
}

# Known research methodologies that map to codebase patterns
METHODOLOGY_MAP: dict[str, list[str]] = {
    "Transformer Architecture": ["attention", "transformer", "multi_head"],
    "Supervised Fine-Tuning (SFT)": ["sft", "fine_tune", "trainer"],
    "Reinforcement Learning from Human Feedback": ["rlhf", "reward", "preference"],
    "GRPO / Policy Gradient": ["grpo", "ppo", "policy", "reinforcement"],
    "Retrieval-Augmented Generation": ["rag", "retrieval", "vector_store"],
    "Mixture of Experts": ["moe", "expert", "router"],
    "Knowledge Distillation": ["distill", "teacher", "student"],
    "Chain-of-Thought Reasoning": ["reasoning", "cot", "thought"],
    "Multi-Agent Orchestration": ["agent", "orchestrat", "multi_agent"],
    "Tool-Augmented LLMs": ["tool", "function_call", "mcp"],
    "Embedding & Vector Search": ["embedding", "vector", "semantic_search"],
    "Prompt Engineering": ["prompt", "template", "few_shot"],
    "Distributed Training": ["distributed", "shard", "parallel"],
    "Model Quantization": ["quantiz", "int8", "fp16", "compress"],
    "Test-Time Scaling": ["tts", "time_scaling", "compute"],
}


class CodebaseScanner:
    """Scans the src/ directory and extracts code structure."""

    def __init__(self, src_dir: str | Path | None = None):
        self.src_dir = Path(src_dir) if src_dir else SRC_DIR
        self.modules: dict[str, list[dict[str, Any]]] = {}
        self.imports: Counter = Counter()
        self.all_classes: list[dict[str, Any]] = []
        self.all_functions: list[dict[str, Any]] = []

    def scan(self) -> dict[str, Any]:
        """Scan the entire src/ directory and extract code structure."""
        print(f"  [Scanner] Scanning {self.src_dir}...")

        py_files = sorted(self.src_dir.rglob("*.py"))
        # Exclude cache and venv
        py_files = [f for f in py_files if "__pycache__" not in str(f) and ".venv" not in str(f)]

        module_count = 0
        for py_file in py_files:
            try:
                parsed = self._parse_file(py_file)
                if parsed:
                    rel_path = str(py_file.relative_to(PROJECT_ROOT))
                    self.modules[rel_path] = parsed
                    module_count += 1
            except (SyntaxError, UnicodeDecodeError):
                continue

        print(f"  [Scanner] Parsed {module_count} Python modules")
        print(f"  [Scanner] Found {len(self.all_classes)} classes, {len(self.all_functions)} functions")
        return self._summary()

    def _parse_file(self, py_file: Path) -> list[dict[str, Any]] | None:
        """Parse a Python file and extract classes, functions, imports."""
        source = py_file.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)

        entries: list[dict[str, Any]] = []
        rel_path = str(py_file.relative_to(PROJECT_ROOT))

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                decorators = [self._get_decorator_name(d) for d in node.decorator_list]
                entry = {
                    "type": "class",
                    "name": node.name,
                    "path": rel_path,
                    "line": node.lineno,
                    "methods": methods[:20],
                    "decorators": [d for d in decorators if d],
                    "bases": [self._get_base_name(b) for b in node.bases],
                    "docstring": ast.get_docstring(node) or "",
                }
                entries.append(entry)
                self.all_classes.append(entry)

            elif isinstance(node, ast.FunctionDef):
                if node.name.startswith("_"):
                    continue  # Skip private methods (handled via classes)
                decorators = [self._get_decorator_name(d) for d in node.decorator_list]
                entry = {
                    "type": "function",
                    "name": node.name,
                    "path": rel_path,
                    "line": node.lineno,
                    "decorators": [d for d in decorators if d],
                    "docstring": ast.get_docstring(node) or "",
                }
                entries.append(entry)
                self.all_functions.append(entry)

            elif isinstance(node, ast.Import):
                for alias in node.names:
                    self.imports[alias.name] += 1

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for alias in node.names:
                        self.imports[node.module] += 1

        return entries

    @staticmethod
    def _get_decorator_name(node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        if isinstance(node, ast.Call):
            return CodebaseScanner._get_decorator_name(node.func)
        return ""

    @staticmethod
    def _get_base_name(node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{CodebaseScanner._get_base_name(node.value)}.{node.attr}" if hasattr(node, 'value') else node.attr
        if isinstance(node, ast.Subscript):
            return CodebaseScanner._get_base_name(node.value)
        return ""

    def _summary(self) -> dict[str, Any]:
        """Return a summary of the codebase scan."""
        modules_by_dir: dict[str, int] = defaultdict(int)
        for path in self.modules:
            parts = path.split("/")
            if len(parts) > 2:
                modules_by_dir[parts[1]] += 1

        top_imports = self.imports.most_common(30)

        class_names = [c["name"] for c in self.all_classes]
        function_names = [f["name"] for f in self.all_functions]

        return {
            "total_modules": len(self.modules),
            "total_classes": len(self.all_classes),
            "total_functions": len(self.all_functions),
            "modules_by_directory": dict(sorted(modules_by_dir.items(), key=lambda x: x[1], reverse=True)),
            "top_imports": [{"name": n, "count": c} for n, c in top_imports],
            "class_names": class_names,
            "function_names": function_names,
        }


class CodebaseAlignmentAnalyzer:
    """
    Cross-references the codebase against research papers and books
    to find:
    - Which research topics are covered by code
    - Where modern techniques are missing
    - Alignment scores per module
    - Concrete suggestions for improvement
    """

    def __init__(self):
        self.scanner = CodebaseScanner()

    def analyze(self, paper_keywords: list[str] | None = None) -> dict[str, Any]:
        """
        Run the full alignment analysis.

        Args:
            paper_keywords: Optional list of research keywords from papers.
                            If None, loads from the research knowledge base.

        Returns:
            Report dict with alignment scores, gaps, and suggestions.
        """
        # Step 1: Scan codebase
        code_summary = self.scanner.scan()

        # Step 2: Load research keywords from papers
        if paper_keywords is None:
            paper_keywords = self._load_research_keywords()

        # Step 3: Compute coverage per topic
        topic_coverage = self._compute_topic_coverage(code_summary)

        # Step 4: Compute methodology coverage
        methodology_coverage = self._compute_methodology_coverage(code_summary)

        # Step 5: Classify each class/function by research topic
        code_topics = self._classify_code_entities(code_summary)

        # Step 6: Identify gaps
        gaps = self._identify_gaps(topic_coverage, paper_keywords)

        # Step 7: Generate suggestions
        suggestions = self._generate_suggestions(gaps, methodology_coverage)

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "codebase_summary": {
                "total_modules": code_summary["total_modules"],
                "total_classes": code_summary["total_classes"],
                "total_functions": code_summary["total_functions"],
                "modules_by_directory": code_summary["modules_by_directory"],
            },
            "topic_coverage": topic_coverage,
            "methodology_coverage": methodology_coverage,
            "code_topic_assignments": code_topics,
            "alignment_gaps": gaps,
            "improvement_suggestions": suggestions,
        }

        # Save report
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        ALIGNMENT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

        return report

    def _load_research_keywords(self) -> list[str]:
        """Load research keywords from the paper knowledge base."""
        keywords: list[str] = []

        # Try loading from paper index
        papers_file = DATA_DIR / "papers_index.json"
        if papers_file.exists():
            try:
                data = json.loads(papers_file.read_text(encoding="utf-8"))
                for paper in data.get("papers", []):
                    for kw in paper.get("keywords", []):
                        if isinstance(kw, str) and kw not in keywords:
                            keywords.append(kw)
            except (json.JSONDecodeError, KeyError):
                pass

        # Also try from knowledge chunks
        chunks_file = DATA_DIR / "knowledge_chunks.json"
        if chunks_file.exists():
            try:
                data = json.loads(chunks_file.read_text(encoding="utf-8"))
                for chunk in data[:100]:
                    text = chunk.get("text", "") or chunk.get("title", "")
                    if text:
                        for term in re.findall(r"[A-Z][A-Za-z0-9_-]{3,}", text):
                            if term.lower() not in (k.lower() for k in keywords):
                                keywords.append(term)
            except (json.JSONDecodeError, KeyError):
                pass

        # Add default research topics
        keywords.extend([
            "LLM", "RAG", "transformer", "fine-tuning", "RLHF", "SFT", "GRPO",
            "multi-agent", "reasoning", "knowledge graph", "embedding",
            "quantization", "distillation", "attention", "retrieval",
            "reinforcement learning", "chain of thought", "tool use",
            "instruction tuning", "prompt engineering", "vector database",
        ])

        return list(set(keywords))

    def _compute_topic_coverage(self, code_summary: dict[str, Any]) -> list[dict[str, Any]]:
        """Compute how well each research topic is covered by the codebase."""
        all_text = " ".join(
            code_summary["class_names"] + code_summary["function_names"] + list(self.scanner.imports.keys())
        ).lower()

        coverage: list[dict[str, Any]] = []
        for topic, patterns in TOPIC_MODULE_MAP.items():
            matches = 0
            matched_terms: list[str] = []
            for pattern in patterns:
                if pattern.lower() in all_text:
                    count = all_text.count(pattern.lower())
                    matches += count
                    matched_terms.append(pattern)

            # Find which modules cover this topic
            modules = []
            for path, entries in self.scanner.modules.items():
                path_lower = path.lower()
                if any(p in path_lower for p in patterns):
                    module_classes = [e["name"] for e in entries if e["type"] == "class"]
                    modules.append({
                        "path": path,
                        "classes": module_classes[:5],
                    })

            status = "covered" if matches > 5 else ("partial" if matches > 0 else "missing")
            coverage.append({
                "topic": topic,
                "status": status,
                "match_count": matches,
                "matched_terms": matched_terms[:5],
                "modules": modules[:3],
            })

        return sorted(coverage, key=lambda x: x["match_count"], reverse=True)

    def _compute_methodology_coverage(self, code_summary: dict[str, Any]) -> list[dict[str, Any]]:
        """Compute how well each research methodology is covered."""
        all_text = " ".join(
            code_summary["class_names"] + code_summary["function_names"]
        ).lower()

        coverage: list[dict[str, Any]] = []
        for methodology, patterns in METHODOLOGY_MAP.items():
            matches = sum(1 for p in patterns if p.lower() in all_text)
            status = "covered" if matches >= 2 else ("partial" if matches >= 1 else "missing")
            coverage.append({
                "methodology": methodology,
                "status": status,
                "match_count": matches,
            })

        return sorted(coverage, key=lambda x: x["match_count"], reverse=True)

    def _classify_code_entities(self, code_summary: dict[str, Any]) -> list[dict[str, Any]]:
        """Classify each class/function by research topic."""
        assignments: list[dict[str, Any]] = []

        for cls in code_summary["class_names"]:
            cls_lower = cls.lower()
            topics = []
            for topic, patterns in TOPIC_MODULE_MAP.items():
                if any(p in cls_lower for p in patterns):
                    topics.append(topic)
            if topics:
                assignments.append({"name": cls, "type": "class", "topics": topics[:3]})

        for func in code_summary["function_names"]:
            func_lower = func.lower()
            topics = []
            for topic, patterns in TOPIC_MODULE_MAP.items():
                if any(p in func_lower for p in patterns):
                    topics.append(topic)
            if topics:
                assignments.append({"name": func, "type": "function", "topics": topics[:3]})

        return assignments[:50]

    def _identify_gaps(
        self, topic_coverage: list[dict[str, Any]], paper_keywords: list[str]
    ) -> list[dict[str, Any]]:
        """Identify alignment gaps between research and codebase."""
        gaps: list[dict[str, Any]] = []

        # Gaps from topic coverage
        for tc in topic_coverage:
            if tc["status"] == "missing":
                gaps.append({
                    "type": "missing_topic",
                    "topic": tc["topic"],
                    "severity": "high",
                    "detail": f"No code found for '{tc['topic']}' — consider implementing",
                    "paper_references": [kw for kw in paper_keywords if tc["topic"].lower() in kw.lower()][:3],
                })
            elif tc["status"] == "partial":
                gaps.append({
                    "type": "partial_coverage",
                    "topic": tc["topic"],
                    "severity": "medium",
                    "detail": f"'{tc['topic']}' has limited code coverage ({tc['match_count']} matches)",
                })

        # Gaps from paper keywords that don't match any code
        all_code_text = " ".join(
            c["name"].lower() for c in self.scanner.all_classes
        )
        for kw in paper_keywords:
            if len(kw) < 4:
                continue
            if kw.lower() not in all_code_text:
                # Check if it's already covered by a topic
                covered = any(kw.lower() in t.lower() for gc in gaps for t in [gc["topic"]])
                if not covered:
                    gaps.append({
                        "type": "paper_knowledge_not_in_code",
                        "topic": kw,
                        "severity": "low",
                        "detail": f"Research keyword '{kw}' appears in papers but not in codebase",
                    })

        # Limit gaps
        return gaps[:20]

    def _generate_suggestions(
        self, gaps: list[dict[str, Any]], methodology_coverage: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Generate actionable suggestions from gaps."""
        suggestions: list[dict[str, Any]] = []

        for gap in gaps:
            if gap["severity"] == "high":
                suggestions.append({
                    "priority": "high",
                    "area": f"Implement {gap['topic']}",
                    "finding": gap["detail"],
                    "action": f"Research and implement {gap['topic']} support in the codebase. "
                              f"Review papers_implementations and add corresponding modules.",
                    "impact": "Closes the gap between research and implementation.",
                })

        # Check which methodologies are missing
        missing_methods = [m for m in methodology_coverage if m["status"] == "missing"]
        if missing_methods:
            suggestions.append({
                "priority": "medium",
                "area": f"Missing Methodologies: {', '.join(m['methodology'] for m in missing_methods[:3])}",
                "finding": f"{len(missing_methods)} research methodologies have no code implementation.",
                "action": "Prioritize implementing the most impactful missing methodologies.",
                "impact": "Modernizes the codebase with SOTA techniques.",
            })

        if not suggestions:
            suggestions.append({
                "priority": "low",
                "area": "Codebase Alignment Complete",
                "finding": "No major alignment gaps detected.",
                "action": "Continue monitoring new research for implementation opportunities.",
                "impact": "Maintains codebase-research alignment.",
            })

        return suggestions

    def print_report(self, report: dict[str, Any]) -> None:
        """Print a formatted alignment report."""
        print(f"\n{'='*60}")
        print(f"  CODEBASE-KNOWLEDGE ALIGNMENT REPORT")
        print(f"{'='*60}")

        summary = report.get("codebase_summary", {})
        print(f"\n  Codebase Summary:")
        print(f"    Modules : {summary.get('total_modules', 0)}")
        print(f"    Classes : {summary.get('total_classes', 0)}")
        print(f"    Functions: {summary.get('total_functions', 0)}")
        dirs = summary.get("modules_by_directory", {})
        if dirs:
            print(f"    Top dirs: {', '.join(f'{d}({c})' for d, c in list(dirs.items())[:5])}")

        print(f"\n  Topic Coverage:")
        covered = [t for t in report.get("topic_coverage", []) if t["status"] == "covered"]
        partial = [t for t in report.get("topic_coverage", []) if t["status"] == "partial"]
        missing = [t for t in report.get("topic_coverage", []) if t["status"] == "missing"]
        print(f"    Covered : {len(covered)} topics")
        print(f"    Partial  : {len(partial)} topics")
        print(f"    Missing  : {len(missing)} topics")
        if missing:
            print(f"    Missing topics: {', '.join(t['topic'] for t in missing[:5])}")

        print(f"\n  Methodology Coverage:")
        for m in report.get("methodology_coverage", [])[:10]:
            icon = "+" if m["status"] == "covered" else ("~" if m["status"] == "partial" else "-")
            print(f"    [{icon}] {m['methodology']}")

        gaps = report.get("alignment_gaps", [])
        print(f"\n  Alignment Gaps: {len(gaps)}")
        for g in gaps[:5]:
            print(f"    [{g['severity'].upper()}] {g.get('topic', '?')}: {g['detail'][:100]}")

        suggestions = report.get("improvement_suggestions", [])
        print(f"\n  Improvement Suggestions: {len(suggestions)}")
        for s in suggestions:
            print(f"    [{s['priority'].upper()}] {s['area']}")

        print(f"\n  Report saved to: {ALIGNMENT_FILE}")
        print()


# ═════════════════════════════════════════════════════════════════════
# Convenience
# ═════════════════════════════════════════════════════════════════════


def run_alignment() -> dict[str, Any]:
    """Run the full codebase-knowledge alignment analysis."""
    analyzer = CodebaseAlignmentAnalyzer()
    report = analyzer.analyze()
    analyzer.print_report(report)
    return report


if __name__ == "__main__":
    run_alignment()
