#!/usr/bin/env python3
"""
=========================================================================
  ForgeAI RAG Backend Benchmark Suite

  Compares LightRAG (graph + vector hybrid) vs ChromaDB (BM25 + dense)
  on real coding queries.

  Metrics:
   - Cold-query latency (first-ever query per question)
   - Cache-hit latency (LightRAG only - repeated identical query)
   - Total throughput (concurrent queries)
   - Retrieval-phase latency (ChromaDB hybrid_search only)
   - Answer quality (length as proxy for completeness)

  Usage:
    cd PythonAI && python benchmark_rag.py
=========================================================================
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Ensure src/ is importable
_pythonai_root = Path(__file__).resolve().parent
if str(_pythonai_root) not in sys.path:
    sys.path.insert(0, str(_pythonai_root))

# Fix stdout encoding for Windows terminals
import sys
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
elif sys.platform == 'win32':
    # Fallback: set environment variable
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')  # type: ignore[assignment,union-attr]

# Suppress verbose logging during benchmark
import logging
logging.getLogger().setLevel(logging.WARNING)
logging.getLogger("forgeai.lightrag").setLevel(logging.ERROR)
logging.getLogger("forgeai.api").setLevel(logging.ERROR)

# ======================================================================
# Test Data - 12 real Python questions covering diverse topics
# ======================================================================

BENCHMARK_QUERIES = [
    "How do Python decorators work with arguments?",
    "What is the difference between __str__ and __repr__?",
    "How does asyncio.gather handle exceptions?",
    "What are Python context managers and how do I use contextlib?",
    "How do slots work in Python classes?",
    "What is the difference between a list comprehension and a generator expression?",
    "How does Python's import system work? Absolute vs relative imports.",
    "What are Python data classes and how are they different from named tuples?",
    "How does multiprocessing work in Python? Pool vs Process.",
    "What is the GIL and how does it affect threading in Python?",
    "How do I use typing in Python for better code quality?",
    "What are Python descriptors and how do they work?",
]

# 20 code snippets used as seed data for both backends
SEED_DOCUMENTS = [
    "Python decorators are functions that modify the behavior of other functions. "
    "They use the @ syntax and can accept arguments through nested wrapper functions. "
    "A decorator with arguments requires three levels of nesting: the decorator factory, "
    "the actual decorator, and the wrapper function.",
    "__str__ is called by str() and print() to return a human-readable string representation "
    "of an object. __repr__ is called by repr() and in the REPL to return an unambiguous "
    "representation. Convention: __repr__ should be unambiguous, __str__ should be readable.",
    "asyncio.gather runs awaitables concurrently. If return_exceptions=False (default), "
    "the first exception raises immediately and cancels other tasks. With return_exceptions=True, "
    "exceptions are returned as results instead of raising.",
    "Context managers implement __enter__ and __exit__ methods for resource management. "
    "The contextlib module provides @contextmanager for creating them with yield, "
    "closing() for cleanup, and suppress() for ignoring specific exceptions.",
    "__slots__ is a class variable that restricts attribute creation, saving memory by "
    "preventing the creation of a __dict__ per instance. Useful when creating millions "
    "of objects. Inherited slots are cumulative.",
    "List comprehensions ([x for x in iterable]) create the entire list in memory immediately. "
    "Generator expressions ((x for x in iterable)) produce values lazily one at a time, "
    "using less memory but cannot be indexed or sliced.",
    "Python's import system searches sys.path for modules. Absolute imports specify the "
    "full module path (from package.module import name). Relative imports use dots: "
    ". for current, .. for parent. PEP 328 recommends absolute imports for clarity.",
    "Dataclasses (@dataclass) auto-generate __init__, __repr__, __eq__, and __hash__. "
    "Named tuples are immutable, memory-efficient, and also provide named fields. "
    "Dataclasses offer more flexibility with default factories, __post_init__, and frozen=True.",
    "multiprocessing spawns separate processes with their own GIL. Pool manages a fixed "
    "set of worker processes for map/reduce operations. Process is for individual tasks. "
    "Use if __name__ == '__main__' guard on Windows.",
    "The GIL (Global Interpreter Lock) allows only one thread to execute Python bytecode "
    "at a time. It affects CPU-bound threads but not I/O-bound threads. multiprocessing "
    "bypasses the GIL by using separate processes.",
    "Python's typing module provides type hints: List, Dict, Optional, Union, and Literal. "
    "Use mypy or pyright for static checking. TypedDict for dict shapes, Protocol for "
    "structural subtyping, and TypeVar for generics.",
    "Descriptors are objects that override __get__, __set__, or __delete__ in another "
    "class's namespace. property, classmethod, and staticmethod are built-in descriptors. "
    "They power the entire Python attribute access system.",
    "Python's pathlib module provides object-oriented filesystem paths. Path() replaces "
    "os.path for path manipulation. Supports / operator for joining paths and methods "
    "like .read_text(), .iterdir(), and .glob().",
    "The walrus operator (:=) in Python 3.8+ allows assignment within expressions. "
    "Common uses: while (line := f.readline()):, if (match := re.search(pattern, text)):, "
    "and list comprehensions with intermediate computations.",
    "Python's logging module has five levels: DEBUG, INFO, WARNING, ERROR, CRITICAL. "
    "Use logging.getLogger(__name__) in libraries. Configure with basicConfig() or "
    "a dictConfig for production. Always use lazy %s formatting.",
    "Unit testing in Python uses unittest for traditional OOP tests and pytest for "
    "modern fixtures and assertions. pytest discovers test_*.py files and supports "
    "parametrize, fixtures with yield, and conftest.py for shared setup.",
    "Python's functools module provides lru_cache for memoization, partial for "
    "partial application, reduce for accumulation, wraps for preserving metadata "
    "in decorators, and singledispatch for single-dispatch generic functions.",
    "The itertools module offers efficient looping tools: chain, product, permutations, "
    "combinations, groupby, islice, cycle, repeat, accumulate, and zip_longest. "
    "All return iterators for memory efficiency.",
    "Python exception handling uses try/except/else/finally. The else clause runs "
    "when no exception occurs. finally always runs for cleanup. Use suppress() from "
    "contextlib to ignore specific exceptions without an empty except block.",
    "Virtual environments with venv create isolated Python environments. Use python -m "
    "venv .venv, then source .venv/bin/activate (Linux/Mac) or .venv\\Scripts\\activate "
    "(Windows). requirements.txt tracks dependencies with pip freeze > requirements.txt.",
]


@dataclass
class BenchmarkResult:
    """Stores a single query's benchmark metrics."""
    query: str
    backend: str          # "chroma", "lightrag-naive", "lightrag-local", "lightrag-global", "lightrag-hybrid"
    mode: str             # "cold" or "cache"
    retrieval_ms: float   # Time for retrieval phase only (ChromaDB) or total - LLM overhead
    total_ms: float       # Full end-to-end query time (including LLM generation)
    answer_len: int       # Length of the generated answer in characters
    error: str | None = None


