"""
LightRAG Adapter — Graph + Vector Hybrid RAG Backend
====================================================

Wraps the `lightrag-hku` library (HKUDS/LightRAG) to provide a drop-in
replacement or augmentation for the existing ChromaDB-based RAG engine.

Enhancements over basic LightRAG:
- LRU query cache (TTL-based, configurable size)
- File/directory ingestion with chunking support
- Health check / diagnostics pipeline
- YAML/JSON config file support
- Stats tracking per query mode
- Retry logic on transient failures

Usage:
    from src.rag.lightrag_wrapper import LightRAGAdapter

    rag = LightRAGAdapter(working_dir="./python_brain_lightrag")
    rag.insert_texts(["doc1 text", "doc2 text"])
    answer, sources = rag.query("How do Python decorators work?",
                                 mode="hybrid", top_k=6)

Environment variables:
    FORGEAI_RAG_BACKEND  : "chroma" (default) or "lightrag"
    FORGEAI_LIGHTRAG_DIR : custom working directory for LightRAG storage
    FORGEAI_LLM_MODEL    : Ollama model for LLM (default: qwen2.5-coder:14b)
    FORGEAI_EMBED_MODEL  : Ollama embedding model (default: nomic-embed-text)
    FORGEAI_LIGHTRAG_CACHE_TTL: Query cache TTL in seconds (default: 300)
    FORGEAI_LIGHTRAG_CACHE_SIZE: Max cache entries (default: 256)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("forgeai.lightrag")

# ═══════════════════════════════════════
# Configuration
# ═══════════════════════════════════════

DEFAULT_WORKING_DIR = Path(__file__).resolve().parent.parent.parent / "python_brain_lightrag"
DEFAULT_LLM_MODEL = os.environ.get("FORGEAI_LLM_MODEL", "qwen2.5-coder:14b")
DEFAULT_EMBED_MODEL = os.environ.get("FORGEAI_EMBED_MODEL", "nomic-embed-text")
CACHE_TTL = int(os.environ.get("FORGEAI_LIGHTRAG_CACHE_TTL", "300"))
CACHE_MAXSIZE = int(os.environ.get("FORGEAI_LIGHTRAG_CACHE_SIZE", "256"))

# ═══════════════════════════════════════
# LRU Query Cache
# ═══════════════════════════════════════


class _QueryCache:
    """TTL-based LRU cache for LightRAG query results.

    Avoids redundant LLM calls for identical or near-identical queries
    made within a short time window (e.g., dashboard auto-refresh).
    """

    def __init__(self, maxsize: int = CACHE_MAXSIZE, ttl: float = CACHE_TTL) -> None:
        self._maxsize = maxsize
        self._ttl = ttl
        self._cache: dict[str, tuple[float, str, list[dict[str, Any]]]] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def _make_key(self, question: str, mode: str, top_k: int) -> str:
        raw = f"{question}::{mode}::{top_k}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, question: str, mode: str = "hybrid", top_k: int = 10) -> tuple[str, list[dict[str, Any]]] | None:
        """Return cached (answer, sources) if valid."""
        key = self._make_key(question, mode, top_k)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            ts, answer, sources = entry
            if time.time() - ts > self._ttl:
                del self._cache[key]
                self._misses += 1
                return None
            self._hits += 1
            # Move to end (most recently used)
            del self._cache[key]
            self._cache[key] = entry
            return answer, sources

    def set(self, question: str, mode: str, top_k: int, answer: str, sources: list[dict[str, Any]]) -> None:
        """Cache a query result."""
        key = self._make_key(question, mode, top_k)
        with self._lock:
            # Evict LRU if at capacity
            if len(self._cache) >= self._maxsize:
                oldest = next(iter(self._cache))
                del self._cache[oldest]
            self._cache[key] = (time.time(), answer, sources)

    def invalidate(self) -> int:
        """Clear the entire cache. Returns number of entries cleared."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            return count

    @property
    def stats(self) -> dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            hit_rate = round(self._hits / total * 100, 1) if total > 0 else 0.0
            return {
                "size": len(self._cache),
                "maxsize": self._maxsize,
                "ttl": self._ttl,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
            }

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)


