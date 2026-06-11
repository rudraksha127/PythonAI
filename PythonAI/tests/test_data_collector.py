"""Unit tests for src/data/collector.py — cache, needs_update, error patterns, and crawler."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from src.data.collector import (
    CACHE_FILE,
    ERROR_PATTERNS,
    _crawl_index_page,
    load_cache,
    needs_update,
    save_cache,
)

# ══════════════════════════════════════════════════════════════════════
# load_cache / save_cache
# ══════════════════════════════════════════════════════════════════════


class TestCache:
    """Tests for load_cache and save_cache."""

    def test_load_cache_file_exists(self, tmp_path: Path):
        """load_cache should read existing cache file."""
        cache_data = {"test_key": 1234567890.0}
        cache_file = tmp_path / "collector_cache.json"
        cache_file.write_text(json.dumps(cache_data))

        with patch("src.data.collector.CACHE_FILE", cache_file):
            result = load_cache()
        assert result == cache_data

    def test_load_cache_file_missing(self, tmp_path: Path):
        """load_cache should return empty dict if file doesn't exist."""
        cache_file = tmp_path / "nonexistent.json"
        with patch("src.data.collector.CACHE_FILE", cache_file):
            result = load_cache()
        assert result == {}

    def test_load_cache_corrupted(self, tmp_path: Path):
        """load_cache should return empty dict if file is corrupted."""
        cache_file = tmp_path / "corrupted.json"
        cache_file.write_text("not valid json")

        with patch("src.data.collector.CACHE_FILE", cache_file):
            result = load_cache()
        assert result == {}

    def test_save_cache_writes_file(self, tmp_path: Path):
        """save_cache should write cache data to file."""
        cache_file = tmp_path / "collector_cache.json"
        cache_data = {"key_a": 1000.0, "key_b": 2000.0}

        with patch("src.data.collector.CACHE_FILE", cache_file):
            save_cache(cache_data)

        loaded = json.loads(cache_file.read_text(encoding="utf-8"))
        assert loaded == cache_data

    def test_save_cache_overwrites(self, tmp_path: Path):
        """save_cache should overwrite existing cache file."""
        cache_file = tmp_path / "collector_cache.json"
        cache_file.write_text(json.dumps({"old": 1.0}))

        with patch("src.data.collector.CACHE_FILE", cache_file):
            save_cache({"new": 2.0})

        loaded = json.loads(cache_file.read_text(encoding="utf-8"))
        assert loaded == {"new": 2.0}

    def test_cache_roundtrip(self, tmp_path: Path):
        """Load-modify-save cycle should work correctly."""
        cache_file = tmp_path / "collector_cache.json"
        cache_data = {"existing": time.time()}

        with patch("src.data.collector.CACHE_FILE", cache_file):
            save_cache(cache_data)
            loaded = load_cache()

        assert loaded == cache_data


# ══════════════════════════════════════════════════════════════════════
# needs_update
# ══════════════════════════════════════════════════════════════════════


class TestNeedsUpdate:
    """Tests for needs_update — TTL-based cache expiry."""

    def test_key_not_in_cache(self):
        """Key not in cache should need update."""
        assert needs_update("new_key", {}, ttl_hours=24) is True

    def test_cache_still_valid(self):
        """Recent cache entry should not need update."""
        cache = {"existing": time.time()}  # Just added
        assert needs_update("existing", cache, ttl_hours=24) is False

    def test_cache_expired(self):
        """Old cache entry should need update."""
        cache = {"old": time.time() - 25 * 3600}  # 25 hours ago
        assert needs_update("old", cache, ttl_hours=24) is True

    def test_custom_ttl(self):
        """Custom TTL should be respected."""
        cache = {"key": time.time() - 2 * 3600}  # 2 hours ago
        # 1 hour TTL -> expired
        assert needs_update("key", cache, ttl_hours=1) is True
        # 3 hour TTL -> still valid
        assert needs_update("key", cache, ttl_hours=3) is False

    def test_just_expired(self):
        """Key just past TTL should need update."""
        cache = {"key": time.time() - 24 * 3600 - 1}  # Just past 24h
        assert needs_update("key", cache, ttl_hours=24) is True

    def test_just_valid(self):
        """Key just within TTL should not need update."""
        cache = {"key": time.time() - 24 * 3600 + 1}  # Just within 24h
        assert needs_update("key", cache, ttl_hours=24) is False

    def test_zero_ttl(self):
        """Zero TTL should always need update."""
        cache = {"key": time.time()}
        assert needs_update("key", cache, ttl_hours=0) is True

    def test_negative_ttl(self):
        """Negative TTL should always need update."""
        cache = {"key": time.time()}
        assert needs_update("key", cache, ttl_hours=-1) is True


# ══════════════════════════════════════════════════════════════════════
# ERROR_PATTERNS (static data)
# ══════════════════════════════════════════════════════════════════════