@dataclass
class ConcurrentResult:
    """Stores results from a single concurrent throughput batch."""
    backend: str          # "chroma", "lightrag-hybrid", "lightrag-naive"
    concurrency: int      # Number of parallel workers
    total_queries: int
    wall_time_seconds: float  # Wall-clock time for the entire batch
    qps: float            # Queries per second
    avg_latency_ms: float # Average per-query latency under concurrent load
    p50_ms: float
    p95_ms: float
    min_ms: float
    max_ms: float
    errors: int
    individual_ms: list[float] = field(default_factory=list)


@dataclass
class SummaryStats:
    """Aggregated stats for a backend across all queries."""
    name: str
    count: int
    avg_total_ms: float
    min_total_ms: float
    max_total_ms: float
    p50_ms: float
    p95_ms: float
    avg_retrieval_ms: float
    avg_answer_len: float
    errors: int
    cache_avg_ms: float = 0.0
    cache_hit_rate: float = 0.0


# ======================================================================
# ChromaDB Benchmark
# ======================================================================

def _init_chromadb_seed() -> tuple[Any, Any, Any, list[str]]:
    """Initialize an in-memory ChromaDB with seed documents.
    
    Returns (collection, embedder, bm25, corpus_texts).
    """
    import chromadb
    from sentence_transformers import SentenceTransformer
    
    # Use sentence-transformers for embeddings
    embedder = SentenceTransformer("all-MiniLM-L6-v2")
    
    # Use a unique temp directory for chroma
    temp_dir = tempfile.mkdtemp(prefix="forgeai_bench_chroma_")
    client = chromadb.PersistentClient(path=temp_dir)
    
    try:
        client.delete_collection("benchmark")
    except Exception:
        pass
    
    collection = client.create_collection(name="benchmark", metadata={"hnsw:space": "cosine"})
    
    texts = []
    ids = []
    metadatas = []
    
    for i, doc in enumerate(SEED_DOCUMENTS):
        texts.append(doc)
        ids.append(f"doc_{i:04d}")
        metadatas.append({"title": f"Doc {i}", "version": "", "category": "code"})
    
    embeddings = embedder.encode(texts).tolist()
    collection.add(documents=texts, embeddings=embeddings, ids=ids, metadatas=metadatas)
    
    # Build lightweight BM25
    from src.rag.rag_engine import SimpleBM25
    bm25 = SimpleBM25(texts)
    
    print(f"  [ChromaDB] Seeded {len(SEED_DOCUMENTS)} documents to {temp_dir}")
    return collection, embedder, bm25, texts