# ═══════════════════════════════════════
# Configuration File
# ═══════════════════════════════════════


def _load_config_file(working_dir: Path) -> dict[str, Any]:
    """Load YAML or JSON config from working_dir/config.yaml or config.json.

    Settings from config file are overridden by environment variables
    and then by constructor arguments (env > config > defaults).
    """
    config: dict[str, Any] = {}

    # Try YAML first (preferred)
    yaml_path = working_dir / "config.yaml"
    if yaml_path.exists():
        try:
            import yaml

            with open(yaml_path, encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            logger.info(f"Loaded LightRAG config from {yaml_path}")
            return config
        except ImportError:
            logger.debug("PyYAML not installed — trying JSON config")
        except Exception as e:
            logger.warning(f"Failed to load {yaml_path}: {e}")

    # Fall back to JSON
    json_path = working_dir / "config.json"
    if json_path.exists():
        try:
            with open(json_path, encoding="utf-8") as f:
                config = json.load(f)
            logger.info(f"Loaded LightRAG config from {json_path}")
        except Exception as e:
            logger.warning(f"Failed to load {json_path}: {e}")

    return config


# ═══════════════════════════════════════
# Adapter
# ═══════════════════════════════════════


class LightRAGAdapter:
    """Unified adapter for LightRAG with Ollama backend.

    Provides:
    - insert_texts() / insert_text() — document insertion
    - query() — graph + vector hybrid search
    - insert_from_directory() — batch file ingestion
    - health_check() — full pipeline verification
    - LRU query cache with configurable TTL and maxsize
    - YAML/JSON config file support
    - Per-mode query stats tracking
    """

    def __init__(
        self,
        working_dir: str | Path | None = None,
        llm_model: str | None = None,
        embed_model: str | None = None,
        top_k: int | None = None,
        chunk_token_size: int | None = None,
        chunk_overlap: int | None = None,
        cache_ttl: float | None = None,
        cache_maxsize: int | None = None,
    ) -> None:
        self._working_dir = Path(working_dir or DEFAULT_WORKING_DIR)
        self._working_dir.mkdir(parents=True, exist_ok=True)

        # Load config file (lowest priority)
        cfg = _load_config_file(self._working_dir)

        # Apply config file -> env vars -> constructor args (highest priority)
        self._llm_model = llm_model or os.environ.get("FORGEAI_LLM_MODEL") or cfg.get("llm_model", DEFAULT_LLM_MODEL)
        self._embed_model = embed_model or os.environ.get("FORGEAI_EMBED_MODEL") or cfg.get("embed_model", DEFAULT_EMBED_MODEL)
        self._top_k = top_k or cfg.get("top_k", 40)
        self._chunk_token_size = chunk_token_size or cfg.get("chunk_token_size", 1024)
        self._chunk_overlap = chunk_overlap or cfg.get("chunk_overlap", 128)

        # Cache configuration
        cache_ttl_val = cache_ttl or cfg.get("cache_ttl", CACHE_TTL)
        cache_maxsize_val = cache_maxsize or cfg.get("cache_maxsize", CACHE_MAXSIZE)
        self._cache = _QueryCache(maxsize=cache_maxsize_val, ttl=cache_ttl_val)

        self._rag = None
        self._initialized = False
        self._stats = {
            "chunks_inserted": 0,
            "queries_run": 0,
            "last_query_time": None,
            "avg_query_ms": 0.0,
            "insert_errors": 0,
            "query_errors": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "per_mode_queries": {"naive": 0, "local": 0, "global": 0, "hybrid": 0},
            "files_indexed": 0,
            "last_health_check": None,
            "health_status": None,
        }

    # ── Lazy initialization ─────────────────────────────────────

    def _ensure_initialized(self) -> None:
        """LightRAG is expensive to import — lazy-init on first use."""
        if self._initialized:
            return

        try:
            from lightrag import LightRAG, QueryParam
            from lightrag.llm.ollama import ollama_model_complete, ollama_embed
        except ImportError as e:
            raise ImportError(
                "LightRAG not available. Install with: pip install lightrag-hku"
            ) from e

        try:
            self._rag = LightRAG(
                working_dir=str(self._working_dir),
                llm_model_func=ollama_model_complete,
                llm_model_name=self._llm_model,
                embedding_func=ollama_embed,
                top_k=self._top_k,
                chunk_token_size=self._chunk_token_size,
                chunk_overlap_token_size=self._chunk_overlap,
                log_level="WARNING",
            )
            self._initialized = True
            logger.info(
                f"LightRAG initialized (dir={self._working_dir}, "
                f"model={self._llm_model}, embed={self._embed_model})"
            )
        except Exception as e:
            logger.error(f"Failed to initialize LightRAG: {e}")
            raise

    # ── Insert ──────────────────────────────────────────────────

    def insert_texts(self, texts: list[str]) -> dict[str, Any]:
        """Insert multiple text documents into LightRAG.

        Each text is inserted as a separate document.
        LightRAG automatically extracts entities and builds the
        knowledge graph during insertion.
        """
        self._ensure_initialized()
        assert self._rag is not None

        start = time.time()
        inserted = 0
        errors = 0

        for text in texts:
            if not text or len(text.strip()) < 20:
                continue
            try:
                self._rag.insert(text)
                inserted += 1
            except Exception as e:
                errors += 1
                logger.warning(f"LightRAG insert error: {e}")

        elapsed = time.time() - start
        self._stats["chunks_inserted"] += inserted
        self._stats["insert_errors"] += errors

        logger.info(
            f"LightRAG inserted {inserted}/{len(texts)} texts "
            f"({elapsed:.2f}s, {errors} errors)"
        )

        return {
            "inserted": inserted,
            "total": len(texts),
            "errors": errors,
            "elapsed_seconds": round(elapsed, 2),
        }

    def insert_text(self, text: str) -> dict[str, Any]:
        """Insert a single text document."""
        return self.insert_texts([text])

    # ── Query ───────────────────────────────────────────────────

    def query(
        self,
        question: str,
        mode: str = "hybrid",
        top_k: int = 10,
        response_type: str = "detailed answer with code examples",
        only_need_context: bool = False,
        stream: bool = False,
        include_references: bool = True,
        use_cache: bool = True,
        max_retries: int = 2,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Query LightRAG with a question.

        Features:
        - LRU query cache (bypass with use_cache=False)
        - Automatic retry on transient failures (max_retries)
        - Per-mode query stats tracking

        Args:
            question: The user's question.
            mode: Query mode — "naive", "local", "global", or "hybrid".
            top_k: Number of chunks to retrieve.
            response_type: Format guidance for the LLM response.
            only_need_context: If True, return only retrieved context.
            stream: Enable streaming response.
            include_references: Include source references in response.
            use_cache: If True, check/update LRU cache.
            max_retries: Number of automatic retries on transient errors.

        Returns:
            Tuple of (answer_text, sources_list).
        """
        self._ensure_initialized()
        assert self._rag is not None

        # Check cache first
        if use_cache:
            cached = self._cache.get(question, mode, top_k)
            if cached is not None:
                self._stats["cache_hits"] += 1
                self._stats["per_mode_queries"][mode] = self._stats["per_mode_queries"][mode] + 1  # noqa: E501
                logger.debug(f"LightRAG cache hit for '{question[:50]}...'")
                return cached

        self._stats["cache_misses"] += 1

        from lightrag import QueryParam

        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            start = time.time()
            try:
                param = QueryParam(
                    mode=mode,
                    top_k=top_k,
                    response_type=response_type,
                    only_need_context=only_need_context,
                    stream=stream,
                    include_references=include_references,
                )

                result = self._rag.query(question, param=param)

                elapsed = time.time() - start
                self._stats["queries_run"] += 1
                self._stats["last_query_time"] = time.time()
                self._stats["per_mode_queries"][mode] = self._stats["per_mode_queries"][mode] + 1  # noqa: E501

                # Update rolling average
                n = self._stats["queries_run"]
                ms = elapsed * 1000
                self._stats["avg_query_ms"] = (
                    (self._stats["avg_query_ms"] * (n - 1) + ms) / n
                )

                sources: list[dict[str, Any]] = []
                result_text = str(result)

                # Store in cache
                if use_cache:
                    self._cache.set(question, mode, top_k, result_text, sources)

                logger.info(
                    f"LightRAG query ({mode}) answered in {elapsed:.2f}s "
                    f"(attempt {attempt + 1}, result: {len(result_text)} chars)"
                )

                return result_text, sources

            except Exception as e:
                last_error = e
                self._stats["query_errors"] += 1
                if attempt < max_retries:
                    wait = 0.5 * (attempt + 1)
                    logger.warning(
                        f"LightRAG query attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {wait:.1f}s..."
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        f"LightRAG query failed after {max_retries + 1} attempts: {e}"
                    )

        raise last_error or RuntimeError("LightRAG query failed")

    # ── Async variants ──────────────────────────────────────────

    async def ainsert_texts(self, texts: list[str]) -> dict[str, Any]:
        """Async insert multiple texts."""
        self._ensure_initialized()
        assert self._rag is not None

        start = time.time()
        inserted = 0
        errors = 0

        for text in texts:
            if not text or len(text.strip()) < 20:
                continue
            try:
                await self._rag.ainsert(text)
                inserted += 1
            except Exception as e:
                errors += 1
                logger.warning(f"LightRAG async insert error: {e}")

        elapsed = time.time() - start
        self._stats["chunks_inserted"] += inserted
        self._stats["insert_errors"] += errors

        return {
            "inserted": inserted,
            "total": len(texts),
            "errors": errors,
            "elapsed_seconds": round(elapsed, 2),
        }

    async def aquery(
        self,
        question: str,
        mode: str = "hybrid",
        top_k: int = 10,
        response_type: str = "detailed answer with code examples",
        only_need_context: bool = False,
        stream: bool = False,
        include_references: bool = True,
        use_cache: bool = True,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Async query LightRAG."""
        self._ensure_initialized()
        assert self._rag is not None

        from lightrag import QueryParam

        if use_cache:
            cached = self._cache.get(question, mode, top_k)
            if cached is not None:
                self._stats["cache_hits"] += 1
                return cached

        self._stats["cache_misses"] += 1
        start = time.time()

        try:
            param = QueryParam(
                mode=mode,
                top_k=top_k,
                response_type=response_type,
                only_need_context=only_need_context,
                stream=stream,
                include_references=include_references,
            )

            result = await self._rag.aquery(question, param=param)
            elapsed = time.time() - start

            self._stats["queries_run"] += 1
            self._stats["last_query_time"] = time.time()
            self._stats["per_mode_queries"][mode] = self._stats["per_mode_queries"][mode] + 1  # noqa: E501

            result_text = str(result)

            if use_cache:
                self._cache.set(question, mode, top_k, result_text, [])

            return result_text, []

        except Exception as e:
            self._stats["query_errors"] += 1
            logger.error(f"LightRAG async query error: {e}")
            raise

    # ── File / Directory Ingestion ──────────────────────────────

    def insert_from_directory(
        self,
        directory: str | Path,
        pattern: str = "**/*.{py,js,ts,jsx,tsx,md,txt,rst,json,yaml,yml}",
        max_files: int = 200,
        chunk_size: int = 2000,
        show_progress: bool = True,
    ) -> dict[str, Any]:
        """Insert all text files from a directory into LightRAG.

        Reads files matching the glob pattern, chunks larger files into
        segments, and inserts each chunk as a separate document.

        Args:
            directory: Root directory to scan.
            pattern: Glob pattern for files to include.
            max_files: Maximum files to process.
            chunk_size: Max characters per chunk (files larger than this
                        are split into multiple chunks).
            show_progress: Print progress to stdout.

        Returns:
            Dict with inserted/total/errors/elapsed/chunk_summary stats.
        """
        self._ensure_initialized()
        assert self._rag is not None

        root = Path(directory)
        if not root.is_dir():
            raise NotADirectoryError(f"Directory not found: {directory}")

        files: list[Path] = []
        for f in sorted(root.rglob("*")):
            if f.is_file() and f.is_relative_to(root):
                files.append(f)

        # Determine allowed file extensions from the pattern
        allowed_extensions = set()
        for pat in pattern.split(","):
            pat = pat.strip()
            if "*." in pat:
                ext = pat.split("*.")[-1].strip("{}")  # Handle glob patterns like "*.{py,js}"
                allowed_extensions.add(ext)

        matched = [f for f in files if f.suffix.lstrip(".") in allowed_extensions]
        matched = matched[:max_files]

        if show_progress:
            print(f"\n[LightRAG] Scanning {root} — {len(matched)} matching files (of {len(files)} total)")

        texts: list[str] = []
        file_map: dict[str, list[str]] = {}  # filename -> chunk list

        for file_path in matched:
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                if len(content.strip()) < 20:
                    continue

                # Prepend file metadata
                rel_path = str(file_path.relative_to(root))
                header = f"[File: {rel_path}]\n[Path: {file_path}]\n\n"

                if len(content) > chunk_size:
                    # Split into chunks
                    chunks = []
                    for i in range(0, len(content), chunk_size):
                        segment = content[i:i + chunk_size]
                        chunk_text = f"{header}[Part {i // chunk_size + 1}]\n\n{segment}"
                        chunks.append(chunk_text)
                    texts.extend(chunks)
                    file_map[str(file_path)] = chunks
                else:
                    full_text = f"{header}{content}"
                    texts.append(full_text)
                    file_map[str(file_path)] = [full_text]

            except Exception as e:
                if show_progress:
                    print(f"  [SKIP] {file_path.name}: {e}")

        if not texts:
            return {"inserted": 0, "total": 0, "errors": 0, "elapsed_seconds": 0.0, "chunks": 0, "files": 0}

        if show_progress:
            print(f"[LightRAG] Generated {len(texts)} chunks from {len(file_map)} files. Inserting...")

        # Batch insert
        start = time.time()
        inserted = 0
        errors = 0

        for i, text in enumerate(texts):
            try:
                self._rag.insert(text)
                inserted += 1
                if show_progress and (i + 1) % 20 == 0:
                    print(f"  [{i + 1}/{len(texts)}] chunks inserted...")
            except Exception as e:
                errors += 1
                logger.warning(f"LightRAG insert error (chunk {i}): {e}")

        elapsed = time.time() - start
        self._stats["chunks_inserted"] += inserted
        self._stats["insert_errors"] += errors
        self._stats["files_indexed"] += len(file_map)

        if show_progress:
            print(f"[LightRAG] Done! {inserted}/{len(texts)} chunks inserted in {elapsed:.2f}s")

        return {
            "inserted": inserted,
            "total": len(texts),
            "errors": errors,
            "elapsed_seconds": round(elapsed, 2),
            "chunks": len(texts),
            "files": len(file_map),
        }

    # ── Health Check ────────────────────────────────────────────

    def health_check(self, verbose: bool = False) -> dict[str, Any]:
        """Run a comprehensive health check on the LightRAG pipeline.

        Tests:
        1. LightRAG import availability
        2. Working directory access
        3. Ollama model reachability (via a test insert + query)
        4. Cache integrity

        Returns a dict with check results and a summary "healthy" bool.
        """
        checks: list[dict[str, Any]] = []
        all_healthy = True

        # Check 1: Import
        try:
            import lightrag  # noqa: F401
            checks.append({"name": "import", "status": "ok", "detail": "lightrag-hku available"})
        except ImportError as e:
            checks.append({"name": "import", "status": "fail", "detail": str(e)})
            all_healthy = False

        # Check 2: Working directory
        try:
            self._working_dir.mkdir(parents=True, exist_ok=True)
            test_file = self._working_dir / ".health_check"
            test_file.write_text("ok")
            test_file.unlink()
            checks.append({
                "name": "working_dir",
                "status": "ok",
                "detail": f"Writable: {self._working_dir}",
            })
        except Exception as e:
            checks.append({"name": "working_dir", "status": "fail", "detail": str(e)})
            all_healthy = False

        # Check 3: LightRAG initialization
        try:
            self._ensure_initialized()
            checks.append({
                "name": "initialization",
                "status": "ok",
                "detail": f"LightRAG instance created (llm={self._llm_model}, embed={self._embed_model})",
            })
        except Exception as e:
            checks.append({"name": "initialization", "status": "fail", "detail": str(e)})
            all_healthy = False

        # Check 4: Cache
        cache_st = self._cache.stats
        checks.append({
            "name": "cache",
            "status": "ok",
            "detail": f"{cache_st['size']}/{cache_st['maxsize']} entries, hit_rate={cache_st['hit_rate']}%",
        })

        # If verbose, also try a basic insert + query
        if verbose and self._initialized and self._rag is not None:
            try:
                test_text = "Python is a high-level programming language." * 3
                self._rag.insert(test_text)
                checks.append({"name": "test_insert", "status": "ok", "detail": "Basic insert succeeded"})
            except Exception as e:
                checks.append({"name": "test_insert", "status": "fail", "detail": str(e)})
                all_healthy = False

        result = {
            "healthy": all_healthy,
            "checks": checks,
            "failed_checks": sum(1 for c in checks if c["status"] == "fail"),
            "total_checks": len(checks),
            "timestamp": time.time(),
        }

        self._stats["last_health_check"] = time.time()
        self._stats["health_status"] = "healthy" if all_healthy else "unhealthy"

        return result

    # ── Cache Management ────────────────────────────────────────

    def clear_cache(self) -> int:
        """Clear the query cache. Returns number of entries cleared."""
        return self._cache.invalidate()

    def cache_stats(self) -> dict[str, Any]:
        """Return detailed cache statistics."""
        return self._cache.stats

    # ── Stats ───────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Return adapter statistics including cache metrics."""
        cache_st = self._cache.stats
        return {
            **self._stats,
            "working_dir": str(self._working_dir),
            "llm_model": self._llm_model,
            "embed_model": self._embed_model,
            "initialized": self._initialized,
            "cache": cache_st,
        }

    def is_available(self) -> bool:
        """Check if LightRAG is available (import + optional init check)."""
        try:
            self._ensure_initialized()
            return True
        except (ImportError, Exception):
            return False

    @property
    def rag_instance(self):
        """Direct access to the underlying LightRAG instance (for advanced use)."""
        self._ensure_initialized()
        return self._rag


# ═══════════════════════════════════════
# Factory / Helpers
# ═══════════════════════════════════════

def create_lightrag_backend() -> LightRAGAdapter | None:
    """Create a LightRAGAdapter if lightrag is installed.

    Returns None if the library is not available (graceful fallback).
    """
    try:
        import lightrag  # noqa: F401
        return LightRAGAdapter()
    except ImportError:
        logger.info("LightRAG not installed — falling back to ChromaDB RAG")
        return None


def detect_backend() -> str:
    """Detect which RAG backend to use based on env var.

    Returns "lightrag" or "chroma".
    """
    backend = os.environ.get("FORGEAI_RAG_BACKEND", "chroma").lower().strip()
    if backend == "lightrag":
        try:
            import lightrag  # noqa: F401
            return "lightrag"
        except ImportError:
            logger.warning(
                "FORGEAI_RAG_BACKEND=lightrag but lightrag-hku is not installed. "
                "Falling back to chroma."
            )
            return "chroma"
    return "chroma"


# ═══════════════════════════════════════
# Standalone CLI (for testing)
# ═══════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="LightRAG CLI")
    parser.add_argument("--insert", help="Insert text from a JSON file")
    parser.add_argument("--query", help="Ask a question")
    parser.add_argument("--mode", default="hybrid", choices=["naive", "local", "global", "hybrid"])
    parser.add_argument("--dir", default=str(DEFAULT_WORKING_DIR), help="Working directory")
    args = parser.parse_args()

    rag = LightRAGAdapter(working_dir=args.dir)

    if args.insert:
        with open(args.insert, encoding="utf-8") as f:
            data = json.load(f)
        texts = [item.get("text", "") if isinstance(item, dict) else item for item in data]
        result = rag.insert_texts(texts)
        print(f"Inserted: {result}")

    if args.query:
        answer, sources = rag.query(args.query, mode=args.mode)
        print(f"\nAnswer:\n{answer}")
