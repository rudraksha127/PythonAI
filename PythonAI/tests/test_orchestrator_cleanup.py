"""Unit tests for MCP connection cleanup in AgentOrchestrator.

Tests cover:
  - cleanup() handles no-MCP gracefully
  - cleanup() is idempotent
  - cleanup() calls close_all() on the MCP client
  - cleanup() sets _mcp_client to None after
  - _auto_connect_mcp() calls cleanup() before reconnecting
  - run() calls cleanup() on exit
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.core.agents.orchestrator import AgentOrchestrator
from src.core.registry import get_registry
from src.core.tools import register_all_tools


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def registry():
    """Create a fresh registry with all tools registered."""
    reg = get_registry()
    register_all_tools(reg)
    return reg


@pytest.fixture
def orch(registry):
    """Create an orchestrator with a fresh registry and recording stream."""
    stream_log: list[str] = []

    def stream(msg: str) -> None:
        stream_log.append(msg)

    o = AgentOrchestrator(
        registry=registry,
        on_stream=stream,
        verbose=True,
    )
    return o, stream_log


def make_orch() -> AgentOrchestrator:
    """Create a bare orchestrator with a no-op stream."""
    return AgentOrchestrator(
        on_stream=lambda msg: None,
        verbose=True,
    )


def make_orch_with_log() -> tuple[AgentOrchestrator, list[str]]:
    """Create an orchestrator with a recording stream."""
    logs: list[str] = []

    def stream(msg: str) -> None:
        logs.append(msg)

    o = AgentOrchestrator(on_stream=stream, verbose=True)
    return o, logs


# ── Cleanup: no-MCP graceful handling ─────────────────────────────────


class TestCleanupNoMCP:
    """cleanup() when no MCP client exists should be safe."""

    def test_cleanup_with_no_client(self, orch):
        """cleanup() should not raise when _mcp_client is None."""
        o, _ = orch
        assert o._mcp_client is None
        o.cleanup()  # Should not raise
        assert o._mcp_client is None

    def test_cleanup_with_no_client_does_not_stream(self, orch):
        """cleanup() should not log anything when no client exists."""
        o, log = orch
        log.clear()
        o.cleanup()
        assert not any("MCP connections closed" in msg for msg in log)


# ── Cleanup: idempotency ──────────────────────────────────────────────


class TestCleanupIdempotent:
    """cleanup() should be safe to call multiple times."""

    def test_cleanup_called_twice(self, orch):
        """Calling cleanup() twice should not raise."""
        o, _ = orch
        o.cleanup()
        o.cleanup()
        assert o._mcp_client is None

    def test_cleanup_called_many_times(self, orch):
        """Calling cleanup() many times should be safe."""
        o, _ = orch
        for _ in range(10):
            o.cleanup()
        assert o._mcp_client is None


# ── Cleanup: close_all behavior ────────────────────────────────────────


class TestCleanupWithMCPClient:
    """cleanup() when _mcp_client is set should call close_all()."""

    def test_cleanup_calls_close_all(self):
        """cleanup() should call close_all() on the MCP client."""
        o = make_orch()
        mock_client = MagicMock()
        o._mcp_client = mock_client

        o.cleanup()

        mock_client.close_all.assert_called_once()

    def test_cleanup_sets_client_to_none_after(self):
        """cleanup() should set _mcp_client to None after close_all()."""
        o = make_orch()
        o._mcp_client = MagicMock()

        o.cleanup()

        assert o._mcp_client is None

    def test_cleanup_streams_message(self):
        """cleanup() should log 'MCP connections closed' when client exists."""
        o, logs = make_orch_with_log()
        o._mcp_client = MagicMock()

        o.cleanup()

        assert any("MCP connections closed" in msg for msg in logs)

    def test_cleanup_handles_close_all_exception(self):
        """cleanup() should not raise if close_all() raises."""
        o = make_orch()
        mock_client = MagicMock()
        mock_client.close_all.side_effect = RuntimeError("Connection error")
        o._mcp_client = mock_client

        o.cleanup()  # Should not raise

        assert o._mcp_client is None  # Should still be reset

    def test_cleanup_called_twice_with_client(self):
        """cleanup() called twice with a client should only call close_all() once."""
        o = make_orch()
        mock_client = MagicMock()
        o._mcp_client = mock_client

        o.cleanup()
        o.cleanup()

        mock_client.close_all.assert_called_once()

    def test_cleanup_after_cleanup_logs_once(self):
        """cleanup() called twice should only log the message once."""
        o, logs = make_orch_with_log()
        o._mcp_client = MagicMock()

        o.cleanup()
        o.cleanup()

        close_msgs = [m for m in logs if "MCP connections closed" in m]
        assert len(close_msgs) == 1


# ── _auto_connect_mcp: calls cleanup before reconnect ──────────────────


class TestAutoConnectMCPSafety:
    """_auto_connect_mcp() should call cleanup() before reconnecting."""

    def test_auto_connect_calls_cleanup_before_reconnect(self):
        """_auto_connect_mcp should call cleanup() before creating new connections."""
        o = make_orch()

        # Set up a mock client (simulating a previous connection)
        mock_client = MagicMock()
        o._mcp_client = mock_client

        # Patch MCP module import to fail — cleanup() still runs before import
        with patch.dict("sys.modules", {"src.core.mcp": None}):
            o._auto_connect_mcp()

        # close_all should have been called (from cleanup)
        mock_client.close_all.assert_called_once()
        assert o._mcp_client is None  # Reset by cleanup

    def test_auto_connect_cleanup_handles_old_client(self):
        """_auto_connect_mcp should close old client before reconnecting."""
        o = make_orch()
        old_client = MagicMock()
        o._mcp_client = old_client

        with patch.dict("sys.modules", {"src.core.mcp": None}):
            o._auto_connect_mcp()

        old_client.close_all.assert_called_once()


# ── run(): calls cleanup on exit ──────────────────────────────────────


class TestRunCallsCleanup:
    """run() should call cleanup() before returning."""

    @pytest.mark.integration
    def test_run_calls_cleanup_on_exit(self, orch):
        """run() should trigger cleanup (based on streaming message)."""
        o, log = orch

        # Run with a simple task — should call cleanup at the end
        result = o.run("what is 2+2?")

        # Check that cleanup was called (stream message appears)
        assert any("MCP connections closed" in msg for msg in log)
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.integration
    def test_run_does_not_raise_on_cleanup(self, orch):
        """run() should not raise even if cleanup encounters issues."""
        o, _ = orch

        # Force _auto_connect_mcp to set _mcp_client to a faulty one
        mock_client = MagicMock()
        mock_client.close_all.side_effect = RuntimeError("Cleanup failed")
        o._mcp_client = mock_client

        # run() should still complete without raising
        result = o.run("what is 2+2?")
        assert isinstance(result, str)


# ── __del__: destructor safety ────────────────────────────────────────


class TestDestructorSafety:
    """__del__() should call cleanup() as a safety net."""

    def test_del_calls_cleanup(self):
        """__del__ should call cleanup on the instance."""
        o = make_orch()
        mock_client = MagicMock()
        o._mcp_client = mock_client

        o.__del__()

        mock_client.close_all.assert_called_once()
        assert o._mcp_client is None

    def test_del_safe_with_no_client(self):
        """__del__ should not raise when no client exists."""
        o = make_orch()
        assert o._mcp_client is None
        o.__del__()  # Should not raise


# ── Context manager: with-statement support ──────────────────────────


class TestContextManager:
    """AgentOrchestrator should support the `with` statement."""

    def test_enter_returns_self(self):
        """__enter__ should return the orchestrator instance."""
        o = make_orch()
        result = o.__enter__()
        assert result is o

    def test_exit_calls_cleanup_with_client(self):
        """__exit__ should call cleanup when a client exists."""
        o = make_orch()
        mock_client = MagicMock()
        o._mcp_client = mock_client

        o.__exit__(None, None, None)

        mock_client.close_all.assert_called_once()
        assert o._mcp_client is None

    def test_exit_calls_cleanup_no_client(self):
        """__exit__ should not raise when no client exists."""
        o = make_orch()
        assert o._mcp_client is None
        o.__exit__(None, None, None)  # Should not raise
        assert o._mcp_client is None

    def test_exit_with_exception_still_cleans_up(self):
        """__exit__ should clean up even when an exception occurs."""
        o = make_orch()
        mock_client = MagicMock()
        o._mcp_client = mock_client

        # Simulate exiting with an exception
        o.__exit__(RuntimeError, RuntimeError("fail"), None)

        mock_client.close_all.assert_called_once()
        assert o._mcp_client is None

    def test_exit_handles_close_all_exception(self):
        """__exit__ should not raise if close_all() fails."""
        o = make_orch()
        mock_client = MagicMock()
        mock_client.close_all.side_effect = RuntimeError("Cleanup error")
        o._mcp_client = mock_client

        o.__exit__(None, None, None)  # Should not raise
        assert o._mcp_client is None

    def test_with_statement_syntax(self):
        """Using `with AgentOrchestrator() as orch:` should work."""
        o = make_orch()
        mock_client = MagicMock()
        o._mcp_client = mock_client

        with o:
            pass  # Use orchestrator inside the block

        # __exit__ should have been called, closing the client
        mock_client.close_all.assert_called_once()
        assert o._mcp_client is None


# ── Multiple instances: cross-instance isolation ───────────────────────


class TestMultipleInstances:
    """Multiple orchestrator instances should each clean up independently."""

    def test_two_instances_cleanup_independently(self):
        """Two orchestrators with mock clients should each clean up independently."""
        o1 = make_orch()
        o2 = make_orch()

        mock1 = MagicMock()
        mock2 = MagicMock()
        o1._mcp_client = mock1
        o2._mcp_client = mock2

        o1.cleanup()
        mock1.close_all.assert_called_once()
        assert o1._mcp_client is None

        # o2's client should still be intact
        assert o2._mcp_client is not None
        mock2.close_all.assert_not_called()

        o2.cleanup()
        mock2.close_all.assert_called_once()
        assert o2._mcp_client is None

    def test_three_instances_all_cleanup(self):
        """Three orchestrators should all clean up without interference."""
        instances = [(make_orch(), MagicMock()) for _ in range(3)]
        for o, mock in instances:
            o._mcp_client = mock

        # Clean up each one
        for o, mock in instances:
            o.cleanup()
            assert o._mcp_client is None

        # Verify each mock was called exactly once
        for _, mock in instances:
            mock.close_all.assert_called_once()

    def test_mixed_clients_and_no_clients(self):
        """Mix of instances with and without clients should all clean up."""
        o_with = make_orch()
        o_without = make_orch()

        mock = MagicMock()
        o_with._mcp_client = mock
        # o_without has no client (default)

        o_with.cleanup()
        mock.close_all.assert_called_once()
        assert o_with._mcp_client is None

        o_without.cleanup()
        assert o_without._mcp_client is None  # Still None after cleanup

    def test_multiple_instances_idempotent_cleanup(self):
        """Multiple instances should handle repeated cleanup."""
        o1 = make_orch()
        o2 = make_orch()

        mock1 = MagicMock()
        mock2 = MagicMock()
        o1._mcp_client = mock1
        o2._mcp_client = mock2

        # Double cleanup on each
        o1.cleanup()
        o1.cleanup()
        o2.cleanup()
        o2.cleanup()

        mock1.close_all.assert_called_once()
        mock2.close_all.assert_called_once()
        assert o1._mcp_client is None
        assert o2._mcp_client is None

    def test_instances_with_streams_log_correctly(self):
        """Multiple instances with streams should each log independently."""
        o1, log1 = make_orch_with_log()
        o2, log2 = make_orch_with_log()

        o1._mcp_client = MagicMock()
        o2._mcp_client = MagicMock()

        o1.cleanup()
        assert any("MCP connections closed" in m for m in log1)
        assert not any("MCP connections closed" in m for m in log2)

        o2.cleanup()
        assert any("MCP connections closed" in m for m in log2)

    def test_sequential_runs_cleanup(self):
        """Same instance run sequentially should clean up between runs."""
        cleanups = []

        def tracking_cleanup():
            cleanups.append(1)

        o = make_orch()
        original = o.cleanup
        o.cleanup = lambda: (cleanups.append(1), original())  # type: ignore[method-assign]

        # Simulate: first run creates a client, second run creates another
        for i in range(3):
            o._mcp_client = MagicMock()
            o.cleanup()
            assert o._mcp_client is None

        assert len(cleanups) == 3

    def test_cleanup_via_del_called(self):
        """Orchestrators should clean up via __del__ when deleted."""
        calls = []

        mock = MagicMock()
        mock.close_all.side_effect = lambda: calls.append("closed")

        o = make_orch()
        o._mcp_client = mock

        # Invoke __del__ explicitly (simulating GC)
        o.__del__()
        assert "closed" in calls
        assert len(calls) == 1

        # Calling __del__ again should be a no-op (client already None)
        o.__del__()
        assert len(calls) == 1  # close_all should NOT be called again


# ── Integration: full cleanup cycle ────────────────────────────────────


class TestCleanupIntegration:
    """End-to-end cleanup cycle verification."""

    @pytest.mark.integration
    def test_cleanup_cycle_is_idempotent(self, orch):
        """Full cleanup cycle (auto-connect -> use -> cleanup -> cleanup again)."""
        o, _ = orch

        # Run once
        o.run("what is 2+2?")
        assert o._mcp_client is None  # Cleanup ran

        # Cleanup again (should be a no-op)
        o.cleanup()
        assert o._mcp_client is None

    @pytest.mark.integration
    def test_multiple_run_calls_cleanup(self):
        """Multiple run() calls should each trigger cleanup."""
        o = make_orch()

        # Track cleanup calls
        cleanup_count = 0
        original_cleanup = o.cleanup

        def counting_cleanup():
            nonlocal cleanup_count
            cleanup_count += 1
            original_cleanup()

        o.cleanup = counting_cleanup  # type: ignore[method-assign]

        # Run twice
        o.run("task 1")
        o.run("task 2")

        # cleanup should have been called at least once per run
        assert cleanup_count >= 2
