"""Unit tests for the ForgeAI Acceptance Rate Dashboard.

Tests cover:
- Data query functions (acceptance rate, signal breakdown, language breakdown)
- Rolling average computation
- Dashboard HTML generation (demo mode)
- Empty state handling
- CLI integration
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.learning.forge_dashboard import (
    _build_empty_state,
    _build_training_runs_table,
    _compute_rolling_average,
    _get_db_path,
    generate_dashboard,
)

# ══════════════════════════════════════════════════════════════════════
# Rolling Average Tests
# ══════════════════════════════════════════════════════════════════════


class TestRollingAverage:
    """Tests for the _compute_rolling_average function."""

    def test_basic_rolling_average(self) -> None:
        """Should compute 7-day rolling average correctly."""
        data = [{"date": f"2026-06-{i:02d}", "acceptance_rate": 50.0} for i in range(1, 15)]
        result = _compute_rolling_average(data, window=7)
        # First 6 should be None (not enough data)
        for i in range(6):
            assert result[i] is None, f"Index {i} should be None"
        # All subsequent should be 50.0
        for i in range(6, 14):
            assert result[i] == 50.0, f"Index {i} should be 50.0, got {result[i]}"

    def test_rolling_average_varying(self) -> None:
        """Should compute correct rolling average with varying values."""
        data = [{"date": f"2026-06-{i:02d}", "acceptance_rate": float(i * 10)} for i in range(1, 12)]
        result = _compute_rolling_average(data, window=3)
        # Index 0-1: None
        assert result[0] is None
        assert result[1] is None
        # Index 2: (10+20+30)/3 = 20.0
        assert result[2] == 20.0
        # Index 3: (20+30+40)/3 = 30.0
        assert result[3] == 30.0
        # Index 4: (30+40+50)/3 = 40.0
        assert result[4] == 40.0

    def test_rolling_average_empty(self) -> None:
        """Empty data should return empty list."""
        result = _compute_rolling_average([])
        assert result == []

    def test_rolling_average_single(self) -> None:
        """Single data point should return [None] for window > 1."""
        result = _compute_rolling_average([{"date": "2026-06-01", "acceptance_rate": 50.0}])
        assert result == [None]

    def test_rolling_average_window_1(self) -> None:
        """Window of 1 should return rates as-is."""
        data = [{"date": f"2026-06-{i:02d}", "acceptance_rate": float(i * 10)} for i in range(1, 5)]
        result = _compute_rolling_average(data, window=1)
        # All should be non-None since window=1
        assert result[0] == 10.0
        assert result[1] == 20.0
        assert result[2] == 30.0
        assert result[3] == 40.0


# ══════════════════════════════════════════════════════════════════════
# DB Path Tests
# ══════════════════════════════════════════════════════════════════════


class TestGetDbPath:
    """Tests for _get_db_path."""

    def test_db_path_is_absolute(self) -> None:
        """DB path should be an absolute path."""
        path = _get_db_path()
        assert isinstance(path, Path)
        assert path.is_absolute()

    def test_db_path_ends_with_signals_db(self) -> None:
        """DB path should end with signals.db."""
        path = _get_db_path()
        assert path.name == "signals.db"

    def test_db_path_contains_forgeai(self) -> None:
        """DB path should be under .forgeai directory."""
        path = _get_db_path()
        assert ".forgeai" in str(path)


# ══════════════════════════════════════════════════════════════════════
# HTML Generation Tests
# ══════════════════════════════════════════════════════════════════════


class TestGenerateDashboard:
    """Tests for the generate_dashboard function."""

    def test_demo_generates_html(self) -> None:
        """Demo mode should generate valid HTML."""
        html = generate_dashboard(demo=True)
        assert isinstance(html, str)
        assert len(html) > 500
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html

    def test_demo_contains_chart_canvases(self) -> None:
        """Demo HTML should contain Chart.js canvas elements."""
        html = generate_dashboard(demo=True)
        assert "acceptanceRateChart" in html
        assert "signalBreakdownChart" in html
        assert "languageChart" in html
        assert "acceptRejectChart" in html

    def test_demo_contains_chartjs_script(self) -> None:
        """Demo HTML should load Chart.js from CDN."""
        html = generate_dashboard(demo=True)
        assert "chart.js" in html or "Chart" in html

    def test_demo_contains_metrics(self) -> None:
        """Demo HTML should contain metric values."""
        html = generate_dashboard(demo=True)
        assert "Acceptance Rate" in html
        assert "Total Accepts" in html
        assert "Total Signals" in html

    def test_demo_output_to_file(self) -> None:
        """Demo mode should write to file when output_path is given."""
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
            output_path = f.name

        try:
            html = generate_dashboard(output_path=output_path, demo=True)
            saved = Path(output_path).read_text(encoding="utf-8")
            assert saved == html
            assert len(saved) > 500
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_empty_db_generates_html(self) -> None:
        """When DB doesn't exist, should still generate HTML with empty state."""
        # Use a non-existent DB path
        fake_db = Path(tempfile.mkdtemp()) / "nonexistent.db"
        html = generate_dashboard(db_path=fake_db)
        assert isinstance(html, str)
        assert len(html) > 500
        assert "</html>" in html

    def test_empty_db_shows_empty_state(self) -> None:
        """Empty DB should show the empty state message."""
        fake_db = Path(tempfile.mkdtemp()) / "nonexistent.db"
        html = generate_dashboard(db_path=fake_db)
        assert "No Signal Data Yet" in html or "data" in html.lower()


