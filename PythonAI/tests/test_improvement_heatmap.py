"""
Tests for the /api/metrics/improvement-heatmap endpoint.
Tests endpoint response shape, data fields, and graceful fallbacks.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def client():
    """Create a TestClient. The lifespan will init capture engine, so each
    test must re-patch _capture_engine (and friends) directly."""
    from src.api.server import app

    with TestClient(app) as client:
        yield client


# We need a way to simulate capture engine data. We'll patch at the
# point the endpoint calls _capture_engine methods.


def _make_mock_engine(
    signals_by_type: dict[str, int] | None = None,
    signals_by_language: dict[str, int] | None = None,
    overall_rate: float = 50.0,
    total_sessions: int = 5,
    avg_edit_distance: float = 0.3,
    rates: list[dict[str, Any]] | None = None,
    training_runs: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Build a mock CaptureEngine that returns canned statistics."""
    engine = MagicMock()

    engine.get_statistics.return_value = {
        "signals_by_type": signals_by_type or {
            "accept": 10,
            "reject": 5,
            "edit": 3,
        },
        "signals_by_language": signals_by_language or {
            "python": 12,
            "typescript": 6,
        },
        "total_sessions": total_sessions,
        "overall_acceptance_rate": overall_rate,
        "avg_edit_distance": avg_edit_distance,
    }

    engine.get_acceptance_rate.return_value = (
        rates if rates is not None else [
            {
                "date": "2026-06-09",
                "acceptance_rate": overall_rate,
                "accepts": 10,
                "rejects": 5,
                "edits": 3,
                "total": 18,
            },
        ]
    )

    engine.get_training_runs.return_value = (
        training_runs if training_runs is not None else [
            {
                "run_id": "test-run-1",
                "timestamp": time.time() - 86400,
                "acceptance_delta": 0.05,
                "signals_used": 100,
                "model_name": "Qwen/Qwen2.5-Coder-7B-Instruct",
            },
        ]
    )

    return engine


# ── Tests ────────────────────────────────────────────────────────