class TestErrorPatterns:
    """Tests for the static ERROR_PATTERNS data."""

    def test_non_empty(self):
        """ERROR_PATTERNS should have at least 4 entries."""
        assert len(ERROR_PATTERNS) >= 4

    def test_all_have_required_keys(self):
        """Every error pattern should have all required fields."""
        required = {"id", "title", "text", "type", "category", "version"}
        for pattern in ERROR_PATTERNS:
            assert required.issubset(pattern.keys()), f"Missing keys in {pattern['id']}"

    def test_all_have_unique_ids(self):
        """All error patterns should have unique IDs."""
        ids = [p["id"] for p in ERROR_PATTERNS]
        assert len(ids) == len(set(ids))

    def test_all_are_error_pattern_type(self):
        """All error patterns should have type 'error_pattern'."""
        for pattern in ERROR_PATTERNS:
            assert pattern["type"] == "error_pattern"

    def test_all_have_version_all(self):
        """All error patterns should have version 'all'."""
        for pattern in ERROR_PATTERNS:
            assert pattern["version"] == "all"

    def test_text_not_empty(self):
        """All error patterns should have non-empty text."""
        for pattern in ERROR_PATTERNS:
            assert len(pattern["text"]) > 0

    def test_categories_are_either_debugging_or_performance(self):
        """Categories should be 'debugging' or 'performance'."""
        for pattern in ERROR_PATTERNS:
            assert pattern["category"] in {"debugging", "performance"}

    def test_titles_are_descriptive(self):
        """All error pattern titles should be at least 15 chars."""
        for pattern in ERROR_PATTERNS:
            assert len(pattern["title"]) >= 15

    def test_performance_pattern_exists(self):
        """At least one pattern should have category 'performance'."""
        assert any(p["category"] == "performance" for p in ERROR_PATTERNS)

    def test_typeerror_pattern_exists(self):
        """There should be a TypeError pattern."""
        assert any("typeerror" in p["id"].lower() for p in ERROR_PATTERNS)


# ══════════════════════════════════════════════════════════════════════
# _crawl_index_page (mocked HTTP)
# ══════════════════════════════════════════════════════════════════════