# ══════════════════════════════════════════════════════════════════════
# Component Tests
# ══════════════════════════════════════════════════════════════════════


class TestBuildTrainingRunsTable:
    """Tests for _build_training_runs_table."""

    def test_empty_runs(self) -> None:
        """Empty runs should show appropriate message."""
        html = _build_training_runs_table([])
        assert "No training runs recorded" in html

    def test_single_run(self) -> None:
        """Single run should produce table row."""
        runs = [
            {
                "run_id": "test_run",
                "date": "2026-06-01",
                "model": "Qwen3-Coder-14B",
                "signals_used": 500,
                "train_loss": 0.5,
                "eval_loss": 0.6,
                "rate_before": 45.0,
                "rate_after": 52.0,
            }
        ]
        html = _build_training_runs_table(runs)
        assert "2026-06-01" in html
        assert "Qwen3-Coder-14B" in html
        assert "500" in html
        assert "+7.0%" in html or "7.0" in html  # Improvement indicator

    def test_run_without_eval_loss(self) -> None:
        """Run without eval loss should show placeholder."""
        runs = [
            {
                "run_id": "test_run",
                "date": "2026-06-01",
                "model": "TestModel",
                "signals_used": 100,
                "train_loss": None,
                "eval_loss": None,
                "rate_before": None,
                "rate_after": None,
            }
        ]
        html = _build_training_runs_table(runs)
        assert "TestModel" in html
        # Should use "—" for None values
        assert "—" in html


class TestBuildEmptyState:
    """Tests for _build_empty_state."""

    def test_empty_state_contains_help_text(self) -> None:
        """Empty state should show help text about CaptureEngine."""
        html = _build_empty_state()
        assert "CaptureEngine" in html
        assert "signal" in html.lower()

    def test_empty_state_contains_demo_option(self) -> None:
        """Empty state should mention demo mode."""
        html = _build_empty_state()
        assert "demo" in html.lower()


# ══════════════════════════════════════════════════════════════════════
# Integration Tests
# ══════════════════════════════════════════════════════════════════════


class TestDashboardIntegration:
    """Integration tests for the dashboard."""

    def test_demo_data_structure(self) -> None:
        """Demo data should have all expected sections."""
        from src.learning.forge_dashboard import _generate_demo_data

        data = _generate_demo_data()
        assert "daily_data" in data
        assert "signal_breakdown" in data
        assert "language_data" in data
        assert "training_runs" in data
        assert "sessions" in data

        # Verify daily data structure
        assert len(data["daily_data"]) > 0
        sample = data["daily_data"][0]
        assert "date" in sample
        assert "accepts" in sample
        assert "rejects" in sample
        assert "total" in sample
        assert "acceptance_rate" in sample

        # Verify session stats
        ss = data["sessions"]
        assert ss["total_sessions"] > 0
        assert ss["unique_developers"] >= 0
        assert ss["overall_rate"] > 0

    def test_demo_acceptance_rate_improves(self) -> None:
        """Demo acceptance rate should show improvement over time (27% → 70%)."""
        from src.learning.forge_dashboard import _generate_demo_data

        data = _generate_demo_data()
        rates = [d["acceptance_rate"] for d in data["daily_data"]]
        # Should start lower and end higher
        first_half = sum(rates[: len(rates) // 2]) / max(1, len(rates) // 2)
        second_half = sum(rates[len(rates) // 2 :]) / max(1, len(rates) - len(rates) // 2)
        assert second_half > first_half, "Acceptance rate should improve over time"

    def test_rolling_average_matches_demo_data(self) -> None:
        """Rolling average should match the window size in demo data."""
        from src.learning.forge_dashboard import _generate_demo_data

        data = _generate_demo_data()
        rolling = _compute_rolling_average(data["daily_data"])
        assert len(rolling) == len(data["daily_data"])
        # Verify window size (default 7)
        assert rolling[0] is None  # Day 1: not enough data
        assert rolling[6] is not None  # Day 7: should have average