def _chroma_query(
    question: str,
    collection: Any,
    embedder: Any,
    bm25: Any,
    corpus_texts: list[str],
) -> tuple[float, float, str]:
    """Run a full ChromaDB query and time both retrieval and total phases.
    
    Returns (retrieval_ms, total_ms, answer_text).
    """
    import ollama
    from src.rag.rag_engine import expand_query, hybrid_search, format_sources, USER_PROMPT_TEMPLATE
    
    # Phase 1: Retrieval (timed separately)
    t0 = time.time()
    
    docs = hybrid_search(
        question,
        collection,
        embedder,
        bm25=bm25,
        corpus_texts=corpus_texts,
        top_k=6,
    )
    
    retrieval_ms = (time.time() - t0) * 1000
    
    # Phase 2: LLM generation
    t1 = time.time()
    
    if docs:
        context_parts = []
        for d in docs:
            citation = f"[{d.get('citation_num', 0)}]"
            part = f"{citation} > {d['title']}\n{d['text'][:1500]}"
            context_parts.append(part)
        context = "\n\n---\n\n".join(context_parts)
    else:
        context = "Use your built-in Python knowledge."
    
    messages = [
        {"role": "system", "content": "You are a Python expert. Answer concisely and accurately."},
        {"role": "user", "content": USER_PROMPT_TEMPLATE.format(context=context, question=question)},
    ]
    
    response = ollama.chat(
        model="qwen2.5-coder:14b",
        messages=messages,
        options={"temperature": 0.3, "num_ctx": 512, "num_predict": 1024, "repeat_penalty": 1.1},
    )
    
    total_ms = (time.time() - t1) * 1000
    answer = response["message"]["content"]
    
    return retrieval_ms, total_ms, answer


# ======================================================================
# LightRAG Benchmark
# ======================================================================

def _init_lightrag_seed() -> Any:
    """Initialize LightRAG backend with seed documents.
    
    Returns the LightRAGAdapter instance.
    """
    from src.rag.lightrag_wrapper import LightRAGAdapter
    
    # Use a temp directory so no cross-contamination
    temp_dir = Path(tempfile.mkdtemp(prefix="forgeai_bench_lightrag_"))
    
    rag = LightRAGAdapter(
        working_dir=str(temp_dir),
        llm_model="qwen2.5-coder:14b",
        embed_model="nomic-embed-text",
    )
    
    # Insert seed documents
    result = rag.insert_texts(SEED_DOCUMENTS)
    print(f"  [LightRAG] Seeded {result['inserted']}/{result['total']} documents to {temp_dir}")
    
    return rag


def _lightrag_query(
    rag: Any,
    question: str,
    mode: str = "hybrid",
    use_cache: bool = True,
) -> tuple[float, str, bool]:
    """Run a LightRAG query and time it.
    
    Returns (total_ms, answer_text, was_cached).
    """
    t0 = time.time()
    answer, sources = rag.query(
        question,
        mode=mode,
        top_k=6,
        use_cache=use_cache,
    )
    total_ms = (time.time() - t0) * 1000
    return total_ms, answer, sources


# ======================================================================
# Concurrent Throughput Testing
# ======================================================================

def _run_concurrent_batch(
    queries: list[str],
    backend_fn: Any,  # Callable that takes a single query string and returns (total_ms, ...)
    backend_name: str,
    concurrency: int = 4,
    label: str = "",
) -> ConcurrentResult:
    """Run a batch of queries concurrently and measure throughput.

    Uses ThreadPoolExecutor to submit all queries simultaneously.
    Measures wall-clock time, QPS, and per-query latency distribution.
    """
    t0 = time.time()
    latencies: list[float] = []
    errors = 0

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(backend_fn, q): q for q in queries}
        for future in as_completed(futures):
            try:
                total_ms, *_ = future.result()
                latencies.append(total_ms)
            except Exception:
                errors += 1
                latencies.append(0.0)

    wall_time = time.time() - t0
    valid_lats = [l for l in latencies if l > 0]

    return ConcurrentResult(
        backend=backend_name,
        concurrency=concurrency,
        total_queries=len(queries),
        wall_time_seconds=round(wall_time, 2),
        qps=round(len(queries) / wall_time, 2) if wall_time > 0 else 0.0,
        avg_latency_ms=round(sum(valid_lats) / len(valid_lats), 1) if valid_lats else 0.0,
        p50_ms=round(_percentile(valid_lats, 50), 1),
        p95_ms=round(_percentile(valid_lats, 95), 1),
        min_ms=round(min(valid_lats), 1) if valid_lats else 0.0,
        max_ms=round(max(valid_lats), 1) if valid_lats else 0.0,
        errors=errors,
        individual_ms=latencies,
    )


# ======================================================================
# Main Benchmark Runner
# ======================================================================

BANNER = r"""
+========================================================================+
|              ForgeAI RAG Backend Benchmark Suite                        |
|                                                                         |
|  LightRAG (graph + vector hybrid) vs ChromaDB (BM25 + dense)           |
+========================================================================+
"""


