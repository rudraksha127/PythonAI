"""Unit tests for the LightRAG adapter — lightrag_wrapper.py.

All tests use mocked LightRAG internals since the actual library
requires Ollama + models to be running.

Covers:
- Backend detection
- Factory function
- Adapter init, insert, query, async, error handling
- LRU query cache (hit, miss, TTL eviction, invalidation)
- File/directory ingestion
- Health check / diagnostics
- Config file support
- Per-mode query stats
- Cache stats in get_stats()
- RAG engine integration
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ══════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture
def temp_working_dir() -> Path:
    """Create a temporary working directory for LightRAG tests."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


# ══════════════════════════════════════════════════════════════════════
# _QueryCache
# ══════════════════════════════════════════════════════════════════════


class TestQueryCache:
    """Tests for the internal LRU query cache."""

    def test_cache_hit(self) -> None:
        """A cached query should return the cached result."""
        from src.rag.lightrag_wrapper import _QueryCache

        cache = _QueryCache(maxsize=100, ttl=300)
        cache.set("What is Python?", "hybrid", 10, "Python is a language.", [])

        result = cache.get("What is Python?", "hybrid", 10)
        assert result is not None
        answer, sources = result
        assert answer == "Python is a language."
        assert cache.stats["hits"] == 1
        assert cache.stats["misses"] == 0

    def test_cache_miss(self) -> None:
        """An uncached query should return None."""
        from src.rag.lightrag_wrapper import _QueryCache

        cache = _QueryCache(maxsize=100, ttl=300)
        result = cache.get("Unknown question?", "hybrid", 10)
        assert result is None
        assert cache.stats["hits"] == 0
        assert cache.stats["misses"] == 1

    def test_cache_ttl_eviction(self) -> None:
        """Expired cache entries should not be returned."""
        from src.rag.lightrag_wrapper import _QueryCache

        cache = _QueryCache(maxsize=100, ttl=0)  # Zero TTL = instant expiry
        cache.set("Test?", "hybrid", 10, "Answer", [])

        # Should be expired already
        result = cache.get("Test?", "hybrid", 10)
        assert result is None

    def test_cache_invalidation(self) -> None:
        """Invalidating the cache should clear all entries."""
        from src.rag.lightrag_wrapper import _QueryCache

        cache = _QueryCache(maxsize=100, ttl=300)
        cache.set("Q1?", "hybrid", 10, "A1", [])
        cache.set("Q2?", "hybrid", 10, "A2", [])
        assert len(cache) == 2

        cleared = cache.invalidate()
        assert cleared == 2
        assert len(cache) == 0

    def test_cache_maxsize_eviction(self) -> None:
        """When cache exceeds maxsize, oldest entry should be evicted."""
        from src.rag.lightrag_wrapper import _QueryCache

        cache = _QueryCache(maxsize=2, ttl=300)
        cache.set("Q1?", "hybrid", 10, "A1", [])
        cache.set("Q2?", "hybrid", 10, "A2", [])
        cache.set("Q3?", "hybrid", 10, "A3", [])  # Evicts Q1

        assert cache.get("Q1?", "hybrid", 10) is None  # Evicted
        assert cache.get("Q2?", "hybrid", 10) is not None  # Still there
        assert cache.get("Q3?", "hybrid", 10) is not None  # Still there

    def test_cache_different_keys(self) -> None:
        """Different modes or top_k should produce different cache keys."""
        from src.rag.lightrag_wrapper import _QueryCache

        cache = _QueryCache(maxsize=100, ttl=300)
        cache.set("Same?", "hybrid", 10, "Hybrid answer", [])
        cache.set("Same?", "local", 10, "Local answer", [])

        r1 = cache.get("Same?", "hybrid", 10)
        r2 = cache.get("Same?", "local", 10)
        assert r1 is not None
        assert r2 is not None
        assert r1[0] == "Hybrid answer"
        assert r2[0] == "Local answer"

    def test_cache_stats(self) -> None:
        """Cache stats should reflect hit/miss ratio."""
        from src.rag.lightrag_wrapper import _QueryCache

        cache = _QueryCache(maxsize=100, ttl=300)
        cache.set("Q?", "hybrid", 10, "A", [])
        cache.get("Q?", "hybrid", 10)  # Hit
        cache.get("Missing?", "hybrid", 10)  # Miss

        stats = cache.stats
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 50.0


