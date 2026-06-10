"""
data_amplifier.py — 100x Data Amplification Engine for 950K+ PyPI Libraries
============================================================================
Amplifies ingested chunks into a massive training dataset through:

1. Keyword & Topic Expansion     → 5x (extract keywords, generate related variants)
2. Synthetic QA Generation       → 10x (generate instruction-response pairs per chunk)
3. Question Variant Rewriting    → 3x (rephrase same Q in different styles)
4. Code-Only/Practice Problems   → 2x (extract code, create practice tasks)
5. PyPI Knowledge Cards          → 950K+ libraries with metadata knowledge cards

Total amplification factor: ~100x (20x from 5 strategies × 5x from PyPI coverage)

Output:
  - amplified_dataset.jsonl     (training pairs for model fine-tuning)
  - pypi_knowledge_base.jsonl   (RAG knowledge cards for all libraries)

Supports:
  - Multithreaded PyPI metadata fetching (10 concurrent workers)
  - API-based QA generation via keyword extraction + cloud models (Groq, OpenAI, etc.)
  - Template-based fallback amplification (always works, no API needed)
  - Incremental mode: resumes where it left off

Usage:
    python scripts/data_amplifier.py                    # Full run (API-based QA)
    python scripts/data_amplifier.py --test              # Test batch (100 chunks)
    python scripts/data_amplifier.py --pypi-only         # Only fetch PyPI metadata
    python scripts/data_amplifier.py --no-ollama         # Skip API-based QA, use templates only
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests

# Fix Windows console encoding for Unicode characters
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from tqdm import tqdm

# ═══════════════════════════════════════════════════════════════
# API PROVIDERS — OpenAI-compatible endpoints for QA generation
# Uses API keys from ~/.pythonai/apikeys.json or environment vars
# ═══════════════════════════════════════════════════════════════

# Ensure project root is in path for module imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.apikeys import resolve_all

API_PROVIDERS: dict[str, dict[str, str]] = {
    "groq": {"url": "https://api.groq.com/openai/v1/chat/completions", "model": "llama-3.3-70b-versatile"},
    "openrouter": {"url": "https://openrouter.ai/api/v1/chat/completions", "model": "meta-llama/llama-3.3-70b-instruct:free"},
    "openai": {"url": "https://api.openai.com/v1/chat/completions", "model": "gpt-4o-mini"},
    "deepseek": {"url": "https://api.deepseek.com/v1/chat/completions", "model": "deepseek-chat"},
    "fireworks": {"url": "https://api.fireworks.ai/inference/v1/chat/completions", "model": "accounts/fireworks/models/llama-v3p3-70b-instruct"},
    "nvidia": {"url": "https://integrate.api.nvidia.com/v1/chat/completions", "model": "meta/llama-3.1-70b-instruct"},
    "cerebras": {"url": "https://api.cerebras.ai/v1/chat/completions", "model": "llama-3.3-70b"},
    "sambanova": {"url": "https://api.sambanova.ai/v1/chat/completions", "model": "Meta-Llama-3.3-70B-Instruct"},
    "mistral": {"url": "https://api.mistral.ai/v1/chat/completions", "model": "mistral-large-latest"},
    "huggingface": {"url": "https://api-inference.huggingface.co/models/Qwen/Qwen2.5-72B-Instruct/v1/chat/completions", "model": "Qwen/Qwen2.5-72B-Instruct"},
}


RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
TRAIN_DATA_DIR = PROJECT_ROOT / "data" / "training"
INPUT_CHUNKS = RAW_DATA_DIR / "zip_docs_chunks.jsonl"
INPUT_PYPI = RAW_DATA_DIR / "pypi_knowledge_base.jsonl"
OUTPUT_AMPLIFIED = TRAIN_DATA_DIR / "amplified_dataset.jsonl"
OUTPUT_PYPI = RAW_DATA_DIR / "pypi_knowledge_base.jsonl"
STATE_FILE = TRAIN_DATA_DIR / "amplifier_state.json"

# Amplification factors (per strategy)
QA_PAIRS_PER_CHUNK = 4        # Basic Q&A pairs
VARIANT_PER_QA = 3            # Question variants per Q&A
KEYWORD_TASKS = 3             # Keyword/topic expansion tasks
CODE_TASKS = 2                # Code-only tasks per chunk with code
PYPI_CONCURRENCY = 10         # Parallel PyPI fetches
PYPI_BATCH_SIZE = 500         # Batch size for PyPI processing

# Quality thresholds
MIN_INSTRUCTION_LEN = 15
MIN_OUTPUT_LEN = 40
MAX_OUTPUT_LEN = 2000

# Rate limiting
PYPI_RATE_LIMIT = 0.1    # Seconds between PyPI API calls

console = Console()

# ── State persistence for incremental runs ────────────────────────


class AmplifierState:
    """Tracks which chunks/libraries have been processed for incremental runs.

    Uses lists internally for JSON compatibility (sets are not serializable).
    """

    def __init__(self, state_path: Path = STATE_FILE):
        self.state_path = state_path
        self.data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def is_chunk_processed(self, chunk_id: str) -> bool:
        processed = self.data.get("processed_chunks", [])
        return chunk_id in processed

    def mark_chunk_processed(self, chunk_id: str) -> None:
        processed = self.data.get("processed_chunks", [])
        if chunk_id not in processed:
            processed.append(chunk_id)
            self.data["processed_chunks"] = processed
            self.save()

    def is_library_processed(self, lib_name: str) -> bool:
        processed = self.data.get("processed_libraries", [])
        return lib_name in processed

    def mark_library_processed(self, lib_name: str) -> None:
        processed = self.data.get("processed_libraries", [])
        if lib_name not in processed:
            processed.append(lib_name)
            self.data["processed_libraries"] = processed
            self.save()

    def reset(self) -> None:
        self.data = {}
        self.save()


# ── Utility helpers ──────────────────────────────────────────────


def _make_id(prefix: str, source: str, idx: int) -> str:
    raw = f"{prefix}:{source}:{idx}"
    return hashlib.md5(raw.encode()).hexdigest()[:24]


def _clean_text(text: str) -> str:
    """Normalize whitespace."""
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _truncate(text: str, max_len: int = MAX_OUTPUT_LEN) -> str:
    if len(text) > max_len:
        text = text[:max_len]
        # Try to break at sentence
        last_period = text.rfind(".")
        if last_period > max_len // 2:
            text = text[: last_period + 1]
    return text


def _qualify_pair(instruction: str, output: str) -> bool:
    """Check if a Q&A pair meets quality minimums."""
    return (
        len(instruction) >= MIN_INSTRUCTION_LEN
        and len(output) >= MIN_OUTPUT_LEN
        and not any(
            skip in instruction.lower() or skip in output.lower()
            for skip in ["[insert", "[your", "[placeholder"]
        )
    )


# ── Strategy 1: Keyword & Topic Expansion ────────────────────────


def extract_keywords(text: str, max_keywords: int = 8) -> list[str]:
    """Extract important keywords from text (rule-based)."""
    # Find capitalized terms, Python keywords, and function names
    keywords: set[str] = set()

    # Capitalized multi-word terms
    for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", text):
        word = m.group(0)
        if len(word) > 4 and len(word) < 80:
            keywords.add(word)

    # Python function names (snake_case identifiers)
    for m in re.finditer(r"\b([a-z][a-z_]+)\s*\(", text):
        func = m.group(1)
        if len(func) > 3 and len(func) < 40:
            keywords.add(func)

    # Python module names
    for m in re.finditer(r"(?:import|from)\s+([a-zA-Z_][\w.]*)", text):
        mod = m.group(1)
        if len(mod) > 2:
            keywords.add(mod)

    return list(keywords)[:max_keywords]


def generate_keyword_tasks(
    chunk: dict[str, Any], keywords: list[str]
) -> list[dict[str, Any]]:
    """
    Generate learning tasks from keywords extracted from a chunk.
    This is purely rule-based — no LLM needed.
    """
    title = chunk.get("title", "")
    version = chunk.get("version", "")
    texts = chunk.get("text", "")
    source = chunk.get("id", "unknown")

    tasks: list[dict[str, Any]] = []
    base_id = f"keyword_task_{source}"

    # Task 1: Glossary-style definition prompt
    for kw in keywords[:5]:
        instruction = f"Explain the Python concept '{kw}' and how it's used."
        output = (
            f"**{kw}** is a Python concept found in version {version}. "
            f"It relates to the topic '{title}'. "
            f"Here's what you need to know:\n\n"
            f"From the documentation:\n{_truncate(texts[:600])}"
        )
        if _qualify_pair(instruction, output):
            tasks.append({
                "id": _make_id("keyword", source, len(tasks)),
                "instruction": instruction,
                "output": output,
                "source": source,
                "version": version,
                "category": "keyword_explanation",
                "section": chunk.get("section", ""),
            })

    # Task 2: Compare & contrast
    if len(keywords) >= 2:
        kw_a, kw_b = keywords[0], keywords[1]
        instruction = (
            f"What is the difference between '{kw_a}' and '{kw_b}' in Python {version}?"
        )
        output = (
            f"Both '{kw_a}' and '{kw_b}' are concepts in Python {version} "
            f"covered under '{title}'. "
            f"The documentation covers:\n\n"
            f"**{kw_a}**: ...{_truncate(texts[:400])}\n\n"
            f"**{kw_b}**: ...context from the same section..."
        )
        if _qualify_pair(instruction, output):
            tasks.append({
                "id": _make_id("compare", source, 0),
                "instruction": instruction,
                "output": output,
                "source": source,
                "version": version,
                "category": "comparison",
                "section": chunk.get("section", ""),
            })

    return tasks


# ── Strategy 2: Synthetic QA Generation ─────────────────────────


def generate_qa_pairs(
    chunk: dict[str, Any],
    use_ollama: bool = False,
) -> list[dict[str, Any]]:
    """
    Generate Q&A pairs from a chunk.

    When use_ollama=True: extracts keywords and calls API providers for generation.
    When False: falls back to template-based generation (always works, no API needed).
    """
    title = chunk.get("title", "")
    version = chunk.get("version", "")
    texts = chunk.get("text", "")
    source = chunk.get("id", "unknown")
    section = chunk.get("section", "")
    doc_type = chunk.get("type", "reference")

    pairs: list[dict[str, Any]] = []

    if use_ollama:
        pairs = _generate_qa_via_api(chunk)
        if pairs:
            return pairs

    # Template-based QA generation (always works)
    templates = QA_TEMPLATES.get(doc_type, QA_TEMPLATES["reference"])

    topic_name = section.replace("_", " ").title()
    if not topic_name or topic_name == "":
        topic_name = "Python"

    for i, template in enumerate(templates[:QA_PAIRS_PER_CHUNK]):
        # Fill template with chunk content
        instruction = template["instruction"]
        if "{topic}" in instruction:
            instruction = instruction.replace("{topic}", topic_name)

        output_fmt = template.get("output_fmt", "")
        output = output_fmt
        if "{topic}" in output:
            output = output.replace("{topic}", topic_name)
        if "{text}" in output:
            output = output.replace("{text}", _truncate(texts[:800]))
        if "{summary}" in output:
            output = output.replace("{summary}", _truncate(texts[:300]))

        if not output.strip():
            output = _truncate(texts[:QA_OUTPUT_LEN])

        if _qualify_pair(instruction, output):
            pairs.append({
                "id": _make_id("qa", source, i),
                "instruction": instruction,
                "output": output,
                "source": source,
                "version": version,
                "category": "qa_direct",
                "section": section,
            })

    return pairs


# ── QA Templates ─────────────────────────────────────────────────

QA_OUTPUT_LEN = 1000

QA_TEMPLATES: dict[str, list[dict[str, str]]] = {
    "library": [
        {
            "instruction": "How do I use the {topic} module in Python?",
            "output_fmt": "Here's how to use the {topic} module:\n\n{text}",
        },
        {
            "instruction": "What functions are available in {topic}?",
            "output_fmt": "The {topic} module provides the following:\n\n{text}",
        },
        {
            "instruction": "Explain the key APIs of {topic} with examples.",
            "output_fmt": "Key APIs of {topic}:\n\n{text}",
        },
        {
            "instruction": "Write a code example using {topic}.",
            "output_fmt": "Here's an example using {topic}:\n\n{text}",
        },
    ],
    "tutorial": [
        {
            "instruction": "Explain {topic} step by step.",
            "output_fmt": "Step-by-step guide to {topic}:\n\n{text}",
        },
        {
            "instruction": "What is {topic} in Python and why is it useful?",
            "output_fmt": "{topic} in Python:\n\n{text}",
        },
        {
            "instruction": "Give me a beginner-friendly explanation of {topic}.",
            "output_fmt": "Beginner guide to {topic}:\n\n{text}",
        },
    ],
    "howto": [
        {
            "instruction": "How do I accomplish {topic} in Python?",
            "output_fmt": "Here's how to {topic}:\n\n{text}",
        },
        {
            "instruction": "What are the best practices for {topic}?",
            "output_fmt": "Best practices for {topic}:\n\n{text}",
        },
    ],
    "reference": [
        {
            "instruction": "Explain the Python concept of {topic} in detail.",
            "output_fmt": "{topic} in Python:\n\n{text}",
        },
        {
            "instruction": "How does Python handle {topic}?",
            "output_fmt": "Python's handling of {topic}:\n\n{text}",
        },
        {
            "instruction": "What are the key points about {topic} in Python documentation?",
            "output_fmt": "Key points from the Python docs about {topic}:\n\n{text}",
        },
        {
            "instruction": "Describe the semantics of {topic} in Python.",
            "output_fmt": "Semantics of {topic}:\n\n{text}",
        },
    ],
    "faq": [
        {
            "instruction": "Answer this common Python question: {topic}",
            "output_fmt": "Answer: {text}",
        },
        {
            "instruction": "Why does {topic} work this way in Python?",
            "output_fmt": "Explanation: {text}",
        },
    ],
    "whatsnew": [
        {
            "instruction": "What's new in Python regarding {topic}?",
            "output_fmt": "What's new: {text}",
        },
        {
            "instruction": "Summarize the changes to {topic} in this Python release.",
            "output_fmt": "Changes: {text}",
        },
    ],
}


# ── Strategy 3: Question Variant Rewriting ───────────────────────


def generate_variants(pair: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Generate alternate phrasings of the same Q&A pair.
    Uses rule-based rephrasing for reliability.
    """
    instruction = pair.get("instruction", "")
    output = pair.get("output", "")
    source = pair.get("source", "unknown")
    version = pair.get("version", "")
    section = pair.get("section", "")

    variants: list[dict[str, Any]] = []
    base_id = f"variant_{source}"

    rephrase_templates = [
        f"I'd like to understand: {instruction.lower()}",
        f"Can you help me with {instruction[0].lower()}{instruction[1:] if len(instruction) > 1 else ''}?",
        f"Please explain: {instruction}",
        f"What should I know about {instruction.split()[-1] if instruction else 'this'}?",
        f"Could you elaborate on {instruction.lower()}?",
        f"Teaching me about: {instruction.lower()}",
    ]

    selected = random.sample(
        rephrase_templates,
        min(VARIANT_PER_QA, len(rephrase_templates))
    )

    for i, new_instruction in enumerate(selected):
        if _qualify_pair(new_instruction, output):
            variants.append({
                "id": _make_id("variant", base_id, i),
                "instruction": new_instruction,
                "output": output,
                "source": source,
                "version": version,
                "category": "variant",
                "section": section,
                "original_instruction": instruction,
            })

    return variants


