"""
OMNISCIENT Layer 1 — API Dataset Generator

Mines Stack Overflow + GitHub for real developer experience,
then enriches with LLM to produce high-quality training pairs.

Strategy:
  Chunks  = Reference Knowledge  (what we know)
  SO/GH   = Real Developer Pain  (what they struggle with)
  LLM     = Synthesis Engine     (connect knowledge to experience)

Usage:
  python -m src.data.api_dataset_gen
  python -m src.data.api_dataset_gen --resume
  python -m src.data.api_dataset_gen --so-only --limit 100
  python -m src.data.api_dataset_gen --github-only --limit 50
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent.parent

# ═══════════════════════════════════════
# PATHS
# ═══════════════════════════════════════
CHUNKS_FILE = ROOT / "data" / "raw" / "raw_chunks_godmode.json"
OUTPUT_FILE = ROOT / "data" / "training" / "api_enriched_dataset.json"
CACHE_DIR = ROOT / "data" / "cache"
SO_CACHE = CACHE_DIR / "so_cache.json"
GH_CACHE = CACHE_DIR / "gh_cache.json"
CKPT_FILE = ROOT / "checkpoints" / "api_gen_checkpoint.json"

CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════
SO_API_BASE = "https://api.stackexchange.com/2.3"
GH_API_BASE = "https://api.github.com"

# Quality thresholds
MIN_SO_SCORE = 10  # Minimum SO answer score
MIN_GH_STARS = 100  # Minimum repo stars
QUALITY_MIN = 60  # Minimum pair quality score
MAX_SO_PER_TOPIC = 5  # Max SO questions per topic
MAX_GH_PER_TOPIC = 3  # Max GitHub snippets per topic

SAVE_EVERY = 100  # Checkpoint every N chunks


# ═══════════════════════════════════════
# KEYWORD EXTRACTION (No LLM needed)
# ═══════════════════════════════════════

# Common Python keywords to ignore during extraction
_STOP_WORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "this",
        "that",
        "with",
        "from",
        "are",
        "was",
        "has",
        "have",
        "been",
        "will",
        "can",
        "not",
        "but",
        "all",
        "also",
        "more",
        "most",
        "some",
        "any",
        "each",
        "every",
        "other",
        "such",
        "only",
        "very",
        "just",
        "about",
        "into",
        "over",
        "after",
        "before",
        "between",
        "through",
        "during",
        "without",
        "python",
        "module",
        "class",
        "function",
        "method",
        "object",
        "type",
        "value",
        "none",
        "true",
        "false",
        "example",
        "using",
        "used",
        "use",
        "note",
        "see",
        "new",
        "like",
        "return",
        "returns",
        "given",
        "provides",
        "available",
        "following",
        "deprecated",
        "since",
        "version",
        "changed",
        "added",
        "removed",
    }
)

# Patterns that indicate important Python entities
_FUNC_PATTERN = re.compile(r"(\w+)\s*\(", re.ASCII)
_CLASS_PATTERN = re.compile(r"class\s+(\w+)", re.ASCII)
_MODULE_PATTERN = re.compile(r"(?:import|from)\s+([\w.]+)", re.ASCII)
_ERROR_PATTERN = re.compile(r"(\w+Error|\w+Exception|\w+Warning)", re.ASCII)
_DUNDER_PATTERN = re.compile(r"(__\w+__)", re.ASCII)


@dataclass
class ChunkKeywords:
    """Keywords extracted from a knowledge chunk."""

    primary_topic: str
    function_names: list[str]
    class_names: list[str]
    module_names: list[str]
    error_types: list[str]
    dunder_methods: list[str]
    concepts: list[str]
    version_specific: str
    search_queries: list[str]  # Pre-built SO/GH search queries


def extract_keywords(chunk: dict[str, Any]) -> ChunkKeywords:
    """Extract searchable keywords from a chunk — pure regex, no LLM."""
    title = chunk.get("title", "")
    text = chunk.get("text", "")[:3000]
    codes = chunk.get("codes", [])
    version = chunk.get("version", "")
    chunk.get("category", "")

    code_text = "\n".join(str(c)[:500] for c in codes[:3]) if codes else ""
    all_text = f"{title}\n{text}\n{code_text}"

    # Extract entities
    func_names = list(set(_FUNC_PATTERN.findall(all_text)))[:10]
    class_names = list(set(_CLASS_PATTERN.findall(all_text)))[:5]
    module_names = list(set(_MODULE_PATTERN.findall(all_text)))[:5]
    error_types = list(set(_ERROR_PATTERN.findall(all_text)))[:5]
    dunder_methods = list(set(_DUNDER_PATTERN.findall(all_text)))[:5]

    # Extract concept words (multi-word phrases)
    words = re.findall(r"[a-z][a-z_]{2,}", title.lower())
    concepts = [w for w in words if w not in _STOP_WORDS][:8]

    # Clean title for primary topic
    primary = re.sub(r"[¶§#*`]", "", title).strip()
    primary = re.sub(r"\s+", " ", primary)[:100]

    # Build search queries
    queries: list[str] = []
    if primary:
        queries.append(f"python {primary}")
    for fn in func_names[:3]:
        if len(fn) > 2 and fn not in {"self", "cls", "args", "kwargs", "None"}:
            queries.append(f"python {fn}")
    for err in error_types[:2]:
        queries.append(f"python {err}")

    return ChunkKeywords(
        primary_topic=primary,
        function_names=[f for f in func_names if len(f) > 2],
        class_names=class_names,
        module_names=module_names,
        error_types=error_types,
        dunder_methods=dunder_methods,
        concepts=concepts,
        version_specific=version,
        search_queries=queries[:6],
    )


# ═══════════════════════════════════════
# STACK OVERFLOW CLIENT
# ═══════════════════════════════════════


class StackOverflowClient:
    """Query Stack Overflow API for real developer Q&As."""

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key or os.environ.get("SO_API_KEY", "")
        self._cache: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._request_count = 0
        self._quota_remaining = 300  # Conservative default
        self._load_cache()

    def _load_cache(self) -> None:
        if SO_CACHE.exists():
            try:
                self._cache = json.loads(SO_CACHE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._cache = {}

    def _save_cache(self) -> None:
        try:
            SO_CACHE.write_text(
                json.dumps(self._cache, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass

    def search(self, query: str, max_results: int = MAX_SO_PER_TOPIC) -> list[dict[str, Any]]:
        """Search SO for Python questions matching query."""
        cache_key = hashlib.md5(f"so:{query}".encode()).hexdigest()

        with self._lock:
            if cache_key in self._cache:
                return self._cache[cache_key]

        if self._quota_remaining <= 5:
            return []

        try:
            import requests

            params: dict[str, Any] = {
                "order": "desc",
                "sort": "votes",
                "tagged": "python",
                "intitle": query[:120],
                "site": "stackoverflow",
                "filter": "withbody",
                "pagesize": min(max_results, 10),
            }
            if self.api_key:
                params["key"] = self.api_key

            r = requests.get(
                f"{SO_API_BASE}/search/advanced",
                params=params,
                timeout=15,
            )

            if r.status_code == 200:
                data = r.json()
                self._quota_remaining = data.get("quota_remaining", 0)
                items = data.get("items", [])

                # Filter by minimum score
                quality_items = [
                    {
                        "title": item.get("title", ""),
                        "question_id": item.get("question_id", 0),
                        "score": item.get("score", 0),
                        "answer_count": item.get("answer_count", 0),
                        "is_answered": item.get("is_answered", False),
                        "tags": item.get("tags", []),
                        "link": item.get("link", ""),
                        "body": _strip_html(item.get("body", ""))[:2000],
                    }
                    for item in items
                    if item.get("score", 0) >= MIN_SO_SCORE and item.get("is_answered", False)
                ][:max_results]

                with self._lock:
                    self._cache[cache_key] = quality_items
                    self._request_count += 1
                    if self._request_count % 50 == 0:
                        self._save_cache()

                return quality_items

            elif r.status_code == 429:
                self._quota_remaining = 0
                return []
            else:
                return []

        except Exception:
            return []

    def fetch_answers(self, question_id: int) -> list[dict[str, Any]]:
        """Fetch accepted/top answers for a question."""
        cache_key = f"so_ans:{question_id}"

        with self._lock:
            if cache_key in self._cache:
                return self._cache[cache_key]

        if self._quota_remaining <= 5:
            return []

        try:
            import requests

            params: dict[str, Any] = {
                "order": "desc",
                "sort": "votes",
                "site": "stackoverflow",
                "filter": "withbody",
                "pagesize": 3,
            }
            if self.api_key:
                params["key"] = self.api_key

            r = requests.get(
                f"{SO_API_BASE}/questions/{question_id}/answers",
                params=params,
                timeout=15,
            )

            if r.status_code == 200:
                data = r.json()
                self._quota_remaining = data.get("quota_remaining", 0)
                items = data.get("items", [])

                answers = [
                    {
                        "answer_id": item.get("answer_id", 0),
                        "score": item.get("score", 0),
                        "is_accepted": item.get("is_accepted", False),
                        "body": _strip_html(item.get("body", ""))[:3000],
                    }
                    for item in items
                    if item.get("score", 0) >= 5
                ][:3]

                with self._lock:
                    self._cache[cache_key] = answers
                    self._request_count += 1

                return answers
            return []
        except Exception:
            return []

    def save(self) -> None:
        self._save_cache()

    @property
    def quota(self) -> int:
        return self._quota_remaining


# ═══════════════════════════════════════
# GITHUB CODE CLIENT
# ═══════════════════════════════════════


class GitHubCodeClient:
    """Search GitHub for real production Python code."""

    def __init__(self, token: str = "") -> None:
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self._cache: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._request_count = 0
        self._load_cache()

    def _load_cache(self) -> None:
        if GH_CACHE.exists():
            try:
                self._cache = json.loads(GH_CACHE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._cache = {}

    def _save_cache(self) -> None:
        try:
            GH_CACHE.write_text(
                json.dumps(self._cache, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass

    def search_code(self, query: str, max_results: int = MAX_GH_PER_TOPIC) -> list[dict[str, Any]]:
        """Search GitHub for Python code matching query."""
        cache_key = hashlib.md5(f"gh:{query}".encode()).hexdigest()

        with self._lock:
            if cache_key in self._cache:
                return self._cache[cache_key]

        try:
            import requests

            headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

            params = {
                "q": f"{query} language:python stars:>{MIN_GH_STARS}",
                "per_page": min(max_results, 10),
                "sort": "indexed",
            }

            r = requests.get(
                f"{GH_API_BASE}/search/code",
                headers=headers,
                params=params,
                timeout=15,
            )

            if r.status_code == 200:
                data = r.json()
                items = data.get("items", [])

                results = [
                    {
                        "name": item.get("name", ""),
                        "path": item.get("path", ""),
                        "repo": item.get("repository", {}).get("full_name", ""),
                        "repo_stars": item.get("repository", {}).get("stargazers_count", 0),
                        "html_url": item.get("html_url", ""),
                        "sha": item.get("sha", ""),
                    }
                    for item in items
                ][:max_results]

                with self._lock:
                    self._cache[cache_key] = results
                    self._request_count += 1
                    if self._request_count % 30 == 0:
                        self._save_cache()

                # Rate limit: GitHub requires 2s between code search requests
                time.sleep(2.5)
                return results

            elif r.status_code == 403:
                # Rate limited
                time.sleep(30)
                return []
            else:
                return []
        except Exception:
            return []

    def fetch_file_content(self, repo: str, path: str) -> str:
        """Fetch raw file content from GitHub."""
        cache_key = f"gh_file:{repo}:{path}"

        with self._lock:
            if cache_key in self._cache:
                return self._cache[cache_key]

        try:
            import requests

            headers: dict[str, str] = {"Accept": "application/vnd.github.raw+json"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

            r = requests.get(
                f"{GH_API_BASE}/repos/{repo}/contents/{path}",
                headers=headers,
                timeout=15,
            )

            if r.status_code == 200:
                content = r.text[:5000]
                with self._lock:
                    self._cache[cache_key] = content
                return content
            return ""
        except Exception:
            return ""

    def save(self) -> None:
        self._save_cache()


# ═══════════════════════════════════════
# HTML STRIPPING
# ═══════════════════════════════════════


def _strip_html(html: str) -> str:
    """Strip HTML tags and decode entities."""
    text = re.sub(r"<code>(.*?)</code>", r"```\1```", html, flags=re.DOTALL)
    text = re.sub(r"<pre>(.*?)</pre>", r"\n```\n\1\n```\n", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#39;", "'", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ═══════════════════════════════════════
# AST VALIDATION
# ═══════════════════════════════════════


def validate_code_ast(code: str) -> bool:
    """Check if a code string is valid Python via AST parsing."""
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


# ═══════════════════════════════════════
# QUALITY SCORING (enhanced)
# ═══════════════════════════════════════


def score_enriched_pair(pair: dict[str, Any]) -> tuple[int, list[str]]:
    """Score an enriched training pair on multiple dimensions."""
    ins = str(pair.get("instruction", ""))
    ans = str(pair.get("output", ""))
    score = 0
    reasons: list[str] = []

    # Instruction quality
    if len(ins) >= 20:
        score += 15
        reasons.append("clear instruction")
    if "?" in ins or ins.lower().startswith(("how", "why", "what", "when", "explain")):
        score += 5
        reasons.append("question format")

    # Answer depth
    if len(ans) >= 200:
        score += 20
        reasons.append("detailed answer")
    elif len(ans) >= 100:
        score += 10

    # Code presence + validation
    code_blocks = re.findall(r"```python\n(.*?)```", ans, re.DOTALL)
    if code_blocks:
        score += 15
        reasons.append("code example")
        if any(validate_code_ast(code) for code in code_blocks):
            score += 10
            reasons.append("valid AST")

    # Reasoning indicators
    if any(tok in ans.lower() for tok in ("step 1", "because", "therefore", "trade-off")):
        score += 10
        reasons.append("reasoning")

    # Practical indicators
    if any(tok in ans.lower() for tok in ("pitfall", "warning", "common mistake", "gotcha")):
        score += 10
        reasons.append("pitfalls")

    # Performance / production indicators
    if any(tok in ans.lower() for tok in ("performance", "optimize", "benchmark", "production")):
        score += 5
        reasons.append("production insight")

    # SO/GitHub enrichment bonus
    if pair.get("_so_score", 0) > 50:
        score += 5
        reasons.append("high-vote SO")
    if pair.get("_gh_stars", 0) > 500:
        score += 5
        reasons.append("popular repo")

    return min(score, 100), reasons


# ═══════════════════════════════════════
# LLM ENRICHMENT (reuse existing infra)
# ═══════════════════════════════════════


def build_enrichment_prompt(
    chunk: dict[str, Any],
    so_data: list[dict[str, Any]],
    gh_data: list[dict[str, Any]],
) -> str:
    """Build LLM prompt combining chunk + SO + GitHub context."""
    title = chunk.get("title", "")
    text = chunk.get("text", "")[:1200]
    codes = chunk.get("codes", [])
    code = str(codes[0])[:300] if codes else ""
    version = chunk.get("version", "")

    parts = [
        "Return ONLY a valid JSON array. No text before or after.\n",
        f"=== OFFICIAL PYTHON DOCUMENTATION (Python {version}) ===",
        f"Topic: {title}",
        text,
    ]

    if code:
        parts.append(f"\nOfficial Example:\n{code}")

    # Add SO context
    if so_data:
        parts.append("\n=== REAL STACK OVERFLOW QUESTIONS (Developer Pain Points) ===")
        for i, so in enumerate(so_data[:3], 1):
            parts.append(f"\nSO Q{i} ({so.get('score', 0)} votes): {so.get('title', '')}")
            body = so.get("body", "")[:500]
            if body:
                parts.append(f"  {body}")

    # Add GitHub context
    if gh_data:
        parts.append("\n=== REAL GITHUB CODE (Production Patterns) ===")
        for i, gh in enumerate(gh_data[:2], 1):
            parts.append(f"\nGH{i}: {gh.get('repo', '')} ({gh.get('repo_stars', 0)}★)")
            parts.append(f"  File: {gh.get('path', '')}")

    parts.append("""