# ══════════════════════════════════════════════════════════════════════
# _load_config_file
# ══════════════════════════════════════════════════════════════════════


class TestLoadConfigFile:
    """Tests for config file loading."""

    def test_load_json_config(self, temp_working_dir: Path) -> None:
        """JSON config file should be loaded correctly."""
        config_path = temp_working_dir / "config.json"
        config_data = {"llm_model": "custom-model", "top_k": 20}
        with open(config_path, "w") as f:
            json.dump(config_data, f)

        from src.rag.lightrag_wrapper import _load_config_file

        cfg = _load_config_file(temp_working_dir)
        assert cfg.get("llm_model") == "custom-model"
        assert cfg.get("top_k") == 20

    def test_no_config_file(self, temp_working_dir: Path) -> None:
        """No config file should return empty dict."""
        from src.rag.lightrag_wrapper import _load_config_file

        cfg = _load_config_file(temp_working_dir)
        assert cfg == {}


# ══════════════════════════════════════════════════════════════════════
# detect_backend
# ══════════════════════════════════════════════════════════════════════


class TestDetectBackend:
    """Tests for the detect_backend() function."""

    def test_default_is_chroma(self) -> None:
        """When FORGEAI_RAG_BACKEND is not set, default should be 'chroma'."""
        from src.rag.lightrag_wrapper import detect_backend

        saved = os.environ.pop("FORGEAI_RAG_BACKEND", None)
        try:
            assert detect_backend() == "chroma"
        finally:
            if saved is not None:
                os.environ["FORGEAI_RAG_BACKEND"] = saved

    def test_explicit_chroma(self) -> None:
        """Setting FORGEAI_RAG_BACKEND=chroma should return 'chroma'."""
        from src.rag.lightrag_wrapper import detect_backend

        os.environ["FORGEAI_RAG_BACKEND"] = "chroma"
        try:
            assert detect_backend() == "chroma"
        finally:
            del os.environ["FORGEAI_RAG_BACKEND"]

    def test_lightrag_when_installed(self) -> None:
        """Setting FORGEAI_RAG_BACKEND=lightrag with lightrag installed should return 'lightrag'."""
        from src.rag.lightrag_wrapper import detect_backend

        os.environ["FORGEAI_RAG_BACKEND"] = "lightrag"
        try:
            result = detect_backend()
            assert result == "lightrag"
        finally:
            del os.environ["FORGEAI_RAG_BACKEND"]

    def test_case_insensitive(self) -> None:
        """Backend detection should be case-insensitive."""
        from src.rag.lightrag_wrapper import detect_backend

        os.environ["FORGEAI_RAG_BACKEND"] = "LIGHTRAG"
        try:
            assert detect_backend() == "lightrag"
        finally:
            del os.environ["FORGEAI_RAG_BACKEND"]

    def test_lightrag_unavailable_fallback(self) -> None:
        """When lightrag is not installed, FORGEAI_RAG_BACKEND=lightrag should fall back to chroma."""
        from src.rag.lightrag_wrapper import detect_backend

        os.environ["FORGEAI_RAG_BACKEND"] = "lightrag"
        try:
            with patch.dict("sys.modules", {"lightrag": None}):
                result = detect_backend()
                assert result == "chroma"
        finally:
            del os.environ["FORGEAI_RAG_BACKEND"]


# ══════════════════════════════════════════════════════════════════════
# create_lightrag_backend
# ══════════════════════════════════════════════════════════════════════


class TestCreateLightRAGBackend:
    """Tests for the create_lightrag_backend() factory function."""

    def test_returns_adapter_when_lightrag_installed(self) -> None:
        """create_lightrag_backend should return a LightRAGAdapter when lightrag is installed."""
        from src.rag.lightrag_wrapper import LightRAGAdapter, create_lightrag_backend

        result = create_lightrag_backend()
        assert result is not None
        assert isinstance(result, LightRAGAdapter)

    def test_returns_none_when_lightrag_unavailable(self) -> None:
        """create_lightrag_backend should return None when lightrag is not installed."""
        from src.rag.lightrag_wrapper import create_lightrag_backend

        with patch.dict("sys.modules", {"lightrag": None}):
            result = create_lightrag_backend()
            assert result is None

    def test_adapter_not_initialized(self) -> None:
        """The adapter should not auto-initialize LightRAG (lazy init)."""
        from src.rag.lightrag_wrapper import LightRAGAdapter

        adapter = LightRAGAdapter(working_dir="/tmp/__test_lr__")
        assert adapter._initialized is False
        assert adapter._rag is None


