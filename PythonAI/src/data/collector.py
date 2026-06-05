from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm


ROOT = Path(__file__).resolve().parent.parent.parent
os.makedirs(ROOT / "extra_data", exist_ok=True)

CACHE_FILE = ROOT / "extra_data" / "collector_cache.json"


def load_cache() -> dict[str, float]:
    """Load timestamp cache to avoid re-downloading unchanged sources."""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_cache(cache: dict[str, float]) -> None:
    CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def needs_update(source_key: str, cache: dict[str, float], ttl_hours: int = 24) -> bool:
    """Check if a source needs to be re-downloaded based on cache TTL."""
    if source_key not in cache:
        return True
    elapsed = time.time() - cache[source_key]
    return elapsed > ttl_hours * 3600


# ════════════════════════════
# 1. Python PEPs Download
# ════════════════════════════
def get_peps() -> list[dict[str, str]]:
    print("  Downloading Python PEPs...")
    peps: list[dict[str, str]] = []

    for pep_num in tqdm(range(1, 800), desc="PEPs", leave=False):
        try:
            url = f"https://peps.python.org/pep-{pep_num:04d}/"
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                continue

            soup = BeautifulSoup(r.text, "html.parser")
            title = soup.find("h1")
            body = soup.find("section", id="pep-content") or soup.find(
                "div", class_="pep-content"
            )

            if title and body:
                peps.append(
                    {
                        "id": f"pep_{pep_num}",
                        "title": f"PEP {pep_num}: {title.get_text(strip=True)}",
                        "text": body.get_text("\n", strip=True)[:4000],
                        "type": "pep",
                        "category": "enhancement_proposal",
                        "version": "all",
                    }
                )
        except requests.RequestException:
            continue

    print(f"  PEPs downloaded: {len(peps)}")
    return peps


# ════════════════════════════
# 2. Expanded Libraries Docs
# ════════════════════════════
LIBRARIES: dict[str, str] = {
    "numpy": "https://numpy.org/doc/stable/",
    "pandas": "https://pandas.pydata.org/docs/",
    "requests": "https://requests.readthedocs.io/en/latest/",
    "flask": "https://flask.palletsprojects.com/",
    "fastapi": "https://fastapi.tiangolo.com/",
    "sqlalchemy": "https://docs.sqlalchemy.org/",
    "pytest": "https://docs.pytest.org/",
    "pydantic": "https://docs.pydantic.dev/",
    "django": "https://docs.djangoproject.com/en/stable/",
    "matplotlib": "https://matplotlib.org/stable/contents.html",
    "scikit-learn": "https://scikit-learn.org/stable/",
    "click": "https://click.palletsprojects.com/",
    "rich": "https://rich.readthedocs.io/en/stable/",
    "httpx": "https://www.python-httpx.org/",
    "asyncio": "https://docs.python.org/3/library/asyncio.html",
    "pathlib": "https://docs.python.org/3/library/pathlib.html",
    "typing": "https://docs.python.org/3/library/typing.html",
    "dataclasses": "https://docs.python.org/3/library/dataclasses.html",
    "logging": "https://docs.python.org/3/library/logging.html",
    "unittest": "https://docs.python.org/3/library/unittest.html",
}


