"""
PythonAI Tool — WebFetchTool
==============================
Fetch web page content and extract readable text.
Inspired by Claude Code's WebFetchTool.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from ..tool import (
    InputSchema,
    Parameter,
    ToolResult,
    ToolUseContext,
    ValidationResult,
    build_tool,
)

# User agent to avoid blocks
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _extract_readable_text(html: str) -> str:
    """Extract readable text from HTML."""
    # Remove scripts and styles
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
    html = re.sub(r"<nav[^>]*>.*?</nav>", "", html, flags=re.DOTALL)
    html = re.sub(r"<footer[^>]*>.*?</footer>", "", html, flags=re.DOTALL)
    html = re.sub(r"<header[^>]*>.*?</header>", "", html, flags=re.DOTALL)

    # Replace common block tags with newlines
    for tag in ["</p>", "</div>", "</h[1-6]>", "</li>", "</tr>", "</blockquote>", r"<br\s*/?>"]:
        html = re.sub(tag, "\n", html, flags=re.IGNORECASE)

    # Remove all HTML tags
    text = re.sub(r"<[^>]+>", "", html)

    # Decode common entities
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")
    text = text.replace("&nbsp;", " ")

    # Clean up whitespace
    text = re.sub(r"\n\s*\n", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = text.strip()

    return text


WebFetchTool = build_tool(
    type(
        "WebFetchToolDef",
        (),
        {
            "name": "web_fetch",
            "description": "Fetch and extract readable text content from a URL.",
            "search_hint": "fetch web pages, read URLs, browse",
            "input_schema": InputSchema(
                url=Parameter(
                    type="string",
                    description="The URL to fetch content from",
                    required=True,
                ),
                max_chars=Parameter(
                    type="integer",
                    description="Maximum characters to return (default: 10000)",
                    default=10000,
                ),
            ),
            "is_readonly": True,
            "is_concurrency_safe": True,
            "max_result_size_chars": 50000,
            "call": lambda input_data, context: _fetch_call(input_data, context),
            "validate_input": lambda input_data, context: _fetch_validate(input_data, context),
            "get_activity_description": lambda input_data: (
                f"Fetching {input_data.get('url', '')[:40]}..." if input_data else None
            ),
        },
    )
)


def _fetch_validate(input_data: dict[str, Any], context: ToolUseContext) -> ValidationResult:
    url = input_data.get("url", "")
    if not url:
        return ValidationResult(success=False, message="url is required", error_code=1)

    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ValidationResult(success=False, message=f"Invalid URL: {url}", error_code=2)

    if parsed.scheme not in ("http", "https"):
        return ValidationResult(success=False, message=f"Unsupported scheme: {parsed.scheme}", error_code=3)

    return ValidationResult(success=True)


def _fetch_call(input_data: dict[str, Any], context: ToolUseContext) -> ToolResult:
    url = input_data.get("url", "")
    max_chars = min(input_data.get("max_chars", 10000), 100000)

    try:
        import requests

        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=30,
            allow_redirects=True,
        )
        response.raise_for_status()

        content_type = response.headers.get("content-type", "").lower()

        if "application/json" in content_type:
            text = response.text[:max_chars]
        else:
            text = _extract_readable_text(response.text)[:max_chars]

        return ToolResult(
            data={
                "url": url,
                "status_code": response.status_code,
                "content_type": content_type,
                "content": text,
                "content_length": len(text),
                "headers": dict(response.headers),
            }
        )

    except ImportError:
        return ToolResult(
            data={"error": "requests library not installed. Install with: pip install requests"},
            error="requests library not available",
        )
    except Exception as e:
        return ToolResult(data={"error": f"Failed to fetch {url}: {e}"}, error=f"Failed to fetch {url}: {e}")