# ══════════════════════════════════════════════════════════════════════
# LightRAGAdapter — initialization
# ══════════════════════════════════════════════════════════════════════


class TestLightRAGAdapterInit:
    """Tests for LightRAGAdapter initialization."""

    def test_uses_default_working_dir(self) -> None:
        """When no working_dir is given, it should use the default."""
        from src.rag.lightrag_wrapper import LightRAGAdapter

        adapter = LightRAGAdapter()
        default_dir = adapter._working_dir
        assert "python_brain_lightrag" in str(default_dir)

    def test_creates_working_dir_if_not_exists(self, temp_working_dir: Path) -> None:
        """The working directory should be created on init if it doesn't exist."""
        test_dir = temp_working_dir / "lightrag_test"
        assert not test_dir.exists()

        from src.rag.lightrag_wrapper import LightRAGAdapter

        adapter = LightRAGAdapter(working_dir=test_dir)
        assert test_dir.exists()
        assert adapter._working_dir == test_dir

    def test_custom_llm_model(self) -> None:
        """Custom LLM model name should be stored."""
        from src.rag.lightrag_wrapper import LightRAGAdapter

        adapter = LightRAGAdapter(llm_model="deepseek-coder:6.7b")
        assert adapter._llm_model == "deepseek-coder:6.7b"

    def test_custom_embed_model(self) -> None:
        """Custom embedding model name should be stored."""
        from src.rag.lightrag_wrapper import LightRAGAdapter

        adapter = LightRAGAdapter(embed_model="all-MiniLM-L6-v2")
        assert adapter._embed_model == "all-MiniLM-L6-v2"

    def test_custom_chunk_params(self) -> None:
        """Custom chunk parameters should be passed through."""
        from src.rag.lightrag_wrapper import LightRAGAdapter

        adapter = LightRAGAdapter(chunk_token_size=512, chunk_overlap=64)
        assert adapter._chunk_token_size == 512
        assert adapter._chunk_overlap == 64

    def test_config_file_applied(self, temp_working_dir: Path) -> None:
        """Config file values should be applied during init."""
        config_data = {"llm_model": "config-model", "top_k": 99}
        config_path = temp_working_dir / "config.json"
        with open(config_path, "w") as f:
            json.dump(config_data, f)

        from src.rag.lightrag_wrapper import LightRAGAdapter

        adapter = LightRAGAdapter(working_dir=temp_working_dir)
        assert adapter._llm_model == "config-model"
        assert adapter._top_k == 99


# ══════════════════════════════════════════════════════════════════════
# LightRAGAdapter — is_available
# ══════════════════════════════════════════════════════════════════════


class TestLightRAGAdapterAvailable:
    """Tests for is_available() method."""

    def test_not_available_without_lightrag(self) -> None:
        """is_available() should return False when lightrag is not installed."""
        from src.rag.lightrag_wrapper import LightRAGAdapter

        adapter = LightRAGAdapter(working_dir="/tmp/__test_lr_avail__")

        with patch.dict("sys.modules", {"lightrag": None}):
            assert adapter.is_available() is False

    def test_returns_false_on_init_error(self, temp_working_dir: Path) -> None:
        """is_available() should return False if LightRAG constructor fails."""
        from src.rag.lightrag_wrapper import LightRAGAdapter

        adapter = LightRAGAdapter(working_dir=temp_working_dir)

        with patch("lightrag.LightRAG.__init__", side_effect=ValueError("Bad config")):
            assert adapter.is_available() is False

    def test_stats_reflect_availability(self) -> None:
        """get_stats() should show initialized=False before first use."""
        from src.rag.lightrag_wrapper import LightRAGAdapter

        adapter = LightRAGAdapter(working_dir="/tmp/__test_lr_stats__")
        stats = adapter.get_stats()
        assert stats["initialized"] is False
        assert stats["chunks_inserted"] == 0
        assert stats["queries_run"] == 0


