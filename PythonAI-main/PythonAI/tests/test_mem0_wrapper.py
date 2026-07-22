"""Unit tests for the ForgeAI Memory adapter — mem0_wrapper.py.

All tests use mocked mem0 internals since the actual library requires
Ollama + models + vector store to be running.

Covers:
- Basic CRUD (add, search, get_all, delete, delete_all)
- Graceful fallback when mem0 not installed
- Stats tracking
- format_for_context
- Factory function
- Thread safety
- Error handling
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ══════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture
def temp_storage_dir() -> Path:
    """Create a temporary storage directory."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


def _make_mock_memory() -> MagicMock:
    """Create a mocked mem0 Memory instance with standard return values."""
    mock = MagicMock()
    mock.add.return_value = {"id": "mem_123", "results": [{"id": "mem_123"}]}
    mock.search.return_value = {
        "results": [
            {"id": "mem_1", "memory": "User prefers Python 3.12", "score": 0.95},
            {"id": "mem_2", "memory": "User likes async/await", "score": 0.85},
        ]
    }
    mock.get_all.return_value = {
        "results": [
            {"id": "mem_1", "memory": "User prefers Python 3.12"},
            {"id": "mem_2", "memory": "User likes async/await"},
        ]
    }
    mock.delete.return_value = None
    return mock


# ══════════════════════════════════════════════════════════════════════
# ForgeAIMemory — initialization
# ══════════════════════════════════════════════════════════════════════


class TestForgeAIMemoryInit:
    """Tests for ForgeAIMemory initialization."""

    def test_creates_storage_dir(self, temp_storage_dir: Path) -> None:
        """Storage directory should be created on init."""
        from src.memory.mem0_wrapper import ForgeAIMemory

        mem = ForgeAIMemory(storage_dir=temp_storage_dir)
        assert temp_storage_dir.exists()
        assert mem._storage_dir == temp_storage_dir

    def test_not_initialized_on_creation(self) -> None:
        """mem0 should NOT be initialized at construction time (lazy)."""
        from src.memory.mem0_wrapper import ForgeAIMemory

        mem = ForgeAIMemory()
        assert mem._initialized is False
        assert mem._memory is None

    def test_disabled_when_enabled_false(self) -> None:
        """Setting enabled=False should prevent any initialization."""
        from src.memory.mem0_wrapper import ForgeAIMemory

        mem = ForgeAIMemory(enabled=False)
        assert mem.available() is False
        assert mem._init_error == "Memory disabled via FORGEAI_MEMORY_ENABLED=false"

    def test_graceful_when_mem0_not_installed(self, temp_storage_dir: Path) -> None:
        """ForgeAIMemory should not crash when mem0 is not installed."""
        from src.memory.mem0_wrapper import ForgeAIMemory

        mem = ForgeAIMemory(storage_dir=temp_storage_dir)

        with patch.dict("sys.modules", {"mem0": None}):
            assert mem.available() is False
            assert mem._init_error is not None

    def test_init_error_tracked_in_stats(self, temp_storage_dir: Path) -> None:
        """Init error should appear in get_stats()."""
        from src.memory.mem0_wrapper import ForgeAIMemory

        mem = ForgeAIMemory(storage_dir=temp_storage_dir)

        with patch.dict("sys.modules", {"mem0": None}):
            mem.available()
            stats = mem.get_stats()
            assert stats["available"] is False
            assert stats["init_error"] is not None
            assert "pip install mem0ai" in stats["init_error"]


# ══════════════════════════════════════════════════════════════════════
# ForgeAIMemory — add
# ══════════════════════════════════════════════════════════════════════


class TestForgeAIMemoryAdd:
    """Tests for add() method."""

    @pytest.fixture
    def mem(self, temp_storage_dir: Path) -> Any:
        from src.memory.mem0_wrapper import ForgeAIMemory

        m = ForgeAIMemory(storage_dir=temp_storage_dir)
        m._memory = _make_mock_memory()
        m._initialized = True
        return m

    def test_add_returns_result(self, mem: Any) -> None:
        """add() should return the mem0 result dict."""
        result = mem.add("User prefers Python 3.12", user_id="dev1")
        assert "id" in result
        assert result["id"] == "mem_123"

    def test_add_tracks_stats(self, mem: Any) -> None:
        """After add(), stats should be updated."""
        mem.add("Test memory", user_id="dev1")
        stats = mem.get_stats()
        assert stats["total_adds"] == 1
        assert stats["last_activity"] is not None

    def test_add_returns_error_on_failure(self, mem: Any) -> None:
        """add() should return error dict when mem0 fails."""
        mem._memory.add.side_effect = RuntimeError("DB locked")
        result = mem.add("Test", user_id="dev1")
        assert "error" in result

    def test_add_fallback_when_not_available(self, temp_storage_dir: Path) -> None:
        """add() should return error when mem0 not available."""
        from src.memory.mem0_wrapper import ForgeAIMemory

        mem = ForgeAIMemory(storage_dir=temp_storage_dir)

        with patch.dict("sys.modules", {"mem0": None}):
            result = mem.add("Test", user_id="dev1")
            assert "error" in result


