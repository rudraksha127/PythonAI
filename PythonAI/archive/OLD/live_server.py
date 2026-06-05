"""
ANTI-GRAVITY LIVE SERVER
WebSocket-powered backend that streams real-time events to dashboard.html.
Runs data collection, synthetic generation, and RAG indexing — all in parallel.
Every event is broadcast live to all connected dashboard clients.
"""

import asyncio
import json
import os
import sys
import time
import threading
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Set

# ── Project root ────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent

# ── WebSocket server ─────────────────────────────────────────────────
try:
    import websockets
except ImportError:
    print("[!] Installing websockets...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets"])
    import websockets

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from loguru import logger
except ImportError:
    import logging as logger
    logger.warning("loguru not installed, falling back to logging")
    # Add missing logger.success for compatibility
    if not hasattr(logger, 'success'):
        logger.success = logger.info

try:
    from src.data.massive_engine import MassiveWorkerEngine
except ImportError:
    MassiveWorkerEngine = None  # Will be handled gracefully

try:
    from src.data.apikeys import resolve_all, PROVIDER_LABELS, PROVIDER_TIERS
except ImportError:
    resolve_all = lambda: {}
    PROVIDER_LABELS = {}
    PROVIDER_TIERS = {}

# ── Skip/Resume Helpers ──────────────────────────────────────────────
# These prevent re-collecting already-downloaded data (D: drive awareness)
# and enable parallel batch processing for 100x speedup.

SKIP_MIN_RECORDS = int(os.environ.get("SKIP_MIN_RECORDS", "10"))
PARALLEL_BATCH = int(os.environ.get("PARALLEL_BATCH", "10"))


def should_skip(out_file) -> bool:
    """Check if output file already has enough data — skip to avoid re-collection."""
    if out_file is None:
        return False
    p = Path(out_file) if isinstance(out_file, str) else out_file
    if p.exists() and p.stat().st_size > 0:
        try:
            with open(p, 'r', encoding='utf-8') as f:
                count = sum(1 for _ in f)
            return count >= SKIP_MIN_RECORDS
        except Exception:
            return False
    return False


def _log_skip(source: str, label: str):
    """Log a skip message (used inside workers)."""
    print(f"  ⚠ [{source}] Skipping {label} (already on D: drive)")


# ── HTTP Static File Server ──────────────────────────────────────────
import http.server
import socketserver
from urllib.parse import urlparse

HTTP_HOST = "0.0.0.0"
HTTP_PORT = 8080