# ══════════════════════════════════════════════════════════════════════
# LightRAGAdapter — insert_texts (mocked)
# ══════════════════════════════════════════════════════════════════════


class TestLightRAGAdapterInsert:
    """Tests for insert_texts() with mocked LightRAG internals."""

    @pytest.fixture
    def adapter(self, temp_working_dir: Path):
        from src.rag.lightrag_wrapper import LightRAGAdapter

        adapter = LightRAGAdapter(working_dir=temp_working_dir)
        mock_rag = MagicMock()
        adapter._rag = mock_rag
        adapter._initialized = True
        return adapter

    def test_insert_single_text(self, adapter: Any) -> None:
        result = adapter.insert_text("Python decorators are powerful for metaprogramming.")
        assert result["inserted"] == 1
        assert result["total"] == 1
        assert result["errors"] == 0
        adapter._rag.insert.assert_called_once()

    def test_insert_multiple_texts(self, adapter: Any) -> None:
        texts = ["Python lists are mutable ordered sequences.",
                 "Python dicts store key-value pairs efficiently.",
                 "Python sets are unordered collections of unique items."]
        result = adapter.insert_texts(texts)
        assert result["inserted"] == 3
        assert adapter._rag.insert.call_count == 3

    def test_skip_short_texts(self, adapter: Any) -> None:
        texts = ["short", "also short", "This is a long enough text document for testing."]
        result = adapter.insert_texts(texts)
        assert result["inserted"] == 1

    def test_empty_list(self, adapter: Any) -> None:
        result = adapter.insert_texts([])
        assert result["inserted"] == 0

    def test_partial_insert_errors(self, adapter: Any) -> None:
        adapter._rag.insert.side_effect = [None, RuntimeError("Insert failed"), None]
        texts = ["First document that is long enough for insertion.",
                 "Second document that is also long enough to insert.",
                 "Third document here that should work fine."]
        result = adapter.insert_texts(texts)
        assert result["inserted"] == 2
        assert result["errors"] == 1

    def test_tracks_stats(self, adapter: Any) -> None:
        adapter.insert_text("Python lists are ordered collections of items.")
        adapter.insert_text("Python dicts store key-value pairs efficiently.")
        stats = adapter.get_stats()
        assert stats["chunks_inserted"] == 2


# ══════════════════════════════════════════════════════════════════════
# LightRAGAdapter — query (mocked)
# ══════════════════════════════════════════════════════════════════════