def run_benchmark() -> dict[str, Any]:
    """Main benchmark entry point. Returns structured results."""
    print(BANNER)
    
    all_results: list[BenchmarkResult] = []
    config = {
        "model": "qwen2.5-coder:14b",
        "embed_model": "nomic-embed-text",
        "num_queries": len(BENCHMARK_QUERIES),
        "test_queries": BENCHMARK_QUERIES[:4],  # Use 4 queries for quick run; all 12 for full
        "cache_test_queries": ["How do Python decorators work with arguments?",
                                "What is the difference between __str__ and __repr__?"],
    }
    
    # Phase 1: Initialize backends
    
    print("\n[Phase 1/4] Seeding backends with test data...\n")
    
    t_seed_start = time.time()
    
    # ChromaDB
    print("[1/2] Initializing ChromaDB...")
    chroma_coll, chroma_embedder, chroma_bm25, chroma_corpus = _init_chromadb_seed()
    
    # LightRAG
    print("[2/2] Initializing LightRAG...")
    lightrag = _init_lightrag_seed()
    
    seed_time = time.time() - t_seed_start
    
    # Phase 2: Cold queries (first-ever, no cache)
    
    print(f"\n[Phase 2/4] Running cold queries ({len(config['test_queries'])} questions)...\n")
    
    t_cold_start = time.time()
    
    for i, query in enumerate(config["test_queries"]):
        print(f"  [{i+1}/{len(config['test_queries'])}] \"{query[:50]}...\"")
        
        # ── ChromaDB ──
        try:
            ret_ms, total_ms, answer = _chroma_query(
                query, chroma_coll, chroma_embedder, chroma_bm25, chroma_corpus
            )
            all_results.append(BenchmarkResult(
                query=query, backend="chroma", mode="cold",
                retrieval_ms=ret_ms, total_ms=total_ms, answer_len=len(answer),
            ))
            print(f"    ChromaDB:  {total_ms:7.0f}ms total, {ret_ms:5.0f}ms retrieval, {len(answer)} chars")
        except Exception as e:
            all_results.append(BenchmarkResult(
                query=query, backend="chroma", mode="cold",
                retrieval_ms=0, total_ms=0, answer_len=0, error=str(e),
            ))
            print(f"    ChromaDB:  ERROR - {e}")
        
        # ── LightRAG hybrid ──
        try:
            total_ms, answer, _ = _lightrag_query(lightrag, query, mode="hybrid", use_cache=False)
            all_results.append(BenchmarkResult(
                query=query, backend="lightrag-hybrid", mode="cold",
                retrieval_ms=total_ms, total_ms=total_ms, answer_len=len(answer),
            ))
            print(f"    LightRAG:  {total_ms:7.0f}ms (hybrid), {len(answer)} chars")
        except Exception as e:
            all_results.append(BenchmarkResult(
                query=query, backend="lightrag-hybrid", mode="cold",
                retrieval_ms=0, total_ms=0, answer_len=0, error=str(e),
            ))
            print(f"    LightRAG:  ERROR - {e}")
        
        # ── LightRAG naive (fastest mode) ──
        try:
            total_ms, answer, _ = _lightrag_query(lightrag, query, mode="naive", use_cache=False)
            all_results.append(BenchmarkResult(
                query=query, backend="lightrag-naive", mode="cold",
                retrieval_ms=total_ms, total_ms=total_ms, answer_len=len(answer),
            ))
            print(f"    LightRAG:  {total_ms:7.0f}ms (naive), {len(answer)} chars")
        except Exception as e:
            all_results.append(BenchmarkResult(
                query=query, backend="lightrag-naive", mode="cold",
                retrieval_ms=0, total_ms=0, answer_len=0, error=str(e),
            ))
            print(f"    LightRAG:  ERROR - {e}")
        
        print()
    
    cold_time = time.time() - t_cold_start

    # ── Phase 3: Concurrent throughput testing ──

    throughput_queries = config["test_queries"][:3]  # Use first 3 cold queries
    concurrency_levels = [1, 2, 4]
    throughput_results: list[ConcurrentResult] = []

    # Build single-query wrappers for concurrent dispatch
    def _make_chroma_fn() -> Any:
        """Returns a callable that runs a single ChromaDB query."""
        def _fn(q: str) -> tuple[float, float, str]:
            return _chroma_query(q, chroma_coll, chroma_embedder, chroma_bm25, chroma_corpus)
        return _fn

    def _make_lightrag_fn(mode: str = "hybrid") -> Any:
        """Returns a callable that runs a single LightRAG query."""
        def _fn(q: str) -> tuple[float, str, Any]:
            return _lightrag_query(lightrag, q, mode=mode, use_cache=False)
        return _fn

    print(f"\n[Phase 3/5] Concurrent throughput testing ({len(throughput_queries)} queries x 3 concurrency levels x 3 backends)...\n")

    t_concurrent_start = time.time()

    for backend_label, backend_fn_factory in [
        ("chroma", _make_chroma_fn),
        ("lightrag-hybrid", lambda: _make_lightrag_fn("hybrid")),
        ("lightrag-naive", lambda: _make_lightrag_fn("naive")),
    ]:
        print(f"  [{backend_label}]")
        for cl in concurrency_levels:
            fn = backend_fn_factory()
            result = _run_concurrent_batch(
                queries=throughput_queries,
                backend_fn=fn,
                backend_name=backend_label,
                concurrency=cl,
                label=f"{backend_label} @ concurrency={cl}",
            )
            throughput_results.append(result)
            print(f"    concurrency={cl}: {result.total_queries} queries in {result.wall_time_seconds:.1f}s = {result.qps:.1f} QPS, "
                  f"avg latency {result.avg_latency_ms:.0f}ms, errors={result.errors}")
        print()

    concurrent_time = time.time() - t_concurrent_start
    
    # Phase 4: Cache benchmark (LightRAG only, identical queries)
    
    print(f"\n[Phase 4/5] Cache benchmark (LightRAG, 2 queries x 3 repeats)...\n")
    
    t_cache_start = time.time()
    
    for query in config["cache_test_queries"]:
        print(f"  \"{query[:50]}...\"")
        
        # First call — cold (no cache)
        try:
            # Ensure fresh state by disabling cache for first call
            total_ms_first, _, _ = _lightrag_query(lightrag, query, mode="hybrid", use_cache=False)
            # Clear any residual cache
            lightrag.clear_cache()
            # Now with cache disabled for first call, then enabled
            total_ms_first, _, _ = _lightrag_query(lightrag, query, mode="hybrid", use_cache=False)
            # Now with cache enabled — should hit
            total_ms_cached, answer_cached, _ = _lightrag_query(lightrag, query, mode="hybrid", use_cache=True)
            # and again — should be even faster
            total_ms_cached2, _, _ = _lightrag_query(lightrag, query, mode="hybrid", use_cache=True)
            
            all_results.append(BenchmarkResult(
                query=query, backend="lightrag-cache", mode="cold",
                retrieval_ms=total_ms_first, total_ms=total_ms_first, answer_len=len(answer_cached),
            ))
            all_results.append(BenchmarkResult(
                query=query, backend="lightrag-cache", mode="cache",
                retrieval_ms=total_ms_cached, total_ms=total_ms_cached, answer_len=len(answer_cached),
            ))
            
            print(f"    Cold:   {total_ms_first:7.0f}ms")
            print(f"    Cached: {total_ms_cached:7.0f}ms ({total_ms_cached2:7.0f}ms on 2nd hit)")
            print(f"    Speedup: {total_ms_first / max(total_ms_cached, 1):.1f}x")
        except Exception as e:
            print(f"    ERROR - {e}")
        
        print()
    
    cache_time = time.time() - t_cache_start

    # Phase 5: Summary & Report

    print(f"\n[Phase 5/5] Generating report...\n")

    # Aggregate results
    report = _generate_report(
        results=all_results,
        config=config,
        seed_time=seed_time,
        cold_time=cold_time,
        cache_time=cache_time,
        concurrent_time=concurrent_time,
        throughput_results=throughput_results,
    )

    # Also extract LightRAG cache stats
    try:
        cache_st = lightrag.cache_stats()
        report["cache_stats_from_adapter"] = cache_st
        report["per_mode_queries"] = lightrag.get_stats().get("per_mode_queries", {})
    except Exception:
        pass

    return report


