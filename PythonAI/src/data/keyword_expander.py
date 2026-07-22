"""
keyword_expander.py — Deliberate Knowledge Deepening
=====================================================

Takes a single keyword or phrase and:
1. Auto-detects the topic's domain from a bare keyword
2. Builds a set of questions scaled by a requested "depth"
3. Optionally pulls real context from Stack Overflow and GitHub search
4. Generates answers through the existing provider layer
5. Scores them with the existing QualityPipeline
6. Checkpoints progress so a long run can be resumed

Usage:
    from src.data.keyword_expander import KeywordExpander, ExpansionConfig

    expander = KeywordExpander(ExpansionConfig(keyword="asyncio", depth=3))
    result = expander.run()
    print(f"Generated {result['total_pairs']} Q&A pairs")

    # Resume from checkpoint:
    expander = KeywordExpander(ExpansionConfig(keyword="asyncio", depth=3))
    result = expander.run(resume=True)

CLI:
    python -m src.data.keyword_expander --keyword "asyncio" --depth 3
    python -m src.data.keyword_expander --keyword "docker" --depth 5 --use-web
    python -m src.data.keyword_expander --keyword "cooking" --depth 2   # non-tech test
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("forgeai.keyword_expander")

# ---------------------------------------------------------------------------
# Domain detection — keyword → category mapping
# ---------------------------------------------------------------------------

DOMAIN_SIGNATURES: dict[str, list[str]] = {
    "python": [
        "python", "django", "flask", "fastapi", "pytorch", "numpy", "pandas",
        "asyncio", "celery", "sqlalchemy", "pydantic", "poetry", "pip",
        "virtualenv", "jupyter", "ipython", "pypi", "setuptools",
    ],
    "javascript": [
        "javascript", "node", "react", "vue", "angular", "typescript",
        "express", "nextjs", "nuxt", "svelte", "deno", "bun", "npm", "yarn",
        "webpack", "vite", "eslint", "prettier", "redux", "jquery",
    ],
    "devops": [
        "docker", "kubernetes", "k8s", "terraform", "ansible", "jenkins",
        "gitlab-ci", "github-actions", "helm", "prometheus", "grafana",
        "nginx", "traefik", "argocd", "istio", "vault", "consul",
    ],
    "system_design": [
        "microservices", "load balancing", "caching", "database design",
        "cap theorem", "event sourcing", "cqrs", "distributed systems",
        "message queue", "rabbitmq", "kafka", "redis", "memcached",
    ],
    "ai_ml": [
        "machine learning", "deep learning", "neural network", "transformer",
        "llm", "gpt", "bert", "diffusion", "reinforcement learning",
        "supervised", "unsupervised", "tensorflow", "keras", "scikit-learn",
        "xgboost", "catboost", "nlp", "computer vision", "cnn", "rnn",
    ],
    "databases": [
        "sql", "nosql", "postgresql", "postgres", "mysql", "mongodb",
        "sqlite", "redis", "elasticsearch", "cassandra", "dynamodb",
        "cockroachdb", "clickhouse", "timescaledb", "neo4j",
    ],
    "web_development": [
        "html", "css", "rest", "graphql", "api", "http", "websocket",
        "responsive design", "seo", "accessibility", "a11y", "cors",
    ],
    "mobile": [
        "android", "ios", "swift", "kotlin", "flutter", "react native",
        "xamarin", "mobile development",
    ],
    "security": [
        "security", "encryption", "authentication", "oauth", "jwt",
        "xss", "sql injection", "csrf", "zero trust", "firewall",
        "penetration testing", "owasp",
    ],
    "cloud": [
        "aws", "azure", "gcp", "cloud computing", "serverless", "lambda",
        "ec2", "s3", "cloudformation", "pulumi", "serverless framework",
    ],
    "general_programming": [
        "algorithm", "data structure", "design pattern", "refactoring",
        "clean code", "solid", "tdd", "unit test", "integration test",
        "git", "ci/cd", "debugging", "profiling", "optimization",
    ],
}

# Fallback for topics outside programming
NON_TECHNICAL_INDICATORS: list[str] = [
    "cooking", "baking", "gardening", "painting", "photography", "music",
    "sports", "fitness", "yoga", "meditation", "travel", "history",
    "economics", "philosophy", "psychology", "art", "literature", "poetry",
    "finance", "investing", "marketing", "business",
]

# ---------------------------------------------------------------------------
# Depth-scaled question templates  (1=basic … 5=expert)
# ---------------------------------------------------------------------------

QUESTION_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "python": [
        {"depth": 1, "template": "What is {keyword} in Python and how do you use it?"},
        {"depth": 1, "template": "Write a simple example demonstrating {keyword}."},
        {"depth": 2, "template": "What are the common pitfalls when working with {keyword}?"},
        {"depth": 2, "template": "How does {keyword} compare to alternatives in the Python ecosystem?"},
        {"depth": 3, "template": "Explain how {keyword} works under the hood."},
        {"depth": 3, "template": "Describe a real-world project where {keyword} is the right choice and why."},
        {"depth": 4, "template": "What are the performance characteristics and trade-offs of {keyword} in production systems?"},
        {"depth": 4, "template": "How would you implement a custom extension or plugin for {keyword}?"},
        {"depth": 5, "template": "Analyze {keyword}'s internal architecture: design decisions, edge cases, and how it handles failure scenarios."},
        {"depth": 5, "template": "Compare {keyword}'s approach with three alternatives across 5 dimensions (performance, ergonomics, ecosystem, learning curve, production readiness)."},
    ],
    "javascript": [
        {"depth": 1, "template": "What is {keyword} in JavaScript and how do you use it?"},
        {"depth": 1, "template": "Write a minimal working example of {keyword}."},
        {"depth": 2, "template": "What are common mistakes developers make with {keyword}?"},
        {"depth": 2, "template": "How does {keyword} compare to similar tools or patterns?"},
        {"depth": 3, "template": "Explain the internals of {keyword} and how it interacts with the event loop."},
        {"depth": 4, "template": "What are the performance and memory implications of using {keyword} at scale?"},
        {"depth": 5, "template": "Design a production-grade architecture using {keyword} and justify every decision."},
    ],
    "devops": [
        {"depth": 1, "template": "What is {keyword} and why is it used in DevOps?"},
        {"depth": 1, "template": "Write a basic configuration or setup for {keyword}."},
        {"depth": 2, "template": "What are best practices when using {keyword} in production?"},
        {"depth": 3, "template": "How does {keyword} handle failure scenarios like network partitions or node crashes?"},
        {"depth": 4, "template": "Design a high-availability deployment using {keyword} with disaster recovery."},
        {"depth": 5, "template": "Compare {keyword} with two alternatives across security, scalability, operational cost, and learning curve."},
    ],
    "general_programming": [
        {"depth": 1, "template": "What is {keyword}? Explain it to a beginner."},
        {"depth": 1, "template": "Give a simple code example illustrating {keyword}."},
        {"depth": 2, "template": "What are the trade-offs involved when applying {keyword}?"},
        {"depth": 3, "template": "Explain the theoretical foundation behind {keyword}."},
        {"depth": 4, "template": "Describe an advanced use case where {keyword} solves a non-trivial problem."},
        {"depth": 5, "template": "Critique {keyword}: what are its limitations and when should you avoid it?"},
    ],
    "ai_ml": [
        {"depth": 1, "template": "What is {keyword} in machine learning? Explain simply."},
        {"depth": 2, "template": "How does {keyword} work at a high level? What problem does it solve?"},
        {"depth": 3, "template": "Explain the mathematical formulation behind {keyword}."},
        {"depth": 4, "template": "What are SOTA improvements over {keyword}? How has it evolved?"},
        {"depth": 5, "template": "Implement {keyword} from scratch and explain each component's role."},
    ],
    "non_technical": [
        {"depth": 1, "template": "What is {keyword}? Explain it simply."},
        {"depth": 1, "template": "Give a brief history or origin of {keyword}."},
        {"depth": 2, "template": "What are the key concepts or techniques in {keyword}?"},
        {"depth": 2, "template": "Who are notable figures or works in {keyword}?"},
        {"depth": 3, "template": "How does {keyword} impact everyday life or society?"},
        {"depth": 4, "template": "What are current trends or debates in {keyword}?"},
        {"depth": 5, "template": "Analyze the future of {keyword}: where is the field heading?"},
    ],
}

# Default templates used when domain has no specific templates
DEFAULT_TEMPLATES: list[dict[str, Any]] = [
    {"depth": 1, "template": "What is {keyword}? Provide a clear explanation."},
    {"depth": 1, "template": "Give a practical example of {keyword} in action."},
    {"depth": 2, "template": "What are common challenges when working with {keyword}?"},
    {"depth": 2, "template": "How does {keyword} compare to similar concepts?"},
    {"depth": 3, "template": "Explain the underlying principles of {keyword}."},
    {"depth": 3, "template": "Describe a real-world case study involving {keyword}."},
    {"depth": 4, "template": "What are advanced techniques or patterns related to {keyword}?"},
    {"depth": 5, "template": "Critically analyze the strengths and weaknesses of {keyword}."},
]

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class ExpansionConfig:
    """Configuration for a keyword expansion run."""

    keyword: str
    depth: int = 3
    domain: str = ""  # auto-detected if empty
    use_web_context: bool = False
    max_questions: int = 20
    quality_threshold: float = 0.5
    output_dir: str | Path = field(
        default_factory=lambda: str(Path.home() / ".forgeai" / "keyword_expanded")
    )
    checkpoint_dir: str | Path = field(
        default_factory=lambda: str(Path.home() / ".forgeai" / "checkpoints" / "keyword_expander")
    )
    provider: str = "auto"
    model: str = ""
    max_tokens: int = 512
    temperature: float = 0.6


# ---------------------------------------------------------------------------
# Domain detection
# ---------------------------------------------------------------------------


def detect_domain(keyword: str) -> str:
    """Auto-detect the domain of a keyword by matching against known signatures.

    Returns one of the DOMAIN_SIGNATURES keys, or ``"non_technical"`` if the
    keyword appears in NON_TECHNICAL_INDICATORS, or ``"general_programming"``
    as a final fallback.
    """
    kw_lower = keyword.lower().strip()

    for domain, signatures in DOMAIN_SIGNATURES.items():
        if any(sig in kw_lower or kw_lower in sig for sig in signatures):
            return domain

    if any(indicator in kw_lower for indicator in NON_TECHNICAL_INDICATORS):
        return "non_technical"

    return "general_programming"


# ---------------------------------------------------------------------------
# Question generation
# ---------------------------------------------------------------------------


def generate_questions(
    keyword: str,
    domain: str,
    depth: int,
    max_questions: int = 20,
) -> list[str]:
    """Generate depth-scaled questions for a keyword within a domain.

    Questions are sampled from templates matching the requested depth (and
    shallower depths), shuffled, and capped at ``max_questions``.
    """
    templates = QUESTION_TEMPLATES.get(domain, DEFAULT_TEMPLATES)

    # Collect templates at or below requested depth
    candidates = [t for t in templates if t["depth"] <= depth]
    if not candidates:
        candidates = DEFAULT_TEMPLATES

    # Group by depth and shuffle within each band to preserve progression
    by_depth: dict[int, list[str]] = {}
    for t in candidates:
        q = t["template"].replace("{keyword}", keyword)
        by_depth.setdefault(t["depth"], []).append(q)

    questions: list[str] = []
    for depth_level in sorted(by_depth):
        band = list(by_depth[depth_level])
        random.shuffle(band)
        questions.extend(band)

    return questions[:max_questions]


# ---------------------------------------------------------------------------
# Provider-backed answer generation
# ---------------------------------------------------------------------------

def _call_llm(
    prompt: str,
    max_tokens: int = 512,
    temperature: float = 0.6,
) -> tuple[str, str]:
    """Call an available LLM provider and return ``(response_text, provider_name)``.

    Uses the ProviderRouter for routing, falls back to the round-robin
    approach from ``generator.py`` if the router is unavailable.
    Returns ``("", "none")`` if all providers fail.
    """
    # Strategy 1: try the ProviderRouter
    try:
        from src.core.providers.router import ProviderRouter

        router = ProviderRouter()
        route = router.route(task="coding")

        if route.error is None and route.base_url and route.api_key:
            import requests

            resp = requests.post(
                f"{route.base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {route.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": route.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a technical educator. Provide clear, accurate answers with code examples where appropriate.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                text = resp.json()["choices"][0]["message"]["content"]
                return text, route.provider
    except Exception:
        pass

    # Strategy 2: fall back to generator.py's call_api (round-robin providers)
    try:
        from src.data.generator import call_api

        text, provider = call_api(prompt, max_tokens=max_tokens)
        if text and text != "[]":
            return text, provider
    except Exception:
        pass

    return "", "none"


def _generate_answer_for(
    question: str,
    keyword: str,
    domain: str,
    max_tokens: int = 512,
    temperature: float = 0.6,
) -> dict[str, Any]:
    """Generate an answer for a single question using an LLM provider.

    Returns a dict ready for the quality pipeline.
    """
    system_context = (
        f"You are an expert in {domain}. "
        f"Answer the following question about '{keyword}' thoroughly."
    )

    prompt = (
        f"{system_context}\n\n"
        f"Question: {question}\n\n"
        f"Provide a detailed answer. Include code examples if relevant. "
        f"Be accurate, practical, and well-structured."
    )

    answer_text, provider = _call_llm(prompt, max_tokens, temperature)

    record = {
        "instruction": question,
        "output": answer_text.strip() if answer_text else "",
        "text": f"Question: {question}\n\nAnswer: {answer_text.strip()}" if answer_text else "",
        "metadata": {
            "keyword": keyword,
            "domain": domain,
            "provider": provider,
            "timestamp": time.time(),
            "source": "keyword_expander",
        },
    }

    if not answer_text:
        record["_error"] = "No response from any provider"

    return record


# ---------------------------------------------------------------------------
# Web context enrichment (optional)
# ---------------------------------------------------------------------------


def _fetch_stackoverflow_context(keyword: str) -> str:
    """Fetch top Stack Overflow questions for a keyword."""
    try:
        import urllib.parse
        import urllib.request

        params = urllib.parse.urlencode({
            "order": "desc",
            "sort": "votes",
            "q": keyword,
            "site": "stackoverflow",
        })
        req = urllib.request.Request(
            f"https://api.stackexchange.com/2.3/search?{params}",
            headers={"User-Agent": "ForgeAI/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        items = data.get("items", [])[:5]
        if not items:
            return ""

        context_parts = []
        for item in items:
            title = item.get("title", "")
            tags = ", ".join(item.get("tags", []))
            context_parts.append(f"- {title}  (tags: {tags})")

        return "Related Stack Overflow questions:\n" + "\n".join(context_parts)
    except Exception:
        return ""


def _fetch_github_context(keyword: str) -> str:
    """Fetch top GitHub repositories for a keyword."""
    try:
        import urllib.parse
        import urllib.request

        params = urllib.parse.urlencode({
            "q": keyword,
            "sort": "stars",
            "order": "desc",
            "per_page": 5,
        })
        req = urllib.request.Request(
            f"https://api.github.com/search/repositories?{params}",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "ForgeAI/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        items = data.get("items", [])[:5]
        if not items:
            return ""

        context_parts = []
        for item in items:
            name = item.get("full_name", "")
            stars = item.get("stargazers_count", 0)
            desc = item.get("description", "")
            context_parts.append(f"- {name}  ({stars} stars) — {desc}")

        return "Related GitHub repositories:\n" + "\n".join(context_parts)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Quality scoring
# ---------------------------------------------------------------------------


def score_pairs(
    pairs: list[dict[str, Any]],
    quality_threshold: float = 0.5,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run the QualityPipeline on generated pairs.

    Returns ``(passed_pairs, stats)`` where *passed_pairs* are the records
    whose composite quality score meets the threshold.
    """
    try:
        from src.data.quality import QualityPipeline

        pipeline = QualityPipeline(
            min_text_length=50,
            quality_threshold=quality_threshold,
            text_field="text",
        )
        stats = pipeline.run_records(pairs, dataset_id=f"keyword_{int(time.time())}")

        # Filter records that passed all stages
        passed = [r for r in pairs if r.get("_quality_score", 0) >= quality_threshold]

        # Add quality scores to records that have them
        for r in pairs:
            r.pop("_quality_score", None)
            r.pop("_length_score", None)
            r.pop("_detected_lang", None)
            r.pop("_lang_confidence", None)
            r.pop("_pii_findings", None)
            r.pop("_bp_score", None)
            r.pop("_rep_score", None)

        return passed, stats
    except ImportError:
        # Fallback: simple heuristic scoring
        passed = []
        for pair in pairs:
            text = pair.get("text", "")
            if len(text) >= 100:
                passed.append(pair)

        stats = {
            "total_input": len(pairs),
            "total_output": len(passed),
            "method": "heuristic_fallback",
        }
        return passed, stats