class TestImprovementHeatmapEndpoint:
    """Test suite for GET /api/metrics/improvement-heatmap."""

    def test_returns_expected_structure_when_engine_available(self, client: TestClient):
        """Verify the endpoint returns all expected top-level keys."""
        engine = _make_mock_engine()
        with patch("src.api.server._capture_engine", engine):
            response = client.get("/api/metrics/improvement-heatmap")

        assert response.status_code == 200
        data = response.json()

        # Top-level keys
        assert "version" in data
        assert "timestamp" in data
        assert "languages" in data
        assert "patterns" in data
        assert "weekly_data" in data
        assert "slots" in data
        assert "language_weekly_trend" in data
        assert "training_runs" in data

        # Slots breakdown
        slots = data["slots"]
        assert "overall_delta" in slots
        assert "baseline_rate" in slots
        assert "current_rate" in slots
        assert "target_rate" in slots
        assert "heat_index" in slots
        assert "training_run_count" in slots
        assert "language_count" in slots
        assert "total_signals_used" in slots

        # Numeric types
        assert isinstance(data["version"], str)
        assert isinstance(data["timestamp"], float)
        assert isinstance(data["languages"], list)
        assert isinstance(data["patterns"], list)
        assert isinstance(data["weekly_data"], list)
        assert isinstance(data["training_runs"], list)

    def test_per_language_deltas_are_computed(self, client: TestClient):
        """Each language entry should have before/after rates and a delta."""
        engine = _make_mock_engine(
            signals_by_language={"python": 15, "typescript": 5},
            overall_rate=50.0,
        )
        with patch("src.api.server._capture_engine", engine):
            response = client.get("/api/metrics/improvement-heatmap")

        assert response.status_code == 200
        data = response.json()

        for lang in data["languages"]:
            assert "name" in lang
            assert "signal_count" in lang
            assert "rate_before" in lang
            assert "rate_after" in lang
            assert "delta" in lang
            assert lang["rate_before"] >= 0
            assert lang["rate_after"] >= 0

        # Python should be first (higher signal count)
        assert data["languages"][0]["name"] == "python"
        assert data["languages"][0]["signal_count"] == 15

    def test_signal_patterns_match_types(self, client: TestClient):
        """Pattern entries should reflect signal type distribution."""
        engine = _make_mock_engine(
            signals_by_type={"accept": 10, "reject": 5, "edit": 3},
        )
        with patch("src.api.server._capture_engine", engine):
            response = client.get("/api/metrics/improvement-heatmap")

        assert response.status_code == 200
        data = response.json()

        pattern_keys = {p["key"] for p in data["patterns"]}
        assert "accept" in pattern_keys
        assert "reject" in pattern_keys
        assert "edit" in pattern_keys

        # Accept should be first (highest count)
        assert data["patterns"][0]["key"] == "accept"
        assert data["patterns"][0]["count"] == 10

    def test_training_runs_are_mapped(self, client: TestClient):
        """Training runs should be transformed to include delta, signals, model."""
        runs = [
            {
                "run_id": "run-abc",
                "timestamp": time.time(),
                "acceptance_delta": 0.07,
                "signals_used": 200,
                "model_name": "Qwen/Qwen2.5-Coder-7B-Instruct",
            },
        ]
        engine = _make_mock_engine(training_runs=runs)
        with patch("src.api.server._capture_engine", engine):
            response = client.get("/api/metrics/improvement-heatmap")

        assert response.status_code == 200
        data = response.json()

        assert len(data["training_runs"]) == 1
        tr = data["training_runs"][0]
        assert tr["run_id"] == "run-abc"
        assert tr["delta"] == 7.0  # 0.07 * 100
        assert tr["signals_used"] == 200
        assert tr["model"] == "Qwen2.5-Coder-7B-Instruct"

    def test_weekly_data_maps_rates(self, client: TestClient):
        """Weekly data should include period, acceptance_rate, accepts, etc."""
        rates = [
            {"date": "2026-06-01", "acceptance_rate": 40.0, "accepts": 4, "rejects": 4, "edits": 2, "total": 10},
            {"date": "2026-06-08", "acceptance_rate": 55.0, "accepts": 6, "rejects": 3, "edits": 1, "total": 10},
        ]
        engine = _make_mock_engine(rates=rates)
        with patch("src.api.server._capture_engine", engine):
            response = client.get("/api/metrics/improvement-heatmap")

        assert response.status_code == 200
        data = response.json()

        assert len(data["weekly_data"]) == 2
        w1 = data["weekly_data"][0]
        assert w1["period"] == "Week 1"
        assert w1["acceptance_rate"] == 40.0
        assert w1["accepts"] == 4

        # overall_delta should be 15.0 (55 - 40)
        assert data["slots"]["overall_delta"] == 15.0

    def test_heat_index_is_computed(self, client: TestClient):
        """Heat index should be a composite score 0-100."""
        engine = _make_mock_engine()
        with patch("src.api.server._capture_engine", engine):
            response = client.get("/api/metrics/improvement-heatmap")

        assert response.status_code == 200
        data = response.json()

        hi = data["slots"]["heat_index"]
        assert isinstance(hi, (int, float))
        assert 0 <= hi <= 100

    def test_language_weekly_trend_is_generated(self, client: TestClient):
        """Each language should have a projected weekly trend."""
        engine = _make_mock_engine(
            signals_by_language={"python": 10, "typescript": 5},
            overall_rate=50.0,
        )
        with patch("src.api.server._capture_engine", engine):
            response = client.get("/api/metrics/improvement-heatmap")

        assert response.status_code == 200
        data = response.json()

        for lwt in data["language_weekly_trend"]:
            assert "language" in lwt
            assert "trend" in lwt
            assert lwt["language"] in ("python", "typescript")
            for point in lwt["trend"]:
                assert "week" in point
                assert "rate" in point

    def test_fallback_when_engine_unavailable(self, client: TestClient):
        """Should return empty/null data when capture engine is None."""
        with patch("src.api.server._capture_engine", None):
            response = client.get("/api/metrics/improvement-heatmap")

        assert response.status_code == 200
        data = response.json()

        assert data["languages"] == []
        assert data["patterns"] == []
        assert data["weekly_data"] == []
        assert data["training_runs"] == []
        assert data["slots"]["heat_index"] == 0.0
        assert data["slots"]["overall_delta"] == 0.0

    def test_fallback_when_engine_raises(self, client: TestClient):
        """Should gracefully handle exceptions from capture engine methods."""
        engine = MagicMock()
        engine.get_statistics.side_effect = RuntimeError("DB error")
        engine.get_acceptance_rate.side_effect = RuntimeError("DB error")
        engine.get_training_runs.side_effect = RuntimeError("DB error")

        with patch("src.api.server._capture_engine", engine):
            response = client.get("/api/metrics/improvement-heatmap")

        assert response.status_code == 200
        data = response.json()

        # Should fall back to empty defaults
        assert data["languages"] == []
        assert data["patterns"] == []
        assert data["weekly_data"] == []
        assert data["training_runs"] == []

    def test_single_language_no_training_runs(self, client: TestClient):
        """Should handle edge case of one language and zero training runs."""
        engine = _make_mock_engine(
            signals_by_language={"only_python": 5},
            signals_by_type={"accept": 3, "reject": 2},
            overall_rate=60.0,
            training_runs=[],
        )
        with patch("src.api.server._capture_engine", engine):
            response = client.get("/api/metrics/improvement-heatmap")

        assert response.status_code == 200
        data = response.json()

        assert len(data["languages"]) == 1
        assert data["languages"][0]["name"] == "only_python"
        assert data["slots"]["training_run_count"] == 0
        assert data["slots"]["language_count"] == 1
        assert data["training_runs"] == []

    def test_training_runs_multiple_deltas(self, client: TestClient):
        """Multiple training runs should compute an average delta."""
        now = time.time()
        runs = [
            {"run_id": "r1", "timestamp": now - 200, "acceptance_delta": 0.10, "signals_used": 100, "model_name": "test-model"},
            {"run_id": "r2", "timestamp": now - 100, "acceptance_delta": 0.04, "signals_used": 100, "model_name": "test-model"},
        ]
        engine = _make_mock_engine(training_runs=runs)
        with patch("src.api.server._capture_engine", engine):
            response = client.get("/api/metrics/improvement-heatmap")

        assert response.status_code == 200
        data = response.json()

        # avg_delta = (0.10 + 0.04) / 2 = 0.07
        # target_rate = 50.0 + 0.07 * 100 = 57.0
        assert data["slots"]["target_rate"] >= 55.0  # roughly 57.0
        assert data["slots"]["training_run_count"] == 2

    def test_response_includes_version_and_timestamp(self, client: TestClient):
        """The response should always include version and timestamp."""
        engine = _make_mock_engine()
        with patch("src.api.server._capture_engine", engine):
            response = client.get("/api/metrics/improvement-heatmap")

        assert response.status_code == 200
        data = response.json()

        assert isinstance(data["version"], str)
        assert data["version"] != ""
        assert isinstance(data["timestamp"], (int, float))
        assert data["timestamp"] > 0
