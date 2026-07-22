"""
End-to-End Integration Tests: ROI Calculator Data Flow
======================================================

Tests the full backend API data flow that the ROI Calculator React component
depends on:
  1. POST /api/events     — Seed accept/reject/edit signals
  2. GET  /stats          — Capture statistics → component's currentRate
  3. GET  /api/metrics/acceptance-rate — Time-series data
  4. GET  /api/training/status         — Training runs → component's avgTrainingDelta
  5. GET  /api/metrics/improvement-heatmap — Related REQ-DASH-003 data
  6. GET  /api/metrics/signal-patterns     — Related REQ-DASH-005 data

Uses FastAPI's TestClient with a patched CaptureEngine so tests are
deterministic and require no external database.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    """Create a TestClient. The lifespan will init capture engine, so
    tests must patch _capture_engine (and friends) at the test level."""
    from src.api.server import app

    with TestClient(app) as client:
        yield client


def _make_roi_engine() -> MagicMock:
    """
    Build a CaptureEngine mock that returns data matching what the
    ROI Calculator component expects.

    The component fetches:
      - getCaptureStats()  → capture_engine.get_statistics()
      - getTrainingStatus() → capture_engine.get_training_runs()

    Component expects:
      stats.signals_by_type          → for signal distribution
      stats.signals_by_language      → for language breakdown
      stats.overall_acceptance_rate  → currentRate
      stats.total_sessions
      training runs[].acceptance_delta → avgTrainingDelta
    """
    now = time.time()
    engine = MagicMock()

    # ── get_statistics() ─────────────────────────────────────────
    engine.get_statistics.return_value = {
        "signals_by_type": {
            "accept": 150,
            "reject": 40,
            "edit": 25,
            "pr_merge": 10,
        },
        "signals_by_language": {
            "python": 120,
            "typescript": 60,
            "go": 30,
            "rust": 15,
        },
        "total_sessions": 25,
        "overall_acceptance_rate": 65.0,
        "avg_edit_distance": 0.35,
    }

    # ── get_acceptance_rate(days=84) ─────────────────────────────
    engine.get_acceptance_rate.return_value = [
        {
            "date": "2026-05-25",
            "acceptance_rate": 55.0,
            "accepts": 28,
            "rejects": 18,
            "edits": 4,
            "total": 50,
        },
        {
            "date": "2026-06-01",
            "acceptance_rate": 58.0,
            "accepts": 32,
            "rejects": 15,
            "edits": 3,
            "total": 50,
        },
        {
            "date": "2026-06-08",
            "acceptance_rate": 62.0,
            "accepts": 35,
            "rejects": 12,
            "edits": 3,
            "total": 50,
        },
        {
            "date": "2026-06-15",
            "acceptance_rate": 65.0,
            "accepts": 38,
            "rejects": 9,
            "edits": 3,
            "total": 50,
        },
    ]

    # ── get_training_runs(limit=10) ──────────────────────────────
    engine.get_training_runs.return_value = [
        {
            "run_id": "run-001",
            "timestamp": now - 7 * 86400,
            "model_name": "Qwen/Qwen2.5-Coder-7B-Instruct",
            "signals_used": 100,
            "train_loss": 0.45,
            "eval_loss": 1.02,
            "acceptance_rate_before": 0.55,
            "acceptance_rate_after": 0.58,
            "acceptance_delta": 0.03,
            "adapter_path": "/home/user/.forgeai/adapters/v1",
        },
        {
            "run_id": "run-002",
            "timestamp": now - 14 * 86400,
            "model_name": "Qwen/Qwen2.5-Coder-7B-Instruct",
            "signals_used": 120,
            "train_loss": 0.38,
            "eval_loss": 0.95,
            "acceptance_rate_before": 0.52,
            "acceptance_rate_after": 0.55,
            "acceptance_delta": 0.03,
            "adapter_path": "/home/user/.forgeai/adapters/v2",
        },
        {
            "run_id": "run-003",
            "timestamp": now - 21 * 86400,
            "model_name": "Qwen/Qwen2.5-Coder-7B-Instruct",
            "signals_used": 80,
            "train_loss": 0.52,
            "eval_loss": 1.10,
            "acceptance_rate_before": 0.48,
            "acceptance_rate_after": 0.52,
            "acceptance_delta": 0.04,
            "adapter_path": "/home/user/.forgeai/adapters/v3",
        },
    ]

    # ── get_training_runs(limit=20) — for improvement-heatmap ────
    # (same data, different limit — mock returns same list)
    engine.get_training_runs.return_value = engine.get_training_runs.return_value

    return engine


# ── Tests ────────────────────────────────────────────────────────


class TestRoiCalculatorBackendDataFlow:
    """
    End-to-end tests verifying the API data that powers the
    ROI Calculator React component (REQ-DASH-004).
    """

    # ═════════════════════════════════════════════════════════
    # /stats — Capture Statistics
    # ═════════════════════════════════════════════════════════

    def test_stats_shape_matches_roi_calculator_input(self, client: TestClient):
        """
        The ROI Calculator fetches getCaptureStats() which calls
        GET /stats. Verify the response contains all fields the
        component uses.
        """
        engine = _make_roi_engine()
        with patch("src.api.server._capture_engine", engine):
            response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        # Fields used by RoiCalculator
        assert "signals_by_type" in data
        assert isinstance(data["signals_by_type"], dict)
        assert "signals_by_language" in data
        assert isinstance(data["signals_by_language"], dict)
        assert "overall_acceptance_rate" in data
        assert isinstance(data["overall_acceptance_rate"], (int, float))
        assert "total_sessions" in data
        assert isinstance(data["total_sessions"], int)

        # The component calculates currentRate from overall_acceptance_rate
        current_rate = data["overall_acceptance_rate"]
        assert current_rate == 65.0  # From mock

    def test_stats_acceptance_rate_feed_roi_calculator(self, client: TestClient):
        """
        The ROI Calculator uses overall_acceptance_rate as currentRate.
        Verify realistic values that produce meaningful ROI.
        """
        engine = _make_roi_engine()
        engine.get_statistics.return_value = {
            "signals_by_type": {"accept": 200, "reject": 50, "edit": 30},
            "signals_by_language": {"python": 150, "typescript": 80, "go": 50},
            "total_sessions": 30,
            "overall_acceptance_rate": 72.4,
            "avg_edit_distance": 0.25,
        }
        with patch("src.api.server._capture_engine", engine):
            response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()

        # A 72.4% acceptance rate with teamSize=10, salary=$150K
        # should give meaningful ROI values
        assert data["overall_acceptance_rate"] == 72.4
        assert data["total_sessions"] == 30

    def test_stats_signals_by_type_has_breakdown(self, client: TestClient):
        """
        The ROI Calculator uses signals_by_type for display.
        Verify breakdown keys are present.
        """
        engine = _make_roi_engine()
        with patch("src.api.server._capture_engine", engine):
            response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()
        sbt = data["signals_by_type"]

        # Expected keys
        assert "accept" in sbt
        assert "reject" in sbt
        assert "edit" in sbt

        # Total should be non-zero
        total = sum(sbt.values())
        assert total > 0

    # ═════════════════════════════════════════════════════════
    # /api/metrics/acceptance-rate — Time-series for chart
    # ═════════════════════════════════════════════════════════

    def test_acceptance_rate_returns_weekly_data_for_chart(self, client: TestClient):
        """
        The RoiCalculator doesn't directly use acceptance rate data,
        but the parent DashboardPage does. Verify data is suitable
        for the AreaChart component.
        """
        engine = _make_roi_engine()
        with patch("src.api.server._capture_engine", engine):
            response = client.get("/api/metrics/acceptance-rate?weeks=4")

        assert response.status_code == 200
        data = response.json()

        assert "data" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) == 4  # 4 weeks requested

        for point in data["data"]:
            assert "date" in point
            assert "acceptance_rate" in point
            assert "accepts" in point
            assert "rejects" in point
            assert "total" in point
            # acceptance_rate = accepts / total * 100
            assert point["acceptance_rate"] >= 0 and point["acceptance_rate"] <= 100

    def test_acceptance_rate_monotonic_improvement(self, client: TestClient):
        """
        Verify the mock data shows improving acceptance rate over time,
        which is the core thesis of ForgeAI.
        """
        engine = _make_roi_engine()
        with patch("src.api.server._capture_engine", engine):
            response = client.get("/api/metrics/acceptance-rate?weeks=4")

        assert response.status_code == 200
        data = response.json()

        rates = [p["acceptance_rate"] for p in data["data"]]
        assert rates == sorted(rates), "Acceptance rate should improve over time"
        assert rates[0] < rates[-1], "Latest rate should be higher than earliest"

    def test_acceptance_rate_includes_training_markers(self, client: TestClient):
        """
        The chart may show training run markers. Verify they exist.
        """
        engine = _make_roi_engine()
        with patch("src.api.server._capture_engine", engine):
            response = client.get("/api/metrics/acceptance-rate")

        assert response.status_code == 200
        data = response.json()

        assert "training_markers" in data
        assert isinstance(data["training_markers"], list)
        if data["training_markers"]:
            marker = data["training_markers"][0]
            assert "timestamp" in marker
            assert "delta" in marker
            assert "signals" in marker

    # ═════════════════════════════════════════════════════════
    # /api/training/status — Training runs for avgTrainingDelta
    # ═════════════════════════════════════════════════════════

    def test_training_status_returns_history_for_roi(self, client: TestClient):
        """
        The ROI Calculator gets training runs to compute avgTrainingDelta.
        Verify the response shape matches what the component expects.
        """
        engine = _make_roi_engine()
        with patch("src.api.server._capture_engine", engine):
            response = client.get("/api/training/status")

        assert response.status_code == 200
        data = response.json()

        assert "active_run" in data
        assert "history" in data
        assert isinstance(data["history"], list)

    def test_training_deltas_are_positive(self, client: TestClient):
        """
        The core thesis: each training run should improve acceptance rate.
        Delta should be positive for all runs.
        """
        engine = _make_roi_engine()
        with patch("src.api.server._capture_engine", engine):
            response = client.get("/api/training/status")

        assert response.status_code == 200
        data = response.json()

        for run in data["history"]:
            assert run["acceptance_delta"] >= 0, \
                f"Training run {run['run_id']} has negative delta"
            # acceptance_delta = acceptance_rate_after - acceptance_rate_before
            expected_delta = run["acceptance_rate_after"] - run["acceptance_rate_before"]
            assert abs(run["acceptance_delta"] - expected_delta) < 0.001

    def test_training_deltas_feed_avg_training_delta(self, client: TestClient):
        """
        The component computes avgTrainingDelta = average of acceptance_delta.
        With 3 runs of [0.03, 0.03, 0.04], avg = 0.0333...
        """
        engine = _make_roi_engine()
        with patch("src.api.server._capture_engine", engine):
            response = client.get("/api/training/status")

        assert response.status_code == 200
        data = response.json()

        deltas = [r["acceptance_delta"] for r in data["history"]]
        if deltas:
            avg_delta = sum(deltas) / len(deltas)
            # avg delta ≈ 0.0333
            assert 0.03 <= avg_delta <= 0.04

    # ═════════════════════════════════════════════════════════
    # Full ROI Calculator data pipeline
    # ═════════════════════════════════════════════════════════

    def test_full_roi_pipeline_consistent_data(self, client: TestClient):
        """
        The ROI Calculator fetches both /stats and /api/training/status
        simultaneously. Verify both endpoints return consistent data
        (same session count, no contradictions).
        """
        engine = _make_roi_engine()
        with patch("src.api.server._capture_engine", engine):
            stats_resp = client.get("/stats")
            train_resp = client.get("/api/training/status")

        assert stats_resp.status_code == 200
        assert train_resp.status_code == 200

        stats = stats_resp.json()
        training = train_resp.json()

        # Both should reference the same data
        assert stats["total_sessions"] == 25

        # Training runs should have valid deltas
        for run in training["history"]:
            assert run["acceptance_rate_after"] >= run["acceptance_rate_before"]
            assert run["acceptance_delta"] >= 0

    def test_roi_pipeline_with_no_training_runs(self, client: TestClient):
        """
        Edge case: brand new installation with signals but no training.
        The component should fall back to default 3% delta per run.
        """
        engine = _make_roi_engine()
        engine.get_statistics.return_value = {
            "signals_by_type": {"accept": 10, "reject": 2, "edit": 1},
            "signals_by_language": {"python": 13},
            "total_sessions": 3,
            "overall_acceptance_rate": 50.0,
            "avg_edit_distance": 0.0,
        }
        engine.get_training_runs.return_value = []

        with patch("src.api.server._capture_engine", engine):
            stats_resp = client.get("/stats")
            train_resp = client.get("/api/training/status")

        assert stats_resp.status_code == 200
        assert train_resp.status_code == 200

        stats = stats_resp.json()
        training = train_resp.json()

        assert stats["overall_acceptance_rate"] == 50.0
        assert len(training["history"]) == 0

        # Component would use defaults: currentRate=50%, avgDelta=3%
        # projectedRuns = max(1, 12-0) = 12
        # improvement = min(3*12, 40) = 36pp
        # productivity = min(36*0.75, 35) = 27%
        # This test just validates the API — the component does computation client-side.

    def test_roi_pipeline_with_engine_unavailable(self, client: TestClient):
        """
        Edge case: capture engine is None.
        The endpoints should return fallback empty data.
        """
        with patch("src.api.server._capture_engine", None):
            stats_resp = client.get("/stats")
            train_resp = client.get("/api/training/status")

        # /stats falls back to empty
        assert stats_resp.status_code == 200
        stats = stats_resp.json()
        assert stats["signals_by_type"] == {}
        assert stats["signals_by_language"] == {}
        assert stats["total_sessions"] == 0
        assert stats["overall_acceptance_rate"] == 0.0

        # /api/training/status returns 503
        assert train_resp.status_code == 503
        assert "Capture engine not initialized" in train_resp.text

    def test_roi_pipeline_engine_raises(self, client: TestClient):
        """
        Edge case: capture engine methods raise exceptions.
        Endpoints should handle gracefully.
        """
        engine = MagicMock()
        engine.get_statistics.side_effect = RuntimeError("DB locked")
        engine.get_training_runs.side_effect = RuntimeError("DB locked")
        engine.get_acceptance_rate.side_effect = RuntimeError("DB locked")

        with patch("src.api.server._capture_engine", engine):
            stats_resp = client.get("/stats")

        assert stats_resp.status_code == 200
        stats = stats_resp.json()
        assert stats["signals_by_type"] == {}
        assert stats["overall_acceptance_rate"] == 0.0

    # ═════════════════════════════════════════════════════════
    # Related endpoints (REQ-DASH-003, REQ-DASH-005)
    # ═════════════════════════════════════════════════════════

    def test_improvement_heatmap_endpoint(self, client: TestClient):
        """
        Verify the improvement heatmap endpoint returns expected structure
        when the ROI Calculator engine data is available.
        """
        engine = _make_roi_engine()
        with patch("src.api.server._capture_engine", engine):
            response = client.get("/api/metrics/improvement-heatmap")

        assert response.status_code == 200
        data = response.json()

        # Top-level keys
        assert "languages" in data
        assert "patterns" in data
        assert "slots" in data
        assert "weekly_data" in data
        assert "training_runs" in data

        # Language data should exist
        assert len(data["languages"]) > 0
        assert data["languages"][0]["name"] in ("python", "typescript", "go", "rust")

        # Patterns should include accept, reject, edit
        pattern_keys = {p["key"] for p in data["patterns"]}
        assert "accept" in pattern_keys

        # Training runs should have delta, signals_used, model
        for tr in data["training_runs"]:
            assert "delta" in tr
            assert "signals_used" in tr
            assert "model" in tr

    def test_signal_patterns_endpoint(self, client: TestClient):
        """
        Verify the signal patterns endpoint returns expected structure
        when the ROI Calculator engine data is available.
        """
        engine = _make_roi_engine()
        with patch("src.api.server._capture_engine", engine):
            response = client.get("/api/metrics/signal-patterns")

        assert response.status_code == 200
        data = response.json()

        # Top-level keys
        assert "signal_types" in data
        assert "language_rates" in data
        assert "weekly_trend" in data
        assert "rejection_patterns" in data
        assert "overall" in data

        # Signal types should include accept, reject, edit
        types = {t["key"] for t in data["signal_types"]}
        assert "accept" in types
        assert "reject" in types

        # Language rates should match mocked data
        assert len(data["language_rates"]) == 4  # python, typescript, go, rust

        # Overall metrics
        assert data["overall"]["total_signals"] > 0
        assert data["overall"]["overall_acceptance_rate"] == 65.0
        assert data["overall"]["trend_direction"] in ("up", "down", "stable")

    def test_signal_patterns_rejection_severity(self, client: TestClient):
        """
        Rejection patterns should have severity classification.
        """
        engine = _make_roi_engine()
        with patch("src.api.server._capture_engine", engine):
            response = client.get("/api/metrics/signal-patterns")

        assert response.status_code == 200
        data = response.json()

        for rp in data["rejection_patterns"]:
            assert rp["severity"] in ("high", "medium", "low")
            assert rp["rejection_rate"] >= 0
            assert rp["acceptance_rate"] >= 0
            # rejection_rate + acceptance_rate ≈ 100
            assert abs(rp["rejection_rate"] + rp["acceptance_rate"] - 100) < 1.0


class TestEventCaptureEndToEnd:
    """
    Test the full event capture pipeline that feeds data into
    the ROI Calculator's data sources.
    """

    def _make_real_engine(self):
        """Helper: create a CaptureEngine backed by a temp file (not :memory:).
        SQLite :memory: creates a NEW database per connection, so _init_db()
        tables vanish when _store_signal() opens its own connection.
        """
        import tempfile
        from src.learning.capture_engine import CaptureEngine

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        engine = CaptureEngine(db_path=tmp.name)
        return engine, tmp.name

    def test_capture_event_and_query_stats(self, client: TestClient):
        """
        Simulate a real flow: capture an accept event, then query stats.
        Uses a real CaptureEngine with a temp file DB.
        """
        import os

        real_engine, db_path = self._make_real_engine()
        assert real_engine is not None

        try:
            with patch("src.api.server._capture_engine", real_engine):
                # Capture events
                for i in range(5):
                    resp = client.post("/api/events", json={
                        "event_type": "accept",
                        "session_id": f"session-{i}",
                        "project_id": "test-project",
                        "file_path": f"src/main{i}.py",
                        "line_number": 10 + i,
                        "language": "python",
                        "project_type": "web",
                        "suggestion": f"print('hello {i}')" * 50,
                        "context_before": "def foo():",
                        "context_after": "    pass",
                    })
                    assert resp.status_code == 200, f"Accept {i} failed: {resp.text[:200]}"
                    assert resp.json()["captured"] is True

                for i in range(3):
                    resp = client.post("/api/events", json={
                        "event_type": "reject",
                        "session_id": f"session-reject-{i}",
                        "project_id": "test-project",
                        "file_path": f"src/lib{i}.py",
                        "line_number": 5 + i,
                        "language": "python",
                        "project_type": "web",
                        "suggestion": f"wrong_code_{i}" * 50,
                        "context_before": "def bar():",
                        "context_after": "    pass",
                    })
                    assert resp.status_code == 200, f"Reject {i} failed: {resp.text[:200]}"
                    assert resp.json()["captured"] is True

                for i in range(2):
                    resp = client.post("/api/events", json={
                        "event_type": "edit",
                        "session_id": f"session-edit-{i}",
                        "project_id": "test-project",
                        "file_path": f"src/edit{i}.py",
                        "line_number": 15 + i,
                        "language": "python",
                        "project_type": "web",
                        "suggestion": f"original_code_{i}" * 50,
                        "final_code": f"edited_code_{i}" * 50,
                        "context_before": "def baz():",
                        "context_after": "    pass",
                    })
                    assert resp.status_code == 200, f"Edit {i} failed: {resp.text[:200]}"
                    assert resp.json()["captured"] is True

                # Now query stats
                stats_resp = client.get("/stats")
                assert stats_resp.status_code == 200
                stats = stats_resp.json()

                # Verify captured events are reflected in stats
                assert stats["signals_by_type"].get("accept", 0) == 5
                assert stats["signals_by_type"].get("reject", 0) == 3
                assert stats["signals_by_type"].get("edit", 0) == 2
                assert stats["total_sessions"] > 0
                assert stats["overall_acceptance_rate"] > 0

                # Acceptance rate = 5 accepts / (5 + 3) = 62.5%
                expected_rate = round(5 / (5 + 3) * 100, 1)
                assert abs(stats["overall_acceptance_rate"] - expected_rate) < 1.0
        finally:
            try:
                os.unlink(db_path)
            except OSError:
                pass

    def test_capture_to_acceptance_rate_pipeline(self, client: TestClient):
        """
        Capture events over time and verify they appear in acceptance
        rate data.
        """
        import os

        real_engine, db_path = self._make_real_engine()
        assert real_engine is not None

        # Patch rate limiter AND capture engine to avoid 429 from previous tests
        mock_limiter = MagicMock()
        mock_limiter.allow.return_value = True

        try:
            with patch("src.api.server._rate_limiter", mock_limiter):
                with patch("src.api.server._capture_engine", real_engine):
                    # Bulk capture events
                    for i in range(10):
                        resp = client.post("/api/events", json={
                            "event_type": "accept" if i < 7 else "reject",
                            "session_id": f"bulk-session-{i}",
                            "project_id": "test-project",
                            "file_path": f"src/bulk{i}.py",
                            "line_number": i,
                            "language": "python",
                            "project_type": "web",
                            "suggestion": f"code_{i}" * 50,
                            "context_before": "def bulk():",
                            "context_after": "    pass",
                        })
                        assert resp.status_code == 200, f"Bulk event {i} failed: {resp.text[:200]}"

                    # Store a training run — still inside capture_engine patch
                    real_engine.store_training_run(
                        run_id="e2e-run-001",
                        model_name="Qwen/Qwen2.5-Coder-7B-Instruct",
                        signals_used=10,
                        acceptance_rate_before=0.50,
                        acceptance_rate_after=0.65,
                        train_loss=0.45,
                        eval_loss=1.02,
                        adapter_path="/tmp/test-adapter",
                    )

                    # Verify acceptance rate — still inside capture_engine patch
                    rate_resp = client.get("/api/metrics/acceptance-rate")
                    assert rate_resp.status_code == 200
                    rate_data = rate_resp.json()
                    assert len(rate_data["data"]) > 0

                    # Latest point should have 7 accepts, 3 rejects
                    latest = rate_data["data"][-1]
                    assert latest["accepts"] >= 7
                    assert latest["rejects"] >= 3

                    # Verify training status — still inside capture_engine patch
                    train_resp = client.get("/api/training/status")
                    assert train_resp.status_code == 200
                    train_data = train_resp.json()
                    assert len(train_data["history"]) == 1
                    # 0.65 - 0.50 = 0.15 (with floating point: 0.15000000000000002)
                assert abs(train_data["history"][0]["acceptance_delta"] - 0.15) < 1e-10
        finally:
            try:
                os.unlink(db_path)
            except OSError:
                pass

    def test_health_endpoint_returns_scheduler_info(self, client: TestClient):
        """
        The dashboard health check should return scheduler info.
        Patches rate limiter to prevent 429 from other tests consuming tokens.
        """
        # Mock the rate limiter to always allow
        mock_limiter = MagicMock()
        mock_limiter.allow.return_value = True

        # Mock the scheduler to be running
        mock_scheduler = MagicMock()
        mock_scheduler.running = True

        with patch("src.api.server._rate_limiter", mock_limiter):
            with patch("src.api.server._scheduler", mock_scheduler):
                with patch("src.api.server._schedule_config", {
                    "enabled": True,
                    "cron": "0 2 * * 1",
                    "description": "Weekly Monday 2AM",
                    "last_run": time.time(),
                    "next_run": "2026-06-22T02:00:00",
                    "total_runs": 3,
                }):
                    response = client.get("/health")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "ok"
        assert "version" in data
        assert "uptime_seconds" in data
        assert "scheduler" in data
        assert data["scheduler"]["enabled"] is True
        assert data["scheduler"]["total_runs"] == 3