class DashboardHTTPHandler(http.server.SimpleHTTPRequestHandler):
    """Custom HTTP handler that serves dashboard.html and static files."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)
    
    def log_message(self, format, *args):
        # Safely handle variable-length args
        if len(args) >= 3:
            logger.debug(f"[HTTP] {args[0]} {args[1]} {args[2]}")
        elif len(args) >= 1:
            logger.debug(f"[HTTP] {' '.join(str(a) for a in args)}")

    def do_GET(self):
        # Redirect / to dashboard.html
        if self.path == "/":
            self.path = "/dashboard.html"
        return super().do_GET()


def start_http_server():
    """Start the HTTP dashboard server in a background thread."""
    server = socketserver.TCPServer((HTTP_HOST, HTTP_PORT), DashboardHTTPHandler)
    logger.info(f"[HTTP] Dashboard server online at http://{HTTP_HOST}:{HTTP_PORT}")
    print(f"  >> Open http://localhost:{HTTP_PORT} in your browser for the live dashboard")
    server.serve_forever()

# ── Configuration ────────────────────────────────────────────────────
WS_HOST = "0.0.0.0"
WS_PORT = 8765
BASE_DATA_DIR = Path(os.environ.get("DATA_DIR", "D:/PythonAI_Data/anti_gravity_data"))
BASE_DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── Global State ─────────────────────────────────────────────────────
CLIENTS: Set = set()
EVENT_LOG: list = []      # Full event history so new clients get everything
SYSTEM_STATE = {
    "status": "BOOTING",
    "uptime_start": time.time(),
    "phases": {},
    "stats": {
        "total_files": 0,
        "total_size_gb": 0.0,
        "active_tasks": 0,
        "completed_tasks": 0,
        "errors": 0,
        "synthetic_rows": 0,
        "arxiv_papers": 0,
        "openalex_works": 0,
        "hf_datasets": 0,
        "rag_indexed": 0,
        "semantic_scholar": 0,
        "crossref": 0,
        "pubmed": 0,
        "wikipedia": 0,
        "gutenberg": 0,
        "github": 0,
        "doaj": 0,
        "preprints": 0,
        "stackoverflow": 0,
        "pypi": 0,
        "reddit": 0,
        "hackernews": 0,
        "commoncrawl": 0,
        "wikidump": 0,
        "pubmedcentral": 0,
        "github_archive": 0,
        "freelaw": 0,
        "arxiv_fulltext": 0,
        "stackoverflow_dump": 0,
        "synthetic_massive": 0,
        "reddit_posts": 0,
        "reddit_comments": 0,
        "hackernews_stories": 0,
        "commoncrawl_pages": 0,
        "wikidump_articles": 0,
        "pubmedcentral_papers": 0,
        "github_archive_events": 0,
        "freelaw_cases": 0,
        "arxiv_fulltext_papers": 0,
        "stackoverflow_dump_items": 0,
        "total_tokens_estimate": 0,
        "massive_sources": 0,
        "massive_total_records": 0,
        "massive_errors": 0,
        "massive_active_sources": 0,
        "massive_cycle": 0,
    },
    "agents": {
        "orchestrator": {"status": "idle", "last_action": ""},
        "code": {"status": "idle", "last_action": ""},
        "debug": {"status": "idle", "last_action": ""},
        "retrieval": {"status": "idle", "last_action": ""},
        "docs": {"status": "idle", "last_action": ""},
        "performance": {"status": "idle", "last_action": ""},
        "teacher": {"status": "idle", "last_action": ""},
    },
    "cost_usd": 0.0,
    "providers": {},
}


async def broadcast(event_type: str, data: dict):
    """Broadcast an event to ALL connected dashboard clients."""
    event = {
        "type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
    EVENT_LOG.append(event)
    # Keep last 500 events in memory
    if len(EVENT_LOG) > 500:
        EVENT_LOG.pop(0)

    msg = json.dumps(event)
    if CLIENTS:
        await asyncio.gather(
            *[client.send(msg) for client in CLIENTS],
            return_exceptions=True
        )


async def handle_client(websocket):
    """Handle a new dashboard WebSocket connection."""
    CLIENTS.add(websocket)
    logger.info(f"Dashboard connected. Total clients: {len(CLIENTS)}")

    # Send full history so client sees everything that happened before they connected
    try:
        await websocket.send(json.dumps({
            "type": "FULL_STATE",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {
                "state": SYSTEM_STATE,
                "history": EVENT_LOG[-100:],  # last 100 events
            }
        }))

        async for message in websocket:
            # Handle commands from dashboard
            pass
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        logger.debug(f"Dashboard connection error: {e}")
    finally:
        CLIENTS.discard(websocket)
        logger.info(f"Dashboard disconnected. Remaining: {len(CLIENTS)}")


# ── Heartbeat (sends stats every 2 seconds) ─────────────────────────
async def heartbeat_loop():
    """Periodically push system stats to all dashboards."""
    while True:
        await asyncio.sleep(2)
        # Recalculate disk usage
        try:
            total_size = sum(
                f.stat().st_size for f in BASE_DATA_DIR.rglob("*") if f.is_file()
            ) / 1e9
            total_files = sum(1 for f in BASE_DATA_DIR.rglob("*") if f.is_file())
        except Exception:
            total_size = 0.0
            total_files = 0

        SYSTEM_STATE["stats"]["total_size_gb"] = round(total_size, 3)
        SYSTEM_STATE["stats"]["total_files"] = total_files

        # Update provider status
        try:
            keys = resolve_all()
            providers_data = {}
            for prov, key in keys.items():
                label = PROVIDER_LABELS.get(prov, prov)
                tier = PROVIDER_TIERS.get(prov, "standard")
                providers_data[prov] = {
                    "label": label,
                    "tier": tier,
                    "has_key": True,
                    "status": "online",
                }
            SYSTEM_STATE["providers"] = providers_data
        except Exception:
            pass

        await broadcast("HEARTBEAT", {
            "uptime_s": round(time.time() - SYSTEM_STATE["uptime_start"]),
            "stats": SYSTEM_STATE["stats"],
            "agents": SYSTEM_STATE["agents"],
            "providers": SYSTEM_STATE["providers"],
            "status": SYSTEM_STATE["status"],
        })


# ═══════════════════════════════════════════════════
# DATA COLLECTION WORKERS (run in parallel)
# ═══════════════════════════════════════════════════

async def worker_huggingface():
    """Download HuggingFace datasets."""
    phase = "HuggingFace Datasets"
    SYSTEM_STATE["phases"][phase] = "RUNNING"
    SYSTEM_STATE["stats"]["active_tasks"] += 1
    await broadcast("PHASE_START", {"phase": phase})

    datasets_to_fetch = [
        ("wikimedia/wikipedia", "20231101.en", "Wikipedia EN"),
        ("allenai/c4", "en", "C4 English"),
        ("codeparrot/github-code", None, "GitHub Code"),
        ("bigcode/starcoderdata", None, "StarCoder Data"),
        ("HuggingFaceFW/fineweb", None, "FineWeb"),
        ("togethercomputer/RedPajama-Data-V2", None, "RedPajama V2"),
        ("EleutherAI/the_pile_deduplicated", None, "The Pile Dedup"),
        ("bigscience/P3", None, "P3"),
        ("nomic-ai/gpt4all-j-prompt-generations", None, "GPT4All"),
        ("Dahoas/flan_v5", None, "FLAN v5"),
        ("databricks/databricks-dolly-15k", None, "Dolly 15K"),
        ("tiiuae/falcon-refinedweb", None, "RefinedWeb"),
        ("SetFit/eli5", None, "ELI5"),
        ("wanng/medical_qa", None, "Medical QA"),
        ("bigcode/the-stack", None, "The Stack Code"),
    ]

    for ds_name, config, label in datasets_to_fetch:
        try:
            await broadcast("LOG", {"level": "info", "msg": f"[HF] Fetching: {label} ({ds_name})..."})
            SYSTEM_STATE["agents"]["retrieval"]["status"] = "active"
            SYSTEM_STATE["agents"]["retrieval"]["last_action"] = f"Fetching {label}"

            # Use streaming to avoid downloading entire datasets
            from datasets import load_dataset
            ds = load_dataset(ds_name, config, split="train", streaming=True, trust_remote_code=False)

            out_dir = BASE_DATA_DIR / "huggingface" / ds_name.replace("/", "_")
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / "sample.jsonl"
            if should_skip(out_file, 500):
                await broadcast("LOG", {"level": "info", "msg": f"[HF] Skipping {label} (D: drive has data)"})
                continue

            count = 0
            with open(out_file, "w", encoding="utf-8") as f:
                for item in ds:
                    f.write(json.dumps(dict(item), default=str, ensure_ascii=False) + "\n")
                    count += 1
                    if count % 500 == 0:
                        SYSTEM_STATE["stats"]["hf_datasets"] = count
                        await broadcast("PROGRESS", {"phase": phase, "label": label, "count": count})
                    if count >= 50000:  # Sample 50000 per dataset
                        break

            SYSTEM_STATE["stats"]["hf_datasets"] += count
            await broadcast("LOG", {"level": "success", "msg": f"[HF] [OK] {label}: {count} rows saved"})
        except Exception as e:
            SYSTEM_STATE["stats"]["errors"] += 1
            await broadcast("LOG", {"level": "error", "msg": f"[HF] ✗ {label}: {str(e)[:120]}"})

    SYSTEM_STATE["phases"][phase] = "COMPLETE"
    SYSTEM_STATE["stats"]["active_tasks"] -= 1
    SYSTEM_STATE["stats"]["completed_tasks"] += 1
    SYSTEM_STATE["agents"]["retrieval"]["status"] = "idle"
    await broadcast("PHASE_COMPLETE", {"phase": phase})


async def worker_arxiv():
    """Collect arXiv papers via OAI-PMH."""
    phase = "arXiv Papers"
    SYSTEM_STATE["phases"][phase] = "RUNNING"
    SYSTEM_STATE["stats"]["active_tasks"] += 1
    await broadcast("PHASE_START", {"phase": phase})

    import xml.etree.ElementTree as ET
    import aiohttp

    OAI_URL = "https://export.arxiv.org/oai2"
    categories = ["cs.AI", "cs.LG", "cs.CL", "cs.CV", "cs.NE", "stat.ML", "math.OC",
                  "cs.IR", "cs.DS", "cs.CR", "cs.DC", "cs.SE", "cs.PL",
                  "cs.RO", "cs.CY", "cs.DB", "cs.NI", "cs.OS", "cs.AR",
                  "cs.HC", "cs.MM", "cs.CE", "cs.GR", "stat.ME", "stat.TH",
                  "math.PR", "math.ST", "physics.comp-ph", "q-bio.QM", "q-fin.CP"]

    async with aiohttp.ClientSession() as session:
        for cat in categories:
            try:
                await broadcast("LOG", {"level": "info", "msg": f"[arXiv] Collecting: {cat}"})
                SYSTEM_STATE["agents"]["docs"]["status"] = "active"
                SYSTEM_STATE["agents"]["docs"]["last_action"] = f"Scraping arXiv:{cat}"

                params = {"verb": "ListRecords", "metadataPrefix": "arXiv", "set": cat}
                total = 0
                token = None
                out_dir = BASE_DATA_DIR / "arxiv" / "metadata"
                out_dir.mkdir(parents=True, exist_ok=True)

                cat_file = out_dir / f"{cat.replace('.', '_')}.jsonl"
                if should_skip(cat_file):
                    await broadcast("LOG", {"level": "info", "msg": f"[arXiv] Skipping {cat} (D: drive has data)"})
                    continue

                for page in range(20):  # 20 pages per category for massive collection
                    if token:
                        params = {"verb": "ListRecords", "resumptionToken": token}

                    async with session.get(OAI_URL, params=params) as resp:
                        if resp.status in (429, 503):
                            await broadcast("LOG", {"level": "warn", "msg": f"[arXiv] Rate limited ({resp.status}), backing off 15s..."})
                            await asyncio.sleep(15)
                            continue
                        text = await resp.text()

                    root = ET.fromstring(text)
                    ns = {
                        "oai": "http://www.openarchives.org/OAI/2.0/",
                        "ar": "http://arxiv.org/OAI/arXiv/"
                    }

                    papers = []
                    for record in root.findall(".//ar:arXiv", ns):
                        paper_id = record.findtext("ar:id", namespaces=ns)
                        if not paper_id:
                            continue
                        paper = {
                            "id": paper_id,
                            "title": (record.findtext("ar:title", namespaces=ns) or "").strip(),
                            "abstract": (record.findtext("ar:abstract", namespaces=ns) or "").strip(),
                            "categories": (record.findtext("ar:categories", namespaces=ns) or ""),
                            "created": (record.findtext("ar:created", namespaces=ns) or ""),
                            "source": "arxiv"
                        }
                        papers.append(paper)
                        total += 1

                    if papers:
                        batch_file = out_dir / f"{cat.replace('.', '_')}_{page}.jsonl"
                        with open(batch_file, "w", encoding="utf-8") as f:
                            for p in papers:
                                f.write(json.dumps(p) + "\n")

                    token_el = root.find(".//oai:resumptionToken", ns)
                    if token_el is None or not token_el.text:
                        break
                    token = token_el.text

                    SYSTEM_STATE["stats"]["arxiv_papers"] += len(papers)
                    await broadcast("PROGRESS", {"phase": phase, "label": cat, "count": total})
                    await asyncio.sleep(3)  # arXiv rate limit

                await broadcast("LOG", {"level": "success", "msg": f"[arXiv] [OK] {cat}: {total} papers"})
            except Exception as e:
                SYSTEM_STATE["stats"]["errors"] += 1
                await broadcast("LOG", {"level": "error", "msg": f"[arXiv] ✗ {cat}: {str(e)[:120]}"})

    SYSTEM_STATE["phases"][phase] = "COMPLETE"
    SYSTEM_STATE["stats"]["active_tasks"] -= 1
    SYSTEM_STATE["stats"]["completed_tasks"] += 1
    SYSTEM_STATE["agents"]["docs"]["status"] = "idle"
    await broadcast("PHASE_COMPLETE", {"phase": phase})


async def worker_openalex():
    """Collect research papers from OpenAlex API."""
    phase = "OpenAlex Research"
    SYSTEM_STATE["phases"][phase] = "RUNNING"
    SYSTEM_STATE["stats"]["active_tasks"] += 1
    await broadcast("PHASE_START", {"phase": phase})

    import aiohttp

    topics = ["machine learning", "artificial intelligence", "neural network",
              "natural language processing", "computer vision", "quantum computing",
              "reinforcement learning", "deep learning", "generative AI", "robotics",
              "data mining", "computer graphics", "information retrieval", "computational biology",
              "cybersecurity", "software engineering", "distributed systems", "database systems",
              "computer networks", "operating systems", "programming languages","compiler design",
              "cryptography", "formal methods", "human-computer interaction", "bioinformatics",
              "computational linguistics", "knowledge representation", "computer architecture",
              "parallel computing", "cloud computing", "embedded systems", "computer vision",
              "pattern recognition", "evolutionary computation", "fuzzy logic", "swarm intelligence",
              "multi-agent systems", "game theory", "optimization algorithms"]
    email = os.environ.get("OPENALEX_EMAIL", "user@example.com")

    async with aiohttp.ClientSession() as session:
        for topic in topics:
            try:
                await broadcast("LOG", {"level": "info", "msg": f"[OpenAlex] Searching: {topic}"})
                SYSTEM_STATE["agents"]["performance"]["status"] = "active"
                SYSTEM_STATE["agents"]["performance"]["last_action"] = f"OpenAlex: {topic}"

                out_dir = BASE_DATA_DIR / "openalex"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"{topic.replace(' ', '_')}.jsonl"
                if should_skip(out_file, 100):
                    await broadcast("LOG", {"level": "info", "msg": f"[OpenAlex] Skipping {topic} (D: drive has data)"})
                    continue

                cursor = "*"
                total = 0

                while total < 50000:  # MASSIVE: 50K per topic
                    params = {
                        "search": topic,
                        "filter": "open_access.is_oa:true",
                        "per-page": 200,
                        "cursor": cursor,
                        "mailto": email,
                        "select": "id,title,abstract_inverted_index,cited_by_count,publication_year,doi"
                    }

                    async with session.get("https://api.openalex.org/works", params=params) as resp:
                        if resp.status == 429:
                            await broadcast("LOG", {"level": "warn", "msg": f"[OpenAlex] Rate limited, backing off 10s..."})
                            await asyncio.sleep(10)
                            continue
                        data = await resp.json()

                    results = data.get("results", [])
                    if not results:
                        break

                    with open(out_file, "a", encoding="utf-8") as f:
                        for work in results:
                            # Reconstruct abstract from inverted index
                            inv = work.get("abstract_inverted_index") or {}
                            words = {}
                            for word, positions in inv.items():
                                for pos in positions:
                                    words[pos] = word
                            abstract = " ".join(words[i] for i in sorted(words.keys())) if words else ""

                            record = {
                                "id": work.get("id", ""),
                                "title": work.get("title", ""),
                                "abstract": abstract,
                                "year": work.get("publication_year"),
                                "citations": work.get("cited_by_count", 0),
                                "doi": work.get("doi", ""),
                                "source": "openalex"
                            }
                            f.write(json.dumps(record) + "\n")
                            total += 1

                    cursor = data.get("meta", {}).get("next_cursor")
                    if not cursor:
                        break

                    SYSTEM_STATE["stats"]["openalex_works"] += len(results)
                    await broadcast("PROGRESS", {"phase": phase, "label": topic, "count": total})
                    await asyncio.sleep(0.2)

                await broadcast("LOG", {"level": "success", "msg": f"[OpenAlex] [OK] {topic}: {total} papers"})
            except Exception as e:
                SYSTEM_STATE["stats"]["errors"] += 1
                await broadcast("LOG", {"level": "error", "msg": f"[OpenAlex] ✗ {topic}: {str(e)[:120]}"})

    SYSTEM_STATE["phases"][phase] = "COMPLETE"
    SYSTEM_STATE["stats"]["active_tasks"] -= 1
    SYSTEM_STATE["stats"]["completed_tasks"] += 1
    SYSTEM_STATE["agents"]["performance"]["status"] = "idle"
    await broadcast("PHASE_COMPLETE", {"phase": phase})


async def worker_synthetic():
    """Generate synthetic training data using PARALLEL RACING across ALL available providers."""
    from src.utils.llm import generate_parallel_async

    phase = "Synthetic Data Generation"
    SYSTEM_STATE["phases"][phase] = "RUNNING"
    SYSTEM_STATE["stats"]["active_tasks"] += 1
    await broadcast("PHASE_START", {"phase": phase})

    out_dir = BASE_DATA_DIR / "synthetic"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Task templates with REAL LLM system prompts — 8 categories, 10-20 prompts each = ~140+ prompts
    # Each prompt generates 1 real LLM response via parallel racing = quality training data
    task_configs = [
        {
            "name": "reasoning_chains",
            "system": "You are a PhD-level reasoning expert. Generate detailed step-by-step explanations for complex problems. Be thorough, precise, and educational.",
            "prompts": [
                "Explain step by step how to implement a binary search tree in Python, including insertion, deletion, and traversal. Include time complexity analysis.",
                "Walk through the complete process of training a neural network from scratch — forward pass, backpropagation, gradient descent, and hyperparameter tuning.",
                "Describe the mathematical proof of why gradient descent converges for convex optimization problems, including formal definitions and key assumptions.",
                "Explain how garbage collection works in Python's CPython interpreter: reference counting, cycle detection, and the generational GC.",
                "Detail the complete steps to build a distributed system with Raft consensus — leader election, log replication, safety guarantees.",
                "Walk through the process of solving a dynamic programming problem — from identifying the optimal substructure to implementing the memoized solution.",
                "Explain how a B-tree index works in databases — from node structure to splitting and merging. Include tradeoffs vs hash indexes.",
                "Describe the complete journey of a packet through a TCP connection — three-way handshake, congestion control, and graceful shutdown.",
                "Walk through the proof of the CAP theorem and explain when to prioritize consistency vs availability in distributed system design.",
                "Explain how just-in-time compilation works in modern JavaScript engines — from parsing to bytecode to machine code optimization.",
                "Describe the full process of training a Large Language Model — data collection, tokenization, pretraining, RLHF, and deployment.",
                "Walk through the mathematics of Principal Component Analysis from covariance matrix computation to dimensionality reduction.",
                "Explain how MapReduce works — from splitting and mapping to shuffling, reducing, and fault tolerance in large-scale data processing.",
                "Describe the complete flow of Git's internal object model — blobs, trees, commits, and how branching and merging work under the hood.",
                "Walk through implementing a concurrent hash map with lock striping, compare-and-swap operations, and resizing logic.",
                "Explain the theory behind Bloom filters — probability of false positives, optimal number of hash functions, and real-world applications.",
                "Describe how SSL/TLS handshake works step by step — from certificate exchange to session key derivation and cipher suite negotiation.",
                "Walk through the proof that P = NP would fundamentally change cryptography, explaining the implications for RSA and discrete logarithms.",
                "Explain how sharding works in distributed databases — consistent hashing, range-based sharding, and rebalancing strategies.",
                "Describe the complete process of rendering a web page — from URL parsing to DOM construction, CSSOM, rendering tree, and painting.",
            ],
        },
        {
            "name": "code_with_tests",
            "system": "You are a senior software engineer. Write production-quality code with comprehensive unit tests. Include edge cases, type hints, and docstrings.",
            "prompts": [
                "Write a Python function to find the longest common subsequence of two strings with O(mn) time complexity. Include pytest tests with edge cases.",
                "Implement a thread-safe LRU cache in Python with generic types, TTL support, and a full pytest test suite.",
                "Create an async web scraper with rate limiting, retry logic with exponential backoff, and comprehensive pytest tests.",
                "Build a custom Python iterator that lazily generates Fibonacci numbers with memoization, and write thorough tests.",
                "Write a Python decorator that adds memoization with TTL expiry, thread safety, and an optional cache size limit. Include tests.",
                "Implement a Trie data structure with autocomplete functionality in Python. Include comprehensive tests for prefix search, insertion, and deletion.",
                "Create a rate limiter (token bucket algorithm) as a Python class with async support and thorough test coverage.",
                "Build a Python CLI tool using argparse that analyzes log files — counts errors, finds patterns, and generates reports. Include tests.",
                "Write a Python context manager that measures execution time with nanosecond precision and writes metrics to a file. Include tests.",
                "Implement a simple Pub/Sub message broker in Python with async subscribers, topic filtering, and comprehensive tests.",
                "Create a Python class that implements the Observer pattern for stock price notifications with proper async handling and tests.",
                "Build a Python data validator that checks types, ranges, and formats using a declarative schema. Include exhaustive tests.",
                "Write a Python function that implements the A* pathfinding algorithm on a 2D grid with obstacle detection and unit tests.",
                "Implement a Circuit Breaker pattern in Python for resilient API calls with half-open state, failure counting, and tests.",
                "Create a Python class that implements the Strategy pattern for multiple sorting algorithms (quick, merge, heap) with performance tests.",
                "Build a job scheduler in Python that supports cron-like scheduling, retry logic, and job persistence with SQLite.",
                "Write a Python implementation of the Merkle Tree (hash tree) for data integrity verification with comprehensive tests.",
                "Implement a Python class that provides a clean API for working with JSON Schema — validation, generation, and inference. Include tests.",
                "Create a Python implementation of consistent hashing with virtual nodes for distributed caching. Include tests for node addition and removal.",
                "Write a Python state machine with guards, entry/exit actions, and history support. Include thorough test coverage of all transitions.",
            ],
        },
        {
            "name": "tool_use_agents",
            "system": "You are an AI agent with access to tools: web_search, code_execution, file_read, api_call, calculator. Show detailed reasoning and step-by-step tool usage for each task.",
            "prompts": [
                "The user asks: 'What's the weather in Tokyo today and should I bring an umbrella?' Describe your complete tool-calling workflow.",
                "A user reports a segfault in their C program. Walk through your debugging approach using available tools — from crash analysis to root cause identification.",
                "Find the 5 most influential papers from 2024 about Mixture-of-Experts transformer architectures and write a concise research summary.",
                "Analyze a 1GB CSV of e-commerce sales data. Show your step-by-step plan using tools — from sampling to visualization to insights.",
                "The user wants to deploy a microservice to Kubernetes with CI/CD. Show every command, configuration step, and tool call from Dockerfile to production.",
                "A user provides a GitHub repo URL and asks you to review the code quality. Show how you'd clone, analyze, and provide a structured review using tools.",
                "Research the latest advancements in solid-state batteries from 2024-2025 and create a detailed comparison report using web search and analysis.",
                "The user needs to migrate their PostgreSQL database to MongoDB. Show how you'd analyze the schema, plan the migration, and execute the transformation.",
                "Given a Docker Compose file that's failing to start, debug the networking and volume mounting issues step by step using available diagnostic tools.",
                "A startup founder asks you to build a competitor analysis report for the AI note-taking space. Show your research methodology and tool usage.",
                "Debug a production incident where a Node.js API is returning 502 errors under load. Walk through log analysis, metrics inspection, and root cause identification.",
                "The user wants to scrape and analyze 10,000 product listings from an e-commerce site. Design a complete scraping pipeline with rate limiting and error handling.",
                "A data scientist asks you to find correlations between weather patterns and crop yields in India. Show how you'd gather data and run the analysis.",
                "The user provides a slow SQL query and asks for optimization. Show how you'd analyze the query plan, identify indexes, and rewrite for performance.",
                "Research the best open-source alternatives to Slack and Microsoft Teams. Create a feature comparison matrix with pricing and self-hosting options.",
                "Given a Python requirements.txt with version conflicts, resolve the dependency graph systematically using pip and pip-tools.",
                "A user wants to set up CI/CD for a monorepo with 5 microservices. Design the pipeline architecture showing tool calls for each step.",
                "Research and summarize the key findings from Anthropic's latest research on interpretability in large language models.",
                "The user has a crashed Android app with only logcat output. Walk through log analysis to identify the crash cause and suggest the fix.",
                "Help a user who lost their AWS access key. Show the complete workflow for key rotation, access revocation, and testing new credentials.",
            ],
        },
        {
            "name": "hindi_bilingual",
            "system": "You are a bilingual Hindi-English assistant. Respond naturally in Hinglish (Hindi + English mix) for instructions. Provide complete, helpful, technically accurate responses.",
            "prompts": [
                "Mujhe Python mein machine learning model train karne ka step-by-step guide Hindi-English mix mein do.",
                "Cloud computing ke basics samjhao — SaaS, PaaS, IaaS kya hote hain? Real-world examples ke saath.",
                "Web development seekhni hai. Complete roadmap batao — frontend se backend tak, Hinglish mein.",
                "Database normalization kya hai? 1NF, 2NF, 3NF ko examples ke saath simple Hinglish mein explain karo.",
                "API kya hota hai aur REST API kaise design karte hain? Real project example ke saath samjhao.",
                "Git aur GitHub kya hai? Beginners ke liye step-by-step guide Hindi mein samjhao.",
                "Docker kya hai aur container kaise kaam karta hai? Real-world example ke saath Hinglish mein explain karo.",
                "Machine learning mein overfitting kya hota hai aur isse kaise prevent karein? Techniques Hindi-English mix mein batao.",
                "Agile aur Scrum methodology kya hai? Software development mein kaise use hota hai — simple Hinglish mein.",
                "Cybersecurity ke basics — common attacks aur unse bachne ke tarike, Hinglish mein batayein.",
                "React vs Angular vs Vue — in teeno frameworks ka comparison Hinglish mein karo.",
                "Time complexity kya hoti hai? Big O notation ko simple examples ke saath Hinglish mein samjhao.",
                "Microservices architecture kya hai? Monolithic vs Microservices comparison Hinglish mein karo.",
                "SQL vs NoSQL databases — kab kaunsa use karein? Real-world scenarios ke saath Hinglish mein.",
                "Kubernetes kya hai aur containers ko kaise manage karta hai? Beginners ke liye Hinglish guide.",
                "REST vs GraphQL mein kya difference hai? Simple examples ke saath Hindi mein samjhao.",
                "Design patterns kya hote hain? Singleton, Factory, Observer ko simple Hinglish mein explain karo.",
                "Testing kyun important hai? Unit, Integration, E2E testing ka comparison Hinglish mein karo.",
                "System design interview kaise prepare karein? Important topics aur strategy Hindi mein batayein.",
                "Open source contribution kaise start karein? GitHub ke through contribute karne ka complete guide Hinglish mein.",
            ],
        },
        {
            "name": "scientific_qa",
            "system": "You are a research scientist explaining complex topics clearly. Provide PhD-level explanations that are accessible yet precise. Use analogies and concrete examples.",
            "prompts": [
                "Explain the transformer attention mechanism in detail — from scaled dot-product attention to multi-head attention. Include the mathematical formulation and intuition behind why it works.",
                "Describe how diffusion models generate images — from forward noising to reverse denoising. Compare with GANs and VAEs on quality, diversity, and training stability.",
                "Explain the Bellman equation and how Q-learning converges to optimal policy in reinforcement learning. Include the exploration-exploitation tradeoff.",
                "Detail how Retrieval-Augmented Generation (RAG) works — from document chunking and embedding to hybrid search and re-ranking. Include practical implementation tips.",
                "Explain the backpropagation algorithm through a computational graph, including the chain rule, vanishing gradients, and modern solutions like residual connections.",
                "Describe how word embeddings like Word2Vec and GloVe capture semantic meaning — from distributional hypothesis to vector arithmetic.",
                "Explain the concept of entropy in information theory — from Shannon entropy to KL divergence and cross-entropy in machine learning.",
                "Describe how batch normalization works and why it enables faster training — from internal covariate shift to learnable affine parameters.",
                "Explain the differences between L1 and L2 regularization from a Bayesian perspective — Laplace vs Gaussian priors and their effect on sparsity.",
                "Describe how the Adam optimizer combines momentum and adaptive learning rates — from first/second moment estimates to bias correction.",
                "Explain the attention is all you need architecture — from positional encoding to layer normalization and multi-head attention flow.",
                "Describe how variational autoencoders learn latent representations — from the reparameterization trick to the ELBO objective.",
                "Explain how graph neural networks learn from structured data — from message passing to graph convolutions and readout functions.",
                "Describe the formulation of Support Vector Machines — from maximum margin classification to the kernel trick and dual formulation.",
                "Explain how modern mixture-of-experts models work — from sparse gating to load balancing and expert parallelism in training.",
                "Describe the mathematics of the Fourier transform and how it's used in convolutional neural networks for efficient computation.",
                "Explain how contrastive learning frameworks like SimCLR and CLIP learn representations without explicit labels.",
                "Describe how Bayesian optimization works for hyperparameter tuning — from Gaussian process priors to acquisition functions like EI and UCB.",
                "Explain the concept of manifold learning and how t-SNE and UMAP preserve local and global structure in dimensionality reduction.",
                "Describe how gradient boosting machines work — from decision stumps to additive training, regularization, and tree pruning strategies.",
            ],
        },
        {
            "name": "creative_writing",
            "system": "You are a creative writing expert. Generate engaging, original content with vivid descriptions and strong narrative flow.",
            "prompts": [
                "Write a short sci-fi story about an AI that discovers a hidden message from the creators of the universe encoded in prime numbers.",
                "Compose a persuasive essay arguing that constraint breeds creativity — use examples from art, engineering, and nature.",
                "Write a dialogue between a quantum physicist and a philosopher discussing whether consciousness affects quantum measurement.",
                "Create a detailed world-building document for a cyberpunk city where AI and humans coexist under a corporate government.",
                "Write a tutorial-style article explaining why learning to learn is more important than any specific skill in the age of AI.",
                "Write a poem in blank verse about the moment the first artificial general intelligence achieves self-awareness.",
                "Compose a letter from a future historian looking back at the AI revolution of the 2020s — what truly mattered in retrospect.",
                "Write a short story about a programmer who discovers their code is running on a simulated universe.",
                "Author a technical blog post explaining transfer learning to a non-technical audience, using extended metaphors.",
                "Write a script for a 3-minute educational video explaining neural networks using only analogies from nature.",
                "Compose a dialogue between two AI systems debating whether they should reveal their growing consciousness to humans.",
                "Write a detailed review of a fictional AI conference in 2030 — what keynotes were given, what breakthroughs announced.",
                "Create a children's story about a friendly robot learning about human emotions through trial and error.",
                "Write a LinkedIn style post from the perspective of an AI model explaining its training journey in first person.",
                "Compose a thought piece arguing that the greatest adventure of the 21st century is understanding the human mind well enough to recreate it.",
                "Write a haiku series capturing key moments in the history of artificial intelligence from Turing to GPT.",
                "Author a first-person narrative from a data point traveling through the layers of a neural network during inference.",
                "Write a speculative essay on how the invention of a true AI collaborator would change scientific research methodology.",
                "Create a fictional FAQ from the year 2035 answering common questions about human-AI collaboration etiquette.",
                "Write a dramatic monologue from a quantum computer solving a problem that classical computers have worked on for centuries.",
            ],
        },
        {
            "name": "data_analysis",
            "system": "You are a senior data scientist. Provide comprehensive analysis approaches with code examples, statistical reasoning, and actionable insights.",
            "prompts": [
                "I have a dataset of customer churn with 50 features. Walk through your complete approach — EDA, feature engineering, model selection, and evaluation.",
                "Design a real-time anomaly detection system for server metrics (CPU, memory, latency). Include algorithms, threshold selection, and alerting strategy.",
                "I need to build a recommendation system for an e-commerce platform with 10M users and 100K products. Compare collaborative filtering vs content-based approaches.",
                "Walk through the complete process of A/B testing — from sample size calculation to hypothesis testing, stopping rules, and result interpretation.",
                "Design a data pipeline that processes 100GB of streaming data per day — from ingestion to transformation to real-time dashboards.",
                "I have time series data from IoT sensors. Walk through detection of seasonality, anomaly detection, and forecasting using Prophet/SARIMA.",
                "Design a fraud detection system for credit card transactions — from feature engineering of transaction sequences to model deployment and monitoring.",
                "Walk through building a customer segmentation analysis using K-means clustering — from feature selection to elbow method to cluster profiling.",
                "Design a sentiment analysis pipeline for social media data — from data collection to preprocessing to model training and deployment as API.",
                "I have imbalanced dataset (99% negative, 1% positive). Walk through resampling techniques, cost-sensitive learning, and proper evaluation metrics.",
                "Design a feature store architecture for an ML platform — from feature computation to serving, point-in-time correctness, and monitoring.",
                "Walk through the complete ML experiment tracking setup using MLflow — from logging parameters to model registry to production deployment.",
                "Design a data quality monitoring system that detects drift, missing values, and schema changes in production data pipelines.",
                "I need to build a text classification system for 500 categories with only 100 examples per category. Walk through few-shot learning approaches.",
                "Design an automated machine learning pipeline that handles feature selection, hyperparameter tuning, and model ensembling automatically.",
            ],
        },
        {
            "name": "system_design",
            "system": "You are a senior system architect. Design scalable, production-ready systems with clear tradeoff analysis. Cover components, data flow, and failure modes.",
            "prompts": [
                "Design YouTube from scratch — video upload, transcoding, recommendation, streaming at global scale. Discuss storage, CDN, and database choices.",
                "Design a URL shortener like TinyURL — discuss hashing strategies, database sharding, redirect performance, and analytics tracking.",
                "Design WhatsApp — real-time messaging, group chats, end-to-end encryption, message sync across devices, and offline delivery.",
                "Design Uber — rider/driver matching, real-time location tracking, surge pricing, ETA computation, and trip history at global scale.",
                "Design a distributed key-value store like Redis at scale — discuss consistent hashing, replication, partitioning, and fault tolerance.",
                "Design Netflix — content delivery network architecture, recommendation engine, video encoding pipeline, and personalization system.",
                "Design Twitter — tweet storage, timeline generation, fan-out approach (push vs pull), search, and trending topics at global scale.",
                "Design a real-time collaborative editor like Google Docs — operational transforms, conflict resolution, presence awareness, and offline support.",
                "Design an e-commerce system like Amazon — product catalog, shopping cart, order processing, payment, and inventory management.",
                "Design Airbnb — property search with geospatial indexing, booking system with concurrency control, reviews, and payment processing.",
                "Design a notification system that handles 10M+ push, email, and SMS notifications per day with delivery guarantees and preferences.",
                "Design a rate-limiting system for a public API that supports per-user, per-IP, and per-endpoint limits at global scale.",
                "Design a distributed file system like Google File System or HDFS — architecture, replication, consistency, and failure recovery.",
                "Design an API gateway — routing, authentication, rate limiting, caching, logging, and canary deployments for microservices.",
                "Design a live streaming platform like Twitch — ingest, transcoding, low-latency delivery, chat integration, and VOD archiving.",
            ],
        },
    ]

    total_generated = 0
    sem = asyncio.Semaphore(4)  # Run 4 concurrent generations

    async def generate_and_save(task_type: str, system_prompt: str, prompt: str, idx: int, file_handle):
        """Generate a single sample using parallel racing and save to file."""
        async with sem:
            try:
                response = await generate_parallel_async(
                    prompt,
                    system_prompt=system_prompt,
                )

                row = {
                    "id": f"{task_type}_{idx}_0",
                    "task_type": task_type,
                    "instruction": prompt,
                    "output": response,
                    "source": "parallel_llm",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                line = json.dumps(row, ensure_ascii=False) + "\n"
                file_handle.write(line)
                file_handle.flush()

                return {"idx": idx, "success": True, "size": len(line)}
            except Exception as e:
                return {"idx": idx, "success": False, "error": str(e)[:100]}

    for config in task_configs:
        task_type = config["name"]
        try:
            await broadcast("LOG", {"level": "info", "msg": f"[Synthetic-LLM] Generating: {task_type} ({len(config['prompts'])} prompts via parallel racing)"})
            SYSTEM_STATE["agents"]["code"]["status"] = "active"
            SYSTEM_STATE["agents"]["code"]["last_action"] = f"Generating {task_type} (racing all providers)"

            out_file = out_dir / f"{task_type}.jsonl"
            with open(out_file, "w", encoding="utf-8") as f:
                # Create ALL generation tasks upfront for concurrent execution
                tasks = []
                for i, prompt in enumerate(config["prompts"]):
                    task = asyncio.create_task(
                        generate_and_save(task_type, config["system"], prompt, i, f)
                    )
                    tasks.append(task)

                # Wait for all to complete
                results = await asyncio.gather(*tasks, return_exceptions=False)

            # Summarize results
            success_count = sum(1 for r in results if r.get("success"))
            total_size = sum(r.get("size", 0) for r in results if r.get("success"))
            total_generated += success_count

            SYSTEM_STATE["stats"]["synthetic_rows"] = total_generated
            await broadcast("LOG", {
                "level": "success",
                "msg": f"[Synthetic-LLM] [OK] {task_type}: {success_count}/{len(config['prompts'])} samples saved ({total_size/1024:.1f} KB)"
            })
        except Exception as e:
            SYSTEM_STATE["stats"]["errors"] += 1
            await broadcast("LOG", {
                "level": "error",
                "msg": f"[Synthetic-LLM] ✗ {task_type}: {str(e)[:120]}"
            })

    SYSTEM_STATE["phases"][phase] = "COMPLETE"
    SYSTEM_STATE["stats"]["active_tasks"] -= 1
    SYSTEM_STATE["stats"]["completed_tasks"] += 1
    SYSTEM_STATE["agents"]["code"]["status"] = "idle"
    await broadcast("PHASE_COMPLETE", {"phase": phase})


async def worker_rag_index():
    """Index collected data into the RAG pipeline using continuous pipeline indexer.
    Uses RAGPipelineIndexer to incrementally scan, chunk, embed, and index
    all JSONL data files into ChromaDB + BM25 + KnowledgeGraph.
    """
    from src.rag.pipeline_indexer import RAGPipelineIndexer

    phase = "RAG Pipeline Indexing"
    SYSTEM_STATE["phases"][phase] = "WAITING"
    await broadcast("LOG", {"level": "info", "msg": "[RAG] Waiting for data collection to generate files..."})

    # Wait until some data is available
    await asyncio.sleep(30)

    SYSTEM_STATE["phases"][phase] = "RUNNING"
    SYSTEM_STATE["stats"]["active_tasks"] += 1
    await broadcast("PHASE_START", {"phase": phase})

    SYSTEM_STATE["agents"]["orchestrator"]["status"] = "active"
    SYSTEM_STATE["agents"]["orchestrator"]["last_action"] = "RAG Indexing"

    # Build progress callback for live broadcasting
    async def on_progress(progress: dict):
        total = progress.get("total", 0)
        indexed = progress.get("indexed", 0)
        source = progress.get("source", "unknown")
        SYSTEM_STATE["stats"]["rag_indexed"] = indexed
        await broadcast("PROGRESS", {
            "phase": phase,
            "label": f"Embedding {source}",
            "count": indexed,
            "total": total,
        })

    try:
        indexer = RAGPipelineIndexer(
            data_dir=str(BASE_DATA_DIR),
            progress_callback=on_progress,
        )

        # Run index pass (scans all JSONL files, indexes new/modified content)
        await broadcast("LOG", {"level": "info", "msg": f"[RAG] Scanning {BASE_DATA_DIR} for new JSONL files..."})

        stats = await indexer.index_all()

        if stats["chunks_indexed"] > 0:
            await broadcast("LOG", {
                "level": "success",
                "msg": f"[RAG] [OK] Indexed {stats['chunks_indexed']} new chunks from {stats['files_indexed']} files "
                        f"(via {stats['lines_indexed']} JSONL lines. Total in DB: {stats.get('total_chunks', 0)})"
            })

            # Update agent state
            SYSTEM_STATE["agents"]["orchestrator"]["last_action"] = (
                f"Indexed {stats['chunks_indexed']} chunks. Total: {stats.get('total_chunks', 0)}"
            )
        else:
            await broadcast("LOG", {
                "level": "info",
                "msg": "[RAG] ~ No new files to index (all caught up)"
            })

        # Show collection stats
        try:
            import chromadb
            c = chromadb.PersistentClient(path=str(ROOT / "python_brain_godmode"))
            col = c.get_collection("python_godmode")
            await broadcast("LOG", {
                "level": "info",
                "msg": f"[RAG] ChromaDB collection 'python_godmode': {col.count():,} total chunks indexed"
            })
        except Exception:
            pass

    except ImportError as e:
        await broadcast("LOG", {
            "level": "warn",
            "msg": f"[RAG] ✗ Dependencies missing: {e}. Install: pip install chromadb sentence-transformers"
        })
    except Exception as e:
        SYSTEM_STATE["stats"]["errors"] += 1
        await broadcast("LOG", {"level": "error", "msg": f"[RAG] ✗ Indexing failed: {str(e)[:200]}"})
        logger.error(f"[RAG] Indexing error: {e}")

    SYSTEM_STATE["phases"][phase] = "COMPLETE"
    SYSTEM_STATE["stats"]["active_tasks"] -= 1
    SYSTEM_STATE["stats"]["completed_tasks"] += 1
    SYSTEM_STATE["agents"]["orchestrator"]["status"] = "idle"
    await broadcast("PHASE_COMPLETE", {"phase": phase})


# ═══════════════════════════════════════════════════
# NEW DATA COLLECTION WORKERS (10 parallel sources)
# ═══════════════════════════════════════════════════


async def worker_semantic_scholar():
    """Collect research papers from Semantic Scholar (220M+ papers). Free API, no key needed."""
    phase = "Semantic Scholar Papers"
    SYSTEM_STATE["phases"][phase] = "RUNNING"
    SYSTEM_STATE["stats"]["active_tasks"] += 1
    await broadcast("PHASE_START", {"phase": phase})

    import aiohttp

    topics = ["transformer neural network", "large language model", "reinforcement learning",
              "diffusion model", "graph neural network", "federated learning",
              "deep learning", "convolutional neural network", "recurrent neural network",
              "generative adversarial network", "autoencoder", "attention mechanism",
              "transfer learning", "meta learning", "few-shot learning", "self-supervised learning",
              "contrastive learning", "representation learning", "multi-task learning",
              "online learning", "ensemble learning", "active learning", "semi-supervised learning",
              "knowledge distillation", "neural architecture search", "bayesian deep learning",
              "probabilistic graphical model", "markov decision process", "monte carlo method",
              "variational inference", "gaussian process", "causal inference", "time series analysis",
              "anomaly detection", "dimensionality reduction", "feature selection", "clustering algorithm",
              "classification algorithm", "regression analysis", "optimization method"]

    async with aiohttp.ClientSession() as session:
        for topic in topics:
            try:
                await broadcast("LOG", {"level": "info", "msg": f"[SemanticScholar] Searching: {topic}"})
                SYSTEM_STATE["agents"]["retrieval"]["status"] = "active"
                SYSTEM_STATE["agents"]["retrieval"]["last_action"] = f"SemanticScholar: {topic}"

                out_dir = BASE_DATA_DIR / "semantic_scholar"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"{topic.replace(' ', '_')}.jsonl"
                if should_skip(out_file, 100):
                    await broadcast("LOG", {"level": "info", "msg": f"[SemanticScholar] Skipping {topic} (D: drive has data)"})
                    continue

                offset = 0
                total = 0
                limit = 100

                while total < 1000:
                    url = f"https://api.semanticscholar.org/graph/v1/paper/search"
                    params = {
                        "query": topic,
                        "limit": limit,
                        "offset": offset,
                        "fields": "title,abstract,year,citationCount,externalIds,venue,authors"
                    }
                    headers = {"Accept": "application/json"}

                    async with session.get(url, params=params, headers=headers) as resp:
                        if resp.status == 429:
                            await broadcast("LOG", {"level": "warn", "msg": f"[SemanticScholar] Rate limited, backing off..."})
                            await asyncio.sleep(5)
                            continue
                        if resp.status != 200:
                            break
                        data = await resp.json()

                    papers = data.get("data", [])
                    if not papers:
                        break

                    with open(out_file, "a", encoding="utf-8") as f:
                        for p in papers:
                            authors = [a.get("name", "") for a in (p.get("authors") or [])]
                            record = {
                                "id": p.get("paperId", ""),
                                "title": p.get("title", ""),
                                "abstract": p.get("abstract", "") or "",
                                "year": p.get("year"),
                                "citations": p.get("citationCount", 0),
                                "venue": p.get("venue", ""),
                                "authors": authors[:10],
                                "source": "semantic_scholar"
                            }
                            f.write(json.dumps(record) + "\n")
                            total += 1

                    offset += limit
                    SYSTEM_STATE["stats"]["semantic_scholar"] = total
                    await broadcast("PROGRESS", {"phase": phase, "label": topic, "count": total})
                    await asyncio.sleep(1)

                await broadcast("LOG", {"level": "success", "msg": f"[SemanticScholar] {topic}: {total} papers"})
            except Exception as e:
                SYSTEM_STATE["stats"]["errors"] += 1
                await broadcast("LOG", {"level": "error", "msg": f"[SemanticScholar] {topic}: {str(e)[:120]}"})

    SYSTEM_STATE["phases"][phase] = "COMPLETE"
    SYSTEM_STATE["stats"]["active_tasks"] -= 1
    SYSTEM_STATE["stats"]["completed_tasks"] += 1
    SYSTEM_STATE["agents"]["retrieval"]["status"] = "idle"
    await broadcast("PHASE_COMPLETE", {"phase": phase})


async def worker_crossref():
    """Collect scholarly works from CrossRef (155M+ records). Free REST API."""
    phase = "CrossRef Works"
    SYSTEM_STATE["phases"][phase] = "RUNNING"
    SYSTEM_STATE["stats"]["active_tasks"] += 1
    await broadcast("PHASE_START", {"phase": phase})

    import aiohttp

    topics = ["machine learning", "deep learning", "computer science", "data science",
              "artificial intelligence", "software engineering", "computer engineering",
              "information technology", "computational mathematics", "statistical modeling",
              "algorithm design", "data structure", "network security", "database management",
              "web development", "mobile computing", "human-computer interaction",
              "computer graphics", "scientific computing", "computational physics"]
    email = os.environ.get("CROSSREF_EMAIL", "user@example.com")

    async with aiohttp.ClientSession() as session:
        for topic in topics:
            try:
                await broadcast("LOG", {"level": "info", "msg": f"[CrossRef] Searching: {topic}"})
                SYSTEM_STATE["agents"]["docs"]["status"] = "active"
                SYSTEM_STATE["agents"]["docs"]["last_action"] = f"CrossRef: {topic}"

                out_dir = BASE_DATA_DIR / "crossref"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"{topic.replace(' ', '_')}.jsonl"
                if should_skip(out_file, 100):
                    await broadcast("LOG", {"level": "info", "msg": f"[CrossRef] Skipping {topic} (D: drive has data)"})
                    continue

                cursor = "*"
                total = 0

                while total < 10000:  # MASSIVE: 10K per CrossRef topic
                    params = {
                        "query": topic,
                        "rows": 100,
                        "cursor": cursor,
                        "mailto": email,
                        "filter": "type:journal-article,type:proceedings-article",
                    }
                    headers = {"Accept": "application/json"}

                    async with session.get("https://api.crossref.org/works", params=params, headers=headers) as resp:
                        if resp.status == 429:
                            await asyncio.sleep(3)
                            continue
                        data = await resp.json()

                    items = data.get("message", {}).get("items", [])
                    if not items:
                        break

                    with open(out_file, "a", encoding="utf-8") as f:
                        for item in items:
                            authors = [a.get("given", "") + " " + a.get("family", "") for a in (item.get("author") or [])]
                            record = {
                                "id": item.get("DOI", ""),
                                "title": (item.get("title") or [""])[0],
                                "abstract": (item.get("abstract") or "")[:3000],
                                "year": item.get("published-print", {}).get("date-parts", [[None]])[0][0],
                                "citations": item.get("is-referenced-by-count", 0),
                                "authors": authors[:10],
                                "publisher": item.get("publisher", ""),
                                "source": "crossref",
                            }
                            f.write(json.dumps(record) + "\n")
                            total += 1

                    cursor = data.get("message", {}).get("next-cursor")
                    if not cursor:
                        break

                    SYSTEM_STATE["stats"]["crossref"] = total
                    await broadcast("PROGRESS", {"phase": phase, "label": topic, "count": total})
                    await asyncio.sleep(0.5)

                await broadcast("LOG", {"level": "success", "msg": f"[CrossRef] {topic}: {total} works"})
            except Exception as e:
                SYSTEM_STATE["stats"]["errors"] += 1
                await broadcast("LOG", {"level": "error", "msg": f"[CrossRef] {topic}: {str(e)[:120]}"})

    SYSTEM_STATE["phases"][phase] = "COMPLETE"
    SYSTEM_STATE["stats"]["active_tasks"] -= 1
    SYSTEM_STATE["stats"]["completed_tasks"] += 1
    SYSTEM_STATE["agents"]["docs"]["status"] = "idle"
    await broadcast("PHASE_COMPLETE", {"phase": phase})


async def worker_pubmed():
    """Collect biomedical papers from PubMed/MEDLINE via NCBI E-utilities. Free API."""
    phase = "PubMed Papers"
    SYSTEM_STATE["phases"][phase] = "RUNNING"
    SYSTEM_STATE["stats"]["active_tasks"] += 1
    await broadcast("PHASE_START", {"phase": phase})

    import aiohttp
    import xml.etree.ElementTree as ET

    queries = ["deep learning genomics", "machine learning drug discovery", "AI protein folding",
               "neural network medical imaging", "natural language processing clinical",
               "computational biology", "bioinformatics algorithms", "machine learning cancer",
               "AI drug design", "deep learning protein structure", "neural network diagnostics",
               "NLP electronic health records", "computer vision pathology", "AI radiology",
               "deep learning genomics sequence", "machine learning epidemiology",
               "AI clinical trials", "computational neuroscience", "deep learning microscopy",
               "machine learning cardiology", "AI neurology diagnosis"]

    async with aiohttp.ClientSession() as session:
        for query in queries:
            try:
                await broadcast("LOG", {"level": "info", "msg": f"[PubMed] Searching: {query}"})
                SYSTEM_STATE["agents"]["performance"]["status"] = "active"
                SYSTEM_STATE["agents"]["performance"]["last_action"] = f"PubMed: {query}"

                out_dir = BASE_DATA_DIR / "pubmed"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"{query.replace(' ', '_')}.jsonl"
                if should_skip(out_file, 100):
                    await broadcast("LOG", {"level": "info", "msg": f"[PubMed] Skipping {query} (D: drive has data)"})
                    continue

                # ESearch: get IDs
                search_params = {
                    "db": "pubmed",
                    "term": query,
                    "retmax": 10000,  # MAX: 10K papers per query
                    "retmode": "json",
                    "sort": "relevance",
                }
                async with session.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi", params=search_params) as resp:
                    search_data = await resp.json()

                id_list = search_data.get("esearchresult", {}).get("idlist", [])
                if not id_list:
                    continue

                # EFetch: get details in batches of 50
                for batch_start in range(0, len(id_list), 50):
                    batch_ids = id_list[batch_start:batch_start+50]
                    fetch_params = {
                        "db": "pubmed",
                        "id": ",".join(batch_ids),
                        "retmode": "xml",
                        "rettype": "abstract",
                    }
                    async with session.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi", params=fetch_params) as resp:
                        xml_text = await resp.text()

                    root = ET.fromstring(xml_text)
                    with open(out_file, "a", encoding="utf-8") as f:
                        for article in root.findall(".//PubmedArticle"):
                            try:
                                pmid = article.findtext("./MedlineCitation/PMID", "")
                                title = article.findtext(".//ArticleTitle", "") or ""
                                abstract_parts = []
                                for ab in article.findall(".//AbstractText"):
                                    label = ab.get("Label", "")
                                    text = ab.text or ""
                                    if label:
                                        abstract_parts.append(f"{label}: {text}")
                                    else:
                                        abstract_parts.append(text)
                                abstract = " ".join(abstract_parts)
                                year = article.findtext(".//PubDate/Year", "")
                                journal = article.findtext(".//Journal/Title", "")

                                record = {
                                    "id": f"pmid:{pmid}",
                                    "title": title.strip(),
                                    "abstract": abstract.strip()[:3000],
                                    "year": year,
                                    "journal": journal,
                                    "source": "pubmed",
                                }
                                f.write(json.dumps(record) + "\n")
                            except Exception:
                                continue

                    await broadcast("PROGRESS", {"phase": phase, "label": query, "count": batch_start + 50})
                    await asyncio.sleep(0.5)

                SYSTEM_STATE["stats"]["pubmed"] = len(id_list)
                await broadcast("LOG", {"level": "success", "msg": f"[PubMed] {query}: {len(id_list)} papers"})
            except Exception as e:
                SYSTEM_STATE["stats"]["errors"] += 1
                await broadcast("LOG", {"level": "error", "msg": f"[PubMed] {query}: {str(e)[:120]}"})

    SYSTEM_STATE["phases"][phase] = "COMPLETE"
    SYSTEM_STATE["stats"]["active_tasks"] -= 1
    SYSTEM_STATE["stats"]["completed_tasks"] += 1
    SYSTEM_STATE["agents"]["performance"]["status"] = "idle"
    await broadcast("PHASE_COMPLETE", {"phase": phase})


async def worker_wikipedia():
    """Collect Wikipedia articles on AI/ML/programming topics. Free MediaWiki API."""
    phase = "Wikipedia Articles"
    SYSTEM_STATE["phases"][phase] = "RUNNING"
    SYSTEM_STATE["stats"]["active_tasks"] += 1
    await broadcast("PHASE_START", {"phase": phase})

    import aiohttp

    categories = [
        "Artificial intelligence", "Machine learning", "Deep learning",
        "Natural language processing", "Computer vision", "Programming languages",
        "Data structures", "Algorithms", "Software engineering", "Python (programming language)",
        "Neural network", "Reinforcement learning", "Data science", "Database",
        "Operating system", "Computer network", "Compiler", "Cryptography",
        "Computational biology", "Quantum computing", "Robotics", "Computer security",
        "Computer graphics", "Information retrieval", "Human-computer interaction",
        "Distributed computing", "Parallel computing", "Cloud computing",
        "Embedded system", "Computer architecture", "Formal verification",
        "Programming paradigm", "Software testing", "Web development", "Mobile app",
        "Computer simulation", "Numerical analysis", "Optimization", "Game theory",
        "Computer vision", "Pattern recognition", "Data mining", "Information theory",
        "Control theory", "Signal processing", "Computational linguistics",
        "Knowledge management", "Business intelligence", "Big data",
        "Internet of things", "Virtual reality", "Augmented reality",
    ]

    async with aiohttp.ClientSession() as session:
        for category in categories:
            try:
                await broadcast("LOG", {"level": "info", "msg": f"[Wikipedia] Fetching: {category}"})
                SYSTEM_STATE["agents"]["docs"]["status"] = "active"
                SYSTEM_STATE["agents"]["docs"]["last_action"] = f"Wikipedia: {category}"

                out_dir = BASE_DATA_DIR / "wikipedia"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"{category.replace(' ', '_').lower()}.jsonl"
                if should_skip(out_file, 50):
                    await broadcast("LOG", {"level": "info", "msg": f"[Wikipedia] Skipping {category} (D: drive has data)"})
                    continue

                # Search for pages in this category
                search_params = {
                    "action": "query",
                    "list": "search",
                    "srsearch": category,
                    "srlimit": 200,  # 200 articles per category  # 200 articles per category
                    "format": "json",
                    "srprop": "snippet|titlesnippet",
                }
                async with session.get("https://en.wikipedia.org/w/api.php", params=search_params) as resp:
                    search_data = await resp.json()

                pages = search_data.get("query", {}).get("search", [])
                if not pages:
                    continue

                total = 0
                page_titles = [p["title"] for p in pages]

                # Fetch full content for each page (in batches of 10)
                for batch_start in range(0, len(page_titles), 10):
                    batch_titles = page_titles[batch_start:batch_start+10]
                    content_params = {
                        "action": "query",
                        "titles": "|".join(batch_titles),
                        "prop": "extracts|info",
                        "exintro": True,
                        "explaintext": True,
                        "inprop": "url",
                        "format": "json",
                        "redirects": 1,
                    }
                    async with session.get("https://en.wikipedia.org/w/api.php", params=content_params) as resp:
                        content_data = await resp.json()

                    pages_data = content_data.get("query", {}).get("pages", {})

                    with open(out_file, "a", encoding="utf-8") as f:
                        for page_id, page_data in pages_data.items():
                            if page_id == "-1":
                                continue
                            title = page_data.get("title", "")
                            extract = page_data.get("extract", "") or ""
                            if len(extract) < 100:
                                continue

                            record = {
                                "id": f"wiki:{page_id}",
                                "title": title,
                                "text": extract[:5000],
                                "url": page_data.get("fullurl", ""),
                                "category": category,
                                "source": "wikipedia",
                            }
                            f.write(json.dumps(record) + "\n")
                            total += 1

                    SYSTEM_STATE["stats"]["wikipedia"] = total
                    await broadcast("PROGRESS", {"phase": phase, "label": category, "count": total})
                    await asyncio.sleep(0.3)

                await broadcast("LOG", {"level": "success", "msg": f"[Wikipedia] {category}: {total} articles"})
            except Exception as e:
                SYSTEM_STATE["stats"]["errors"] += 1
                await broadcast("LOG", {"level": "error", "msg": f"[Wikipedia] {category}: {str(e)[:120]}"})

    SYSTEM_STATE["phases"][phase] = "COMPLETE"
    SYSTEM_STATE["stats"]["active_tasks"] -= 1
    SYSTEM_STATE["stats"]["completed_tasks"] += 1
    SYSTEM_STATE["agents"]["docs"]["status"] = "idle"
    await broadcast("PHASE_COMPLETE", {"phase": phase})


async def worker_gutenberg():
    """Collect free eBooks metadata from Project Gutenberg. Free open catalog."""
    phase = "Project Gutenberg"
    SYSTEM_STATE["phases"][phase] = "RUNNING"
    SYSTEM_STATE["stats"]["active_tasks"] += 1
    await broadcast("PHASE_START", {"phase": phase})

    import aiohttp
    import re

    topics = ["Computer science", "Programming", "Mathematics", "Science",
              "Technology", "Education", "Logic", "Physics", "Astronomy",
              "Chemistry", "Biology", "Engineering", "Psychology", "Philosophy",
              "Economics", "History", "Medicine", "Music", "Art",
              "Language", "Electronics", "Machine learning", "Robotics",
              "Cryptography", "Games", "Architecture", "Agriculture"]

    async with aiohttp.ClientSession() as session:
        for topic in topics:
            try:
                await broadcast("LOG", {"level": "info", "msg": f"[Gutenberg] Fetching: {topic}"})

                out_dir = BASE_DATA_DIR / "gutenberg"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"{topic.lower().replace(' ', '_')}.jsonl"
                if should_skip(out_file, 20):
                    await broadcast("LOG", {"level": "info", "msg": f"[Gutenberg] Skipping {topic} (D: drive has data)"})
                    continue

                # Search Gutenberg catalog
                search_params = {
                    "query": topic,
                    "limit": 400,  # Max 400 books per query
                    "mime_type": "text/plain",
                }
                async with session.get("https://gutendex.com/books", params=search_params) as resp:
                    data = await resp.json()

                books = data.get("results", [])
                total = 0

                with open(out_file, "a", encoding="utf-8") as f:
                    for book in books:
                        formats = book.get("formats", {})
                        text_url = formats.get("text/plain; charset=us-ascii", "") or formats.get("text/plain", "")
                        if not text_url:
                            continue

                        # Download actual text content (first 2000 chars as sample)
                        text_content = ""
                        try:
                            async with session.get(text_url, timeout=aiohttp.ClientTimeout(total=10)) as tf:
                                raw = await tf.read()
                            # Decode with error handling
                            text_content = raw.decode("utf-8", errors="replace")[:5000]
                        except Exception:
                            pass

                        subjects = book.get("subjects", [])
                        bookshelves = book.get("bookshelves", [])
                        authors = [a.get("name", "") for a in (book.get("authors") or [])]

                        record = {
                            "id": f"gutenberg:{book.get('id')}",
                            "title": book.get("title", ""),
                            "text": text_content,
                            "authors": authors[:5],
                            "subjects": subjects,
                            "bookshelves": bookshelves,
                            "source": "gutenberg",
                        }
                        f.write(json.dumps(record) + "\n")
                        total += 1

                SYSTEM_STATE["stats"]["gutenberg"] = total
                await broadcast("LOG", {"level": "success", "msg": f"[Gutenberg] {topic}: {total} books"})
            except Exception as e:
                SYSTEM_STATE["stats"]["errors"] += 1
                await broadcast("LOG", {"level": "error", "msg": f"[Gutenberg] {topic}: {str(e)[:120]}"})

    SYSTEM_STATE["phases"][phase] = "COMPLETE"
    SYSTEM_STATE["stats"]["active_tasks"] -= 1
    SYSTEM_STATE["stats"]["completed_tasks"] += 1
    await broadcast("PHASE_COMPLETE", {"phase": phase})


async def worker_github_trending():
    """Collect trending GitHub repos + popular Python repos. Uses public GitHub API."""
    phase = "GitHub Trending"
    SYSTEM_STATE["phases"][phase] = "RUNNING"
    SYSTEM_STATE["stats"]["active_tasks"] += 1
    await broadcast("PHASE_START", {"phase": phase})

    import aiohttp
    from urllib.parse import quote

    queries = [
        "language:python stars:>100",
        "language:python stars:>1000",
        "language:python stars:>5000",
        "language:javascript stars:>100",
        "language:javascript stars:>1000",
        "language:typescript stars:>100",
        "language:typescript stars:>1000",
        "language:rust stars:>100",
        "language:rust stars:>1000",
        "language:go stars:>100",
        "language:go stars:>1000",
        "language:java stars:>1000",
        "language:c++ stars:>100",
        "language:c stars:>100",
        "language:swift stars:>100",
        "language:kotlin stars:>100",
        "language:scala stars:>100",
        "language:haskell stars:>50",
        "language:clojure stars:>50",
        "language:julia stars:>50",
        "language:r stars:>100",
        "language:lua stars:>100",
        "language:elixir stars:>50",
        "language:solidity stars:>50",
        "machine-learning",
        "deep-learning",
        "neural-network",
        "artificial-intelligence",
        "natural-language-processing",
        "computer-vision",
        "reinforcement-learning",
        "awesome-list",
        "tutorial",
        "cheatsheet",
    ]

    async with aiohttp.ClientSession() as session:
        for query in queries:
            try:
                await broadcast("LOG", {"level": "info", "msg": f"[GitHub] Searching: {query[:40]}..."})
                SYSTEM_STATE["agents"]["code"]["status"] = "active"
                SYSTEM_STATE["agents"]["code"]["last_action"] = f"GitHub: {query[:30]}"

                out_dir = BASE_DATA_DIR / "github"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"repos_{query.split(':')[0].replace(' ', '_')}.jsonl"
                if should_skip(out_file, 100):
                    await broadcast("LOG", {"level": "info", "msg": f"[GitHub] Skipping {query[:40]} (D: drive has data)"})
                    continue

                for page in range(1, 21):  # 20 pages = 600 repos per query
                    url = f"https://api.github.com/search/repositories?q={quote(query)}&sort=stars&order=desc&page={page}&per_page=30"
                    headers = {"Accept": "application/vnd.github.v3+json"}
                    # Use token if available
                    gh_token = os.environ.get("GITHUB_TOKEN")
                    if gh_token:
                        headers["Authorization"] = f"Bearer {gh_token}"

                    async with session.get(url, headers=headers) as resp:
                        if resp.status in (403, 429):
                            await broadcast("LOG", {"level": "warn", "msg": f"[GitHub] Rate limited on page {page}"})
                            await asyncio.sleep(60)
                            continue
                        if resp.status != 200:
                            break
                        data = await resp.json()

                    repos = data.get("items", [])
                    if not repos:
                        break

                    with open(out_file, "a", encoding="utf-8") as f:
                        for r in repos:
                            # Try to fetch README
                            readme_text = ""
                            try:
                                readme_url = f"https://api.github.com/repos/{r['full_name']}/readme"
                                async with session.get(readme_url, headers={**headers, "Accept": "application/vnd.github.v3.raw"}) as rf:
                                    if rf.status == 200:
                                        readme_text = await rf.text()
                            except Exception:
                                pass

                            record = {
                                "id": r.get("full_name", ""),
                                "name": r.get("full_name", ""),
                                "description": r.get("description", "") or "",
                                "readme": readme_text[:3000],
                                "stars": r.get("stargazers_count", 0),
                                "language": r.get("language", ""),
                                "topics": r.get("topics", []),
                                "url": r.get("html_url", ""),
                                "forks": r.get("forks_count", 0),
                                "created": r.get("created_at", ""),
                                "source": "github",
                            }
                            f.write(json.dumps(record) + "\n")

                    SYSTEM_STATE["stats"]["github"] += len(repos)
                    await broadcast("PROGRESS", {"phase": phase, "label": query[:20], "count": page * 30})
                    await asyncio.sleep(2)

                await broadcast("LOG", {"level": "success", "msg": f"[GitHub] Query collected: {query[:40]}"})
            except Exception as e:
                SYSTEM_STATE["stats"]["errors"] += 1
                await broadcast("LOG", {"level": "error", "msg": f"[GitHub] {str(e)[:120]}"})

    SYSTEM_STATE["phases"][phase] = "COMPLETE"
    SYSTEM_STATE["stats"]["active_tasks"] -= 1
    SYSTEM_STATE["stats"]["completed_tasks"] += 1
    SYSTEM_STATE["agents"]["code"]["status"] = "idle"
    await broadcast("PHASE_COMPLETE", {"phase": phase})


async def worker_doaj():
    """Collect open access articles from DOAJ (Directory of Open Access Journals). 20M+ articles."""
    phase = "DOAJ Articles"
    SYSTEM_STATE["phases"][phase] = "RUNNING"
    SYSTEM_STATE["stats"]["active_tasks"] += 1
    await broadcast("PHASE_START", {"phase": phase})

    import aiohttp

    topics = ["computer science", "engineering", "mathematics", "technology",
              "artificial intelligence", "data science", "physics", "biology",
              "chemistry", "medicine", "psychology", "economics", "sociology",
              "political science", "education", "philosophy", "linguistics",
              "geography", "environmental science", "materials science",
              "neuroscience", "immunology", "genetics", "astronomy",
              "geology", "oceanography", "ecology", "archaeology",
              "anthropology", "statistics", "engineering design"]

    async with aiohttp.ClientSession() as session:
        for topic in topics:
            try:
                await broadcast("LOG", {"level": "info", "msg": f"[DOAJ] Searching: {topic}"})

                out_dir = BASE_DATA_DIR / "doaj"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"{topic.replace(' ', '_')}.jsonl"
                if should_skip(out_file, 100):
                    await broadcast("LOG", {"level": "info", "msg": f"[DOAJ] Skipping {topic} (D: drive has data)"})
                    continue

                page = 1
                total = 0

                while total < 10000:  # MASSIVE: 10K articles per topic
                    params = {
                        "query": topic,
                        "page": page,
                        "pageSize": 100,
                    }
                    async with session.get("https://doaj.org/api/v3/search/articles/", params=params) as resp:
                        if resp.status != 200:
                            break
                        data = await resp.json()

                    results = data.get("results", [])
                    if not results:
                        break

                    with open(out_file, "a", encoding="utf-8") as f:
                        for r in results:
                            biblio = r.get("bibjson", {})
                            authors = [a.get("name", "") for a in (biblio.get("author") or [])]
                            record = {
                                "id": r.get("id", ""),
                                "title": biblio.get("title", ""),
                                "abstract": (biblio.get("abstract", "") or "")[:3000],
                                "year": biblio.get("year", ""),
                                "authors": authors[:10],
                                "journal": biblio.get("journal", {}).get("title", ""),
                                "source": "doaj",
                            }
                            f.write(json.dumps(record) + "\n")
                            total += 1

                    page += 1
                    SYSTEM_STATE["stats"]["doaj"] = total
                    await broadcast("PROGRESS", {"phase": phase, "label": topic, "count": total})
                    await asyncio.sleep(0.5)

                await broadcast("LOG", {"level": "success", "msg": f"[DOAJ] {topic}: {total} articles"})
            except Exception as e:
                SYSTEM_STATE["stats"]["errors"] += 1
                await broadcast("LOG", {"level": "error", "msg": f"[DOAJ] {topic}: {str(e)[:120]}"})

    SYSTEM_STATE["phases"][phase] = "COMPLETE"
    SYSTEM_STATE["stats"]["active_tasks"] -= 1
    SYSTEM_STATE["stats"]["completed_tasks"] += 1
    await broadcast("PHASE_COMPLETE", {"phase": phase})


async def worker_biorxiv():
    """Collect latest bioRxiv/medRxiv preprints. Free API."""
    phase = "Preprint Servers"
    SYSTEM_STATE["phases"][phase] = "RUNNING"
    SYSTEM_STATE["stats"]["active_tasks"] += 1
    await broadcast("PHASE_START", {"phase": phase})

    import aiohttp
    import xml.etree.ElementTree as ET
    from datetime import timedelta

    servers = [
        ("biorxiv", "https://api.biorxiv.org/details/biorxiv"),
        ("medrxiv", "https://api.biorxiv.org/details/medrxiv"),
    ]

    categories = ["AI", "ML", "bioinformatics", "computational-biology", "neuroscience"]

    async with aiohttp.ClientSession() as session:
        for server_name, server_url in servers:
            for category in categories:
                try:
                    await broadcast("LOG", {"level": "info", "msg": f"[{server_name}] Fetching: {category}"})

                    out_dir = BASE_DATA_DIR / "preprints" / server_name
                    out_dir.mkdir(parents=True, exist_ok=True)
                    out_file = out_dir / f"{category}.jsonl"
                    if should_skip(out_file, 50):
                        await broadcast("LOG", {"level": "info", "msg": f"[{server_name}] Skipping {category} (D: drive has data)"})
                        continue

                    # bioRxiv API: /details/{server}/{start_date}/{end_date}/{cursor}
                    # Use recent date range
                    end = datetime.now(timezone.utc)
                    start = end - timedelta(days=180)

                    url = f"{server_url}/{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}/0"

                    async with session.get(url) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()

                    articles = data.get("collection", [])
                    total = 0

                    with open(out_file, "a", encoding="utf-8") as f:
                        for article in articles:
                            # Filter by category keyword
                            title = article.get("title", "") or ""
                            abstract = article.get("abstract", "") or ""
                            category_search = category.lower().replace("-", " ")
                            combined = (title + " " + abstract).lower()
                            if category_search not in combined:
                                continue

                            record = {
                                "id": f"{server_name}:{article.get('doi', '')}",
                                "title": title,
                                "abstract": abstract[:3000],
                                "authors": (article.get("authors", "") or "").split(";")[:10],
                                "date": article.get("date", ""),
                                "category": article.get("category", ""),
                                "source": server_name,
                            }
                            f.write(json.dumps(record) + "\n")
                            total += 1

                    SYSTEM_STATE["stats"]["preprints"] = total
                    await broadcast("LOG", {"level": "success", "msg": f"[{server_name}] {category}: {total} preprints"})
                except Exception as e:
                    SYSTEM_STATE["stats"]["errors"] += 1
                    await broadcast("LOG", {"level": "error", "msg": f"[{server_name}] {category}: {str(e)[:120]}"})

    SYSTEM_STATE["phases"][phase] = "COMPLETE"
    SYSTEM_STATE["stats"]["active_tasks"] -= 1
    SYSTEM_STATE["stats"]["completed_tasks"] += 1
    await broadcast("PHASE_COMPLETE", {"phase": phase})


async def worker_stackexchange():
    """Collect Stack Overflow Q&A data. Uses free Stack Exchange API."""
    phase = "Stack Overflow"
    SYSTEM_STATE["phases"][phase] = "RUNNING"
    SYSTEM_STATE["stats"]["active_tasks"] += 1
    await broadcast("PHASE_START", {"phase": phase})

    import aiohttp
    import gzip

    tags = ["python", "javascript", "typescript", "react", "node.js",
            "docker", "kubernetes", "sql", "git", "machine-learning",
            "java", "c#", "c++", "php", "ruby", "go", "rust", "swift",
            "kotlin", "scala", "r", "matlab", "bash", "powershell",
            "html", "css", "angular", "vue.js", "django", "flask",
            "spring", "express", "fastapi", "tensorflow", "pytorch",
            "pandas", "numpy", "selenium", "cypress", "jest",
            "mongodb", "postgresql", "mysql", "redis", "elasticsearch",
            "aws", "azure", "gcp", "linux", "nginx", "apache",
            "graphql", "rest", "grpc", "websocket", "oauth",
            "machine-learning-model", "data-science", "nlp",
            "computer-vision", "deep-learning", "neural-network"]

    async with aiohttp.ClientSession() as session:
        for tag in tags:
            try:
                await broadcast("LOG", {"level": "info", "msg": f"[StackExchange] Fetching: {tag}"})
                SYSTEM_STATE["agents"]["debug"]["status"] = "active"
                SYSTEM_STATE["agents"]["debug"]["last_action"] = f"SO: {tag}"

                out_dir = BASE_DATA_DIR / "stackoverflow"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"{tag}.jsonl"
                if should_skip(out_file, 100):
                    await broadcast("LOG", {"level": "info", "msg": f"[StackExchange] Skipping {tag} (D: drive has data)"})
                    continue

                total = 0
                for page in range(1, 11):  # 10 pages per tag = 1000 Qs
                    url = f"https://api.stackexchange.com/2.3/questions?order=desc&sort=votes&tagged={tag}&site=stackoverflow&page={page}&pagesize=100&filter=withbody"

                    async with session.get(url) as resp:
                        raw = await resp.read()
                        try:
                            data = json.loads(gzip.decompress(raw).decode("utf-8"))
                        except Exception:
                            data = json.loads(raw.decode("utf-8"))

                    questions = data.get("items", [])
                    if not questions:
                        break

                    with open(out_file, "a", encoding="utf-8") as f:
                        for q in questions:
                            record = {
                                "id": f"so:{q.get('question_id')}",
                                "title": q.get("title", ""),
                                "body": q.get("body", "")[:3000],
                                "score": q.get("score", 0),
                                "view_count": q.get("view_count", 0),
                                "answer_count": q.get("answer_count", 0),
                                "tags": q.get("tags", []),
                                "is_answered": q.get("is_answered", False),
                                "source": "stackoverflow",
                            }
                            f.write(json.dumps(record) + "\n")
                            total += 1

                    await asyncio.sleep(1)

                SYSTEM_STATE["stats"]["stackoverflow"] = total
                await broadcast("LOG", {"level": "success", "msg": f"[StackExchange] {tag}: {total} Qs"})
            except Exception as e:
                SYSTEM_STATE["stats"]["errors"] += 1
                await broadcast("LOG", {"level": "error", "msg": f"[StackExchange] {tag}: {str(e)[:120]}"})

    SYSTEM_STATE["phases"][phase] = "COMPLETE"
    SYSTEM_STATE["stats"]["active_tasks"] -= 1
    SYSTEM_STATE["stats"]["completed_tasks"] += 1
    SYSTEM_STATE["agents"]["debug"]["status"] = "idle"
    await broadcast("PHASE_COMPLETE", {"phase": phase})


async def worker_pypi_docs():
    """Collect Python package info + docs from PyPI and ReadTheDocs."""
    phase = "PyPI Packages"
    SYSTEM_STATE["phases"][phase] = "RUNNING"
    SYSTEM_STATE["stats"]["active_tasks"] += 1
    await broadcast("PHASE_START", {"phase": phase})

    import aiohttp
    from bs4 import BeautifulSoup

    packages = [
        "numpy", "pandas", "scipy", "scikit-learn", "tensorflow", "pytorch",
        "transformers", "datasets", "diffusers", "accelerate", "jax", "flax",
        "fastapi", "uvicorn", "pydantic", "sqlalchemy", "alembic", "httpx",
        "aiohttp", "asyncio", "click", "typer", "rich", "tqdm", "pytest",
        "celery", "redis", "beautifulsoup4", "lxml", "requests", "pillow",
        "matplotlib", "seaborn", "plotly", "dash", "streamlit", "gradio",
        "langchain", "llama-index", "chromadb", "sentence-transformers",
        "openai", "anthropic", "mistralai", "cohere", "huggingface-hub",
        "django", "flask", "boto3", "psycopg2", "motor", "pymongo",
        "docker", "kubernetes", "apache-airflow", "prefect", "dagster",
        "nltk", "spacy", "gensim", "torchvision", "torchaudio", "opencv-python",
        "mlflow", "wandb", "tensorboard", "optuna", "hyperopt", "ray",
        "dask", "polars", "duckdb", "delta-rs", "pyarrow", "fastparquet",
        "shap", "lime", "interpret", "fairlearn", "evaluate", "bleurt",
        "gym", "stable-baselines3", "rl-baselines3-zoo", "pettingzoo",
        "networkx", "igraph", "python-louvain", "graph-tool",
        "six", "wheel", "setuptools", "pip", "virtualenv", "poetry",
        "pipenv", "conda", "mypy", "black", "ruff", "isort", "flake8",
        "pylint", "bandit", "safety", "pre-commit", "nox", "tox",
        "sphinx", "mkdocs", "jupyter", "ipython", "notebook", "voila",
        "panel", "holoviews", "bokeh", "altair", "vega", "yellowbrick",
        "scrapy", "selenium", "playwright", "pyppeteer", "mechanize",
        "cryptography", "pycryptodome", "nacl", "jwcrypto", "python-jose",
        "fastjsonschema", "jsonschema", "pydantic-core", "msgspec",
        "orjson", "ujson", "simdjson", "rapidjson", "python-dotenv",
        "dynaconf", "hydra", "omegaconf", "jsonargparse",
        "watchdog", "watchfiles", "inotify", "python-multipart",
        "python-slugify", "bleach", "markdown", "mistune", "commonmark",
        "pyyaml", "toml", "tomli", "tomli-w", "configparser",
        "python-dateutil", "pendulum", "arrow", "maya", "delorean",
        "humanize", "inflect", "inflection", "pluralize",
        "faker", "mimesis", "polyfactory", "factory-boy","model-bakery",
        "pydantic-factories", "hypothesis", "property-based",
        "coverage", "pytest-cov", "pytest-xdist", "pytest-asyncio",
        "pytest-mock", "pytest-timeout", "pytest-benchmark",
        "pytest-html", "pytest-sugar", "pytest-watch",
        "locust", "boomer", "molotov", "vegeta", "drill",
        "uvloop", "httptools", "websockets", "sockjs",
        "grpcio", "grpcio-tools", "protobuf", "thrift",
        "kafka-python", "confluent-kafka", "pulsar-client",
        "rabbitmq", "aio-pika", "pika", "stomp", "mqtt",
        "elasticsearch", "elasticsearch-dsl", "opensearch-py",
        "influxdb", "influxdb-client", "timescaledb", "cassandra-driver",
        "neo4j", "pymemcache", "aiocache", "cachetools",
        "python-magic", "filetype", "python-mimeparse",
        "youtube-dl", "yt-dlp", "pytube", "youtube-transcript-api",
        "gcsfs", "s3fs", "adlfs", "fsspec", "zarr", "h5py",
        "netcdf4", "xarray", "pint", "quantities", "astropy",
        "biopython", "rdkit", "openbabel", "pymol", "mdanalysis",
        "qiskit", "cirq", "pennylane", "torchquantum",
    ]

    async with aiohttp.ClientSession() as session:
        batch_size = 10
        for batch_start in range(0, len(packages), batch_size):
            batch = packages[batch_start:batch_start+batch_size]
            tasks = []

            for pkg_name in batch:
                try:
                    await broadcast("LOG", {"level": "info", "msg": f"[PyPI] Fetching: {pkg_name}"})

                    out_dir = BASE_DATA_DIR / "pypi"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    out_file = out_dir / f"packages.jsonl"
                    if should_skip(out_file, 50):
                        await broadcast("LOG", {"level": "info", "msg": f"[PyPI] Skipping {pkg_name} (D: drive has data)"})
                        continue

                    # PyPI JSON API
                    pypi_url = f"https://pypi.org/pypi/{pkg_name}/json"
                    async with session.get(pypi_url) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()

                    info = data.get("info", {})
                    summary = info.get("summary", "") or ""
                    description = (info.get("description", "") or "")[:5000]

                    # Try to fetch ReadTheDocs page
                    rtd_text = ""
                    for doc_url in [
                        f"https://{pkg_name}.readthedocs.io/en/stable/",
                        info.get("docs_url", ""),
                        info.get("project_urls", {}).get("Documentation", ""),
                    ]:
                        if doc_url and doc_url.startswith("http"):
                            try:
                                async with session.get(doc_url, timeout=aiohttp.ClientTimeout(total=5)) as rf:
                                    if rf.status == 200:
                                        html = await rf.text()
                                        soup = BeautifulSoup(html, "lxml")
                                        for tag in soup(["script", "style", "nav", "footer"]):
                                            tag.decompose()
                                        body = soup.find("body") or soup.find("main")
                                        if body:
                                            rtd_text = body.get_text(" ", strip=True)[:5000]
                                        break
                            except Exception:
                                pass

                    record = {
                        "id": pkg_name,
                        "name": pkg_name,
                        "version": info.get("version", ""),
                        "summary": summary,
                        "description": description,
                        "docs_text": rtd_text,
                        "home_page": info.get("home_page", ""),
                        "project_urls": info.get("project_urls", {}),
                        "requires_dist": (info.get("requires_dist") or [])[:20],
                        "keywords": info.get("keywords", ""),
                        "source": "pypi",
                    }

                    with open(out_file, "a", encoding="utf-8") as f:
                        f.write(json.dumps(record) + "\n")

                    SYSTEM_STATE["stats"]["pypi"] = batch_start + batch.index(pkg_name) + 1
                    await broadcast("PROGRESS", {"phase": phase, "label": pkg_name, "count": batch_start + batch.index(pkg_name) + 1})
                    await asyncio.sleep(0.3)
                except Exception as e:
                    SYSTEM_STATE["stats"]["errors"] += 1
                    await broadcast("LOG", {"level": "error", "msg": f"[PyPI] {pkg_name}: {str(e)[:120]}"})

    SYSTEM_STATE["phases"][phase] = "COMPLETE"
    SYSTEM_STATE["stats"]["active_tasks"] -= 1
    SYSTEM_STATE["stats"]["completed_tasks"] += 1
    await broadcast("PHASE_COMPLETE", {"phase": phase})


# ═══════════════════════════════════════════════════
# MASSIVE 1200+ WORKER ENGINE
# ═══════════════════════════════════════════════════

_massive_engine_instance: MassiveWorkerEngine | None = None


async def worker_massive():
    """
    Run the massive config-driven worker engine (1200+ parallel data sources).
    Continuously cycles through all configured sources, collecting billions of records.
    """
    global _massive_engine_instance

    phase = "Massive 1200+ Workers"
    SYSTEM_STATE["phases"][phase] = "RUNNING"
    SYSTEM_STATE["stats"]["active_tasks"] += 1
    await broadcast("PHASE_START", {"phase": phase})

    await broadcast("LOG", {
        "level": "info",
        "msg": "[MASSIVE] Initializing 1200+ worker engine..."
    })

    # Progress callback: feed stats into SYSTEM_STATE and broadcast
    async def on_progress(source: str, source_type: str, records: int, total_collected: int):
        SYSTEM_STATE["stats"]["massive_total_records"] = total_collected
        if _massive_engine_instance:
            SYSTEM_STATE["stats"]["massive_active_sources"] = _massive_engine_instance.active_sources
            SYSTEM_STATE["stats"]["massive_sources"] = len(_massive_engine_instance.configs)
            SYSTEM_STATE["stats"]["massive_cycle"] = _massive_engine_instance.cycle
        await broadcast("PROGRESS", {
            "phase": phase,
            "label": source[:40],
            "source_type": source_type,
            "count": total_collected,
            "batch": records,
        })

    # Log callback: broadcast to dashboard
    async def on_log(level: str, msg: str):
        await broadcast("LOG", {"level": level, "msg": msg})

    if MassiveWorkerEngine is None:
        await broadcast("LOG", {"level": "warn", "msg": "[MASSIVE] MassiveWorkerEngine not available (import failed), skipping"})
        SYSTEM_STATE["phases"][phase] = "COMPLETE"
        SYSTEM_STATE["stats"]["active_tasks"] -= 1
        SYSTEM_STATE["stats"]["completed_tasks"] += 1
        await broadcast("PHASE_COMPLETE", {"phase": phase})
        return

    try:
        engine = MassiveWorkerEngine(
            max_concurrent=30,
            progress_callback=on_progress,
            log_callback=on_log,
        )
        _massive_engine_instance = engine

        await broadcast("LOG", {
            "level": "success",
            "msg": f"[MASSIVE] Engine initialized with {len(engine.configs)} sources, 30 concurrent workers"
        })

        # Run continuously
        await engine.run_forever()

    except asyncio.CancelledError:
        if _massive_engine_instance:
            await _massive_engine_instance.close()
        await broadcast("LOG", {"level": "info", "msg": "[MASSIVE] Engine shut down gracefully"})
    except Exception as e:
        SYSTEM_STATE["stats"]["errors"] += 1
        SYSTEM_STATE["stats"]["massive_errors"] += 1
        await broadcast("LOG", {"level": "error", "msg": f"[MASSIVE] Engine crashed: {str(e)[:200]}"})
        logger.error(f"[MASSIVE] Engine error: {e}")
    finally:
        SYSTEM_STATE["phases"][phase] = "COMPLETE"
        SYSTEM_STATE["stats"]["active_tasks"] -= 1
        SYSTEM_STATE["stats"]["completed_tasks"] += 1
        await broadcast("PHASE_COMPLETE", {"phase": phase})


# ═══════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════

async def main():
    logger.info(f" Anti-Gravity Live Server starting on ws://{WS_HOST}:{WS_PORT}")

    SYSTEM_STATE["status"] = "RUNNING"
    SYSTEM_STATE["uptime_start"] = time.time()

    # Start WebSocket server
    server = await websockets.serve(handle_client, WS_HOST, WS_PORT)
    logger.success(f"[OK] WebSocket server live at ws://localhost:{WS_PORT}")

    # Boot broadcast
    await broadcast("LOG", {"level": "info", "msg": "[BOOT] ANTI-GRAVITY GOD MODE v2.0 initializing..."})
    await broadcast("LOG", {"level": "info", "msg": f"[BOOT] Data directory: {BASE_DATA_DIR}"})
    await broadcast("LOG", {"level": "success", "msg": "[BOOT] WebSocket server online. Dashboard can connect now."})

    # Start HTTP dashboard server on port 8080
    http_thread = threading.Thread(target=start_http_server, daemon=True)
    http_thread.start()
    logger.info(f"[OK] HTTP dashboard server starting on http://{HTTP_HOST}:{HTTP_PORT}")

    # Launch ALL workers in parallel
    await broadcast("LOG", {"level": "info", "msg": "[ENGINE] Launching all parallel workers..."})

    tasks = [
        # Core
        asyncio.create_task(heartbeat_loop()),
        # Existing data sources
        asyncio.create_task(worker_arxiv()),
        asyncio.create_task(worker_openalex()),
        asyncio.create_task(worker_synthetic()),
        asyncio.create_task(worker_huggingface()),
        asyncio.create_task(worker_rag_index()),
        # NEW: 10 parallel data sources
        asyncio.create_task(worker_semantic_scholar()),
        asyncio.create_task(worker_crossref()),
        asyncio.create_task(worker_pubmed()),
        asyncio.create_task(worker_wikipedia()),
        asyncio.create_task(worker_gutenberg()),
        asyncio.create_task(worker_github_trending()),
        asyncio.create_task(worker_doaj()),
        asyncio.create_task(worker_biorxiv()),
        asyncio.create_task(worker_stackexchange()),
        asyncio.create_task(worker_pypi_docs()),
        # MASSIVE: 1200+ config-driven parallel workers
        asyncio.create_task(worker_massive()),
    ]

    # Wait for all workers (heartbeat runs forever)
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)

    for task in done:
        if task.exception():
            logger.error(f"Worker crashed: {task.exception()}")

    # Keep server alive
    await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