# ======================================================================
# Report Generator
# ======================================================================

def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    idx = max(0, min(len(sorted_v) - 1, int(len(sorted_v) * p / 100)))
    return sorted_v[idx]


def _generate_report(
    results: list[BenchmarkResult],
    config: dict[str, Any],
    seed_time: float,
    cold_time: float,
    cache_time: float,
    concurrent_time: float = 0.0,
    throughput_results: list[ConcurrentResult] | None = None,
) -> dict[str, Any]:
    """Generate a structured benchmark report."""
    
    # Group by backend and mode
    groups: dict[str, list[BenchmarkResult]] = {}
    for r in results:
        key = f"{r.backend}::{r.mode}"
        if key not in groups:
            groups[key] = []
        groups[key].append(r)
    
    # Compute stats per group
    stats_by_backend: dict[str, SummaryStats] = {}
    for key, group in groups.items():
        backend_name = key.split("::")[0]
        mode = key.split("::")[1]
        
        totals = [r.total_ms for r in group if r.error is None]
        retrievals = [r.retrieval_ms for r in group if r.error is None]
        answer_lens = [r.answer_len for r in group if r.error is None]
        errors = sum(1 for r in group if r.error is not None)
        
        # Display name
        display_name = {
            "chroma": "ChromaDB  ",
            "lightrag-hybrid": "LightRAG  ",
            "lightrag-naive": "L-Naive   ",
            "lightrag-cache": "L-Cache   ",
        }.get(backend_name, backend_name)
        
        stats = SummaryStats(
            name=display_name,
            count=len(group) - errors,
            avg_total_ms=sum(totals) / len(totals) if totals else 0.0,
            min_total_ms=min(totals) if totals else 0.0,
            max_total_ms=max(totals) if totals else 0.0,
            p50_ms=_percentile(totals, 50),
            p95_ms=_percentile(totals, 95),
            avg_retrieval_ms=sum(retrievals) / len(retrievals) if retrievals else 0.0,
            avg_answer_len=sum(answer_lens) / len(answer_lens) if answer_lens else 0.0,
            errors=errors,
        )
        stats_by_backend[f"{backend_name} ({mode})"] = stats
    
    # Print report
    _print_report_table(stats_by_backend, config, seed_time, cold_time, cache_time, len(results),
                        concurrent_time=concurrent_time, throughput_results=throughput_results)
    
    # Return structured data for dashboard
    return _build_report_structured(
        stats_by_backend, config, seed_time, cold_time, cache_time, results,
        concurrent_time=concurrent_time, throughput_results=throughput_results,
    )