class TestCrawlIndexPage:
    """Tests for _crawl_index_page with mocked HTTP responses."""

    def _make_mock_html(self, title: str = "Test Page", body_text: str = "Test content") -> str:
        """Create a simple HTML page for mocking."""
        return f"""<html>
        <head><title>{title}</title></head>
        <body>
            <h1>{title}</h1>
            <div class="body">{body_text}</div>
            <pre>brief code</pre>
            <pre>code block with longer content for testing purposes</pre>
        </body>
        </html>"""

    def _make_index_html(self, links: list[str]) -> str:
        """Create an index HTML page with links."""
        link_tags = "\n".join(f'<a href="{link}">{link}</a>' for link in links)
        return f"""<html>
        <body>
            <h1>Index</h1>
            <div class="body">{link_tags}</div>
        </body>
        </html>"""

    @patch("src.data.collector.requests.get")
    @patch("src.data.collector.load_cache")
    def test_empty_index_page(self, mock_load_cache, mock_get):
        """Index page with no links should return empty."""
        mock_load_cache.return_value = {}
        mock_response = MagicMock()
        mock_response.text = "<html><body><h1>Empty</h1></body></html>"
        mock_get.return_value = mock_response

        result = _crawl_index_page(
            "https://docs.python.org/3/test/index.html",
            source_key="test",
            category="test_cat",
        )
        assert result == []

    @patch("src.data.collector.requests.get")
    @patch("src.data.collector.load_cache")
    def test_crawls_sub_pages(self, mock_load_cache, mock_get):
        """Should crawl each link on the index page."""
        mock_load_cache.return_value = {}

        # First call: fetch index page
        index_html = self._make_index_html(["tutorial/appetite.html"])
        # Second call: fetch the sub-page
        sub_html = self._make_mock_html("Appetite", "Real Python content here")

        mock_get.side_effect = [
            MagicMock(text=index_html),   # Index page
            MagicMock(text=sub_html),      # Sub page
        ]

        with patch("src.data.collector.save_cache"):
            result = _crawl_index_page(
                "https://docs.python.org/3/tutorial/index.html",
                source_key="tutorial",
                category="python_tutorial",
            )

        assert len(result) == 1
        assert result[0]["title"] == "Appetite"
        assert "Real Python content here" in result[0]["text"]
        assert result[0]["type"] == "python_doc"
        assert result[0]["category"] == "python_tutorial"
        assert result[0]["version"] == "3.x"

    @patch("src.data.collector.requests.get")
    @patch("src.data.collector.load_cache")
    def test_uses_cached_pages(self, mock_load_cache, mock_get):
        """Sub-pages in cache should not be re-downloaded."""
        now = time.time()
        mock_load_cache.return_value = {"tutorial_appetite.html": now}

        index_html = self._make_index_html(["tutorial/appetite.html"])
        mock_get.return_value = MagicMock(text=index_html)

        with patch("src.data.collector.save_cache"):
            result = _crawl_index_page(
                "https://docs.python.org/3/tutorial/index.html",
                source_key="tutorial",
                category="python_tutorial",
            )

        # Should NOT have made a second HTTP call (cached)
        assert mock_get.call_count == 1
        assert result == []

    @patch("src.data.collector.requests.get")
    @patch("src.data.collector.load_cache")
    def test_filters_links(self, mock_load_cache, mock_get):
        """link_filter should exclude non-matching links."""
        mock_load_cache.return_value = {}

        index_html = self._make_index_html([
            "tutorial/appetite.html",
            "http://external.com/",
            "#anchor",
        ])
        # index call succeeds; no sub-pages pass the filter that also need to be fetched
        mock_get.return_value = MagicMock(text=index_html)

        with patch("src.data.collector.save_cache"):
            result = _crawl_index_page(
                "https://docs.python.org/3/tutorial/index.html",
                source_key="tutorial",
                category="python_tutorial",
                link_filter=lambda href: href.startswith("tutorial/") and href.endswith(".html"),
            )

        # Only 1 link (tutorial/appetite.html) passes BOTH the internal-link check
        # AND the custom filter. The external and anchor links are filtered out
        # by the internal-link check before the custom filter runs.
        # But since there's only 1 sub-page to download, we verify the index was fetched
        # and the result should have just the sub-page
        assert len(result) == 1

    @patch("src.data.collector.requests.get")
    @patch("src.data.collector.load_cache")
    def test_request_exception_handled(self, mock_load_cache, mock_get):
        """RequestExceptions during crawl should be handled gracefully."""
        mock_load_cache.return_value = {}

        index_html = self._make_index_html(["tutorial/appetite.html"])
        mock_get.side_effect = [
            MagicMock(text=index_html),   # Index succeeds
            requests.exceptions.ConnectionError("Connection error"),  # Sub-page fails
        ]

        with patch("src.data.collector.save_cache"):
            result = _crawl_index_page(
                "https://docs.python.org/3/tutorial/index.html",
                source_key="tutorial",
                category="python_tutorial",
            )

        # Should return empty since the sub-page failed
        assert result == []

    @patch("src.data.collector.requests.get")
    @patch("src.data.collector.load_cache")
    def test_index_fetch_failure(self, mock_load_cache, mock_get):
        """If index fetch fails, should return empty."""
        mock_load_cache.return_value = {}
        mock_get.side_effect = requests.exceptions.ConnectionError("Index fetch failed")

        result = _crawl_index_page(
            "https://docs.python.org/3/tutorial/index.html",
            source_key="tutorial",
            category="python_tutorial",
        )

        assert result == []

    @patch("src.data.collector.requests.get")
    @patch("src.data.collector.load_cache")
    def test_code_blocks_extracted(self, mock_load_cache, mock_get):
        """Pre/code blocks should be extracted from sub-pages."""
        mock_load_cache.return_value = {}

        index_html = self._make_index_html(["tutorial/code.html"])
        sub_html = """<html><body>
        <h1>Code Examples</h1>
        <div class="body">
            <p>Here is some code:</p>
            <pre>def multiply(a, b): return a * b</pre>
            <pre>for i in range(10): print(i ** 2)</pre>
        </div>
        </body></html>"""

        mock_get.side_effect = [
            MagicMock(text=index_html),
            MagicMock(text=sub_html),
        ]

        with patch("src.data.collector.save_cache"):
            result = _crawl_index_page(
                "https://docs.python.org/3/tutorial/index.html",
                source_key="tutorial",
                category="python_tutorial",
            )

        assert len(result) == 1
        assert len(result[0].get("codes", [])) >= 1
        assert any("multiply" in c for c in result[0]["codes"])

    @patch("src.data.collector.requests.get")
    @patch("src.data.collector.load_cache")
    def test_multiple_sub_pages(self, mock_load_cache, mock_get):
        """Multiple sub-pages should all be crawled."""
        mock_load_cache.return_value = {}

        index_html = self._make_index_html([
            "tutorial/page1.html",
            "tutorial/page2.html",
        ])
        page1_html = self._make_mock_html("Page 1", "Content 1")
        page2_html = self._make_mock_html("Page 2", "Content 2")

        mock_get.side_effect = [
            MagicMock(text=index_html),
            MagicMock(text=page1_html),
            MagicMock(text=page2_html),
        ]

        with patch("src.data.collector.save_cache"):
            result = _crawl_index_page(
                "https://docs.python.org/3/tutorial/index.html",
                source_key="tutorial",
                category="python_tutorial",
            )

        assert len(result) == 2
        titles = [r["title"] for r in result]
        assert "Page 1" in titles
        assert "Page 2" in titles


# ══════════════════════════════════════════════════════════════════════
# CACHE_FILE path verification
# ══════════════════════════════════════════════════════════════════════


class TestCacheFilePath:
    """Tests for CACHE_FILE constant."""

    def test_cache_file_is_json(self):
        """CACHE_FILE should be a .json path."""
        assert str(CACHE_FILE).endswith(".json")

    def test_cache_file_name(self):
        """CACHE_FILE should be named collector_cache.json."""
        assert CACHE_FILE.name == "collector_cache.json"