# ══════════════════════════════════════════════════════════════════════
# ForgeAIMemory — search
# ══════════════════════════════════════════════════════════════════════


class TestForgeAIMemorySearch:
    """Tests for search() method."""

    @pytest.fixture
    def mem(self, temp_storage_dir: Path) -> Any:
        from src.memory.mem0_wrapper import ForgeAIMemory

        m = ForgeAIMemory(storage_dir=temp_storage_dir)
        m._memory = _make_mock_memory()
        m._initialized = True
        return m

    def test_search_returns_list(self, mem: Any) -> None:
        """search() should return a list of memory dicts."""
        results = mem.search("Python version", user_id="dev1")
        assert isinstance(results, list)
        assert len(results) == 2

    def test_search_returns_relevant_fields(self, mem: Any) -> None:
        """Each result should have 'id', 'memory', 'score'."""
        results = mem.search("Python", user_id="dev1")
        for r in results:
            assert "id" in r
            assert "memory" in r

    def test_search_tracks_stats(self, mem: Any) -> None:
        """After search(), stats should be updated."""
        mem.search("query", user_id="dev1")
        stats = mem.get_stats()
        assert stats["total_searches"] == 1

    def test_search_limit(self, mem: Any) -> None:
        """search() should respect limit parameter."""
        results = mem.search("test", user_id="dev1", limit=1)
        assert len(results) <= 1

    def test_search_empty_when_not_available(self, temp_storage_dir: Path) -> None:
        """search() should return empty list when mem0 not available."""
        from src.memory.mem0_wrapper import ForgeAIMemory

        mem = ForgeAIMemory(storage_dir=temp_storage_dir)

        with patch.dict("sys.modules", {"mem0": None}):
            results = mem.search("test", user_id="dev1")
            assert results == []


# ══════════════════════════════════════════════════════════════════════
# ForgeAIMemory — get_all / delete
# ══════════════════════════════════════════════════════════════════════


class TestForgeAIMemoryGetAll:
    """Tests for get_all() and delete() methods."""

    @pytest.fixture
    def mem(self, temp_storage_dir: Path) -> Any:
        from src.memory.mem0_wrapper import ForgeAIMemory

        m = ForgeAIMemory(storage_dir=temp_storage_dir)
        m._memory = _make_mock_memory()
        m._initialized = True
        return m

    def test_get_all_returns_list(self, mem: Any) -> None:
        """get_all() should return a list of memory dicts."""
        results = mem.get_all(user_id="dev1")
        assert isinstance(results, list)
        assert len(results) == 2

    def test_get_all_tracks_stats(self, mem: Any) -> None:
        """After get_all(), stats should be updated."""
        mem.get_all(user_id="dev1")
        stats = mem.get_stats()
        assert stats["total_get_all"] == 1

    def test_delete_returns_true(self, mem: Any) -> None:
        """delete() should return True on success."""
        assert mem.delete("mem_123") is True

    def test_delete_false_on_failure(self, mem: Any) -> None:
        """delete() should return False on failure."""
        mem._memory.delete.side_effect = RuntimeError("Not found")
        assert mem.delete("mem_999") is False

    def test_delete_all_returns_count(self, mem: Any) -> None:
        """delete_all() should return the number of deleted memories."""
        count = mem.delete_all(user_id="dev1")
        assert count == 2  # Mock has 2 memories

    def test_delete_all_zero_when_empty(self, temp_storage_dir: Path) -> None:
        """delete_all() should return 0 when mem0 not available."""
        from src.memory.mem0_wrapper import ForgeAIMemory

        mem = ForgeAIMemory(storage_dir=temp_storage_dir)
        with patch.dict("sys.modules", {"mem0": None}):
            count = mem.delete_all(user_id="dev1")
            assert count == 0


# ══════════════════════════════════════════════════════════════════════
# ForgeAIMemory — format_for_context
# ══════════════════════════════════════════════════════════════════════