# ---------------------------------------------------------------------------
# Checkpoint support
# ---------------------------------------------------------------------------


def _checkpoint_path(cfg: ExpansionConfig) -> Path:
    return Path(cfg.checkpoint_dir) / f"{cfg.keyword.replace('/', '_')}.ckpt.json"


def _save_checkpoint(
    cfg: ExpansionConfig,
    pairs: list[dict[str, Any]],
    questions_answered: int,
    total_questions: int,
) -> Path:
    """Save progress so a long run can be resumed."""
    ckpt_path = _checkpoint_path(cfg)
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)

    ckpt = {
        "keyword": cfg.keyword,
        "domain": cfg.domain,
        "depth": cfg.depth,
        "questions_answered": questions_answered,
        "total_questions": total_questions,
        "pairs": pairs,
        "timestamp": time.time(),
    }
    ckpt_path.write_text(json.dumps(ckpt, ensure_ascii=False, indent=2), encoding="utf-8")
    return ckpt_path


def _load_checkpoint(cfg: ExpansionConfig) -> dict[str, Any] | None:
    """Load a prior checkpoint, or return ``None``."""
    ckpt_path = _checkpoint_path(cfg)
    if not ckpt_path.exists():
        return None
    try:
        return json.loads(ckpt_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _dedup_new_vs_existing(
    new_pairs: list[dict[str, Any]],
    existing_pairs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove pairs from *new_pairs* whose instruction+output already exist."""
    seen: set[str] = set()
    for p in existing_pairs:
        h = hashlib.md5(
            f"{p.get('instruction', '')}|{p.get('output', '')}".encode()
        ).hexdigest()
        seen.add(h)

    deduped = []
    for p in new_pairs:
        h = hashlib.md5(
            f"{p.get('instruction', '')}|{p.get('output', '')}".encode()
        ).hexdigest()
        if h not in seen:
            seen.add(h)
            deduped.append(p)

    return deduped


# ---------------------------------------------------------------------------
# Main expander class
# ---------------------------------------------------------------------------


class KeywordExpander:
    """Generate a curriculum of Q&A pairs from a single keyword.

    Usage::

        expander = KeywordExpander(ExpansionConfig(keyword="asyncio", depth=3))
        result = expander.run()
        print(result["total_pairs"], "pairs generated")
    """

    def __init__(self, config: ExpansionConfig) -> None:
        self.config = config
        if not config.domain:
            self.config.domain = detect_domain(config.keyword)

    # ── Public API ────────────────────────────────────────────────────

    def run(self, resume: bool = False) -> dict[str, Any]:
        """Execute the full expansion pipeline.

        Steps:
        1. Detect domain (if not already set)
        2. Generate questions at the requested depth
        3. Optionally enrich with web context (Stack Overflow + GitHub)
        4. Generate answers via the provider layer
        5. Score with QualityPipeline
        6. Deduplicate and save output
        7. Save final checkpoint

        Args:
            resume: If ``True``, load prior checkpoint and continue from
                    where the last run left off.

        Returns:
            A dict with keys ``keyword``, ``domain``, ``depth``,
            ``total_questions``, ``total_pairs``, ``passed_pairs``,
            ``quality_stats``, ``output_path``, and ``elapsed_seconds``.
        """
        start = time.time()
        kw = self.config.keyword
        domain = self.config.domain

        logger.info(f"KeywordExpander: keyword='{kw}' domain='{domain}' depth={self.config.depth}")

        # ── Step 1: Load checkpoint if resuming ──────────────
        existing_pairs: list[dict[str, Any]] = []
        questions_answered = 0

        if resume:
            ckpt = _load_checkpoint(self.config)
            if ckpt:
                existing_pairs = ckpt.get("pairs", [])
                questions_answered = ckpt.get("questions_answered", 0)
                logger.info(
                    f"Resumed from checkpoint: {len(existing_pairs)} pairs already generated, "
                    f"{questions_answered}/{ckpt.get('total_questions', '?')} questions answered"
                )

        # ── Step 2: Generate questions ───────────────────────
        all_questions = generate_questions(
            kw, domain, self.config.depth, self.config.max_questions
        )
        total_questions = len(all_questions)
        remaining_questions = all_questions[questions_answered:]

        logger.info(f"Generated {total_questions} questions ({len(remaining_questions)} remaining)")

        if not remaining_questions:
            logger.info("All questions already answered. Skipping generation.")
            return self._build_result(kw, domain, self.config.depth, existing_pairs, start, total_questions)

        # ── Step 3: Optional web context enrichment ──────────
        web_context = ""
        if self.config.use_web_context:
            logger.info("Fetching web context (Stack Overflow + GitHub)...")
            so = _fetch_stackoverflow_context(kw)
            gh = _fetch_github_context(kw)
            web_context = "\n\n".join(part for part in [so, gh] if part)
            if web_context:
                logger.info(f"Got web context: {len(web_context)} chars")

        # ── Step 4: Generate answers ─────────────────────────
        pairs: list[dict[str, Any]] = list(existing_pairs)
        for idx, question in enumerate(remaining_questions):
            logger.info(
                f"Answering [{questions_answered + idx + 1}/{total_questions}]: "
                f"{question[:60]}..."
            )

            record = _generate_answer_for(
                question,
                kw,
                domain,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
            )

            if web_context and record.get("output"):
                # Append web context for richer answers
                record["_web_context"] = web_context
                record["text"] += "\n\n" + web_context

            pairs.append(record)

            # Checkpoint every 5 questions
            if (idx + 1) % 5 == 0:
                _save_checkpoint(
                    self.config, pairs, questions_answered + idx + 1, total_questions
                )
                logger.info(f"Checkpoint saved ({len(pairs)} pairs)")

        # ── Step 5: Quality scoring ──────────────────────────
        logger.info(f"Scoring {len(pairs)} pairs with QualityPipeline...")
        passed_pairs, quality_stats = score_pairs(
            pairs, self.config.quality_threshold
        )

        # ── Step 6: Deduplicate ──────────────────────────────
        # Merge into the shared dataset location if an existing file is present
        output_path = Path(self.config.output_dir) / f"keyword_{kw.replace('/', '_')}.jsonl"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        existing_dataset: list[dict[str, Any]] = []
        if output_path.exists():
            with open(output_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            existing_dataset.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue

        deduped = _dedup_new_vs_existing(passed_pairs, existing_dataset)

        # ── Step 7: Write output ─────────────────────────────
        all_records = existing_dataset + deduped
        with open(output_path, "w", encoding="utf-8") as f:
            for record in all_records:
                # Strip internal keys before writing
                clean = {
                    k: v
                    for k, v in record.items()
                    if not k.startswith("_")
                }
                f.write(json.dumps(clean, ensure_ascii=False) + "\n")

        # Save final checkpoint
        _save_checkpoint(self.config, pairs, total_questions, total_questions)

        elapsed = time.time() - start
        result = self._build_result(
            kw, domain, self.config.depth, passed_pairs, start, total_questions,
            output_path=str(output_path),
            quality_stats=quality_stats,
            deduped_count=len(deduped),
            existing_count=len(existing_dataset),
            total_written=len(all_records),
        )
        result["elapsed_seconds"] = round(elapsed, 1)

        logger.info(
            f"Done: {result['total_pairs']} pairs generated, "
            f"{len(deduped)} new after dedup, "
            f"{result['total_written']} total in {output_path} "
            f"({elapsed:.1f}s)"
        )

        return result

    # ── Internal helpers ────────────────────────────────────────

    @staticmethod
    def _build_result(
        keyword: str,
        domain: str,
        depth: int,
        pairs: list[dict[str, Any]],
        start_time: float,
        total_questions: int,
        output_path: str = "",
        quality_stats: dict[str, Any] | None = None,
        deduped_count: int = 0,
        existing_count: int = 0,
        total_written: int = 0,
    ) -> dict[str, Any]:
        return {
            "keyword": keyword,
            "domain": domain,
            "depth": depth,
            "total_questions": total_questions,
            "total_pairs": len(pairs),
            "passed_pairs": len(pairs),
            "quality_stats": quality_stats or {},
            "output_path": output_path,
            "deduped_new": deduped_count,
            "existing_before": existing_count,
            "total_written": total_written or len(pairs),
            "elapsed_seconds": round(time.time() - start_time, 1),
        }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ForgeAI Keyword Expander — deliberate knowledge deepening")
    parser.add_argument("--keyword", "-k", required=True, help="Keyword or phrase to expand")
    parser.add_argument("--depth", "-d", type=int, default=3, choices=[1, 2, 3, 4, 5], help="Expansion depth (1=basic, 5=expert)")
    parser.add_argument("--domain", default="", help="Override domain auto-detection")
    parser.add_argument("--use-web", action="store_true", help="Fetch Stack Overflow + GitHub context")
    parser.add_argument("--max-questions", type=int, default=20, help="Maximum number of questions to generate")
    parser.add_argument("--quality-threshold", type=float, default=0.5, help="Minimum quality score (0-1)")
    parser.add_argument("--output-dir", default="", help="Output directory for generated JSONL")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    config = ExpansionConfig(
        keyword=args.keyword,
        depth=args.depth,
        domain=args.domain,
        use_web_context=args.use_web,
        max_questions=args.max_questions,
        quality_threshold=args.quality_threshold,
    )
    if args.output_dir:
        config.output_dir = args.output_dir

    expander = KeywordExpander(config)
    result = expander.run(resume=args.resume)

    print(f"\n{'=' * 50}")
    print(f"Keyword:      {args.keyword}")
    print(f"Domain:       {config.domain or '(auto-detected)'}")
    print(f"Depth:        {args.depth}")
    print(f"Questions:    {result['total_questions']}")
    print(f"Pairs passed: {result['total_pairs']}")
    print(f"  - New:      {result.get('deduped_new', result['total_pairs'])}")
    print(f"  - Existing: {result.get('existing_before', 0)}")
    print(f"  - Total:    {result.get('total_written', result['total_pairs'])}")
    print(f"Output:       {result.get('output_path', '(not saved)')}")
    print(f"Time:         {result['elapsed_seconds']}s")
    print(f"{'=' * 50}")