def _print_report_table(
    stats: dict[str, SummaryStats],
    config: dict[str, Any],
    seed_time: float,
    cold_time: float,
    cache_time: float,
    total_runs: int,
    concurrent_time: float = 0.0,
    throughput_results: list[ConcurrentResult] | None = None,
) -> None:
    """Print a formatted comparison table."""
    
    print("=" * 100)
    print("  BENCHMARK RESULTS SUMMARY")
    print("=" * 100)
    print(f"  Model: {config['model']}")
    print(f"  Queries: {config['num_queries']} (cold: {len(config['test_queries'])}, cache: {len(config['cache_test_queries'])})")
    print(f"  Seed time: {seed_time:.1f}s | Cold runs: {cold_time:.1f}s | "
          f"Throughput: {concurrent_time:.1f}s | Cache runs: {cache_time:.1f}s")
    print()
    
    # Table header
    print(f"  {'Backend':<15s} {'Avg (ms)':<10s} {'Min (ms)':<10s} {'Max (ms)':<10s} "
          f"{'P50 (ms)':<10s} {'P95 (ms)':<10s} {'Avg Chars':<10s} {'Errors':<8s}")
    print(f"  {'─' * 14}  {'─' * 8}  {'─' * 8}  {'─' * 8}  "
          f"{'─' * 8}  {'─' * 8}  {'─' * 8}  {'─' * 6}")
    
    # Sort by avg total_ms
    sorted_stats = sorted(stats.values(), key=lambda s: s.avg_total_ms)
    
    for s in sorted_stats:
        print(f"  {s.name:<15s} {s.avg_total_ms:>8.0f}  {s.min_total_ms:>8.0f}  {s.max_total_ms:>8.0f}  "
              f"{s.p50_ms:>8.0f}  {s.p95_ms:>8.0f}  {s.avg_answer_len:>8.0f}  {s.errors:>6d}")
    
    print()
    
    # Comparison ratios
    chroma_cold = None
    lightrag_hybrid_cold = None
    lightrag_naive_cold = None
    lightrag_cache = None
    
    for name, s in stats.items():
        if "chroma" in name.lower() and "cold" in name:
            chroma_cold = s
        elif "lightrag" in name.lower() and "hybrid" in name.lower() and "cold" in name:
            lightrag_hybrid_cold = s
        elif "naive" in name.lower() and "cold" in name:
            lightrag_naive_cold = s
        elif "cache" in name.lower() and "cache" in name:
            lightrag_cache = s
    
    if chroma_cold and lightrag_hybrid_cold:
        ratio = chroma_cold.avg_total_ms / max(lightrag_hybrid_cold.avg_total_ms, 1)
        print(f"  [BENCH] LightRAG hybrid vs ChromaDB: {ratio:.1f}x {'faster' if ratio > 1 else 'slower'}")
    
    if lightrag_naive_cold and lightrag_hybrid_cold:
        ratio = lightrag_hybrid_cold.avg_total_ms / max(lightrag_naive_cold.avg_total_ms, 1)
        print(f"  [BENCH] LightRAG naive vs hybrid: {ratio:.1f}x {'faster' if ratio > 1 else 'slower'}")
    
    if lightrag_cache and lightrag_hybrid_cold:
        ratio = lightrag_hybrid_cold.avg_total_ms / max(lightrag_cache.avg_total_ms, 1)
        print(f"  [BENCH] LightRAG cache vs cold: {ratio:.1f}x speedup")
    
    if chroma_cold and lightrag_naive_cold:
        ratio = chroma_cold.avg_total_ms / max(lightrag_naive_cold.avg_total_ms, 1)
        print(f"  [BENCH] LightRAG naive vs ChromaDB: {ratio:.1f}x {'faster' if ratio > 1 else 'slower'}")
    
    # Answer quality comparison
    print()
    print(f"  {'Backend':<15s} {'Avg Chars':<10s} {'Quality Ratio':<15s}")
    print(f"  {'─' * 14}  {'─' * 8}  {'─' * 13}")
    if chroma_cold:
        baseline = chroma_cold.avg_answer_len
        for s in sorted_stats:
            if baseline > 0:
                qual_ratio = s.avg_answer_len / baseline
                indicator = "^" if qual_ratio > 1.1 else "v" if qual_ratio < 0.9 else "~"
                print(f"  {s.name:<15s} {s.avg_answer_len:>8.0f}  {qual_ratio:>6.2f}x {indicator}")
    
    print()
    print("  Legend: ^ longer (more verbose)  v shorter (more concise)  ~ similar")
    print("=" * 100)
    print()

    # Throughput results section
    if throughput_results:
        print("  CONCURRENT THROUGHPUT RESULTS")
        print()
        print(f"  {'Backend':<20s} {'Conc':<6s} {'Queries':<8s} {'Wall (s)':<10s} {'QPS':<10s} {'Avg Lat (ms)':<14s} {'P50 (ms)':<10s} {'P95 (ms)':<10s} {'Errors':<8s}")
        print(f"  {'─' * 19}  {'─' * 4}  {'─' * 6}  {'─' * 8}  {'─' * 8}  {'─' * 12}  {'─' * 8}  {'─' * 8}  {'─' * 6}")
        for tr in throughput_results:
            label = {"chroma": "ChromaDB", "lightrag-hybrid": "LightRAG  ", "lightrag-naive": "L-Naive   "}.get(tr.backend, tr.backend)
            print(f"  {label:<20s} {tr.concurrency:<6d} {tr.total_queries:<8d} "
                  f"{tr.wall_time_seconds:<10.1f} {tr.qps:<10.1f} {tr.avg_latency_ms:<14.0f} "
                  f"{tr.p50_ms:<10.0f} {tr.p95_ms:<10.0f} {tr.errors:<8d}")
        print()

        # QPS speedup summary
        qps_by_backend: dict[str, dict[int, float]] = {}
        for tr in throughput_results:
            qps_by_backend.setdefault(tr.backend, {})[tr.concurrency] = tr.qps

        print("  Throughput scaling (QPS ratio vs concurrency=1):")
        for backend_label in ["chroma", "lightrag-hybrid", "lightrag-naive"]:
            if backend_label in qps_by_backend:
                q1 = qps_by_backend[backend_label].get(1, 0)
                parts = [f"  {backend_label:<20s}"]
                for cl in [2, 4]:
                    qc = qps_by_backend[backend_label].get(cl, 0)
                    if q1 > 0 and qc > 0:
                        parts.append(f"@{cl}: {qc / q1:.1f}x")
                    else:
                        parts.append(f"@{cl}: N/A")
                print("  ".join(parts))
        print()
        print("  Best QPS:")
        best_qps = max(throughput_results, key=lambda r: r.qps, default=None)
        if best_qps:
            print(f"    {best_qps.backend} @ concurrency={best_qps.concurrency}: {best_qps.qps:.1f} QPS")
        print("=" * 100)
        print()


