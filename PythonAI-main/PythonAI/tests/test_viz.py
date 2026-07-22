"""Tests for the training visualization module (src/training/viz.py).

Covers TrainingMetrics, smoothing, plotting (mocked), JSON/HTML export,
and the EnhancedTrainingCurvesCallback integration with trainer.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _make_metrics(**overrides: Any):
    """Create a TrainingMetrics instance with some default data for testing."""
    from src.training.viz import TrainingMetrics

    metrics = TrainingMetrics()
    defaults: dict[str, Any] = {
        "train_steps": [0, 1, 2, 3, 4],
        "train_losses": [2.0, 1.5, 1.2, 1.0, 0.9],
        "eval_steps": [0, 2, 4],
        "eval_losses": [2.1, 1.6, 1.3],
        "lr_steps": [0, 1, 2, 3, 4],
        "learning_rates": [5e-5, 4e-5, 3e-5, 2e-5, 1e-5],
        "throughput_steps": [0, 1, 2, 3, 4],
        "tokens_per_second": [100.0, 110.0, 120.0, 115.0, 125.0],
        "total_train_examples": 100,
        "total_eval_examples": 10,
        "max_length": 512,
        "batch_size": 1,
        "grad_accum": 4,
        "base_model": "sshleifer/tiny-gpt2",
        "dataset_version": "v1",
        "early_stopping_patience": 5,
        "lr_scheduler_type": "cosine",
    }
    for k, v in overrides.items():
        defaults[k] = v
    for k, v in defaults.items():
        setattr(metrics, k, v)
    return metrics


# ──────────────────────────────────────────────────────────────────────
# TrainingMetrics
# ──────────────────────────────────────────────────────────────────────


class TestTrainingMetrics:
    def test_record_functions(self):
        from src.training.viz import TrainingMetrics

        m = TrainingMetrics()
        m.record_train_loss(1, 2.0)
        m.record_eval_loss(2, 1.5)
        m.record_lr(1, 1e-4)
        m.record_throughput(1, 200.0)

        assert m.train_steps == [1]
        assert m.train_losses == [2.0]
        assert m.eval_steps == [2]
        assert m.eval_losses == [1.5]
        assert m.lr_steps == [1]
        assert m.learning_rates == [1e-4]
        assert m.throughput_steps == [1]
        assert m.tokens_per_second == [200.0]

    def test_to_dict_structure(self):
        m = _make_metrics()
        d = m.to_dict()

        assert "train" in d
        assert "eval" in d
        assert "learning_rate" in d
        assert "throughput" in d
        assert "metadata" in d

        assert d["train"]["steps"] == m.train_steps
        assert d["eval"]["steps"] == m.eval_steps
        assert d["metadata"]["base_model"] == m.base_model
        assert d["metadata"]["lr_scheduler_type"] == "cosine"
        # Losses should be rounded to 6 decimal places
        assert all(isinstance(v, float) for v in d["train"]["losses"])

    def test_empty_metrics(self):
        from src.training.viz import TrainingMetrics

        m = TrainingMetrics()
        d = m.to_dict()
        assert d["train"]["steps"] == []
        assert d["train"]["losses"] == []
        assert d["metadata"]["total_train_examples"] == 0


# ──────────────────────────────────────────────────────────────────────
# smooth_curve
# ──────────────────────────────────────────────────────────────────────


class TestSmoothCurve:
    def test_smoothes_values(self):
        from src.training.viz import smooth_curve

        raw = [2.0, 1.5, 1.2, 1.0, 0.9]
        smoothed = smooth_curve(raw, alpha=0.4)
        assert len(smoothed) == len(raw)
        # Smoothed values should be closer to each other than raw
        raw_range = max(raw) - min(raw)
        smooth_range = max(smoothed) - min(smoothed)
        assert smooth_range <= raw_range

    def test_alpha_zero_no_smoothing(self):
        from src.training.viz import smooth_curve

        raw = [2.0, 1.5, 1.2]
        # With alpha=0, no smoothing is applied
        smoothed = smooth_curve(raw, alpha=0.0)
        assert smoothed == raw

    def test_empty_input(self):
        from src.training.viz import smooth_curve

        assert smooth_curve([], alpha=0.4) == []

    def test_single_value(self):
        from src.training.viz import smooth_curve

        assert smooth_curve([1.0], alpha=0.4) == [1.0]


# ──────────────────────────────────────────────────────────────────────
# JSON Export
# ──────────────────────────────────────────────────────────────────────


class TestExportMetricsJson:
    def test_exports_valid_json(self):
        from src.training.viz import export_metrics_json

        m = _make_metrics()
        with tempfile.TemporaryDirectory() as td:
            path = export_metrics_json(m, Path(td) / "metrics.json")
            assert Path(path).exists()
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            assert data["metadata"]["base_model"] == "sshleifer/tiny-gpt2"
            assert len(data["train"]["steps"]) == 5

    def test_overwrites_existing_file(self):
        from src.training.viz import export_metrics_json

        m = _make_metrics()
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "metrics.json"
            fp.write_text("{}", encoding="utf-8")
            path = export_metrics_json(m, fp)
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            assert "train" in data


# ──────────────────────────────────────────────────────────────────────
# HTML Export
# ──────────────────────────────────────────────────────────────────────


class TestExportHtmlDashboard:
    def test_exports_valid_html(self):
        from src.training.viz import export_html_dashboard

        m = _make_metrics()
        with tempfile.TemporaryDirectory() as td:
            path = export_html_dashboard(m, Path(td) / "dashboard.html")
            content = Path(path).read_text(encoding="utf-8")
            assert "<!DOCTYPE html>" in content
            assert "PythonAI" in content
            assert "sshleifer/tiny-gpt2" in content
            assert "Training Dashboard" in content

    def test_empty_metrics_html(self):
        from src.training.viz import TrainingMetrics, export_html_dashboard

        m = TrainingMetrics()
        with tempfile.TemporaryDirectory() as td:
            path = export_html_dashboard(m, Path(td) / "dashboard.html")
            content = Path(path).read_text(encoding="utf-8")
            assert "<!DOCTYPE html>" in content
            assert "No data" in content or "—" in content


# ──────────────────────────────────────────────────────────────────────
# load_metrics_from_json
# ──────────────────────────────────────────────────────────────────────


class TestLoadMetricsFromJson:
    def test_roundtrip(self):
        from src.training.viz import load_metrics_from_json

        m1 = _make_metrics()
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "metrics.json"
            import src.training.viz as viz

            viz.export_metrics_json(m1, fp)
            m2 = load_metrics_from_json(fp)

            assert m2.train_steps == m1.train_steps
            assert m2.train_losses == m1.train_losses
            assert m2.base_model == m1.base_model
            assert m2.lr_scheduler_type == m1.lr_scheduler_type

    def test_partial_data(self):
        from src.training.viz import TrainingMetrics, export_metrics_json, load_metrics_from_json

        m1 = TrainingMetrics()
        m1.base_model = "test-model"
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "metrics.json"
            export_metrics_json(m1, fp)
            m2 = load_metrics_from_json(fp)
            assert m2.base_model == "test-model"
            assert m2.train_steps == []


# ──────────────────────────────────────────────────────────────────────
# Plotting functions (skipped if matplotlib not available)
# ──────────────────────────────────────────────────────────────────────


_MATPLOTLIB_AVAILABLE: bool = False
try:
    import matplotlib  # noqa: F401

    _MATPLOTLIB_AVAILABLE = True
except ImportError:
    pass


class TestPlotFunctions:
    def test_plot_loss_curves_with_enough_data(self):
        if not _MATPLOTLIB_AVAILABLE:
            pytest.skip("matplotlib not installed")
        from src.training.viz import plot_loss_curves

        m = _make_metrics()
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "loss.png"
            result = plot_loss_curves(m, fp)
            assert Path(result).exists()
            # PNG should have actual content
            assert Path(result).stat().st_size > 100

    def test_plot_loss_curves_insufficient_data(self):
        if not _MATPLOTLIB_AVAILABLE:
            pytest.skip("matplotlib not installed")
        from src.training.viz import TrainingMetrics, plot_loss_curves

        m = TrainingMetrics()
        m.train_steps = [0]
        m.train_losses = [1.0]

        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "loss.png"
            result = plot_loss_curves(m, fp)
            assert Path(result).exists()

    def test_plot_lr_schedule(self):
        if not _MATPLOTLIB_AVAILABLE:
            pytest.skip("matplotlib not installed")
        from src.training.viz import plot_lr_schedule

        m = _make_metrics()
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "lr.png"
            result = plot_lr_schedule(m, fp)
            assert Path(result).exists()
            assert Path(result).stat().st_size > 100

    def test_plot_lr_schedule_insufficient_data(self):
        if not _MATPLOTLIB_AVAILABLE:
            pytest.skip("matplotlib not installed")
        from src.training.viz import TrainingMetrics, plot_lr_schedule

        m = TrainingMetrics()
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "lr.png"
            result = plot_lr_schedule(m, fp)
            assert Path(result).exists()

    def test_plot_throughput(self):
        if not _MATPLOTLIB_AVAILABLE:
            pytest.skip("matplotlib not installed")
        from src.training.viz import plot_throughput

        m = _make_metrics()
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "throughput.png"
            result = plot_throughput(m, fp)
            assert Path(result).exists()
            assert Path(result).stat().st_size > 100

    def test_plot_throughput_insufficient_data(self):
        if not _MATPLOTLIB_AVAILABLE:
            pytest.skip("matplotlib not installed")
        from src.training.viz import TrainingMetrics, plot_throughput

        m = TrainingMetrics()
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "throughput.png"
            result = plot_throughput(m, fp)
            assert Path(result).exists()

    def test_plot_dashboard(self):
        if not _MATPLOTLIB_AVAILABLE:
            pytest.skip("matplotlib not installed")
        from src.training.viz import plot_dashboard

        m = _make_metrics()
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "dashboard.png"
            result = plot_dashboard(m, fp)
            assert Path(result).exists()
            assert Path(result).stat().st_size > 100

    def test_render_all_with_matplotlib(self):
        if not _MATPLOTLIB_AVAILABLE:
            pytest.skip("matplotlib not installed")
        from src.training.viz import render_all

        m = _make_metrics()
        with tempfile.TemporaryDirectory() as td:
            results = render_all(m, td, render_html=True)
            for key in ["loss_curves", "lr_schedule", "throughput", "dashboard", "metrics_json", "html_dashboard"]:
                assert key in results, f"Missing key: {key}"
                assert Path(results[key]).exists(), f"File missing: {results[key]}"


# ──────────────────────────────────────────────────────────────────────
# render_all
# ──────────────────────────────────────────────────────────────────────


class TestRenderAll:
    def test_generates_all_files_with_matplotlib(self):
        if not _MATPLOTLIB_AVAILABLE:
            pytest.skip("matplotlib not installed")
        from src.training.viz import render_all

        m = _make_metrics()
        with tempfile.TemporaryDirectory() as td:
            results = render_all(m, td, render_html=True)
            for key in ["loss_curves", "lr_schedule", "throughput", "dashboard", "metrics_json", "html_dashboard"]:
                assert key in results, f"Missing key: {key}"
                assert Path(results[key]).exists(), f"File missing: {results[key]}"

    def test_generates_all_files_without_matplotlib(self):
        from src.training.viz import render_all

        m = _make_metrics()
        with tempfile.TemporaryDirectory() as td:
            results = render_all(m, td, render_html=True)
            # Without matplotlib, only JSON and HTML should succeed
            assert "metrics_json" in results
            assert "html_dashboard" in results

    def test_skip_html(self):
        from src.training.viz import render_all

        m = _make_metrics()
        with tempfile.TemporaryDirectory() as td:
            results = render_all(m, td, render_html=False)
            assert "html_dashboard" not in results
            assert "metrics_json" in results

    def test_empty_metrics_does_not_crash(self):
        from src.training.viz import TrainingMetrics, render_all

        m = TrainingMetrics()
        with tempfile.TemporaryDirectory() as td:
            results = render_all(m, td)
            # Should gracefully handle missing data
            assert isinstance(results, dict)


# ──────────────────────────────────────────────────────────────────────
# EnhancedTrainingCurvesCallback integration
# ──────────────────────────────────────────────────────────────────────


class TestEnhancedTrainingCurvesCallback:
    def test_collects_metrics(self):
        from src.training.trainer import EnhancedTrainingCurvesCallback

        cb = EnhancedTrainingCurvesCallback(output_dir=".")

        class FakeArgs:
            per_device_train_batch_size = 2
            gradient_accumulation_steps = 4
            max_length = 256
            base_model = "test-model"

        class FakeState:
            global_step = 0
            num_train_examples = 50
            num_eval_examples = 10

        # First call initializes metadata
        cb.on_log(FakeArgs(), FakeState(), None, logs={"loss": 2.0})

        # Second call records metrics
        FakeState.global_step = 1
        cb.on_log(FakeArgs(), FakeState(), None, logs={"loss": 1.5, "learning_rate": 3e-5})

        assert cb.metrics.train_steps == [0, 1]
        assert cb.metrics.train_losses == [2.0, 1.5]
        assert len(cb.metrics.learning_rates) == 1  # only logged in second call
        assert cb.metrics.base_model == "test-model"
        assert cb.metrics.total_train_examples == 50

    def test_collects_eval_loss(self):
        from src.training.trainer import EnhancedTrainingCurvesCallback

        cb = EnhancedTrainingCurvesCallback(output_dir=".")

        class FakeArgs:
            per_device_train_batch_size = 1
            gradient_accumulation_steps = 1
            max_length = 128
            base_model = ""

        class FakeState:
            global_step = 0
            num_train_examples = 0
            num_eval_examples = 0

        cb.on_log(FakeArgs(), FakeState(), None, logs={"eval_loss": 2.0})
        FakeState.global_step = 1
        cb.on_log(FakeArgs(), FakeState(), None, logs={"eval_loss": 1.5})

        assert cb.metrics.eval_steps == [0, 1]
        assert cb.metrics.eval_losses == [2.0, 1.5]

    def test_finalize_saves_files(self):
        from src.training.trainer import EnhancedTrainingCurvesCallback

        with tempfile.TemporaryDirectory() as td:
            cb = EnhancedTrainingCurvesCallback(output_dir=td)

            class FakeArgs:
                per_device_train_batch_size = 1
                gradient_accumulation_steps = 1
                max_length = 128
                base_model = ""
                max_examples = 50

            class FakeState:
                global_step = 0
                num_train_examples = 0
                num_eval_examples = 0

            # Add some data
            for step in range(5):
                FakeState.global_step = step
                cb.on_log(FakeArgs(), FakeState(), None, logs={"loss": 2.0 - step * 0.2})

            cb.finalize(FakeArgs())
            # Check that files were created in temp dir
            files = list(Path(td).iterdir())
            assert len(files) > 0
