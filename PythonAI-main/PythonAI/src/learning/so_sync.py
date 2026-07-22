"""
StackOverflow Sync — Fetch Trending Python Q&A
===============================================

Fetches trending Python questions and accepted answers from the
StackOverflow API and formats them for the PythonAI knowledge base.

Features:
- StackOverflow API v2.3 (keyless with rate limiting)
- Filters by python/python-3.x tags
- Extracts accepted answers only
- Rate limiting to respect API quotas (30 requests/sec keyless)
- Caching to avoid refetching
- Outputs RAG-compatible JSONL

Usage:
    from src.learning.so_sync import sync_stackoverflow, StackOverflowSyncer

    stats = sync_stackoverflow(pages=2)
    print(stats)  # {"fetched": 60, "saved": 55, ...}
"""

from __future__ import annotations

import gzip
import hashlib
import html
import io
import json
import logging
import re
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger("pythonai.learning.so_sync")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_OUTPUT_DIR = _PROJECT_ROOT / "data" / "raw"
_DEFAULT_CACHE_DIR = _PROJECT_ROOT / "data" / "cache"

# StackOverflow API v2.3
_SO_API_BASE = "https://api.stackexchange.com/2.3"
_SO_RATE_LIMIT_DELAY = 1.0  # seconds between requests (conservative for keyless)


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities from SO content."""
    # Decode HTML entities
    text = html.unescape(text)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_code_blocks(html_text: str) -> list[str]:
    """Extract code blocks from SO HTML content."""
    blocks = []
    # SO uses <code> inside <pre> for code blocks
    code_pattern = re.compile(r"<pre[^>]*><code[^>]*>(.*?)</code></pre>", re.DOTALL)
    for match in code_pattern.finditer(html_text):
        code = html.unescape(match.group(1))
        code = re.sub(r"<[^>]+>", "", code)  # Strip any remaining HTML
        blocks.append(code.strip())
    return blocks


def _format_answer(html_body: str) -> str:
    """
    Convert SO HTML answer to clean markdown-like text.

    Preserves code blocks as ```python fenced blocks.
    """
    # Extract code blocks first
    code_blocks = _extract_code_blocks(html_body)

    # Replace code blocks with placeholders
    body = html_body
    placeholder_map: dict[str, str] = {}
    for i, code in enumerate(code_blocks):
        placeholder = f"__CODE_BLOCK_{i}__"
        # Replace the first <pre><code>...</code></pre> occurrence
        body = re.sub(
            r"<pre[^>]*><code[^>]*>.*?</code></pre>",
            placeholder,
            body,
            count=1,
            flags=re.DOTALL,
        )
        placeholder_map[placeholder] = f"```python\n{code}\n```"

    # Convert remaining HTML to text
    body = _strip_html(body)

    # Restore code blocks
    for placeholder, code_md in placeholder_map.items():
        body = body.replace(placeholder, f"\n\n{code_md}\n\n")

    # Clean up extra whitespace
    body = re.sub(r"\n{3,}", "\n\n", body).strip()

    return body


class StackOverflowSyncer:
    """
    Fetches and stores trending Python Q&A from StackOverflow.
    """

    def __init__(
        self,
        output_dir: str | Path | None = None,
        cache_dir: str | Path | None = None,
        api_key: str | None = None,
    ):
        self.output_dir = Path(output_dir) if output_dir else _DEFAULT_OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.cache_dir = Path(cache_dir) if cache_dir else _DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.api_key = api_key  # Optional: increases rate limit
        self._last_request_time = 0.0

        # Load existing hashes for dedup
        self._known_hashes: set[str] = self._load_known_hashes()

    def _load_known_hashes(self) -> set[str]:
        """Load content hashes from existing SO sync files."""
        hashes: set[str] = set()
        cache_file = self.cache_dir / "so_sync_hashes.json"
        if cache_file.exists():
            try:
                with open(cache_file, encoding="utf-8") as f:
                    hashes = set(json.load(f))
            except (json.JSONDecodeError, OSError):
                pass
        return hashes

    def _save_known_hashes(self) -> None:
        """Persist known hashes."""
        cache_file = self.cache_dir / "so_sync_hashes.json"
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(sorted(self._known_hashes), f)
        except OSError as e:
            logger.warning("Failed to save SO hashes: %s", e)

    def _rate_limit(self) -> None:
        """Enforce rate limiting between API calls."""
        elapsed = time.time() - self._last_request_time
        if elapsed < _SO_RATE_LIMIT_DELAY:
            time.sleep(_SO_RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()

    def _api_request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        """
        Make a rate-limited request to the SO API.

        Returns the parsed JSON response.
        """
        self._rate_limit()

        if self.api_key:
            params["key"] = self.api_key

        url = f"{_SO_API_BASE}{endpoint}?{urlencode(params)}"

        headers = {
            "Accept-Encoding": "gzip",
            "User-Agent": "PythonAI/2.1 (Learning Module)",
        }

        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=30) as response:
                # SO API always returns gzip-compressed data
                if response.headers.get("Content-Encoding") == "gzip":
                    buf = io.BytesIO(response.read())
                    with gzip.GzipFile(fileobj=buf) as gz:
                        raw_data = gz.read().decode("utf-8")
                else:
                    raw_data = response.read().decode("utf-8")

                return json.loads(raw_data)

        except HTTPError as e:
            if e.code == 429:
                logger.warning("SO API rate limited. Waiting 60s...")
                time.sleep(60)
                return {"items": [], "has_more": False, "quota_remaining": 0}
            logger.error("SO API error %d: %s", e.code, e.reason)
            return {"items": [], "has_more": False, "quota_remaining": 0}
        except (URLError, TimeoutError) as e:
            logger.error("SO API request failed: %s", e)
            return {"items": [], "has_more": False, "quota_remaining": 0}

    def fetch_questions(
        self,
        pages: int = 1,
        sort: str = "votes",
        min_score: int = 5,
        tags: str = "python",
    ) -> list[dict[str, Any]]:
        """
        Fetch trending Python questions with accepted answers.

        Args:
            pages: Number of pages to fetch (30 questions/page).
            sort: Sort order: 'votes', 'activity', 'creation'.
            min_score: Minimum question score filter.
            tags: Tag filter (semicolon-separated for multiple).

        Returns:
            List of question dicts with answers.
        """
        all_questions: list[dict[str, Any]] = []

        for page in range(1, pages + 1):
            logger.info("Fetching SO questions page %d/%d (sort=%s)", page, pages, sort)

            params = {
                "page": page,
                "pagesize": 30,
                "order": "desc",
                "sort": sort,
                "tagged": tags,
                "filter": "withbody",  # Include question body
                "site": "stackoverflow",
                "min": min_score,
            }

            data = self._api_request("/questions", params)
            items = data.get("items", [])

            if not items:
                logger.info("No more questions on page %d", page)
                break

            # Fetch accepted answers for questions that have them
            questions_with_accepted = [q for q in items if q.get("accepted_answer_id")]

            if questions_with_accepted:
                # Batch fetch answers
                answer_ids = [str(q["accepted_answer_id"]) for q in questions_with_accepted]
                answers = self._fetch_answers(answer_ids)
                answer_map = {a["answer_id"]: a for a in answers}

                for q in questions_with_accepted:
                    answer = answer_map.get(q["accepted_answer_id"])
                    if answer:
                        q["accepted_answer"] = answer

            all_questions.extend(items)

            quota = data.get("quota_remaining", "?")
            logger.info(
                "Fetched %d questions (total: %d, quota remaining: %s)",
                len(items),
                len(all_questions),
                quota,
            )

            if not data.get("has_more", False):
                break

        return all_questions

    def _fetch_answers(self, answer_ids: list[str]) -> list[dict[str, Any]]:
        """Fetch answer bodies by IDs (batch)."""
        if not answer_ids:
            return []

        # SO API allows up to 100 IDs per request
        ids_str = ";".join(answer_ids[:100])
        params = {
            "filter": "withbody",
            "site": "stackoverflow",
        }

        data = self._api_request(f"/answers/{ids_str}", params)
        return data.get("items", [])

    def sync(
        self,
        pages: int = 2,
        sort: str = "votes",
        min_score: int = 5,
    ) -> dict[str, Any]:
        """
        Full sync: fetch, deduplicate, format, and save.

        Returns stats dict.
        """
        stats = {
            "fetched": 0,
            "with_answers": 0,
            "saved": 0,
            "duplicates_skipped": 0,
            "errors": 0,
        }

        questions = self.fetch_questions(pages=pages, sort=sort, min_score=min_score)
        stats["fetched"] = len(questions)

        entries: list[dict[str, Any]] = []

        for q in questions:
            answer_data = q.get("accepted_answer")
            if not answer_data or not answer_data.get("body"):
                continue

            stats["with_answers"] += 1

            # Dedup
            content_hash = hashlib.sha256(f"{q['question_id']}".encode()).hexdigest()[:16]

            if content_hash in self._known_hashes:
                stats["duplicates_skipped"] += 1
                continue

            try:
                title = html.unescape(q.get("title", ""))
                question_body = _strip_html(q.get("body", ""))
                answer_body = _format_answer(answer_data.get("body", ""))

                if not answer_body or len(answer_body) < 30:
                    continue

                entry = {
                    "instruction": title,
                    "input": question_body[:1000] if question_body != title else "",
                    "output": answer_body,
                    "source": "stackoverflow",
                    "category": "qa",
                    "metadata": {
                        "question_id": q["question_id"],
                        "score": q.get("score", 0),
                        "answer_score": answer_data.get("score", 0),
                        "tags": q.get("tags", []),
                        "view_count": q.get("view_count", 0),
                        "link": q.get("link", ""),
                        "content_hash": content_hash,
                    },
                }

                entries.append(entry)
                self._known_hashes.add(content_hash)

            except Exception as e:
                logger.warning("Error processing question %s: %s", q.get("question_id"), e)
                stats["errors"] += 1

        # Write to JSONL
        if entries:
            output_file = self.output_dir / "stackoverflow_sync.jsonl"
            try:
                with open(output_file, "a", encoding="utf-8") as f:
                    for entry in entries:
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                stats["saved"] = len(entries)
                logger.info("Saved %d SO entries to %s", len(entries), output_file.name)
            except OSError as e:
                logger.error("Failed to write SO data: %s", e)
                stats["errors"] += 1

        # Persist hashes
        self._save_known_hashes()

        return stats


def sync_stackoverflow(
    pages: int = 2,
    sort: str = "votes",
    min_score: int = 5,
    api_key: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """
    Convenience function: sync trending Python Q&A from StackOverflow.

    Args:
        pages: Number of pages to fetch per tag (30 Q/page).
        sort: Sort order ('votes', 'activity', 'creation').
        min_score: Minimum question score.
        api_key: Optional SO API key for higher rate limits.
        tags: List of tags to fetch. Defaults to specialized Python tags.

    Returns:
        Stats dict with fetched/saved counts.
    """
    syncer = StackOverflowSyncer(api_key=api_key)

    if not tags:
        tags = ["python", "python-3.x", "python-asyncio", "pandas", "fastapi", "django", "pytest"]

    overall_stats = {
        "fetched": 0,
        "with_answers": 0,
        "saved": 0,
        "duplicates_skipped": 0,
        "errors": 0,
    }

    for tag in tags:
        logger.info(f"Syncing StackOverflow tag: {tag}")
        questions = syncer.fetch_questions(pages=pages, sort=sort, min_score=min_score, tags=tag)
        overall_stats["fetched"] += len(questions)

        entries: list[dict[str, Any]] = []

        for q in questions:
            answer_data = q.get("accepted_answer")
            if not answer_data or not answer_data.get("body"):
                continue

            overall_stats["with_answers"] += 1

            # Dedup
            content_hash = hashlib.sha256(f"{q['question_id']}".encode()).hexdigest()[:16]

            if content_hash in syncer._known_hashes:
                overall_stats["duplicates_skipped"] += 1
                continue

            try:
                title = html.unescape(q.get("title", ""))
                question_body = _strip_html(q.get("body", ""))
                answer_body = _format_answer(answer_data.get("body", ""))

                if not answer_body or len(answer_body) < 30:
                    continue

                entry = {
                    "instruction": title,
                    "input": question_body[:1000] if question_body != title else "",
                    "output": answer_body,
                    "source": "stackoverflow",
                    "category": "qa",
                    "metadata": {
                        "question_id": q["question_id"],
                        "score": q.get("score", 0),
                        "answer_score": answer_data.get("score", 0),
                        "tags": q.get("tags", []),
                        "view_count": q.get("view_count", 0),
                        "link": q.get("link", ""),
                        "content_hash": content_hash,
                        "fetched_tag": tag,
                    },
                }

                entries.append(entry)
                syncer._known_hashes.add(content_hash)

            except Exception as e:
                logger.warning("Error processing question %s: %s", q.get("question_id"), e)
                overall_stats["errors"] += 1

        # Write to JSONL
        if entries:
            output_file = syncer.output_dir / "stackoverflow_sync.jsonl"
            try:
                with open(output_file, "a", encoding="utf-8") as f:
                    for entry in entries:
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                overall_stats["saved"] += len(entries)
                logger.info("Saved %d SO entries for tag '%s'", len(entries), tag)
            except OSError as e:
                logger.error("Failed to write SO data: %s", e)
                overall_stats["errors"] += 1

    # Persist hashes
    syncer._save_known_hashes()

    return overall_stats