def _build_report_structured(
    stats: dict[str, SummaryStats],
    config: dict[str, Any],
    seed_time: float,
    cold_time: float,
    cache_time: float,
    results: list[BenchmarkResult],
    concurrent_time: float = 0.0,
    throughput_results: list[ConcurrentResult] | None = None,
) -> dict[str, Any]:
    """Build a structured dict for dashboard consumption."""
    
    comparisons: dict[str, float] = {}
    
    chroma_cold = next((s for name, s in stats.items() if "chroma" in name.lower() and "cold" in name), None)
    lr_hybrid = next((s for name, s in stats.items() if "lightrag" in name.lower() and "hybrid" in name.lower() and "cold" in name), None)
    lr_naive = next((s for name, s in stats.items() if "naive" in name.lower() and "cold" in name), None)
    lr_cache = next((s for name, s in stats.items() if "cache" in name.lower() and "cache" in name), None)
    
    if chroma_cold and lr_hybrid:
        comparisons["lightrag_vs_chromadb"] = round(chroma_cold.avg_total_ms / max(lr_hybrid.avg_total_ms, 1), 2)
    if chroma_cold and lr_naive:
        comparisons["naive_vs_chromadb"] = round(chroma_cold.avg_total_ms / max(lr_naive.avg_total_ms, 1), 2)
    if lr_hybrid and lr_cache:
        comparisons["cache_vs_cold"] = round(lr_hybrid.avg_total_ms / max(lr_cache.avg_total_ms, 1), 2)
    if lr_hybrid and lr_naive:
        comparisons["hybrid_vs_naive"] = round(lr_hybrid.avg_total_ms / max(lr_naive.avg_total_ms, 1), 2)
    
    # Raw details per query
    details = []
    for r in results:
        details.append({
            "query": r.query[:80],
            "backend": r.backend,
            "mode": r.mode,
            "total_ms": round(r.total_ms, 1),
            "retrieval_ms": round(r.retrieval_ms, 1),
            "answer_len": r.answer_len,
            "error": r.error,
        })
    
    # Build throughput section
    throughput = {
        "concurrent_time_seconds": round(concurrent_time, 1),
        "results": [],
        "scaling": {},
        "best_qps": 0.0,
        "best_backend": "",
        "best_concurrency": 0,
    }
    if throughput_results:
        qps_by_backend: dict[str, dict[int, float]] = {}
        for tr in throughput_results:
            tr_dict = {
                "backend": tr.backend,
                "concurrency": tr.concurrency,
                "total_queries": tr.total_queries,
                "wall_time_seconds": tr.wall_time_seconds,
                "qps": tr.qps,
                "avg_latency_ms": tr.avg_latency_ms,
                "p50_ms": tr.p50_ms,
                "p95_ms": tr.p95_ms,
                "min_ms": tr.min_ms,
                "max_ms": tr.max_ms,
                "errors": tr.errors,
            }
            throughput["results"].append(tr_dict)
            qps_by_backend.setdefault(tr.backend, {})[tr.concurrency] = tr.qps

        # Compute scaling ratios
        scaling: dict[str, dict[str, float]] = {}
        for backend_label, levels in qps_by_backend.items():
            q1 = levels.get(1, 0)
            scaling[backend_label] = {}
            for cl in [2, 4]:
                qc = levels.get(cl, 0)
                scaling[backend_label][str(cl)] = round(qc / q1, 2) if q1 > 0 else 0.0
        throughput["scaling"] = scaling

        # Best QPS across all runs
        best = max(throughput_results, key=lambda r: r.qps, default=None)
        if best:
            throughput["best_qps"] = best.qps
            throughput["best_backend"] = best.backend
            throughput["best_concurrency"] = best.concurrency

        # Throughput speedup comparisons
        chroma_q4 = qps_by_backend.get("chroma", {}).get(4, 0)
        lr_hybrid_q4 = qps_by_backend.get("lightrag-hybrid", {}).get(4, 0)
        lr_naive_q4 = qps_by_backend.get("lightrag-naive", {}).get(4, 0)
        if chroma_q4 > 0 and lr_hybrid_q4 > 0:
            comparisons["throughput_lightrag_vs_chromadb_q4"] = round(lr_hybrid_q4 / chroma_q4, 2)
        if chroma_q4 > 0 and lr_naive_q4 > 0:
            comparisons["throughput_naive_vs_chromadb_q4"] = round(lr_naive_q4 / chroma_q4, 2)

    return {
        "version": "1.0",
        "timestamp": time.time(),
        "config": config,
        "timing": {
            "seed_seconds": round(seed_time, 1),
            "cold_queries_seconds": round(cold_time, 1),
            "concurrent_seconds": round(concurrent_time, 1),
            "cache_queries_seconds": round(cache_time, 1),
            "total_seconds": round(seed_time + cold_time + concurrent_time + cache_time, 1),
        },
        "throughput": throughput,
        "comparisons": comparisons,
        "stats": {name: {
            "avg_total_ms": round(s.avg_total_ms, 1),
            "min_total_ms": round(s.min_total_ms, 1),
            "max_total_ms": round(s.max_total_ms, 1),
            "p50_ms": round(s.p50_ms, 1),
            "p95_ms": round(s.p95_ms, 1),
            "avg_retrieval_ms": round(s.avg_retrieval_ms, 1),
            "avg_answer_len": round(s.avg_answer_len, 1),
            "count": s.count,
            "errors": s.errors,
        } for name, s in stats.items()},
        "details": details,
    }