Create 3 high-quality instruction-output training pairs that combine:
1. Official documentation accuracy
2. Real developer pain points from Stack Overflow
3. Production code patterns from GitHub

Each pair MUST include:
- A practical question a real developer would ask
- A detailed answer with working Python code (```python blocks)
- Version notes if behavior differs across Python versions
- At least one pitfall or common mistake

Format:
[{"instruction":"...", "output":"..."}]""")

    return "\n".join(parts)


def build_direct_pairs(
    chunk: dict[str, Any],
    so_data: list[dict[str, Any]],
    gh_data: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build training pairs directly from SO data without LLM (fallback)."""
    pairs: list[dict[str, Any]] = []
    title = chunk.get("title", "")
    version = chunk.get("version", "")
    category = chunk.get("category", "")

    for so in so_data[:3]:
        so_title = so.get("title", "")
        so_body = so.get("body", "")[:2000]
        so_score = so.get("score", 0)

        if not so_title or not so_body:
            continue

        pair = {
            "instruction": f"Solve this Python problem: {so_title}",
            "output": so_body,
            "source": title,
            "category": category,
            "version": version,
            "_type": "so_direct",
            "_so_score": so_score,
            "_enriched": False,
        }
        pairs.append(pair)

    return pairs


# ═══════════════════════════════════════
# DEDUP + CHECKPOINT
# ═══════════════════════════════════════

_seen_hashes: set[str] = set()
_seen_lock = threading.Lock()


def dedup_pair(pair: dict[str, Any]) -> bool:
    """Return True if pair is unique (not seen before)."""
    ins = str(pair.get("instruction", ""))
    out = str(pair.get("output", ""))
    h = hashlib.md5(f"{ins}|{out}".encode()).hexdigest()
    with _seen_lock:
        if h in _seen_hashes:
            return False
        _seen_hashes.add(h)
        return True


def save_checkpoint(pairs: list[dict[str, Any]], chunk_idx: int, stats: dict[str, int]) -> None:
    """Save progress checkpoint."""
    meta = {
        "chunk_index": chunk_idx,
        "total_pairs": len(pairs),
        "stats": dict(stats),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    CKPT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CKPT_FILE.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def load_checkpoint() -> tuple[int, dict[str, int]]:
    """Load checkpoint if exists."""
    if not CKPT_FILE.exists():
        return 0, defaultdict(int)
    try:
        meta = json.loads(CKPT_FILE.read_text(encoding="utf-8"))
        return meta.get("chunk_index", 0), defaultdict(int, meta.get("stats", {}))
    except Exception:
        return 0, defaultdict(int)


# ═══════════════════════════════════════
# MAIN PIPELINE
# ═══════════════════════════════════════


def process_chunk(
    chunk: dict[str, Any],
    so_client: StackOverflowClient,
    gh_client: GitHubCodeClient,
    use_llm: bool = True,
    so_only: bool = False,
    gh_only: bool = False,
) -> list[dict[str, Any]]:
    """Process a single chunk: extract keywords → mine SO/GH → enrich → score."""
    keywords = extract_keywords(chunk)
    if not keywords.search_queries:
        return []

    so_data: list[dict[str, Any]] = []
    gh_data: list[dict[str, Any]] = []

    # Mine Stack Overflow
    if not gh_only:
        for query in keywords.search_queries[:3]:
            results = so_client.search(query, max_results=3)
            for r in results:
                # Fetch top answer
                answers = so_client.fetch_answers(r.get("question_id", 0))
                if answers:
                    r["top_answer"] = answers[0]
                so_data.append(r)
            if so_data:
                break  # Got results, stop querying
            time.sleep(0.5)  # Rate limit

    # Mine GitHub
    if not so_only:
        for query in keywords.search_queries[:2]:
            results = gh_client.search_code(query, max_results=2)
            gh_data.extend(results)
            if gh_data:
                break
            time.sleep(1)

    if not so_data and not gh_data:
        return []

    # Build pairs
    pairs: list[dict[str, Any]] = []
    title = chunk.get("title", "")
    version = chunk.get("version", "")
    category = chunk.get("category", "")

    if use_llm:
        # Try LLM enrichment via existing provider rotation
        try:
            from src.data.generator import call_api, safe_json

            prompt = build_enrichment_prompt(chunk, so_data, gh_data)
            raw_text, api_name = call_api(prompt, max_tokens=1200)
            raw_pairs = safe_json(raw_text)

            for p in raw_pairs:
                if not isinstance(p, dict):
                    continue
                p["source"] = title
                p["category"] = category
                p["version"] = version
                p["_type"] = "api_enriched"
                p["_api"] = api_name
                p["_so_score"] = max((s.get("score", 0) for s in so_data), default=0)
                p["_gh_stars"] = max((g.get("repo_stars", 0) for g in gh_data), default=0)
                p["_enriched"] = True

                score, _ = score_enriched_pair(p)
                if score >= QUALITY_MIN and dedup_pair(p):
                    p["_score"] = score
                    pairs.append(p)
        except Exception:
            pass  # Fall through to direct pairs

    # Fallback: build direct pairs from SO data (no LLM)
    if not pairs:
        direct = build_direct_pairs(chunk, so_data, gh_data)
        for p in direct:
            score, _ = score_enriched_pair(p)
            if score >= 40 and dedup_pair(p):
                p["_score"] = score
                pairs.append(p)

    return pairs


def main(
    resume: bool = False,
    limit: int = 0,
    so_only: bool = False,
    gh_only: bool = False,
    use_llm: bool = True,
    workers: int = 4,
) -> None:
    """Main entry point for API dataset generation."""
    print("\n" + "=" * 65)
    print("  OMNISCIENT Layer 1 — API Dataset Generator")
    print("  SO + GitHub Mining → LLM Enrichment → Quality Gate")
    print("=" * 65)

    # Load chunks
    chunks_file = CHUNKS_FILE if CHUNKS_FILE.exists() else ROOT / "data" / "raw" / "raw_chunks.json"
    if not chunks_file.exists():
        print(f"[ERROR] Chunks file not found: {chunks_file}")
        return

    print(f"\n[Load] Reading: {chunks_file.name}")
    with open(chunks_file, encoding="utf-8") as f:
        chunks = json.load(f)

    skip_types = {"font", "image_png", "image_jpg", "image_gif", "static", "css"}
    valid = [c for c in chunks if c.get("type", "") not in skip_types and len(c.get("text", "")) > 80]

    if limit > 0:
        valid = valid[:limit]

    # Initialize clients
    so_client = StackOverflowClient()
    gh_client = GitHubCodeClient()

    print(f"[OK] Valid chunks: {len(valid):,}")
    print(f"[OK] SO API quota: {so_client.quota}")
    print(f"[OK] SO key: {'set' if so_client.api_key else 'not set (300/day limit)'}")
    print(f"[OK] GH token: {'set' if gh_client.token else 'not set (60/hr limit)'}")
    print(f"[Config] SO only: {so_only} | GH only: {gh_only} | LLM: {use_llm}")

    # Try to setup LLM APIs if needed
    if use_llm:
        try:
            from src.data.generator import active
            from src.data.generator import setup as setup_apis

            if not active:
                setup_apis()
            print(f"[OK] LLM APIs: {len(active)} active")
        except Exception as e:
            print(f"[WARN] LLM APIs not available ({e}), using direct pairs only")
            use_llm = False

    # Resume from checkpoint
    start_idx = 0
    stats: dict[str, int] = defaultdict(int)
    if resume:
        start_idx, stats = load_checkpoint()
        if start_idx > 0:
            print(f"[Resume] Continuing from chunk {start_idx}")

    # Process chunks
    all_pairs: list[dict[str, Any]] = []
    if resume and OUTPUT_FILE.exists():
        try:
            existing = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
            if isinstance(existing, list):
                all_pairs = existing
                for p in all_pairs:
                    dedup_pair(p)  # Mark as seen
                print(f"[Resume] Loaded {len(all_pairs)} existing pairs")
        except Exception:
            pass

    start_time = time.time()
    print(f"\n[Mining] Starting from chunk {start_idx} with {workers} workers...\n")

    # Limit processing if specified
    tasks_to_run = valid[start_idx:]
    if limit > 0:
        tasks_to_run = tasks_to_run[:limit]

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                process_chunk, chunk, so_client, gh_client, use_llm=use_llm, so_only=so_only, gh_only=gh_only
            ): i
            for i, chunk in enumerate(tasks_to_run, start=start_idx)
        }

        pbar = tqdm(as_completed(futures), total=len(futures), desc="Mining")

        for future in pbar:
            i = futures[future]
            try:
                pairs = future.result()
                if pairs:
                    all_pairs.extend(pairs)
                    for p in pairs:
                        stats[p.get("_type", "?")] += 1
            except Exception:
                stats["errors"] += 1

            # Checkpoint
            if (i + 1) % SAVE_EVERY == 0:
                save_checkpoint(all_pairs, i + 1, stats)
                OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
                OUTPUT_FILE.write_text(
                    json.dumps(all_pairs, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                so_client.save()
                gh_client.save()

            pbar.set_postfix(
                {
                    "pairs": f"{len(all_pairs):,}",
                    "quota": so_client.quota,
                }
            )

            # Stop if quota exhausted
            if so_client.quota <= 2 and not gh_only:
                print("\n[STOP] SO API quota exhausted. Resume tomorrow with --resume.")
                # Cancel remaining futures
                for f in futures:
                    f.cancel()
                break

    # Final save
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(all_pairs, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    so_client.save()
    gh_client.save()
    save_checkpoint(all_pairs, len(valid), stats)

    elapsed = (time.time() - start_time) / 60

    print(f"\n{'=' * 65}")
    print("  MINING COMPLETE!")
    print(f"  Total pairs : {len(all_pairs):,}")
    print(f"  Time        : {elapsed:.1f} min")
    print(f"  Output      : {OUTPUT_FILE}")
    print("\n  By type:")
    for t, n in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"    {t:20s}: {n:,}")
    print(f"  SO quota remaining: {so_client.quota}")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OMNISCIENT API Dataset Generator")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of chunks to process")
    parser.add_argument("--so-only", action="store_true", help="Only mine Stack Overflow")
    parser.add_argument("--github-only", action="store_true", help="Only mine GitHub")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM enrichment (direct pairs only)")
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers")
    args = parser.parse_args()

    main(
        resume=args.resume,
        limit=args.limit,
        so_only=args.so_only,
        gh_only=args.github_only,
        use_llm=not args.no_llm,
        workers=args.workers,
    )
