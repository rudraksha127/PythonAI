"""
ForgeAI Crawl4AI Data Collector — AI-Powered Web Scraping
===========================================================
Crawls technical documentation, API reference sites, and developer portals
to build RAG indexable datasets.

Integrates crawl4ai when available, or falls back to httpx + markdown conversion.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

logger = logging.getLogger("forgeai.crawl4ai")

_CRAWLER_AVAILABLE = None


def is_crawl4ai_available() -> bool:
    """Check if crawl4ai is installed and functional."""
    global _CRAWLER_AVAILABLE
    if _CRAWLER_AVAILABLE is not None:
        return _CRAWLER_AVAILABLE

    try:
        import crawl4ai

        _CRAWLER_AVAILABLE = True
        logger.info("Crawl4AI web crawler available")
    except ImportError:
        _CRAWLER_AVAILABLE = False
        logger.debug("crawl4ai package not installed. Using httpx fallback for web scraping.")

    return _CRAWLER_AVAILABLE


async def crawl_url(url: str, extract_markdown: bool = True) -> dict[str, Any]:
    """Crawl a single URL and return content + metadata.

    Args:
        url: Target web page URL.
        extract_markdown: Convert HTML output to clean markdown.
    """
    if is_crawl4ai_available():
        try:
            from crawl4ai import AsyncWebCrawler

            async with AsyncWebCrawler(verbose=False) as crawler:
                result = await crawler.arun(url=url)
                markdown_content = getattr(result, "markdown", "") or getattr(result, "cleaned_html", "")
                return {
                    "url": url,
                    "title": getattr(result, "title", ""),
                    "content": markdown_content,
                    "status_code": getattr(result, "status_code", 200),
                    "backend": "crawl4ai",
                }
        except Exception as e:
            logger.warning(f"Crawl4AI failed for {url} ({e}). Using httpx fallback.")

    # Fallback via httpx
    try:
        import httpx

        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(url, headers={"User-Agent": "ForgeAI-Crawler/1.0"})
            html = resp.text
            title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE)
            title = title_match.group(1) if title_match else url

            # Basic HTML strip to text
            text = re.sub(r"<script[\s\S]*?</script>", "", html)
            text = re.sub(r"<style[\s\S]*?</style>", "", text)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()

            return {
                "url": url,
                "title": title,
                "content": text[:50000],
                "status_code": resp.status_code,
                "backend": "httpx_fallback",
            }
    except Exception as e:
        logger.error(f"Scraping failed for {url}: {e}")
        return {"url": url, "title": "", "content": "", "status_code": 500, "error": str(e), "backend": "failed"}


async def crawl_batch(urls: list[str]) -> list[dict[str, Any]]:
    """Crawl multiple URLs concurrently."""
    tasks = [crawl_url(u) for u in urls]
    return await asyncio.gather(*tasks)
