"""
Doc Watcher — Monitor Python Documentation for New Releases
=============================================================

Watches the Python changelog RSS feed for new releases and triggers
re-indexing of updated documentation.

Features:
- Fetches Python changelog RSS from docs.python.org
- Parses RSS/Atom feed for new release entries
- Detects new Python versions
- State tracking (persists last-checked date/version)
- Triggers re-indexing notification

Usage:
    from src.learning.doc_watcher import watch_docs, DocWatcher

    result = watch_docs()
    print(result)  # {"new_releases": [...], "needs_reindex": True, ...}
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree

logger = logging.getLogger("pythonai.learning.doc_watcher")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_STATE_DIR = _PROJECT_ROOT / "data" / "cache"

# Python documentation RSS feeds
_PYTHON_RSS_URLS = [
    "https://docs.python.org/3/whatsnew/changelog.html",
    "https://blog.python.org/feeds/posts/default?alt=rss",
]

# Python release page for version scraping
_PYTHON_DOWNLOADS_URL = "https://www.python.org/downloads/"
_PYTHON_API_URL = "https://www.python.org/api/v2/downloads/release/?limit=10&offset=0&is_published=true"


def _parse_version(version_str: str) -> tuple[int, ...]:
    """Parse a version string into a comparable tuple."""
    parts = re.findall(r"\d+", version_str)
    return tuple(int(p) for p in parts) if parts else (0,)


class DocWatcher:
    """
    Watches Python documentation for new releases.

    Maintains state to track last-checked version and timestamp.
    """

    def __init__(
        self,
        state_dir: str | Path | None = None,
    ):
        self.state_dir = Path(state_dir) if state_dir else _DEFAULT_STATE_DIR
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / "doc_watcher_state.json"
        self._state = self._load_state()

    def _load_state(self) -> dict[str, Any]:
        """Load persisted state."""
        if self.state_file.exists():
            try:
                with open(self.state_file, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

        return {
            "last_checked": None,
            "last_known_version": "3.12.0",
            "known_versions": [],
            "check_count": 0,
        }

    def _save_state(self) -> None:
        """Persist state."""
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2)
        except OSError as e:
            logger.error("Failed to save doc watcher state: %s", e)

    def _fetch_url(self, url: str, timeout: int = 15) -> str | None:
        """Fetch a URL and return its content as string."""
        headers = {
            "User-Agent": "PythonAI/2.1 (DocWatcher)",
            "Accept": "application/rss+xml, application/xml, text/xml, text/html",
        }

        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=timeout) as response:
                return response.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError) as e:
            logger.warning("Failed to fetch %s: %s", url, e)
            return None

    def _fetch_releases_from_api(self) -> list[dict[str, Any]]:
        """Fetch Python releases from the python.org JSON API."""
        releases: list[dict[str, Any]] = []

        content = self._fetch_url(_PYTHON_API_URL)
        if not content:
            return releases

        try:
            data = json.loads(content)
            for release in data.get("results", []):
                name = release.get("name", "")
                version_match = re.search(r"Python\s+([\d.]+\w*)", name)
                if version_match:
                    version = version_match.group(1)
                    releases.append(
                        {
                            "version": version,
                            "name": name,
                            "release_date": release.get("release_date", ""),
                            "is_published": release.get("is_published", True),
                            "url": release.get("resource_uri", ""),
                        }
                    )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to parse Python API response: %s", e)

        return releases

    def _fetch_releases_from_rss(self) -> list[dict[str, Any]]:
        """Fetch Python releases from the blog RSS feed."""
        releases: list[dict[str, Any]] = []

        rss_url = _PYTHON_RSS_URLS[1]  # Blog RSS
        content = self._fetch_url(rss_url)
        if not content:
            return releases

        try:
            root = ElementTree.fromstring(content)

            # Handle both RSS and Atom namespaces

            # Try RSS format
            for item in root.iter("item"):
                title = item.findtext("title", "")
                if "release" in title.lower() or "python" in title.lower():
                    version_match = re.search(r"Python\s+([\d.]+\w*)", title)
                    if version_match:
                        releases.append(
                            {
                                "version": version_match.group(1),
                                "name": title,
                                "release_date": item.findtext("pubDate", ""),
                                "url": item.findtext("link", ""),
                            }
                        )

            # Try Atom format
            for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
                title = entry.findtext("{http://www.w3.org/2005/Atom}title", "")
                if "release" in title.lower() or "python" in title.lower():
                    version_match = re.search(r"Python\s+([\d.]+\w*)", title)
                    if version_match:
                        releases.append(
                            {
                                "version": version_match.group(1),
                                "name": title,
                                "release_date": entry.findtext("{http://www.w3.org/2005/Atom}published", ""),
                                "url": "",
                            }
                        )

        except ElementTree.ParseError as e:
            logger.warning("Failed to parse RSS feed: %s", e)

        return releases

    def check(self) -> dict[str, Any]:
        """
        Check for new Python releases.

        Returns:
            Result dict: {
                new_releases: list of new version dicts,
                needs_reindex: bool,
                latest_version: str,
                last_checked: str,
            }
        """
        logger.info("Checking for new Python versions...")

        result: dict[str, Any] = {
            "new_releases": [],
            "needs_reindex": False,
            "latest_version": self._state.get("last_known_version", "3.12.0"),
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "check_count": self._state.get("check_count", 0) + 1,
            "source": "none",
        }

        # Try API first (more reliable), then RSS fallback
        all_releases: list[dict[str, Any]] = []

        api_releases = self._fetch_releases_from_api()
        if api_releases:
            all_releases.extend(api_releases)
            result["source"] = "api"
        else:
            rss_releases = self._fetch_releases_from_rss()
            if rss_releases:
                all_releases.extend(rss_releases)
                result["source"] = "rss"

        if not all_releases:
            logger.info("No release data available (network may be offline)")
            result["source"] = "offline"
            self._state["last_checked"] = result["last_checked"]
            self._state["check_count"] = result["check_count"]
            self._save_state()
            return result

        # Find new releases
        known_versions = set(self._state.get("known_versions", []))
        last_known_tuple = _parse_version(self._state.get("last_known_version", "3.12.0"))

        new_releases: list[dict[str, Any]] = []
        latest_version = self._state.get("last_known_version", "3.12.0")
        latest_tuple = last_known_tuple

        for release in all_releases:
            version = release["version"]
            version_tuple = _parse_version(version)

            if version not in known_versions:
                if version_tuple > last_known_tuple:
                    new_releases.append(release)
                    logger.info("🆕 New Python release detected: %s", version)

            if version_tuple > latest_tuple:
                latest_tuple = version_tuple
                latest_version = version

            known_versions.add(version)

        # Update result
        result["new_releases"] = new_releases
        result["needs_reindex"] = len(new_releases) > 0
        result["latest_version"] = latest_version

        # Update state
        self._state["last_checked"] = result["last_checked"]
        self._state["last_known_version"] = latest_version
        self._state["known_versions"] = sorted(known_versions)
        self._state["check_count"] = result["check_count"]
        self._save_state()

        if new_releases:
            logger.info(
                "Found %d new Python releases! Latest: %s",
                len(new_releases),
                latest_version,
            )
        else:
            logger.info("No new Python releases. Latest known: %s", latest_version)

        return result

    def get_state(self) -> dict[str, Any]:
        """Get current watcher state."""
        return dict(self._state)


def watch_docs(state_dir: str | Path | None = None) -> dict[str, Any]:
    """
    Check for new Python versions and report.

    Convenience function for quick checks.

    Returns:
        Result dict with new releases and reindex flag.
    """
    watcher = DocWatcher(state_dir=state_dir)
    return watcher.check()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = watch_docs()
    print(json.dumps(result, indent=2))