# ======================================================================
# Save results and CLI
# ======================================================================

def save_report(report: dict[str, Any], path: str | Path | None = None) -> Path:
    """Save benchmark report as JSON.
    
    Defaults to PythonAI/data/benchmark/rag_benchmark_TIMESTAMP.json
    """
    if path is None:
        data_dir = Path(__file__).parent / "data" / "benchmark"
        data_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        path = data_dir / f"rag_benchmark_{timestamp}.json"
    
    path = Path(path)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  Report saved to: {path}")
    return path


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="ForgeAI RAG Backend Benchmark")
    parser.add_argument("--quick", action="store_true", help="Quick run: 2 queries instead of 4")
    parser.add_argument("--output", default="", help="Path to save report JSON")
    parser.add_argument("--no-save", action="store_true", help="Don't save report to file")
    parser.add_argument("--compare-only", action="store_true", help="Skip seed phase, use existing")
    args = parser.parse_args()
    
    # Quick mode is handled inside run_benchmark() via BENCHMARK_QUERIES[:2]
    if args.quick:
        BENCHMARK_QUERIES = BENCHMARK_QUERIES[:2]  # type: ignore[name-defined]
    print("  This benchmark seeds both ChromaDB and LightRAG with 20 sample")
    print("  Python documentation snippets, then runs queries against both.")
    print()
    print("  NOTE: Each query triggers an Ollama call (qwen2.5-coder:14b).")
    print(f"  Estimated time: ~3-5 minutes for {len(BENCHMARK_QUERIES[:4]) * 3} queries.")
    print()
    
    try:
        report = run_benchmark()
        
        if not args.no_save:
            output_path = args.output if args.output else ""
            save_report(report, output_path)
        
        # Quick validity check
        comparisons = report.get("comparisons", {})
        ratios = []
        for key, val in comparisons.items():
            ratios.append(f"{key}={val}x")
        
        if ratios:
            print(f"\n  Key ratios: {', '.join(ratios)}")
        
        print("\n  [OK] Benchmark complete!")
        
    except KeyboardInterrupt:
        print("\n\n  [WARN] Benchmark cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n  [FAIL] Benchmark failed: {e}")
        traceback.print_exc()
        sys.exit(1)