class TestLightRAGAdapterQuery:
    """Tests for query() with mocked LightRAG internals."""

    @pytest.fixture
    def adapter(self, temp_working_dir: Path):
        from src.rag.lightrag_wrapper import LightRAGAdapter

        adapter = LightRAGAdapter(working_dir=temp_working_dir)
        mock_rag = MagicMock()
        mock_rag.query.return_value = (
            "Python decorators are functions that modify other functions."
        )
        adapter._rag = mock_rag
        adapter._initialized = True
        return adapter

    def test_query_returns_answer_and_sources(self, adapter: Any) -> None:
        answer, sources = adapter.query("What are Python decorators?")
        assert isinstance(answer, str)
        assert isinstance(sources, list)
        assert len(answer) > 0
        adapter._rag.query.assert_called_once()

    def test_query_hybrid_mode_default(self, adapter: Any) -> None:
        from lightrag import QueryParam

        adapter.query("How do lists work?")
        call_args = adapter._rag.query.call_args
        _, kwargs = call_args
        param: QueryParam = kwargs.get("param")
        assert param.mode == "hybrid"

    def test_query_naive_mode(self, adapter: Any) -> None:
        adapter.query("Simple question?", mode="naive")
        call_args = adapter._rag.query.call_args
        _, kwargs = call_args
        param = kwargs.get("param")
        assert param.mode == "naive"

    def test_query_local_mode(self, adapter: Any) -> None:
        adapter.query("Local context question?", mode="local")
        call_args = adapter._rag.query.call_args
        _, kwargs = call_args
        param = kwargs.get("param")
        assert param.mode == "local"

    def test_query_global_mode(self, adapter: Any) -> None:
        adapter.query("Global overview question?", mode="global")
        call_args = adapter._rag.query.call_args
        _, kwargs = call_args
        param = kwargs.get("param")
        assert param.mode == "global"

    def test_query_custom_top_k(self, adapter: Any) -> None:
        adapter.query("Question?", top_k=15)
        call_args = adapter._rag.query.call_args
        _, kwargs = call_args
        param = kwargs.get("param")
        assert param.top_k == 15

    def test_query_tracks_stats(self, adapter: Any) -> None:
        adapter.query("First question?")
        adapter.query("Second question?")
        stats = adapter.get_stats()
        assert stats["queries_run"] == 2
        assert stats["last_query_time"] is not None
        assert stats["avg_query_ms"] > 0

    def test_query_per_mode_stats(self, adapter: Any) -> None:
        """Per-mode query counts should be tracked correctly."""
        adapter.query("Q1", mode="hybrid")
        adapter.query("Q2", mode="local")
        adapter.query("Q3", mode="hybrid")
        stats = adapter.get_stats()
        assert stats["per_mode_queries"]["hybrid"] == 2
        assert stats["per_mode_queries"]["local"] == 1

    def test_query_cache_hit(self, adapter: Any) -> None:
        """Querying the same question twice should hit the cache on the second call."""
        adapter.query("Same question?", use_cache=True)
        adapter.query("Same question?", use_cache=True)
        # Only 1 actual query call to LightRAG (second is cache hit)
        assert adapter._rag.query.call_count == 1
        # Cache should have 1 hit + 1 miss (cache populated on first call... wait, no)
        # First call: miss (cache miss on _cache.get, but the return value gets cached)
        # Second call: hit (cache hit on _cache.get)
        # But the adapter._cache.stats should show 1 hit, 1 miss
        stats = adapter.get_stats()
        assert stats["cache"]["hits"] >= 1
        assert stats["cache"]["misses"] >= 1

    def test_query_bypass_cache(self, adapter: Any) -> None:
        """Setting use_cache=False should always query LightRAG directly."""
        adapter.query("Q?", use_cache=False)
        adapter.query("Q?", use_cache=False)
        assert adapter._rag.query.call_count == 2


# ══════════════════════════════════════════════════════════════════════
# LightRAGAdapter — error handling
# ══════════════════════════════════════════════════════════════════════


class TestLightRAGAdapterErrors:
    """Tests for LightRAGAdapter error handling."""

    def test_query_raises_on_not_initialized(self, temp_working_dir: Path) -> None:
        from src.rag.lightrag_wrapper import LightRAGAdapter

        adapter = LightRAGAdapter(working_dir=temp_working_dir)
        with patch.object(adapter, '_ensure_initialized', side_effect=RuntimeError("LightRAG unavailable")):
            with pytest.raises((ImportError, RuntimeError, ValueError)):
                adapter.query("This should fail")

    def test_insert_raises_on_not_initialized(self, temp_working_dir: Path) -> None:
        from src.rag.lightrag_wrapper import LightRAGAdapter

        adapter = LightRAGAdapter(working_dir=temp_working_dir)
        with patch.object(adapter, '_ensure_initialized', side_effect=RuntimeError("LightRAG unavailable")):
            with pytest.raises((ImportError, RuntimeError, ValueError)):
                adapter.insert_text("This should fail")

    def test_query_retry_on_failure(self, temp_working_dir: Path) -> None:
        """query() should retry on transient failures."""
        from src.rag.lightrag_wrapper import LightRAGAdapter

        adapter = LightRAGAdapter(working_dir=temp_working_dir)
        mock_rag = MagicMock()
        mock_rag.query.side_effect = [
            RuntimeError("Temp error"),
            "Final answer after retry."
        ]
        adapter._rag = mock_rag
        adapter._initialized = True

        answer, _ = adapter.query("Will retry?", max_retries=2)
        assert "Final answer" in answer
        assert adapter._rag.query.call_count == 2

    def test_query_all_retries_exhausted(self, temp_working_dir: Path) -> None:
        """query() should raise after all retries exhausted."""
        from src.rag.lightrag_wrapper import LightRAGAdapter

        adapter = LightRAGAdapter(working_dir=temp_working_dir)
        mock_rag = MagicMock()
        mock_rag.query.side_effect = RuntimeError("Persistent error")
        adapter._rag = mock_rag
        adapter._initialized = True

        with pytest.raises(RuntimeError):
            adapter.query("Will fail?", max_retries=1)
        assert adapter._rag.query.call_count == 2  # initial + 1 retry