class TestForgeAIMemoryFormat:
    """Tests for format_for_context() method."""

    @pytest.fixture
    def mem(self, temp_storage_dir: Path) -> Any:
        from src.memory.mem0_wrapper import ForgeAIMemory

        m = ForgeAIMemory(storage_dir=temp_storage_dir)
        m._memory = _make_mock_memory()
        m._initialized = True
        return m

    def test_format_returns_string(self, mem: Any) -> None:
        """format_for_context() should return a formatted string."""
        context = mem.format_for_context(user_id="dev1")
        assert isinstance(context, str)
        assert "Developer context:" in context
        assert "Python 3.12" in context
        assert "async/await" in context

    def test_format_empty_when_no_memories(self, temp_storage_dir: Path) -> None:
        """format_for_context() should return empty string when no memories."""
        from src.memory.mem0_wrapper import ForgeAIMemory

        mem = ForgeAIMemory(storage_dir=temp_storage_dir)
        with patch.dict("sys.modules", {"mem0": None}):
            context = mem.format_for_context(user_id="dev1")
            assert context == ""

    def test_format_respects_max(self, mem: Any) -> None:
        """format_for_context() should respect max_memories."""
        context = mem.format_for_context(user_id="dev1", max_memories=1)
        lines = [l for l in context.split("\n") if l.startswith("- ")]
        assert len(lines) <= 1


# ══════════════════════════════════════════════════════════════════════
# ForgeAIMemory — stats
# ══════════════════════════════════════════════════════════════════════


class TestForgeAIMemoryStats:
    """Tests for get_stats() method."""

    def test_stats_contains_all_keys(self, temp_storage_dir: Path) -> None:
        """get_stats() should contain expected keys."""
        from src.memory.mem0_wrapper import ForgeAIMemory

        mem = ForgeAIMemory(storage_dir=temp_storage_dir)
        stats = mem.get_stats()
        assert "total_adds" in stats
        assert "total_searches" in stats
        assert "available" in stats
        assert "initialized" in stats
        assert "enabled" in stats
        assert "storage_dir" in stats

    def test_stats_tracks_errors(self, temp_storage_dir: Path) -> None:
        """Errors should be tracked in stats."""
        from src.memory.mem0_wrapper import ForgeAIMemory

        mem = ForgeAIMemory(storage_dir=temp_storage_dir)
        with patch.dict("sys.modules", {"mem0": None}):
            mem.add("test", user_id="dev1")
            stats = mem.get_stats()
            assert stats["errors"] >= 1
            assert stats["last_error"] is not None


# ══════════════════════════════════════════════════════════════════════
# create_memory_backend
# ══════════════════════════════════════════════════════════════════════


class TestCreateMemoryBackend:
    """Tests for the create_memory_backend() factory function."""

    def test_returns_forgeai_memory_instance(self) -> None:
        """create_memory_backend() should return a ForgeAIMemory instance."""
        from src.memory.mem0_wrapper import ForgeAIMemory, create_memory_backend

        result = create_memory_backend()
        assert result is not None
        assert isinstance(result, ForgeAIMemory)

    def test_returns_disabled_instance_when_disabled(self) -> None:
        """create_memory_backend() should return disabled instance when FORGEAI_MEMORY_ENABLED=false."""
        os.environ["FORGEAI_MEMORY_ENABLED"] = "false"
        try:
            from src.memory.mem0_wrapper import create_memory_backend

            result = create_memory_backend()
            assert result is not None
            assert result.available() is False
        finally:
            del os.environ["FORGEAI_MEMORY_ENABLED"]

    def test_respects_custom_storage_dir(self) -> None:
        """create_memory_backend() should use FORGEAI_MEMORY_DIR if set."""
        test_dir = tempfile.mkdtemp()
        os.environ["FORGEAI_MEMORY_DIR"] = test_dir
        try:
            from src.memory.mem0_wrapper import create_memory_backend

            result = create_memory_backend()
            assert result is not None
            assert str(result._storage_dir) == test_dir
        finally:
            del os.environ["FORGEAI_MEMORY_DIR"]
            import shutil

            shutil.rmtree(test_dir, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# Thread safety
# ══════════════════════════════════════════════════════════════════════


class TestForgeAIMemoryThreadSafety:
    """Basic thread safety check for ForgeAIMemory."""

    def test_no_crash_on_concurrent_access(self, temp_storage_dir: Path) -> None:
        """Concurrent add/search should not crash."""
        from concurrent.futures import ThreadPoolExecutor
        from src.memory.mem0_wrapper import ForgeAIMemory

        mem = ForgeAIMemory(storage_dir=temp_storage_dir)
        mock_mem = _make_mock_memory()
        mem._memory = mock_mem
        mem._initialized = True

        def worker_add() -> None:
            mem.add("test", user_id="dev1")

        def worker_search() -> None:
            mem.search("test", user_id="dev1")

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(worker_add) for _ in range(10)]
            futures += [pool.submit(worker_search) for _ in range(10)]
            for f in futures:
                f.result()

        assert mem.get_stats()["total_adds"] == 10
        assert mem.get_stats()["total_searches"] == 10