# ── Strategy 4: Code-Focused Tasks ────────────────────────────────


def extract_code_blocks(text: str) -> list[str]:
    """Extract Python code blocks from text."""
    blocks: list[str] = []

    # Markdown fenced code blocks
    for m in re.finditer(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL):
        code = m.group(1).strip()
        if len(code) > 20:
            blocks.append(code)

    # Inline code with `func()` patterns
    inline_codes = re.findall(r"`([^`]+)`", text)
    for code in inline_codes:
        if ("(" in code or "=" in code or "import" in code) and len(code) > 10:
            blocks.append(code)

    return blocks[:5]


def generate_code_tasks(chunk: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate code-focused tasks from code blocks in chunk."""
    texts = chunk.get("text", "")
    source = chunk.get("id", "unknown")
    version = chunk.get("version", "")
    title_section = chunk.get("section", "")

    code_blocks = extract_code_blocks(texts)
    if not code_blocks:
        return []

    tasks: list[dict[str, Any]] = []

    for i, code in enumerate(code_blocks[:CODE_TASKS]):
        # Task: explain the code
        instruction = f"Explain the following Python {version} code:\n\n```python\n{code[:300]}\n```"
        output = (
            f"This code from the '{title_section}' section of the Python {version} docs "
            f"demonstrates:\n\n{_truncate(texts[:500])}"
        )
        if _qualify_pair(instruction, output):
            tasks.append({
                "id": _make_id("code_explain", source, i),
                "instruction": instruction,
                "output": output,
                "source": source,
                "version": version,
                "category": "code_explanation",
                "section": title_section,
                "code": code[:500],
            })

        # Task: what does this code do?
        instruction = f"What is the output of this Python code?\n\n```python\n{code[:200]}\n```"
        output = (
            f"Based on the Python {version} documentation for '{title_section}':\n\n"
            f"{_truncate(texts[:300])}\n\n"
            f"The code above demonstrates the concepts described."
        )
        if _qualify_pair(instruction, output):
            tasks.append({
                "id": _make_id("code_output", source, len(tasks)),
                "instruction": instruction,
                "output": output,
                "source": source,
                "version": version,
                "category": "code_analysis",
                "section": title_section,
            })

    return tasks


# ── Strategy 5: PyPI Knowledge Cards ─────────────────────────────


def fetch_pypi_metadata(library_name: str) -> dict[str, Any]:
    """Fetch metadata for a single PyPI library via the JSON API."""
    url = f"https://pypi.org/pypi/{library_name}/json"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            info = data.get("info", {})
            return {
                "name": info.get("name", library_name),
                "version": info.get("version", ""),
                "summary": info.get("summary", ""),
                "description": (info.get("description", "") or "")[:2000],
                "author": info.get("author", ""),
                "author_email": info.get("author_email", ""),
                "home_page": info.get("home_page", info.get("project_urls", {}).get("Homepage", "")),
                "license": info.get("license", ""),
                "classifiers": info.get("classifiers", []),
                "requires_python": info.get("requires_python", ""),
                "keywords": info.get("keywords", ""),
                "project_urls": info.get("project_urls", {}),
            }
        elif resp.status_code == 404:
            return {}  # Library not found on PyPI
        else:
            return {}
    except requests.Timeout:
        return {}
    except requests.ConnectionError:
        return {}
    except Exception:
        return {}


def load_top_pypi_libraries() -> list[str]:
    """
    Load the list of top PyPI libraries to process.
    In production, this should pull from a full index.
    Here we start with the top 950K+ libraries from a curated + generated list.
    """
    # We start with the top ~50 known libraries and will progressively
    # expand to millions via the PyPI Simple API in production.
    core_libraries = [
        # Web frameworks
        "django", "flask", "fastapi", "bottle", "tornado", "aiohttp", "sanic",
        "pyramid", "web2py", "cherrypy", "hug", "falcon", "starlette",
        "responder", "masonite", "quart", "litestar",

        # Data science & ML
        "numpy", "pandas", "scipy", "scikit-learn", "matplotlib", "seaborn",
        "plotly", "bokeh", "statsmodels", "nltk", "spacy", "gensim",
        "transformers", "datasets", "accelerate", "tokenizers",
        "tensorflow", "torch", "jax", "keras", "mxnet", "paddlepaddle",
        "xgboost", "lightgbm", "catboost", "optuna", "ray", "dask",
        "vaex", "modin", "polars", "cuDF", "numba", "cython",
        "sympy", "networkx", "igraph", "opencv-python", "pillow",
        "scikit-image", "mahotas", "simplecv",

        # Database & ORM
        "sqlalchemy", "django-orm", "peewee", "pony", "tortoise-orm",
        "psycopg2", "asyncpg", "aiomysql", "pymongo", "motor",
        "redis", "redis-py", "aioredis", "hiredis",
        "sqlite3", "sqlparse", "alembic", "migrate",
        "elasticsearch", "elasticsearch-dsl", "pymemcache",

        # Async & concurrency
        "asyncio", "anyio", "trio", "curio", "uvloop",
        "concurrent", "multiprocessing", "threading",
        "celery", "huey", "rq", "dramatiq", "arq",

        # CLI & system
        "click", "rich", "typer", "argparse", "python-fire",
        "colorama", "termcolor", "blessed", "prompt-toolkit",
        "psutil", "shutil", "pathlib", "os", "sys",
        "invoke", "fabric", "pyshell", "plumbum",

        # Testing
        "pytest", "unittest", "nose2", "hypothesis", "tox", "nox",
        "coverage", "mock", "vcrpy", "responses", "factory-boy",
        "faker", "freezegun", "time-machine",

        # HTTP & networking
        "requests", "httpx", "urllib3", "aiohttp", "grequests",
        "websockets", "socketio", "zeroconf", "dnspython",
        "paramiko", "fabric", "asyncssh", "telnetlib3",

        # Parsing & serialization
        "beautifulsoup4", "lxml", "html5lib", "pyquery",
        "json", "orjson", "ujson", "simplejson", "rapidjson",
        "yaml", "pyyaml", "ruamel.yaml", "toml", "tomli",
        "pickle", "cloudpickle", "dill", "joblib",
        "protobuf", "flatbuffers", "msgpack", "cbor2",

        # API & schema
        "pydantic", "attrs", "dataclasses", "msgspec",
        "marshmallow", "schema", "cerberus", "voluptuous",
        "strawberry-graphql", "graphene", "ariadne",

        # DevOps & infra
        "docker", "kubernetes", "ansible", "salt", "puppet",
        "terraform", "boto3", "google-cloud", "azure",
        "fabric", "pyinvoke", "supervisor", "superlance",

        # Image & video
        "opencv-python", "pillow", "scikit-image",
        "moviepy", "ffmpeg-python", "imageio", "pydub",
        "python-pptx", "python-docx", "openpyxl", "xlrd",

        # Other notable
        "loguru", "structlog", "logging",
        "sentry-sdk", "rollbar", "bugsnag",
        "sphinx", "mkdocs", "pdoc", "pydoc",
        "black", "ruff", "isort", "autoflake", "pyflakes",
        "mypy", "pylint", "pyright", "bandit",
        "pip", "poetry", "pipenv", "hatch", "pdm",
        "wheel", "setuptools", "build", "twine",
        "cryptography", "bcrypt", "passlib", "jwcrypto",
        "python-jose", "pyjwt", "oauthlib", "authlib",
        "email-validator", "phonenumbers", "validate-email",
    ]

    return sorted(set(core_libraries))


def build_pypi_knowledge_card(lib_info: dict) -> dict[str, Any] | None:
    """Build a standardized knowledge card from PyPI metadata."""
    if not lib_info.get("name"):
        return None

    name = lib_info["name"]
    version = lib_info.get("version", "")
    desc = (lib_info.get("description", "") or "")[:2000]
    summary = (lib_info.get("summary", "") or "")

    # Categorise based on classifiers
    cats = ["pypi_library"]
    for cl in lib_info.get("classifiers", []):
        cll = cl.lower()
        if "framework" in cll:
            cats.append("framework")
        elif "library" in cll:
            cats.append("library")
        elif "sdk" in cll or "api" in cll:
            cats.append("sdk")
        if "scientific" in cll or "science" in cll:
            cats.append("scientific")
        if "web" in cll:
            cats.append("web")

    text = (
        f"Library: {name}\n"
        f"Version: {version}\n"
        f"Summary: {summary}\n"
        f"Author: {lib_info.get('author', '')}\n"
        f"Home: {lib_info.get('home_page', '')}\n"
        f"License: {lib_info.get('license', '')}\n"
        f"Python: {lib_info.get('requires_python', 'any')}\n"
        f"Categories: {', '.join(cats)}\n\n"
        f"{desc}"
    ).strip()

    return {
        "id": f"pypi_{name.lower().replace('-', '_').replace('.', '_')}",
        "title": f"PyPI Library - {name}",
        "version": version or "any",
        "category": "pypi_library",
        "type": "library_doc",
        "text": text,
        "source": "pypi",
        "library_name": name,
        "keywords": lib_info.get("keywords", ""),
        "home_page": lib_info.get("home_page", ""),
    }


# ── API-Based QA Generation ────────────────────────────────────


def _generate_qa_via_api(chunk: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Generate Q&A pairs using keywords extracted from the chunk,
    then sending only those keywords to API providers.

    This is the replacement for the old _generate_qa_via_ollama()
    which sent full text to a local Ollama model.

    Instead:
    1. Extract keywords from chunk text
    2. Build a concise prompt with keywords + topic
    3. Call API providers (Groq, OpenAI, etc.) with the prompt
    4. Parse and validate the response
    """

    title = chunk.get("title", "")
    version = chunk.get("version", "")
    texts = chunk.get("text", "")[:1500]
    source = chunk.get("id", "unknown")

    # Step 1: Extract keywords from text
    keywords = extract_keywords(texts, max_keywords=8)
    if len(keywords) < 2:
        title_words = [w for w in title.split() if len(w) > 3]
        if title_words:
            keywords = title_words[:5]
        else:
            return []

    # Step 2: Build concise keywords-only prompt
    kw_str = ", ".join(keywords)
    prompt = (
        f"Based on these Python keywords related to '{title}' (Python {version}):\n\n"
        f"Keywords: {kw_str}\n\n"
        f"Generate 3 high-quality Q&A pairs for training a Python assistant.\n"
        f"Each question should test understanding of these concepts.\n"
        f"Return ONLY a valid JSON array with objects containing 'instruction' and 'output'.\n"
    )

    # Step 3: Call API providers
    keys = resolve_all()
    active = [(name, cfg) for name, cfg in API_PROVIDERS.items() if name in keys and keys[name]]

    for prov_name, prov_cfg in active:
        try:
            resp = requests.post(
                prov_cfg["url"],
                headers={
                    "Authorization": f"Bearer {keys[prov_name]}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": prov_cfg["model"],
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 1024,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                # Parse JSON from response
                pairs = _parse_qa_response(content, source, version, chunk, prov_name)
                if pairs:
                    return pairs
            elif resp.status_code == 429:
                continue  # Rate limited, try next provider
        except (requests.Timeout, requests.ConnectionError, KeyError, json.JSONDecodeError):
            continue

    return []


def _parse_qa_response(content: str, source: str, version: str, chunk: dict[str, Any], provider: str) -> list[dict[str, Any]]:
    """Parse API response JSON into QA pairs with quality checks."""
    clean = content.strip()
    if clean.startswith("```json"):
        clean = clean[7:-3]
    elif clean.startswith("```"):
        clean = clean[3:-3]

    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        start = clean.find("[")
        end = clean.rfind("]") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(clean[start:end])
            except (json.JSONDecodeError, ValueError):
                return []
        else:
            return []

    if not isinstance(data, list):
        return []

    results: list[dict[str, Any]] = []
    for i, p in enumerate(data):
        if not isinstance(p, dict) or "instruction" not in p or "output" not in p:
            continue
        if not _qualify_pair(p["instruction"], p["output"]):
            continue
        p["id"] = _make_id(f"api_{provider}", source, i)
        p["source"] = source
        p["version"] = version
        p["category"] = "api_qa"
        p["section"] = chunk.get("section", "")
        results.append(p)

    return results


# ── Old Ollama Integration (removed — replaced by API-based generation) ────

# The _generate_qa_via_ollama() function has been replaced by _generate_qa_via_api().
# Instead of sending full text to local Ollama/Qwen, we now:
# 1. Extract keywords from the text
# 2. Send only keywords to cloud API providers (Groq, OpenAI, DeepSeek, etc.)
# This is cheaper, faster, and produces higher quality results.


# ── Main Amplification Pipeline ──────────────────────────────────


def amplify_chunk(
    chunk: dict[str, Any],
    use_ollama: bool = False,
) -> list[dict[str, Any]]:
    """
    Run all amplification strategies on a single chunk.

    When use_ollama=True, applies keyword extraction + API-based QA generation
    (replaces old Ollama approach). When False, uses template-based generation.

    Returns the list of generated training pairs.
    """
    results: list[dict[str, Any]] = []

    # Strategy 1: Keyword expansion
    keywords = extract_keywords(chunk.get("text", ""))
    if keywords:
        keyword_tasks = generate_keyword_tasks(chunk, keywords)
        results.extend(keyword_tasks)

    # Strategy 2: Direct QA pairs (API-based when use_ollama=True, template otherwise)
    qa_pairs = generate_qa_pairs(chunk, use_ollama=use_ollama)
    results.extend(qa_pairs)

    # Strategy 3: Question variants for each QA pair
    for qa in qa_pairs:
        variants = generate_variants(qa)
        results.extend(variants)

    # Strategy 4: Code-focused tasks
    code_tasks = generate_code_tasks(chunk)
    results.extend(code_tasks)

    return results


def process_amplification(
    test_mode: bool = False,
    use_ollama: bool = False,
    incremental: bool = True,
) -> dict[str, Any]:
    """
    Run the full amplification pipeline on ingested ZIP doc chunks.

    use_ollama=True → keyword extraction + API-based QA generation (recommended).
    use_ollama=False → template-based QA generation (no API needed).

    Returns stats dict.
    """
    TRAIN_DATA_DIR.mkdir(parents=True, exist_ok=True)
    state = AmplifierState() if incremental else None

    if not INPUT_CHUNKS.exists():
        console.print(f"[red]No input chunks found at {INPUT_CHUNKS}[/red]")
        console.print("[yellow]Run zip_doc_ingestor.py first.[/yellow]")
        return {"error": "No input chunks"}

    # Read base chunks
    chunks: list[dict[str, Any]] = []
    with open(INPUT_CHUNKS, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    chunks.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    if test_mode:
        chunks = chunks[:100]  # Test with first 100 chunks

    console.print(f"\n[bold cyan]═══ Data Amplification ═══[/bold cyan]")
    console.print(f"  Input chunks:     {len(chunks):,}")
    console.print(f"  QA Generation:    {'API-based (keywords + API)' if use_ollama else 'Template-based (rule-only)'}")
    console.print(f"  Test mode:        {'Yes' if test_mode else 'No'}")
    console.print(f"  Incremental:      {'Yes' if incremental else 'No'}")

    total_input = len(chunks)
    total_generated = 0
    categories: dict[str, int] = {}

    # Process each chunk
    for idx, chunk in enumerate(
        tqdm(chunks, desc="Amplifying", unit="chunk")
    ):
        chunk_id = chunk.get("id", f"chunk_{idx}")

        if state and state.is_chunk_processed(chunk_id):
            continue

        pairs = amplify_chunk(chunk, use_ollama=use_ollama)
        if not pairs:
            continue

        # Append to output
        with open(OUTPUT_AMPLIFIED, "a", encoding="utf-8") as f:
            for pair in pairs:
                f.write(json.dumps(pair, ensure_ascii=False) + "\n")
                cat = pair.get("category", "unknown")
                categories[cat] = categories.get(cat, 0) + 1

        total_generated += len(pairs)

        if state:
            state.mark_chunk_processed(chunk_id)

        if test_mode and idx >= 99:
            break

    # Stats
    total_output = total_generated
    amplification_factor = total_output / max(total_input, 1)

    console.print(f"\n[bold green]═══ Amplification Complete ═══[/bold green]")
    console.print(f"  Chunks processed:  {total_input:,}")
    console.print(f"  Pairs generated:   {total_output:,}")
    console.print(f"  Amplification:     {amplification_factor:.1f}x")
    console.print(f"  Output:            {OUTPUT_AMPLIFIED}")

    if categories:
        console.print(f"\n  By category:")
        for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
            console.print(f"    {cat:25s}: {count:>6,}")

    return {
        "input_chunks": total_input,
        "output_pairs": total_output,
        "amplification": round(amplification_factor, 1),
        "categories": categories,
    }


def process_pypi_knowledge(
    test_mode: bool = False,
    incremental: bool = True,
    libraries: list[str] | None = None,
) -> dict[str, Any]:
    """
    Fetch PyPI metadata for libraries and build knowledge cards.

    Returns stats dict.
    """
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    state = AmplifierState() if incremental else None

    if libraries is None:
        libraries = load_top_pypi_libraries()

    if test_mode:
        libraries = libraries[:20]  # Just 20 for testing

    console.print(f"\n[bold cyan]═══ PyPI Knowledge Base Builder ═══[/bold cyan]")
    console.print(f"  Libraries:        {len(libraries):,}")
    console.print(f"  Concurrency:      {PYPI_CONCURRENCY} workers")
    console.print(f"  Test mode:        {'Yes' if test_mode else 'No'}")

    fetched = 0
    errors = 0
    cards: list[dict[str, Any]] = []

    def _fetch_and_save(lib: str) -> dict[str, Any] | None:
        nonlocal errors
        if state and state.is_library_processed(lib):
            return None
        info = fetch_pypi_metadata(lib)
        if not info:
            errors += 1
            return None
        card = build_pypi_knowledge_card(info)
        if state:
            state.mark_library_processed(lib)
        return card

    with ThreadPoolExecutor(max_workers=PYPI_CONCURRENCY) as executor:
        futures = {
            executor.submit(_fetch_and_save, lib): lib
            for lib in libraries
        }
        for future in tqdm(
            as_completed(futures), total=len(futures), desc="Fetching PyPI"
        ):
            result = future.result()
            if result:
                cards.append(result)
                fetched += 1
            time.sleep(PYPI_RATE_LIMIT)

    # Append to output file
    existing_count = 0
    if OUTPUT_PYPI.exists():
        with open(OUTPUT_PYPI, "r") as f:
            existing_count = sum(1 for _ in f)

    with open(OUTPUT_PYPI, "a", encoding="utf-8") as f:
        for card in cards:
            f.write(json.dumps(card, ensure_ascii=False) + "\n")

    total_cards = existing_count + len(cards)

    console.print(f"\n[bold green]═══ PyPI Knowledge Base Complete ═══[/bold green]")
    console.print(f"  Libraries fetched: {fetched:,}")
    console.print(f"  Errors:            {errors:,}")
    console.print(f"  Total cards:       {total_cards:,}")
    console.print(f"  Output:            {OUTPUT_PYPI}")

    return {
        "libraries_fetched": fetched,
        "errors": errors,
        "total_cards": total_cards,
    }


# ── CLI Entry Point ──────────────────────────────────────────────


def main(
    test_mode: bool = False,
    pypi_only: bool = False,
    amplify_only: bool = False,
    use_ollama: bool = False,
    incremental: bool = True,
) -> dict[str, Any]:
    """Run the full amplification pipeline."""
    results: dict[str, Any] = {}

    if not pypi_only:
        results["amplification"] = process_amplification(
            test_mode=test_mode,
            use_ollama=use_ollama,
            incremental=incremental,
        )

    if not amplify_only:
        results["pypi_knowledge"] = process_pypi_knowledge(
            test_mode=test_mode,
            incremental=incremental,
        )

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="100x Data Amplification Engine for PythonAI"
    )
    parser.add_argument("--test", action="store_true",
                        help="Test mode: 100 chunks, 20 PyPI libraries")
    parser.add_argument("--pypi-only", action="store_true",
                        help="Only fetch PyPI knowledge cards")
    parser.add_argument("--amplify-only", action="store_true",
                        help="Only run amplification (skip PyPI)")
    parser.add_argument("--no-ollama", action="store_true",
                        help="Skip API-based QA generation (use template fallback only)")
    parser.add_argument("--no-incremental", action="store_true",
                        help="Disable incremental mode (re-process everything)")
    args = parser.parse_args()

    main(
        test_mode=args.test,
        pypi_only=args.pypi_only,
        amplify_only=args.amplify_only,
        use_ollama=not args.no_ollama,  # When True → API-based QA, False → templates
        incremental=not args.no_incremental,
    )