# ══════════════════════════════════════════════════════════════════════
# LightRAGAdapter — async (mocked)
# ══════════════════════════════════════════════════════════════════════


class TestLightRAGAdapterAsync:
    """Tests for async methods with mocked LightRAG internals."""

    @pytest.fixture
    def adapter(self, temp_working_dir: Path):
        from src.rag.lightrag_wrapper import LightRAGAdapter

        adapter = LightRAGAdapter(working_dir=temp_working_dir)
        mock_rag = MagicMock()
        mock_rag.ainsert = AsyncMock()
        mock_rag.aquery = AsyncMock(return_value="Async answer text.")
        adapter._rag = mock_rag
        adapter._initialized = True
        return adapter

    @pytest.mark.asyncio
    async def test_ainsert_texts(self, adapter: Any) -> None:
        result = await adapter.ainsert_texts([
            "Python lists are mutable ordered sequences.",
            "Python dicts store key-value pairs efficiently."
        ])
        assert result["inserted"] == 2
        assert result["errors"] == 0
        assert adapter._rag.ainsert.call_count == 2

    @pytest.mark.asyncio
    async def test_aquery_returns_answer(self, adapter: Any) -> None:
        answer, sources = await adapter.aquery("Async question?")
        assert isinstance(answer, str)
        assert len(answer) > 0
        assert isinstance(sources, list)
        assert adapter._rag.aquery.called

    @pytest.mark.asyncio
    async def test_aquery_cache_hit(self, adapter: Any) -> None:
        """Async query cache should work."""
        await adapter.aquery("Same?", use_cache=True)
        await adapter.aquery("Same?", use_cache=True)
        assert adapter._rag.aquery.call_count == 1


# ══════════════════════════════════════════════════════════════════════
# pytest-asyncio is v1.3.0 (old) — class-level decorators don't propagate.
# Use per-method decorators instead.
# ══════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════
# LightRAGAdapter — file/directory ingestion
# ══════════════════════════════════════════════════════════════════════


class TestLightRAGAdapterIngestion:
    """Tests for insert_from_directory() method."""

    @pytest.fixture
    def adapter(self, temp_working_dir: Path):
        from src.rag.lightrag_wrapper import LightRAGAdapter

        adapter = LightRAGAdapter(working_dir=temp_working_dir)
        mock_rag = MagicMock()
        adapter._rag = mock_rag
        adapter._initialized = True
        return adapter

    def test_raise_on_missing_directory(self, adapter: Any) -> None:
        """Non-existent directory should raise NotADirectoryError."""
        with pytest.raises(NotADirectoryError):
            adapter.insert_from_directory("/nonexistent/path")

    def test_no_matching_files(self, adapter: Any, temp_working_dir: Path) -> None:
        """Empty directory should return zero inserted."""
        result = adapter.insert_from_directory(temp_working_dir, show_progress=False)
        assert result["inserted"] == 0
        assert result["files"] == 0

    def test_inserts_text_files(self, adapter: Any, temp_working_dir: Path) -> None:
        """Python files in directory should be read and inserted."""
        src_dir = temp_working_dir / "src"
        src_dir.mkdir()
        (src_dir / "test.py").write_text("print('hello world')" * 10, encoding="utf-8")

        result = adapter.insert_from_directory(temp_working_dir, show_progress=False)
        assert result["inserted"] >= 1
        assert result["files"] >= 1
        adapter._rag.insert.assert_called()

    def test_chunks_large_files(self, adapter: Any, temp_working_dir: Path) -> None:
        """Files larger than chunk_size should be split."""
        src_dir = temp_working_dir / "src"
        src_dir.mkdir()
        # Create a file larger than default chunk_size (2000)
        large_content = "x" * 5000
        (src_dir / "large.py").write_text(large_content, encoding="utf-8")

        result = adapter.insert_from_directory(
            temp_working_dir, chunk_size=2000, show_progress=False
        )
        # Should produce at least 2-3 chunks
        assert result["chunks"] >= 2

    def test_tracks_files_indexed_stat(self, adapter: Any, temp_working_dir: Path) -> None:
        """After ingestion, files_indexed stat should be updated."""
        src_dir = temp_working_dir / "src"
        src_dir.mkdir()
        (src_dir / "a.py").write_text("print('hello')" * 20, encoding="utf-8")
        (src_dir / "b.py").write_text("print('world')" * 20, encoding="utf-8")

        adapter.insert_from_directory(temp_working_dir, show_progress=False)
        stats = adapter.get_stats()
        assert stats["files_indexed"] >= 2