def get_library_docs() -> list[dict[str, str]]:
    print("  Downloading library docs...")
    lib_chunks: list[dict[str, str]] = []
    cache = load_cache()

    for lib_name, url in tqdm(LIBRARIES.items(), desc="Libraries", leave=False):
        cache_key = f"lib_{lib_name}"
        if not needs_update(cache_key, cache, ttl_hours=48):
            continue

        try:
            r = requests.get(url, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")

            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()

            body = soup.find("main") or soup.find("body")
            if body:
                lib_chunks.append(
                    {
                        "id": f"lib_{lib_name}",
                        "title": f"{lib_name} Documentation",
                        "text": body.get_text("\n", strip=True)[:4000],
                        "type": "library_doc",
                        "category": f"library_{lib_name}",
                        "version": "latest",
                    }
                )
            cache[cache_key] = time.time()
        except requests.RequestException:
            continue

    save_cache(cache)
    print(f"  Library docs: {len(lib_chunks)}")
    return lib_chunks


# ════════════════════════════
# 3. Python Release Notes
# ════════════════════════════
PYTHON_VERSIONS = ["3.10", "3.11", "3.12", "3.13"]


def get_release_notes() -> list[dict[str, str]]:
    print("  Downloading Python release notes...")
    notes: list[dict[str, str]] = []

    for ver in tqdm(PYTHON_VERSIONS, desc="Release notes", leave=False):
        try:
            url = f"https://docs.python.org/3/whatsnew/{ver}.html"
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                continue

            soup = BeautifulSoup(r.text, "html.parser")
            body = soup.find("body")
            if body:
                notes.append(
                    {
                        "id": f"whatsnew_{ver}",
                        "title": f"What's New in Python {ver}",
                        "text": body.get_text("\n", strip=True)[:4000],
                        "type": "release_notes",
                        "category": "release_notes",
                        "version": ver,
                    }
                )
        except requests.RequestException:
            continue

    print(f"  Release notes: {len(notes)}")
    return notes


# ════════════════════════════
# 4. Python Error Patterns
# ════════════════════════════
ERROR_PATTERNS: list[dict[str, str]] = [
    {
        "id": "err_typeerror",
        "title": "TypeError — Common Causes and Fixes",
        "text": "TypeError occurs when operation applied to wrong type.\n"
        "Common causes:\n"
        "1. Concatenating str + int\n"
        "2. Calling non-callable\n"
        "3. Wrong argument types\n"
        "4. NoneType operations\n"
        "Fix: Use type() to check, or try/except with type hints.",
        "type": "error_pattern",
        "category": "debugging",
        "version": "all",
    },
    {
        "id": "err_keyerror",
        "title": "KeyError — Dict Key Not Found",
        "text": "KeyError when accessing dict key that doesn't exist.\n"
        "Fix: Use .get() method or check 'if key in dict'.\n"
        "For nested dicts, use collections.defaultdict.",
        "type": "error_pattern",
        "category": "debugging",
        "version": "all",
    },
    {
        "id": "err_importerror",
        "title": "ImportError and ModuleNotFoundError",
        "text": "ImportError when module can't be found.\n"
        "Fix: pip install, check spelling, verify virtual env is active.\n"
        "Also check for circular imports in your code.",
        "type": "error_pattern",
        "category": "debugging",
        "version": "all",
    },
    {
        "id": "err_attributeerror",
        "title": "AttributeError — Object Has No Attribute",
        "text": "AttributeError when accessing missing attribute.\n"
        "Common causes:\n"
        "1. Typo in attribute name\n"
        "2. Wrong object type (e.g., None has no .append())\n"
        "3. Missing __init__ in class\n"
        "4. Property not decorated with @property",
        "type": "error_pattern",
        "category": "debugging",
        "version": "all",
    },
    {
        "id": "err_indexerror",
        "title": "IndexError and KeyError — Sequence Out of Bounds",
        "text": "IndexError when list index out of range.\n"
        "Fix: Check list length before indexing.\n"
        "Use slicing which handles bounds gracefully.\n"
        "For negative indexing, ensure the list is long enough.",
        "type": "error_pattern",
        "category": "debugging",
        "version": "all",
    },
    {
        "id": "err_performance",
        "title": "Common Python Performance Issues",
        "text": "Performance anti-patterns:\n"
        "1. Using for loop instead of list comprehension\n"
        "2. Repeated .append() in tight loops\n"
        "3. Not using set() for membership tests\n"
        "4. String concatenation with + in loops (use .join())\n"
        "5. Not using local variable bindings in hot loops",
        "type": "error_pattern",
        "category": "performance",
        "version": "all",
    },
]


# ════════════════════════════
# 5. Python Tutorial (docs.python.org/3/tutorial/)
# ════════════════════════════
PYDOC_BASE = "https://docs.python.org/3"


def _crawl_index_page(index_url: str, source_key: str, category: str,
                      link_filter: callable = None) -> list[dict[str, str]]:
    """
    Generic helper: fetch an index page, find all internal links,
    download each sub-page, and return chunks.

    Args:
        index_url: Full URL of the index page.
        source_key: Cache key prefix.
        category: Category tag for each chunk.
        link_filter: Optional function(href) -> bool to filter links.

    Returns:
        List of chunk dicts.
    """
    cache = load_cache()
    chunks: list[dict[str, str]] = []

    try:
        r = requests.get(index_url, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
    except requests.RequestException as e:
        print(f"  [WARN] Failed to fetch index {index_url}: {e}")
        return chunks

    # Find all links on the index page
    links: list[str] = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        # Filter: internal links only (relative or same domain)
        if href.startswith("#") or href.startswith("http"):
            continue
        if link_filter and not link_filter(href):
            continue
        # Resolve relative URL
        if href.startswith("/"):
            full_url = f"https://docs.python.org{href}"
        else:
            full_url = f"{PYDOC_BASE}/{href.lstrip('/')}"
        if full_url not in links:
            links.append(full_url)

    print(f"  Found {len(links)} sub-pages on index")

    for url in tqdm(links, desc=f"  {source_key}", leave=False):
        cache_key = f"{source_key}_{url.split('/')[-1]}"
        if not needs_update(cache_key, cache, ttl_hours=168):
            continue

        try:
            r2 = requests.get(url, timeout=15)
            soup2 = BeautifulSoup(r2.text, "html.parser")

            # Remove navigation / boilerplate
            for tag in soup2(["script", "style", "nav", "footer", ".sphinxsidebar"]):
                tag.decompose()

            title = soup2.find("h1") or soup2.find("title")
            body = soup2.find("div", class_="body") or soup2.find("article") or soup2.find("main") or soup2.find("body")

            if title and body:
                title_text = title.get_text(strip=True)[:120]
                body_text = body.get_text("\n", strip=True)[:4000]

                # Extract code blocks
                codes: list[str] = []
                for pre in body.find_all("pre"):
                    code = pre.get_text(strip=True)
                    if code and len(code) > 20:
                        codes.append(code[:500])

                chunks.append({
                    "id": f"{source_key}_{url.split('/')[-1].replace('.html', '')}",
                    "title": title_text,
                    "text": body_text,
                    "type": "python_doc",
                    "category": category,
                    "version": "3.x",
                    "codes": codes[:5],
                })
            cache[cache_key] = time.time()
        except requests.RequestException:
            continue

    save_cache(cache)
    return chunks


def get_python_tutorial() -> list[dict[str, str]]:
    """Download all pages from the official Python 3 tutorial."""
    print("  Downloading Python Tutorial...")

    def filter_tutorial(href: str) -> bool:
        return href.startswith("tutorial/") and href.endswith(".html")

    return _crawl_index_page(
        f"{PYDOC_BASE}/tutorial/index.html",
        source_key="tutorial",
        category="python_tutorial",
        link_filter=filter_tutorial,
    )


# ════════════════════════════
# 6. Python Library Reference (docs.python.org/3/library/)
# ════════════════════════════
def get_python_library_ref() -> list[dict[str, str]]:
    """Download all module pages from the Python library reference."""
    print("  Downloading Python Library Reference...")

    def filter_library(href: str) -> bool:
        # Only follow library module pages (skip index, genindex, modindex, etc.)
        if not href.startswith("library/"):
            return False
        if not href.endswith(".html"):
            return False
        skip_keywords = ["index", "genindex", "modindex", "search"]
        if any(k in href for k in skip_keywords):
            return False
        return True

    return _crawl_index_page(
        f"{PYDOC_BASE}/library/index.html",
        source_key="libref",
        category="python_library_reference",
        link_filter=filter_library,
    )


# ════════════════════════════
# 7. Python HOWTOs (docs.python.org/3/howto/)
# ════════════════════════════
def get_python_howto() -> list[dict[str, str]]:
    """Download all Python HOWTO guides."""
    print("  Downloading Python HOWTO guides...")

    def filter_howto(href: str) -> bool:
        return href.startswith("howto/") and href.endswith(".html") and "index" not in href

    return _crawl_index_page(
        f"{PYDOC_BASE}/howto/index.html",
        source_key="howto",
        category="python_howto",
        link_filter=filter_howto,
    )


# ════════════════════════════
# 8. Python FAQs (docs.python.org/3/faq/)
# ════════════════════════════
def get_python_faq() -> list[dict[str, str]]:
    """Download all Python FAQ pages."""
    print("  Downloading Python FAQs...")

    def filter_faq(href: str) -> bool:
        return href.startswith("faq/") and href.endswith(".html") and "index" not in href

    return _crawl_index_page(
        f"{PYDOC_BASE}/faq/index.html",
        source_key="faq",
        category="python_faq",
        link_filter=filter_faq,
    )


# ════════════════════════════
# 9. Python Language Reference (docs.python.org/3/reference/)
# ════════════════════════════
def get_python_language_ref() -> list[dict[str, str]]:
    """Download all pages from the Python language reference."""
    print("  Downloading Python Language Reference...")

    def filter_ref(href: str) -> bool:
        return href.startswith("reference/") and href.endswith(".html") and "index" not in href

    return _crawl_index_page(
        f"{PYDOC_BASE}/reference/index.html",
        source_key="langref",
        category="python_language_reference",
        link_filter=filter_ref,
    )


# ════════════════════════════
# 10. Python Glossary (docs.python.org/3/glossary.html)
# ════════════════════════════
def get_python_glossary() -> list[dict[str, str]]:
    """Download the Python glossary page as a single chunk."""
    print("  Downloading Python Glossary...")
    cache = load_cache()

    if not needs_update("glossary", cache, ttl_hours=168):
        print("    (cached)")
        return []

    try:
        url = f"{PYDOC_BASE}/glossary.html"
        r = requests.get(url, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        body = soup.find("div", class_="body") or soup.find("article") or soup.find("body")
        if body:
            cache["glossary"] = time.time()
            save_cache(cache)
            return [{
                "id": "glossary",
                "title": "Python Glossary",
                "text": body.get_text("\n", strip=True)[:4000],
                "type": "python_doc",
                "category": "python_glossary",
                "version": "3.x",
                "codes": [],
            }]
    except requests.RequestException as e:
        print(f"  [WARN] Failed to fetch glossary: {e}")

    return []


# ════════════════════════════
# 5. Main Runner
# ════════════════════════════
def run() -> None:
    raw_path = ROOT / "data" / "raw" / "raw_chunks.json"
    with open(raw_path, encoding="utf-8") as f:
        existing = json.load(f)

    print(f"Existing chunks: {len(existing):,}")
    print("Collecting new data...\n")

    new_data: list[dict[str, str]] = []
    try:
        new_data.extend(get_peps())
        new_data.extend(get_library_docs())
        new_data.extend(get_release_notes())
        new_data.extend(ERROR_PATTERNS)
        # New: comprehensive Python docs
        new_data.extend(get_python_tutorial())
        new_data.extend(get_python_library_ref())
        new_data.extend(get_python_howto())
        new_data.extend(get_python_faq())
        new_data.extend(get_python_language_ref())
        new_data.extend(get_python_glossary())
    except Exception as e:
        print(f"Warning: Collection error: {e}")

    all_data = existing + new_data

    output_path = ROOT / "data" / "raw" / "raw_chunks_godmode.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)

    print(f"\nTotal chunks: {len(all_data):,}")
    print(f"  Original : {len(existing):,}")
    print(f"  Added    : {len(new_data):,}")
    print(f"  Saved    : {output_path}")


if __name__ == "__main__":
    run()
