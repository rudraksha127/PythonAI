"""
zip_doc_ingestor.py — Extract & Chunk Python Official Docs (v2.7–v3.16)
========================================================================
Extracts Python documentation from ZIP archives (HTML and text formats),
parses them intelligently, and outputs structured JSONL chunks ready for
RAG indexing and data amplification.

Supported formats:
  - python-{version}-docs-html.zip   (HTML docs, most versions)
  - python-{version}-docs-text.zip   (Plain-text docs, newer versions)

Output format (per chunk):
  {
    "id":       "py_doc_3.12_library/functions_42",
    "title":    "Python 3.12 - library/functions (Part 1)",
    "version":  "3.12",
    "category": "official_docs",
    "type":     "library" | "tutorial" | "howto" | "reference" | "faq",
    "text":     "...chunked content...",
    "source":   "zip_docs",
    "section":  "library/functions",
    "chunk_idx": 0,
    "total_chunks": 5
  }

Usage:
    python scripts/zip_doc_ingestor.py                    # Full run
    python scripts/zip_doc_ingestor.py --test              # 1 ZIP only
    python scripts/zip_doc_ingestor.py --zip-dir PATH      # Custom ZIP dir
    python scripts/zip_doc_ingestor.py --stats             # Show ZIP stats
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import sys
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

# Fix Windows console encoding for Unicode characters
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ZIP_DIR_DEFAULT = PROJECT_ROOT / "ZIP FILES"
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
TEMP_EXTRACT_DIR = RAW_DATA_DIR / "temp_extracted_docs"
OUTPUT_FILE = RAW_DATA_DIR / "zip_docs_chunks.jsonl"

CHUNK_SIZE = 1000  # Target chars per chunk
CHUNK_OVERLAP = 150  # Overlap between consecutive chunks
MAX_FILE_SIZE = 500_000  # Skip files larger than this (single doc)
MIN_CHUNK_LEN = 80  # Drop chunks shorter than this

console = Console()

# ── Version detection ──────────────────────────────────────────────

# Python versions we expect, in semver order
SUPPORTED_VERSIONS = [
    "2.7",
    "3.0",
    "3.1",
    "3.2",
    "3.3",
    "3.4",
    "3.5",
    "3.6",
    "3.7",
    "3.8",
    "3.9",
    "3.10",
    "3.11",
    "3.12",
    "3.13",
    "3.14",
    "3.15",
    "3.16",
]


def _extract_version(zip_name: str) -> str | None:
    """Extract Python version from a ZIP filename like python-3.12.5-docs-html.zip."""
    m = re.search(r"python-(\d+\.\d+)", zip_name)
    if m:
        ver = m.group(1)
        # Map to the closest supported major.minor
        return ver
    return None


# ── HTML parsing ──────────────────────────────────────────────────


class DocHTMLParser(HTMLParser):
    """Strips HTML tags while preserving code blocks and structure."""

    def __init__(self) -> None:
        super().__init__()
        self.text_parts: list[str] = []
        self.in_code = False
        self.in_script = False
        self.in_style = False
        self.skip_tags = {"script", "style", "nav", "footer", "header"}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.skip_tags:
            if tag == "script":
                self.in_script = True
            elif tag == "style":
                self.in_style = True
            elif tag == "nav":
                self.in_style = True  # treat as skip
            return
        if tag in ("pre", "code"):
            self.in_code = True
        if tag in ("br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
            if self.text_parts and not self.text_parts[-1].endswith("\n"):
                self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.skip_tags:
            self.in_script = False
            self.in_style = False
            return
        if tag in ("pre", "code"):
            self.in_code = False
        if tag in ("p", "li", "div", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
            if self.text_parts and not self.text_parts[-1].endswith("\n"):
                self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.in_script or self.in_style:
            return
        data = data.strip()
        if not data:
            return
        if self.in_code:
            self.text_parts.append(data)
        else:
            self.text_parts.append(data)

    def get_text(self) -> str:
        text = " ".join(self.text_parts)
        # Normalise whitespace
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def clean_html(html_content: str) -> str:
    """Parse HTML to clean text."""
    parser = DocHTMLParser()
    try:
        parser.feed(html_content)
        return parser.get_text()
    except Exception:
        # Fallback: brutal regex tag removal
        text = re.sub(r"<[^>]+>", " ", html_content)
        text = re.sub(r"\s+", " ", text)
        return text.strip()


# ── Chunking ──────────────────────────────────────────────────────


def smart_chunk_text(
    text: str, title_prefix: str = "", chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP
) -> list[str]:
    """
    Split text into overlapping chunks at natural boundaries
    (paragraphs, then sentences) aiming for ~chunk_size chars each.
    """
    if not text:
        return []

    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    safety = 0
    max_chunks = 200

    while start < len(text) and safety < max_chunks:
        safety += 1
        end = min(start + chunk_size, len(text))

        if end < len(text):
            # Look for paragraph break (preferred)
            para = text.rfind("\n\n", start + chunk_size // 2, end)
            if para > start:
                end = para + 2
            else:
                # Look for sentence end
                sent = max(
                    text.rfind(". ", start + chunk_size // 2, end),
                    text.rfind("! ", start + chunk_size // 2, end),
                    text.rfind("? ", start + chunk_size // 2, end),
                    text.rfind("\n", start + chunk_size // 2, end),
                )
                if sent > start:
                    end = sent + 2
                else:
                    # Hard break at chunk_size
                    pass

        chunk = text[start:end].strip()
        # Only keep meaningful chunks
        words = chunk.split()
        if len(words) >= 3:
            chunks.append(chunk)
        start = end - overlap

    return chunks


def _make_chunk_id(version: str, section: str, idx: int) -> str:
    """Deterministic chunk ID."""
    raw = f"zip_docs_{version}_{section}_{idx}"
    return hashlib.md5(raw.encode()).hexdigest()[:24]


def _detect_type(file_rel_path: str) -> str:
    """Detect doc type from relative path inside the ZIP."""
    path_lower = file_rel_path.lower()
    if "/library/" in path_lower:
        return "library"
    if "/tutorial/" in path_lower:
        return "tutorial"
    if "/howto/" in path_lower:
        return "howto"
    if "/reference/" in path_lower:
        return "reference"
    if "/faq/" in path_lower:
        return "faq"
    if "/whatsnew/" in path_lower or "/what's new/" in path_lower:
        return "whatsnew"
    if "/install/" in path_lower:
        return "install"
    if "/distributing/" in path_lower:
        return "distributing"
    if "/extending/" in path_lower:
        return "extending"
    if "/c-api/" in path_lower or path_lower.startswith("c-api/"):
        return "c_api"
    if "/using/" in path_lower:
        return "using"
    return "reference"  # default


def _extract_section(file_rel_path: str) -> str:
    """Extract the section path (e.g. library/functions) from file path."""
    # Drop the version-specific prefix and extension
    parts = file_rel_path.replace("\\", "/").split("/")
    # Filter out irrelevant parts
    relevant = [p for p in parts if p not in ("", ".", "..")]
    # Take last 2 meaningful parts
    if len(relevant) >= 2:
        return "/".join(relevant[-2:]).replace(".html", "").replace(".txt", "")
    return relevant[-1].replace(".html", "").replace(".txt", "") if relevant else "unknown"


# ── Processing individual files ───────────────────────────────────


def process_file_content(content: str, file_rel_path: str, version: str, file_stem: str) -> list[dict[str, Any]]:
    """Parse file content (HTML or text) into chunks."""
    # Detect if it's HTML or plain text
    is_html = bool(re.search(r"<html|<body|<div|<h[1-6]", content[:500]))

    if is_html:
        text = clean_html(content)
    else:
        text = content.strip()

    if len(text) < MIN_CHUNK_LEN:
        return []

    # Truncate absurdly long files
    if len(text) > MAX_FILE_SIZE:
        text = text[:MAX_FILE_SIZE]

    doc_type = _detect_type(file_rel_path)
    section = _extract_section(file_rel_path)
    title = f"Python {version} - {section}"
    title_prefix = f"Python {version} :: {doc_type} :: {section}"

    chunks = smart_chunk_text(text, title_prefix)
    results: list[dict[str, Any]] = []
    total = len(chunks)

    for i, chunk_text in enumerate(chunks):
        if len(chunk_text.strip()) < MIN_CHUNK_LEN:
            continue

        results.append(
            {
                "id": _make_chunk_id(version, section, i),
                "title": f"{title} (Part {i + 1})",
                "version": version,
                "category": "official_docs",
                "type": doc_type,
                "text": chunk_text.strip(),
                "source": "zip_docs",
                "section": section,
                "chunk_idx": i,
                "total_chunks": total,
                "file": file_rel_path,
            }
        )

    return results


# ── Processing a single ZIP archive ───────────────────────────────


def process_zip(zip_path: Path, test_mode: bool = False) -> int:
    """
    Extract a ZIP archive, parse all HTML/TXT files within,
    and append chunks to the master JSONL output file.

    Returns the number of chunks produced.
    """
    match = re.search(r"python-(\d+\.\d+)", zip_path.name)
    if not match:
        console.print(f"[yellow]Skipping {zip_path.name}: could not detect version[/yellow]")
        return 0

    version = match.group(1)
    extract_dir = TEMP_EXTRACT_DIR / f"{zip_path.stem}_{version}"
    extract_dir.mkdir(parents=True, exist_ok=True)

    # Extract
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)
    except zipfile.BadZipFile:
        console.print(f"[red]Bad ZIP: {zip_path.name}[/red]")
        return 0
    except Exception as e:
        console.print(f"[red]Failed to extract {zip_path.name}: {e}[/red]")
        return 0

    # Collect all files
    html_files = sorted(extract_dir.rglob("*.html"))
    txt_files = sorted(extract_dir.rglob("*.txt"))

    # Skip non-doc files (e.g. genindex, search, _sources)
    def is_doc_file(path: Path) -> bool:
        name = path.name.lower()
        return not any(
            skip in name
            for skip in [
                "genindex",
                "search",
                "_sources",
                "py-modindex",
                "objects.inv",
            ]
        )

    html_files = [f for f in html_files if is_doc_file(f)]
    txt_files = [f for f in txt_files if is_doc_file(f)]

    all_files = html_files + txt_files

    if test_mode:
        all_files = all_files[:25]  # Just 25 files for testing

    if not all_files:
        console.print(f"  [yellow]No files found in {zip_path.name}[/yellow]")
        shutil.rmtree(extract_dir, ignore_errors=True)
        return 0

    all_chunks: list[dict[str, Any]] = []

    for file_path in tqdm(all_files, desc=f"v{version}", unit="file", leave=False):
        try:
            rel_path = str(file_path.relative_to(extract_dir))
            content = file_path.read_text(encoding="utf-8", errors="replace")

            chunks = process_file_content(content, rel_path, version, file_path.stem)
            all_chunks.extend(chunks)
        except Exception as e:
            continue  # Skip problematic files silently

    # Append to master JSONL
    if all_chunks:
        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            for chunk in all_chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    # Cleanup temp extraction
    shutil.rmtree(extract_dir, ignore_errors=True)

    return len(all_chunks)


# ── Stats ─────────────────────────────────────────────────────────


def show_zip_stats() -> None:
    """Print statistics about available ZIP files."""
    zip_dir = ZIP_DIR_DEFAULT
    if not zip_dir.exists():
        console.print(f"[red]ZIP directory not found: {zip_dir}[/red]")
        return

    zip_files = sorted(zip_dir.glob("*.zip"))
    if not zip_files:
        console.print("[yellow]No ZIP files found.[/yellow]")
        return

    console.print(f"\n[bold cyan]Python Docs ZIP Archives ({len(zip_files)} files)[/bold cyan]")
    console.print(f"{'─' * 70}")

    total_size = 0
    for zf in zip_files:
        size_mb = zf.stat().st_size / (1024 * 1024)
        ver = _extract_version(zf.name) or "???"
        fmt = "HTML" if "html" in zf.suffix or "html" in zf.name else "Text"
        if zf.stat().st_size < 100:
            console.print(f"  [red]{zf.name:50s} {size_mb:.2f} MB (possibly empty!)[/red]")
        else:
            console.print(f"  {zf.name:50s} {size_mb:6.2f} MB  [v{ver} - {fmt}]")
        total_size += zf.stat().st_size

    console.print(f"{'─' * 70}")
    console.print(f"  Total: {len(zip_files)} files, {total_size / (1024 * 1024):.2f} MB")

    # Also show current output
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, "r") as f:
            num_chunks = sum(1 for _ in f)
        console.print(f"  Output: {OUTPUT_FILE} ({num_chunks:,} chunks indexed)")


# ── Main ──────────────────────────────────────────────────────────


def main(
    zip_dir: str | Path = ZIP_DIR_DEFAULT,
    test_mode: bool = False,
    workers: int = 4,
) -> int:
    """
    Run the full ingestion pipeline.

    Returns total number of chunks produced.
    """
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_EXTRACT_DIR.mkdir(parents=True, exist_ok=True)

    zip_dir_path = Path(zip_dir)
    if not zip_dir_path.exists():
        console.print(f"[red]ZIP directory not found: {zip_dir_path}[/red]")
        return 0

    zip_files = sorted(zip_dir_path.glob("*.zip"))
    # Filter out empty files
    zip_files = [z for z in zip_files if z.stat().st_size > 100]

    if not zip_files:
        console.print(f"[yellow]No valid ZIP files found in {zip_dir_path}[/yellow]")
        return 0

    # Clear old output if it's a fresh run
    if OUTPUT_FILE.exists() and not test_mode:
        OUTPUT_FILE.unlink()
        console.print("[dim]Cleared previous output file[/dim]")

    console.print(f"\n[bold green]Processing {len(zip_files)} ZIP archives...[/bold green]")

    total_chunks = 0
    processed_versions: list[str] = []

    # Sequential processing (one ZIP at a time to manage disk space)
    for zip_path in zip_files:
        ver = _extract_version(zip_path.name) or "???"
        console.print(f"\n[cyan]▶ Processing {zip_path.name} (v{ver})[/cyan]")

        chunks = process_zip(zip_path, test_mode=test_mode)
        total_chunks += chunks
        processed_versions.append(ver)

        console.print(f"  [green]✓ {chunks:,} chunks from v{ver}[/green]")

        if test_mode:
            console.print("[yellow]Test mode: stopping after first ZIP[/yellow]")
            break

    # Summary
    console.print(f"\n[bold green]═══ Ingestion Complete ═══[/bold green]")
    console.print(f"  Versions processed: {', '.join(processed_versions)}")
    console.print(f"  Total chunks:       {total_chunks:,}")
    console.print(f"  Output file:        {OUTPUT_FILE}")
    console.print(f"  Output size:        {OUTPUT_FILE.stat().st_size / (1024 * 1024):.2f} MB")

    return total_chunks


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Extract & chunk Python docs from ZIP archives (v2.7–v3.16)")
    parser.add_argument("--zip-dir", default=str(ZIP_DIR_DEFAULT), help="Directory containing Python docs ZIP files")
    parser.add_argument("--test", action="store_true", help="Test mode: process only 1 ZIP with 25 files")
    parser.add_argument("--stats", action="store_true", help="Show ZIP file stats and exit")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel workers (default: 4)")
    args = parser.parse_args()

    if args.stats:
        show_zip_stats()
    else:
        main(zip_dir=args.zip_dir, test_mode=args.test, workers=args.workers)