# ══════════════════════════════════════════════════════════════════════
# LightRAGAdapter — health check
# ══════════════════════════════════════════════════════════════════════


class TestLightRAGAdapterHealthCheck:
    """Tests for health_check() method."""

    def test_health_check_returns_dict(self, temp_working_dir: Path) -> None:
        """health_check() should return a dict with healthy status and checks."""
        from src.rag.lightrag_wrapper import LightRAGAdapter

        adapter = LightRAGAdapter(working_dir=temp_working_dir)
        result = adapter.health_check()

        assert isinstance(result, dict)
        assert "healthy" in result
        assert "checks" in result
        assert "total_checks" in result
        assert isinstance(result["checks"], list)

    def test_health_check_tracks_timestamp(self, temp_working_dir: Path) -> None:
        """After health_check, last_health_check should be set."""
        from src.rag.lightrag_wrapper import LightRAGAdapter

        adapter = LightRAGAdapter(working_dir=temp_working_dir)
        adapter.health_check()
        stats = adapter.get_stats()
        assert stats["last_health_check"] is not None
        assert stats["health_status"] in ("healthy", "unhealthy")


# ══════════════════════════════════════════════════════════════════════
# LightRAGAdapter — cache management
# ══════════════════════════════════════════════════════════════════════


class TestLightRAGAdapterCacheManagement:
    """Tests for clear_cache() and cache_stats() methods."""

    def test_clear_cache_returns_count(self, temp_working_dir: Path) -> None:
        """clear_cache() should return the number of cleared entries."""
        from src.rag.lightrag_wrapper import LightRAGAdapter

        adapter = LightRAGAdapter(working_dir=temp_working_dir)
        adapter._cache.set("Q1?", "hybrid", 10, "A1", [])
        adapter._cache.set("Q2?", "hybrid", 10, "A2", [])

        cleared = adapter.clear_cache()
        assert cleared == 2

    def test_cache_stats_returns_dict(self, temp_working_dir: Path) -> None:
        """cache_stats() should return a dict with size/maxsize/hit_rate."""
        from src.rag.lightrag_wrapper import LightRAGAdapter

        adapter = LightRAGAdapter(working_dir=temp_working_dir)
        stats = adapter.cache_stats()
        assert "size" in stats
        assert "maxsize" in stats
        assert "hit_rate" in stats
        assert "hits" in stats


# ══════════════════════════════════════════════════════════════════════
# RAG Engine integration tests
# ══════════════════════════════════════════════════════════════════════


class TestRagEngineIntegration:
    """Tests for the RAG engine integration with the backend detection."""

    def test_rag_backend_module_variable(self) -> None:
        from src.rag.rag_engine import RAG_BACKEND

        assert RAG_BACKEND in ("chroma", "lightrag")

    def test_get_lightrag_returns_none_for_chroma_backend(self) -> None:
        from src.rag.rag_engine import RAG_BACKEND, get_lightrag

        if RAG_BACKEND == "chroma":
            result = get_lightrag()
            assert result is None
        else:
            result = get_lightrag()
            assert result is not None
            from src.rag.lightrag_wrapper import LightRAGAdapter
            assert isinstance(result, LightRAGAdapter)

    def test_load_or_build_db_returns_stubs_for_lightrag(self) -> None:
        from src.rag.rag_engine import load_or_build_db

        result = load_or_build_db(backend="lightrag")
        coll, embedder, bm25, corpus, kg, cfile = result
        assert coll is None
        assert embedder is None
        assert bm25 is None
        assert corpus == []
        assert kg is None
        assert cfile == Path("")
