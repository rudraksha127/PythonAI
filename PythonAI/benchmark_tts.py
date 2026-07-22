#!/usr/bin/env python3
"""
TTS Quality Benchmark - Compare agent answers WITH and WITHOUT Test-Time Scaling

Measures the quality delta of PDR+RTV (Test-Time Scaling) vs a single-pass
LLM call on a set of hard coding benchmark tasks.

Usage:
    # Real mode (requires Ollama running):
    python benchmark_tts.py

    # Simulation mode (synthetic data for testing the framework):
    python benchmark_tts.py --simulate

    # Specify model:
    python benchmark_tts.py --model qwen2.5-coder:14b

    # Fewer tasks for quick run:
    python benchmark_tts.py --num-tasks 3 --simulate

Output:
    - data/benchmark/tts_benchmark_<timestamp>.json  (full results)
    - Prints summary table with quality delta per task
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("tts_benchmark")

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data" / "benchmark"
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Hard Coding Benchmark Tasks
# ---------------------------------------------------------------------------

BENCHMARK_TASKS: list[dict[str, Any]] = [
    {
        "id": "multi_threaded_cache",
        "title": "Thread-Safe LRU Cache",
        "description": "Multi-threaded LRU cache with TTL",
        "question": (
            "Implement a thread-safe LRU cache in Python with the following requirements:\n"
            "1. Fixed maximum size (configurable at init)\n"
            "2. TTL (time-to-live) per entry\n"
            "3. Thread-safe for concurrent reads and writes\n"
            "4. A 'stats' method returning hit/miss counts and cache size\n"
            "5. A 'clear' method to invalidate all entries\n"
            "6. Use only the standard library\n"
            "Include proper edge case handling, docstrings, and a usage example with assertions."
        ),
        "domain": "python",
        "keywords": ["thread-safe", "LRU", "cache", "TTL", "concurrent"],
    },
    {
        "id": "rest_api_auth",
        "title": "REST API with JWT Auth",
        "description": "FastAPI-inspired REST API with JWT authentication middleware",
        "question": (
            "Design and implement a lightweight REST API framework in Python that includes:\n"
            "1. Route registration (@route decorator for GET, POST, PUT, DELETE)\n"
            "2. JWT token-based authentication middleware\n"
            "3. Request body parsing (JSON)\n"
            "4. URL parameter extraction from paths like /users/:id\n"
            "5. Error handling with proper HTTP status codes\n"
            "6. CORS header support\n"
            "Do NOT use external frameworks - implement the core logic from scratch "
            "using only the standard library. Include a working example with at least "
            "3 endpoints, one requiring authentication."
        ),
        "domain": "python",
        "keywords": ["REST", "API", "JWT", "auth", "middleware", "framework"],
    },
    {
        "id": "async_task_queue",
        "title": "Async Task Queue with Retries",
        "description": "Async task queue with priority, retries, and backoff",
        "question": (
            "Build an async task queue system in Python with:\n"
            "1. Task submission with priority levels (high, medium, low)\n"
            "2. Configurable retry logic (max_retries, exponential backoff)\n"
            "3. Task status tracking (pending, running, completed, failed)\n"
            "4. Graceful shutdown - wait for running tasks to complete\n"
            "5. A progress callback mechanism\n"
            "6. Proper error handling that doesn't crash the queue\n"
            "Use asyncio and only the standard library. Include a demonstration "
            "with at least 5 tasks of varying priorities where some fail and get retried."
        ),
        "domain": "python",
        "keywords": ["async", "task queue", "retry", "backoff", "priority"],
    },
    {
        "id": "sql_query_builder",
        "title": "SQL Query Builder with Injection Prevention",
        "description": "SQL query builder with parameterized queries and injection prevention",
        "question": (
            "Create a SQL query builder class in Python that:\n"
            "1. Supports SELECT, INSERT, UPDATE, DELETE statements\n"
            "2. Parameterized queries to prevent SQL injection\n"
            "3. WHERE clause builder with AND/OR conditions\n"
            "4. JOIN support (INNER, LEFT, RIGHT)\n"
            "5. ORDER BY, GROUP BY, LIMIT/OFFSET\n"
            "6. Subquery support\n"
            "7. Debug method that shows the final SQL with parameters\n"
            "All queries must use parameterized placeholders (never string interpolation). "
            "Include a security-focused example showing why parameterization matters."
        ),
        "domain": "python",
        "keywords": ["SQL", "query builder", "injection", "parameterized"],
    },
    {
        "id": "circuit_breaker",
        "title": "Circuit Breaker Pattern",
        "description": "Circuit breaker for external service calls with health checks",
        "question": (
            "Implement the Circuit Breaker pattern in Python for resilient external service calls:\n"
            "1. Three states: CLOSED (normal), OPEN (failing), HALF_OPEN (testing recovery)\n"
            "2. Configurable failure threshold to trip open\n"
            "3. Configurable timeout before transitioning to HALF_OPEN\n"
            "4. Success count in HALF_OPEN to close again\n"
            "5. Decorator @circuit_breaker for wrapping async functions\n"
            "6. Thread-safe for concurrent access\n"
            "7. Event callbacks on state transitions\n"
            "8. Metrics tracking (total calls, failures, successes per state)\n"
            "Include a realistic example with a flaky HTTP service simulation."
        ),
        "domain": "python",
        "keywords": ["circuit breaker", "resilience", "retry", "decorator"],
    },
    {
        "id": "rate_limiter_algo",
        "title": "Multi-Algorithm Rate Limiter",
        "description": "Rate limiter supporting token bucket, sliding window, and leaky bucket",
        "question": (
            "Design a rate limiting library in Python supporting multiple algorithms:\n"
            "1. Token Bucket - fixed capacity, refill rate\n"
            "2. Sliding Window Log - per-client request log with window\n"
            "3. Sliding Window Counter - approximate count with lower memory\n"
            "4. Leaky Bucket - constant drain rate\n"
            "5. A unified RateLimiterFactory to create instances\n"
            "6. In-memory storage (Redis adapter interface for future)\n"
            "7. Thread-safe implementation\n"
            "Each algorithm should be a separate class implementing a common interface. "
            "Include examples showing usage patterns and comparative memory/time tradeoffs."
        ),
        "domain": "python",
        "keywords": ["rate limit", "token bucket", "sliding window", "algorithm"],
    },
    {
        "id": "data_pipeline_etl",
        "title": "ETL Data Pipeline with Validation",
        "description": "ETL pipeline with schema validation, transformations, and error reporting",
        "question": (
            "Build an ETL data pipeline framework in Python:\n"
            "1. Extract phase: support CSV, JSON, and Parquet-like (dict list) sources\n"
            "2. Transform phase: chainable transformations (filter, map, aggregate, join)\n"
            "3. Load phase: write to CSV, JSON, or custom callback\n"
            "4. Schema validation with type checking and required fields\n"
            "5. Error handling with detailed error reporting (row-level failures)\n"
            "6. Pipeline statistics: rows processed, errors, execution time\n"
            "7. Progress callback for long-running pipelines\n"
            "Use functional composition (no class-based pipeline config). "
            "Show an example processing a batch of sales data with at least 5 transformations."
        ),
        "domain": "python",
        "keywords": ["ETL", "pipeline", "validation", "transformation", "data"],
    },
    {
        "id": "config_validation",
        "title": "Type-Safe Configuration System",
        "description": "Type-safe config parser with env var support, nested schemas, and validation",
        "question": (
            "Create a type-safe configuration system in Python:\n"
            "1. Define config schemas using dataclasses with validators\n"
            "2. Load from: .env file, environment variables, JSON file, YAML file\n"
            "3. Nested configuration with sub-configs\n"
            "4. Type coercion (str->int, str->bool, str->list with custom delimiters)\n"
            "5. Validation rules: required, min/max, regex patterns, custom validators\n"
            "6. Secret masking in repr/str output\n"
            "7. Watch for file changes and reload\n"
            "8. Merge hierarchy: defaults -> .env -> env vars -> CLI args\n"
            "Only use standard library + os. Show an example with database, redis, "
            "and logging sub-configs."
        ),
        "domain": "python",
        "keywords": ["config", "validation", "type-safe", "env var", "schema"],
    },
    {
        "id": "event_sourcing",
        "title": "Event Sourcing Framework",
        "description": "Event sourcing with aggregate roots, event store, and projections",
        "question": (
            "Implement an event sourcing framework in Python:\n"
            "1. Event base class with aggregate_id, version, timestamp, payload\n"
            "2. AggregateRoot that applies events and tracks uncommitted changes\n"
            "3. In-memory EventStore with get_events(aggregate_id) and save_events\n"
            "4. Repository pattern: load aggregate from event stream, save new events\n"
            "5. Projections: rebuild read models from event history\n"
            "6. Snapshot support for performance\n"
            "7. Concurrency handling via expected_version (optimistic locking)\n"
            "Model a 'BankAccount' aggregate: open, deposit, withdraw, close. "
            "Show a complete example reconstructing account state from events."
        ),
        "domain": "python",
        "keywords": ["event sourcing", "CQRS", "aggregate", "projection", "DDD"],
    },
    {
        "id": "dsl_interpreter",
        "title": "DSL Interpreter for Workflow Automation",
        "description": "Domain-specific language interpreter for defining and executing workflows",
        "question": (
            "Build a DSL (domain-specific language) interpreter in Python for workflow automation:\n"
            "1. Lexer: tokenize workflow definitions into tokens\n"
            "2. Parser: build an AST from tokens\n"
            "3. Executor: walk the AST and execute actions\n"
            "4. Supported constructs: steps, conditions (if/else), loops (for/while), "
            "variables, function calls, error handlers\n"
            "5. A built-in library of common actions: http_request, file_read, file_write, "
            "send_email (mock), log, wait\n"
            "6. Variable interpolation in step parameters\n"
            "7. Error handling with try/catch blocks and retry steps\n"
            "Example workflow:\n"
            "Do NOT use eval or exec. Implement the parser manually."
        ),
        "domain": "python",
        "keywords": ["DSL", "interpreter", "lexer", "parser", "AST", "workflow"],
    },
]


# ---------------------------------------------------------------------------
# Quality Scoring
# ---------------------------------------------------------------------------


def score_keyword_coverage(answer: str, keywords: list[str]) -> float:
    if not keywords:
        return 1.0
    lower = answer.lower()
    covered = sum(1 for kw in keywords if kw.lower() in lower)
    return covered / len(keywords)


def score_code_presence(answer: str) -> float:
    if "```" not in answer:
        return 0.0
    blocks = re.findall(r"```(?:\w+)?\n(.*?)```", answer, re.DOTALL)
    if not blocks:
        return 0.0
    code_text = "\n".join(blocks)
    imports = len(re.findall(r"^(?:import |from )", code_text, re.MULTILINE))
    defs = len(re.findall(r"^(?:def |class )", code_text, re.MULTILINE))
    if imports >= 2 and defs >= 3:
        return 1.0
    elif imports >= 1 and defs >= 1:
        return 0.7
    elif defs >= 1:
        return 0.4
    else:
        return 0.2


def score_code_validity(answer: str) -> float:
    blocks = re.findall(r"```(?:python|py|python3)?\n(.*?)```", answer, re.DOTALL)
    if not blocks:
        return 1.0
    valid = 0
    for block in blocks:
        try:
            cleaned = re.sub(r"^>>>.*$", "", block, flags=re.MULTILINE).strip()
            if not cleaned:
                valid += 1
                continue
            compile(cleaned, "<benchmark>", "exec")
            valid += 1
        except SyntaxError:
            pass
    return valid / len(blocks)


def score_thoroughness(answer: str) -> float:
    word_count = len(answer.split())
    if word_count >= 800:
        length_score = 1.0
    elif word_count >= 500:
        length_score = 0.8
    elif word_count >= 300:
        length_score = 0.6
    elif word_count >= 150:
        length_score = 0.4
    else:
        length_score = 0.2
    has_sections = bool(re.search(r"#{1,3}\s", answer))
    has_code = "```" in answer
    has_example = bool(re.search(r"(example|usage|demonstration|test)", answer.lower()))
    has_edge_cases = bool(re.search(r"(edge.case|error|exception|handle|validation)", answer.lower()))
    has_docstring = bool(re.search(r'""".*?"""', answer, re.DOTALL))
    structure_signals = [has_sections, has_code, has_example, has_edge_cases, has_docstring]
    structure_score = sum(1 for s in structure_signals if s) / len(structure_signals)
    return 0.4 * length_score + 0.6 * structure_score


def score_security_awareness(answer: str) -> float:
    security_terms = [
        "injection", "sanitize", "validate", "escape", "permission",
        "authentication", "authorization", "encrypt", "hash", "secret",
        "xss", "csrf", "safe", "secure", "trust",
    ]
    lower = answer.lower()
    matches = sum(1 for t in security_terms if t in lower)
    return min(1.0, matches / 5)


def score_test_quality(answer: str) -> float:
    has_assert = "assert " in answer
    has_test_func = bool(re.search(r"def test_", answer))
    has_doctest = ">>> " in answer
    has_unittest = "unittest" in answer or "pytest" in answer
    signals = [has_assert, has_test_func, has_doctest, has_unittest]
    return sum(1 for s in signals if s) / len(signals)


def compute_quality_metrics(answer: str, task: dict[str, Any]) -> dict[str, float]:
    return {
        "keyword_coverage": score_keyword_coverage(answer, task.get("keywords", [])),
        "code_presence": score_code_presence(answer),
        "code_validity": score_code_validity(answer),
        "thoroughness": score_thoroughness(answer),
        "security_awareness": score_security_awareness(answer),
        "test_quality": score_test_quality(answer),
    }


def compute_overall_quality(metrics: dict[str, float]) -> float:
    weights = {
        "keyword_coverage": 0.20,
        "code_presence": 0.20,
        "code_validity": 0.20,
        "thoroughness": 0.15,
        "security_awareness": 0.10,
        "test_quality": 0.15,
    }
    score = sum(metrics.get(k, 0) * w for k, w in weights.items())
    return round(score, 4)


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class BenchmarkResult:
    task_id: str
    title: str
    complexity_score: float
    no_tts_answer: str = ""
    no_tts_metrics: dict[str, float] = field(default_factory=dict)
    no_tts_quality: float = 0.0
    no_tts_tokens: int = 0
    no_tts_elapsed_ms: float = 0.0
    tts_answer: str = ""
    tts_metrics: dict[str, float] = field(default_factory=dict)
    tts_quality: float = 0.0
    tts_tokens: int = 0
    tts_elapsed_ms: float = 0.0
    tts_num_rollouts: int = 0
    tts_rtv_applied: bool = False
    tts_pdr_applied: bool = False
    quality_delta: float = 0.0
    quality_delta_pct: float = 0.0
    error: str | None = None


# ---------------------------------------------------------------------------
# LLM Call
# ---------------------------------------------------------------------------


def create_llm_call(model: str = "qwen2.5-coder:14b", timeout: int = 180):
    import httpx

    async def llm_call(question: str, temperature: float = 0.3, max_tokens: int = 4096) -> str:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": question}],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "repeat_penalty": 1.1,
            },
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post("http://localhost:11434/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")

    return llm_call


# ---------------------------------------------------------------------------
# Simulated Answers (for --simulate mode)
# ---------------------------------------------------------------------------


def _make_no_tts_answer(task_id: str, title: str) -> str:
    """Return a short, simple simulated answer (no TTS)."""
    NL = "\n"
    cache_simple = (
        f"Here's a simple LRU cache implementation:{NL}{NL}"
        f"```python{NL}"
        f"from collections import OrderedDict{NL}"
        f"import threading{NL}{NL}"
        f"class LRUCache:{NL}"
        f"    def __init__(self, capacity=100):{NL}"
        f"        self.cache = OrderedDict(){NL}"
        f"        self.capacity = capacity{NL}"
        f"        self.lock = threading.Lock(){NL}{NL}"
        f"    def get(self, key):{NL}"
        f"        with self.lock:{NL}"
        f"            if key not in self.cache:{NL}"
        f"                return None{NL}"
        f"            self.cache.move_to_end(key){NL}"
        f"            return self.cache[key]{NL}{NL}"
        f"    def put(self, key, value):{NL}"
        f"        with self.lock:{NL}"
        f"            self.cache[key] = value{NL}"
        f"            self.cache.move_to_end(key){NL}"
        f"            if len(self.cache) > self.capacity:{NL}"
        f"                self.cache.popitem(last=False){NL}"
        f"```"
    )
    templates = {"multi_threaded_cache": cache_simple}
    default = (
        f"To implement {title}, you can use a class-based approach with appropriate data structures. "
        f"The key considerations are thread safety and performance. "
        f"```python{NL}class Solution:{NL}    pass{NL}```{NL}"
        f"This is a basic implementation that covers the core requirements."
    )
    ans = templates.get(task_id, default)
    return ans + f"{NL}{NL}A basic approach that works for simple use cases."


def _make_tts_answer(task_id: str, title: str) -> str:
    """Return a comprehensive simulated answer (with TTS)."""
    NL = "\n"

    cache_full = (
        f"A comprehensive thread-safe LRU cache with TTL support:{NL}{NL}"
        f"```python{NL}"
        f"from collections import OrderedDict{NL}"
        f"import threading{NL}"
        f"import time{NL}{NL}"
        f"class TTLCacheEntry:{NL}"
        f"    def __init__(self, key, value, ttl=None):{NL}"
        f"        self.key = key{NL}"
        f"        self.value = value{NL}"
        f"        self.created_at = time.time(){NL}"
        f"        self.ttl = ttl{NL}{NL}"
        f"    def is_expired(self):{NL}"
        f"        return self.ttl and (time.time() - self.created_at) > self.ttl{NL}{NL}"
        f"class LRUCache:{NL}"
        f"    def __init__(self, capacity=100, default_ttl=None):{NL}"
        f"        self.capacity = capacity{NL}"
        f"        self.default_ttl = default_ttl{NL}"
        f"        self.cache = OrderedDict(){NL}"
        f"        self.lock = threading.RLock(){NL}"
        f"        self.hits = 0{NL}"
        f"        self.misses = 0{NL}{NL}"
        f"    def get(self, key):{NL}"
        f"        with self.lock:{NL}"
        f"            if key not in self.cache:{NL}"
        f"                self.misses += 1{NL}"
        f"                return None{NL}"
        f"            entry = self.cache[key]{NL}"
        f"            if entry.is_expired():{NL}"
        f"                del self.cache[key]{NL}"
        f"                self.misses += 1{NL}"
        f"                return None{NL}"
        f"            self.hits += 1{NL}"
        f"            self.cache.move_to_end(key){NL}"
        f"            return entry.value{NL}{NL}"
        f"    def put(self, key, value, ttl=None):{NL}"
        f"        with self.lock:{NL}"
        f"            if key in self.cache:{NL}"
        f"                self.cache.move_to_end(key){NL}"
        f"            self.cache[key] = TTLCacheEntry(key, value, ttl or self.default_ttl){NL}"
        f"            if len(self.cache) > self.capacity:{NL}"
        f"                self.cache.popitem(last=False){NL}{NL}"
        f"    def stats(self):{NL}"
        f"        with self.lock:{NL}"
        f"            total = self.hits + self.misses{NL}"
        f"            return {{'hits': self.hits, 'misses': self.misses, {NL}"
        f"                    'hit_rate': self.hits / total if total else 0,{NL}"
        f"                    'size': len(self.cache), 'capacity': self.capacity}}{NL}{NL}"
        f"    def clear(self):{NL}"
        f"        with self.lock:{NL}"
        f"            self.cache.clear(){NL}"
        f"            self.hits = 0{NL}"
        f"            self.misses = 0{NL}"
        f"```{NL}{NL}"
        f"Edge cases: thread safety via RLock, TTL expiration, automatic eviction, "
        f"hit/miss tracking, complete invalidation."
    )

    rest_api_full = (
        f"A complete lightweight REST API framework with JWT authentication:{NL}{NL}"
        f"```python{NL}"
        f"import json, hashlib, hmac, base64, time, re{NL}"
        f"from urllib.parse import urlparse, parse_qs{NL}{NL}"
        f"def base64url_encode(data):{NL}"
        f"    return base64.urlsafe_b64encode(data).rstrip(b'=').decode(){NL}{NL}"
        f"def create_jwt(payload, secret):{NL}"
        f"    header = base64url_encode(json.dumps({{'alg': 'HS256', 'typ': 'JWT'}}).encode()){NL}"
        f"    payload_enc = base64url_encode(json.dumps(payload).encode()){NL}"
        f"    sig = hmac.new(secret.encode(), f'{{header}}.{{payload_enc}}'.encode(), hashlib.sha256).digest(){NL}"
        f"    return f'{{header}}.{{payload_enc}}.{{base64url_encode(sig)}}'{NL}{NL}"
        f"class Router:{NL}"
        f"    def __init__(self):{NL}"
        f"        self.routes = []{NL}"
        f"    def route(self, path, methods=['GET']):{NL}"
        f"        def wrapper(func):{NL}"
        f"            self.routes.append({{'path': path, 'methods': methods, 'handler': func}}){NL}"
        f"            return func{NL}"
        f"        return wrapper{NL}"
        f"    def dispatch(self, request):{NL}"
        f"        for route in self.routes:{NL}"
        f"            if self._match(request.path, route['path']):{NL}"
        f"                return route['handler'](request){NL}"
        f"        return {{'status': 404, 'body': 'Not found'}}{NL}"
        f"    def _match(self, request_path, route_path):{NL}"
        f"        parts_a = request_path.strip('/').split('/'){NL}"
        f"        parts_b = route_path.strip('/').split('/'){NL}"
        f"        if len(parts_a) != len(parts_b):{NL}"
        f"            return False{NL}"
        f"        for a, b in zip(parts_a, parts_b):{NL}"
        f"            if b.startswith(':'): continue{NL}"
        f"            if a != b: return False{NL}"
        f"        return True{NL}"
        f"```{NL}{NL}"
        f"Includes JWT auth middleware, CORS support, JSON body parsing, "
        f"and a complete example with protected and public endpoints."
    )

    async_queue_full = (
        f"Comprehensive async task queue with priority, retries, and backoff:{NL}{NL}"
        f"```python{NL}"
        f"import asyncio, logging{NL}"
        f"from enum import Enum{NL}"
        f"from dataclasses import dataclass{NL}"
        f"from heapq import heappush, heappop{NL}{NL}"
        f"class Priority(Enum): HIGH=0; MEDIUM=1; LOW=2{NL}"
        f"class TaskStatus(Enum): PENDING='pending'; RUNNING='running'; COMPLETED='completed'; FAILED='failed'{NL}{NL}"
        f"@dataclass{NL}"
        f"class Task:{NL}"
        f"    id: str{NL}"
        f"    coro: callable{NL}"
        f"    priority: Priority = Priority.MEDIUM{NL}"
        f"    max_retries: int = 3{NL}"
        f"    status: TaskStatus = TaskStatus.PENDING{NL}"
        f"    retry_count: int = 0{NL}"
        f"    result: any = None{NL}"
        f"    error: str | None = None{NL}{NL}"
        f"class TaskQueue:{NL}"
        f"    def __init__(self):{NL}"
        f"        self._queue = []{NL}"
        f"        self._tasks = {{}}{NL}"
        f"        self._running = False{NL}"
        f"        self._progress_cb = None{NL}{NL}"
        f"    async def submit(self, task):{NL}"
        f"        heappush(self._queue, (task.priority.value, task.id)){NL}"
        f"        self._tasks[task.id] = task{NL}"
        f"        if not self._running:{NL}"
        f"            asyncio.create_task(self._process()){NL}{NL}"
        f"    async def _process(self):{NL}"
        f"        self._running = True{NL}"
        f"        while self._queue:{NL}"
        f"            _, task_id = heappop(self._queue){NL}"
        f"            task = self._tasks[task_id]{NL}"
        f"            task.status = TaskStatus.RUNNING{NL}"
        f"            for attempt in range(task.max_retries):{NL}"
        f"                try:{NL}"
        f"                    task.result = await task.coro(){NL}"
        f"                    task.status = TaskStatus.COMPLETED{NL}"
        f"                    break{NL}"
        f"                except Exception as e:{NL}"
        f"                    task.retry_count = attempt + 1{NL}"
        f"                    task.error = str(e){NL}"
        f"                    if attempt < task.max_retries - 1:{NL}"
        f"                        await asyncio.sleep(2 ** attempt){NL}"
        f"            if task.status != TaskStatus.COMPLETED:{NL}"
        f"                task.status = TaskStatus.FAILED{NL}"
        f"            if self._progress_cb:{NL}"
        f"                self._progress_cb(task){NL}"
        f"        self._running = False{NL}"
        f"```{NL}{NL}"
        f"Full implementation with priority heaps, exponential backoff, "
        f"progress callbacks, and graceful shutdown."
    )

    templates = {
        "multi_threaded_cache": cache_full,
        "rest_api_auth": rest_api_full,
        "async_task_queue": async_queue_full,
    }

    default = (
        f"Comprehensive implementation of {title}.{NL}{NL}"
        f"```python{NL}"
        f"@dataclass{NL}"
        f"class Config: setting: str = 'default'{NL}{NL}"
        f"class Solution:{NL}"
        f"    def __init__(self):{NL}"
        f"        self.config = Config(){NL}"
        f"    async def execute(self):{NL}"
        f"        return await self._process(){NL}"
        f"    async def _process(self):{NL}"
        f"        return {{'status': 'completed'}}{NL}"
        f"```{NL}{NL}"
        f"### Edge Cases and Error Handling{NL}"
        f"- Input validation with type checking{NL}"
        f"- Graceful error recovery{NL}"
        f"- Thread-safe operations{NL}{NL}"
        f"### Example Usage{NL}"
        f"```python{NL}"
        f"async def main():{NL}"
        f"    solution = Solution(){NL}"
        f"    result = await solution.execute(){NL}"
        f"    print(result){NL}"
        f"```{NL}{NL}"
        f"This covers all requirements with attention to edge cases and production readiness."
    )

    ans = templates.get(task_id, default)

    extra_sections = (
        f"{NL}{NL}"
        f"### Security Considerations{NL}"
        f"- Input validation and sanitization{NL}"
        f"- Proper error handling without information leakage{NL}"
        f"- Thread-safe operations with appropriate locking{NL}{NL}"
        f"### Performance Notes{NL}"
        f"- O(1) average time complexity for core operations{NL}"
        f"- Memory-efficient data structures{NL}"
        f"- Minimized lock contention{NL}{NL}"
        f"### Testing Strategy{NL}"
        f"```python{NL}"
        f"def test_basic_operations():{NL}"
        f"    solution = Solution(){NL}"
        f"    result = solution.execute(){NL}"
        f"    assert result is not None{NL}{NL}"
        f"def test_error_handling():{NL}"
        f"    with pytest.raises(ValueError):{NL}"
        f"        pass{NL}"
        f"```"
    )
    ans += extra_sections
    return ans


def _generate_simulated_answer(task: dict[str, Any], use_tts: bool) -> str:
    """Generate a simulated answer for testing the benchmark framework."""
    task_id = task["id"]
    title = task["title"]

    if not use_tts:
        return _make_no_tts_answer(task_id, title)
    else:
        return _make_tts_answer(task_id, title)


# ---------------------------------------------------------------------------
# Benchmark Runners
# ---------------------------------------------------------------------------


async def run_single_no_tts(
    task: dict[str, Any],
    llm_call,
    model: str,
) -> dict[str, Any]:
    question = task["question"]
    start = time.time()
    try:
        answer = await llm_call(question, temperature=0.3)
        elapsed_ms = (time.time() - start) * 1000
        tokens = len(answer.split())
        metrics = compute_quality_metrics(answer, task)
        quality = compute_overall_quality(metrics)
        return {
            "answer": answer, "metrics": metrics, "quality": quality,
            "tokens": tokens, "elapsed_ms": round(elapsed_ms, 1),
        }
    except Exception as e:
        logger.error(f"  [NO-TTS] Error: {e}")
        return {"answer": "", "metrics": {}, "quality": 0.0, "tokens": 0,
                "elapsed_ms": 0.0, "error": str(e)}


async def run_single_with_tts(
    task: dict[str, Any],
    pipeline: Any,
) -> dict[str, Any]:
    question = task["question"]
    try:
        result = await pipeline.run(
            question=question,
            force_hard=True,
        )
        answer = result.get("answer", "")
        metrics = compute_quality_metrics(answer, task)
        quality = compute_overall_quality(metrics)
        return {
            "answer": answer, "metrics": metrics, "quality": quality,
            "tokens": result.get("tokens_used", len(answer.split())),
            "elapsed_ms": result.get("elapsed_ms", 0.0),
            "num_rollouts": result.get("num_rollouts", 0),
            "rtv_applied": result.get("rtv_applied", False),
            "pdr_applied": result.get("pdr_applied", False),
            "error": result.get("error"),
        }
    except Exception as e:
        logger.error(f"  [WITH-TTS] Error: {e}")
        return {"answer": "", "metrics": {}, "quality": 0.0, "tokens": 0,
                "elapsed_ms": 0.0, "num_rollouts": 0, "rtv_applied": False,
                "pdr_applied": False, "error": str(e)}


async def run_simulated_no_tts(task: dict[str, Any]) -> dict[str, Any]:
    import random
    answer = _generate_simulated_answer(task, use_tts=False)
    metrics = compute_quality_metrics(answer, task)
    quality = compute_overall_quality(metrics)
    return {
        "answer": answer, "metrics": metrics, "quality": quality,
        "tokens": len(answer.split()),
        "elapsed_ms": round(random.uniform(2000, 8000), 1),
    }


async def run_simulated_with_tts(task: dict[str, Any]) -> dict[str, Any]:
    import random
    answer = _generate_simulated_answer(task, use_tts=True)
    metrics = compute_quality_metrics(answer, task)
    quality = compute_overall_quality(metrics)
    return {
        "answer": answer, "metrics": metrics, "quality": quality,
        "tokens": len(answer.split()),
        "elapsed_ms": round(random.uniform(30000, 90000), 1),
        "num_rollouts": 5,
        "rtv_applied": True,
        "pdr_applied": True,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main():
    parser = argparse.ArgumentParser(
        description="Benchmark TTS quality vs single-pass LLM on hard coding tasks"
    )
    parser.add_argument("--model", default="qwen2.5-coder:14b", help="Ollama model name")
    parser.add_argument("--num-tasks", type=int, default=0, help="Number of tasks (0 = all)")
    parser.add_argument("--simulate", action="store_true", help="Run with simulated answers")
    parser.add_argument("--output", default=None, help="Output JSON path")
    parser.add_argument("--verbose", action="store_true", help="Print full answers")
    args = parser.parse_args()

    tasks = BENCHMARK_TASKS
    if args.num_tasks > 0:
        tasks = tasks[: args.num_tasks]

    print("=" * 72)
    print("  TTS Quality Benchmark - PDR+RTV vs Single-Pass LLM")
    print("=" * 72)
    print(f"  Tasks: {len(tasks)}")
    print(f"  Model: {args.model if not args.simulate else '(simulated)'}")
    print(f"  Mode:  {'SIMULATION' if args.simulate else 'REMOTE (Ollama)'}")
    print()

    if not args.simulate:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get("http://localhost:11434/api/tags")
                if resp.status_code != 200:
                    print("[ERROR] Ollama not responding on http://localhost:11434")
                    print("Start Ollama first: ollama serve")
                    sys.exit(1)
                models = [m["name"] for m in resp.json().get("models", [])]
                print(f"  Available models: {', '.join(models)}")
                if args.model not in models:
                    print(f"[WARN] Model '{args.model}' not found. Available: {models}")
        except Exception as e:
            print(f"[ERROR] Cannot connect to Ollama: {e}")
            print("  Start with: ollama serve")
            print("  Or use: python benchmark_tts.py --simulate")
            sys.exit(1)

        llm_call = create_llm_call(model=args.model)
        sys.path.insert(0, str(PROJECT_ROOT))
        from src.training.time_scaling import TTSConfig, TestTimeScalingPipeline, create_ollama_llm_call

        tts_config = TTSConfig(
            enabled=True, complexity_threshold=0.7,
            num_initial_rollouts=5, num_pdr_rollouts=2,
            verbose=args.verbose,
        )
        tts_llm = create_ollama_llm_call(model=args.model)
        pipeline = TestTimeScalingPipeline(llm_call=tts_llm, config=tts_config)
    else:
        llm_call = None
        pipeline = None

    results: list[BenchmarkResult] = []

    print(f"  {'Task':30s} {'No-TTS':>8s} {'TTS':>8s} {'Diff':>8s}  {'Diff%':>7s}")
    print(f"  {'-'*30} {'-'*8} {'-'*8} {'-'*8} {'-'*7}")

    for idx, task in enumerate(tasks, 1):
        task_id = task["id"]
        title = task["title"]
        question = task["question"]

        print(f"  [{idx}/{len(tasks)}] {title[:40]:40s}", end="", flush=True)

        if not args.simulate:
            complexity = pipeline.scorer.compute_score(question)
        else:
            complexity = round(0.75 + (hash(task_id) % 20) / 100, 2)

        no_tts = await (run_single_no_tts(task, llm_call, args.model)
                        if not args.simulate else run_simulated_no_tts(task))
        with_tts = await (run_single_with_tts(task, pipeline)
                          if not args.simulate else run_simulated_with_tts(task))

        no_q = no_tts["quality"]
        tts_q = with_tts["quality"]
        delta = round(tts_q - no_q, 4)
        delta_pct = round((delta / no_q * 100) if no_q > 0 else 0.0, 1)

        result = BenchmarkResult(
            task_id=task_id, title=title, complexity_score=complexity,
            no_tts_answer=no_tts["answer"], no_tts_metrics=no_tts["metrics"],
            no_tts_quality=no_q, no_tts_tokens=no_tts["tokens"],
            no_tts_elapsed_ms=no_tts["elapsed_ms"],
            tts_answer=with_tts["answer"], tts_metrics=with_tts["metrics"],
            tts_quality=tts_q, tts_tokens=with_tts["tokens"],
            tts_elapsed_ms=with_tts["elapsed_ms"],
            tts_num_rollouts=with_tts.get("num_rollouts", 0),
            tts_rtv_applied=with_tts.get("rtv_applied", False),
            tts_pdr_applied=with_tts.get("pdr_applied", False),
            quality_delta=delta, quality_delta_pct=delta_pct,
            error=no_tts.get("error") or with_tts.get("error"),
        )
        results.append(result)

        delta_str = f"+{delta:.3f}" if delta >= 0 else f"{delta:.3f}"
        delta_pct_str = f"+{delta_pct:.0f}%" if delta_pct >= 0 else f"{delta_pct:.0f}%"
        print(f"\r  [{idx}/{len(tasks)}] {title[:38]:38s} {no_q:.3f}   {tts_q:.3f}   {delta_str:>8s}  {delta_pct_str:>7s}")
        sys.stdout.flush()

        if args.verbose:
            print(f"\n  -- No-TTS Answer --\n{no_tts['answer'][:500]}")
            print(f"\n  -- TTS Answer --\n{with_tts['answer'][:500]}")
            print(f"  -- Metrics No-TTS: {no_tts['metrics']}")
            print(f"  -- Metrics TTS:    {with_tts['metrics']}")
            print()

    # -- Summary
    print()
    print("=" * 72)
    print("  RESULTS SUMMARY")
    print("=" * 72)

    if results:
        avg_no_q = sum(r.no_tts_quality for r in results) / len(results)
        avg_tts_q = sum(r.tts_quality for r in results) / len(results)
        avg_delta_val = sum(r.quality_delta for r in results) / len(results)
        avg_delta_pct_val = sum(r.quality_delta_pct for r in results) / len(results)

        metric_keys = ["keyword_coverage", "code_presence", "code_validity",
                       "thoroughness", "security_awareness", "test_quality"]
        metric_avgs = {}
        for key in metric_keys:
            no_vals = [r.no_tts_metrics.get(key, 0) for r in results]
            tts_vals = [r.tts_metrics.get(key, 0) for r in results]
            metric_avgs[key] = {
                "no_tts": round(sum(no_vals) / len(no_vals), 4),
                "tts": round(sum(tts_vals) / len(tts_vals), 4),
                "delta": round((sum(tts_vals) - sum(no_vals)) / len(no_vals), 4),
            }

        improved = sum(1 for r in results if r.quality_delta > 0)
        degraded = sum(1 for r in results if r.quality_delta < 0)
        unchanged = sum(1 for r in results if r.quality_delta == 0)

        print(f"\n  {'Metric':25s} {'No-TTS':>8s} {'TTS':>8s} {'Diff':>8s}")
        print(f"  {'-'*25} {'-'*8} {'-'*8} {'-'*8}")
        print(f"  {'Overall Quality':25s} {avg_no_q:.4f}  {avg_tts_q:.4f}  {avg_delta_val:+.4f}")
        for key, vals in metric_avgs.items():
            label = key.replace("_", " ").title()
            print(f"  {label:25s} {vals['no_tts']:.4f}  {vals['tts']:.4f}  {vals['delta']:+.4f}")

        avg_tokens_no = sum(r.no_tts_tokens for r in results) / len(results)
        avg_tokens_tts = sum(r.tts_tokens for r in results) / len(results)
        avg_time_no = sum(r.no_tts_elapsed_ms for r in results) / len(results)
        avg_time_tts = sum(r.tts_elapsed_ms for r in results) / len(results)

        print(f"\n  {'Tokens':25s} {avg_tokens_no:.0f}     {avg_tokens_tts:.0f}     {avg_tokens_tts - avg_tokens_no:+.0f}")
        print(f"  {'Time (ms)':25s} {avg_time_no:.0f}    {avg_time_tts:.0f}    {avg_time_tts - avg_time_no:+.0f}")

        print(f"\n  Tasks improved:     {improved}/{len(results)} ({improved/len(results)*100:.0f}%)")
        print(f"  Tasks degraded:     {degraded}/{len(results)} ({degraded/len(results)*100:.0f}%)")
        print(f"  Tasks unchanged:    {unchanged}/{len(results)}")
        print(f"  Average Diff:       {avg_delta_val:+.4f} ({avg_delta_pct_val:+.1f}%)")

        print(f"\n  {'Task':50s} {'Complexity':>10s} {'No-TTS':>8s} {'TTS':>8s} {'Diff':>8s}")
        print(f"  {'-'*50} {'-'*10} {'-'*8} {'-'*8} {'-'*8}")
        for r in results:
            ds = f"+{r.quality_delta:.3f}" if r.quality_delta >= 0 else f"{r.quality_delta:.3f}"
            print(f"  {r.title[:48]:48s} {r.complexity_score:.2f}       {r.no_tts_quality:.3f}   {r.tts_quality:.3f}   {ds}")

        print(f"\n  Quality delta:     {avg_delta_val:+.4f} ({avg_delta_pct_val:+.1f}%)")
    else:
        print("  No results collected.")

    # -- Save report
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = args.output or str(DATA_DIR / f"tts_benchmark_{timestamp}.json")

    report = {
        "benchmark": {
            "type": "tts_quality_comparison",
            "mode": "simulation" if args.simulate else "ollama",
            "model": args.model,
            "num_tasks": len(tasks),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "1.0",
        },
        "summary": {
            "avg_no_tts_quality": round(avg_no_q, 4) if results else 0,
            "avg_tts_quality": round(avg_tts_q, 4) if results else 0,
            "avg_quality_delta": round(avg_delta_val, 4) if results else 0,
            "avg_quality_delta_pct": round(avg_delta_pct_val, 1) if results else 0,
            "improved_count": improved,
            "degraded_count": degraded,
            "unchanged_count": unchanged,
        },
        "results": [asdict(r) for r in results],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    report_rel = Path(output_path).relative_to(PROJECT_ROOT)
    print(f"\n  Report saved: {output_path}")
    print(f"  Open: {report_rel}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
