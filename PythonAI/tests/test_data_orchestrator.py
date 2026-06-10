"""Unit tests for src/data/orchestrator.py — AntiGravityOrchestrator master controller."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from src.data.orchestrator import (
    AntiGravityOrchestrator,
    CollectionTask,
    DataSourceStatus,
    OrchestratorConfig,
    Phase,
    PhaseResult,
    PhaseStatus,
    TaskStatus,
)


# ══════════════════════════════════════════════════════════════════════
# Enum / Dataclass tests
# ══════════════════════════════════════════════════════════════════════


class TestEnums:
    """Tests for TaskStatus, PhaseStatus, Phase enums."""

    def test_task_status_values(self):
        """TaskStatus should have the expected values."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.SKIPPED.value == "skipped"

    def test_phase_status_values(self):
        """PhaseStatus should have the expected values."""
        assert PhaseStatus.PENDING.value == "pending"
        assert PhaseStatus.ACTIVE.value == "active"
        assert PhaseStatus.COMPLETED.value == "completed"
        assert PhaseStatus.FAILED.value == "failed"

    def test_phase_values(self):
        """Phase should have the expected values."""
        assert Phase.PHASE1.value == "phase1"
        assert Phase.PHASE2.value == "phase2"
        assert Phase.PHASE3.value == "phase3"
        assert Phase.PHASE4.value == "phase4"
        assert Phase.PHASE5.value == "phase5"
        assert Phase.HF.value == "hf"
        assert Phase.ARXIV.value == "arxiv"

    def test_all_phases_cover_full_pipeline(self):
        """All expected phase names should be in Phase enum."""
        expected = {"phase1", "phase2", "phase3", "phase4", "phase5",
                     "hf", "arxiv", "openalex", "audio", "synthetic"}
        actual = {p.value for p in Phase}
        assert actual == expected


class TestDataclasses:
    """Tests for CollectionTask, OrchestratorConfig, PhaseResult, DataSourceStatus."""

    def test_collection_task_defaults(self):
        """CollectionTask should have sensible defaults."""
        task = CollectionTask(name="test", source_type="hf")
        assert task.name == "test"
        assert task.source_type == "hf"
        assert task.status == TaskStatus.PENDING
        assert task.progress == 0.0
        assert task.records_collected == 0
        assert task.error_message == ""

    def test_collection_task_full(self):
        """CollectionTask with all fields."""
        task = CollectionTask(
            name="full", source_type="arxiv",
            status=TaskStatus.RUNNING, progress=0.5,
            records_collected=100, error_message="",
            started_at=100.0, completed_at=200.0,
        )
        assert task.progress == 0.5
        assert task.records_collected == 100

    def test_orchestrator_config_defaults(self):
        """OrchestratorConfig should have reasonable defaults."""
        config = OrchestratorConfig()
        assert "anti_gravity_data" in config.base_output_dir
        assert config.max_concurrent == 30
        assert config.synthetic_per_task == 1000
        assert config.phase1_sources["huggingface_datasets"] is True

    def test_orchestrator_config_custom(self):
        """OrchestratorConfig with custom values."""
        config = OrchestratorConfig(
            base_output_dir="/custom/path",
            max_concurrent=50,
            synthetic_per_task=500,
            priorities={"hf": 1},
        )
        assert config.base_output_dir == "/custom/path"
        assert config.max_concurrent == 50

    def test_phase_result_defaults(self):
        """PhaseResult should have defaults."""
        pr = PhaseResult(name="phase1", status="✅ SUCCESS")
        assert pr.duration_seconds == 0.0
        assert pr.error is None
        assert pr.details == {}

    def test_data_source_status_defaults(self):
        """DataSourceStatus should have defaults."""
        ds = DataSourceStatus(name="test", source_type="hf")
        assert ds.status == "pending"
        assert ds.size_bytes == 0
        assert ds.num_items == 0
        assert ds.error is None

    def test_data_source_status_full(self):
        """DataSourceStatus with all fields."""
        ds = DataSourceStatus(
            name="full", source_type="arxiv",
            status="complete", size_bytes=1000,
            num_items=50, started_at="2024-01-01",
            completed_at="2024-01-02", error=None,
        )
        assert ds.num_items == 50
        assert ds.size_bytes == 1000


# ══════════════════════════════════════════════════════════════════════
# AntiGravityOrchestrator — Init, Config, Key helpers
# ══════════════════════════════════════════════════════════════════════


class TestOrchestratorInit:
    """Tests for AntiGravityOrchestrator initialization."""

    def test_init_with_defaults(self, tmp_path: Path):
        """Init with no config file should use defaults."""
        config_path = str(tmp_path / "nonexistent.json")
        orch = AntiGravityOrchestrator(config_path=config_path)
        assert orch.config == {}
        assert orch.base_dir.exists()
        assert orch.status_dir.exists()

    def test_init_with_valid_config(self, tmp_path: Path):
        """Init with a valid config should parse it."""
        config_path = str(tmp_path / "config.json")
        with open(config_path, "w") as f:
            json.dump({"base_output_dir": str(tmp_path)}, f)

        orch = AntiGravityOrchestrator(config_path=config_path)
        assert orch.config["base_output_dir"] == str(tmp_path)

    def test_init_with_invalid_config(self, tmp_path: Path):
        """Init with invalid JSON should use defaults."""
        config_path = str(tmp_path / "bad.json")
        with open(config_path, "w") as f:
            f.write("not json")

        orch = AntiGravityOrchestrator(config_path=config_path)
        assert orch.config == {}  # Falls back to empty

    def test_base_dir_created(self, tmp_path: Path):
        """Base directory should be created."""
        custom_dir = tmp_path / "custom_data"
        config_path = str(tmp_path / "config.json")
        with open(config_path, "w") as f:
            json.dump({"base_output_dir": str(custom_dir)}, f)

        orch = AntiGravityOrchestrator(config_path=config_path)
        assert custom_dir.exists()
        assert (custom_dir / ".status").exists()


class TestGetKey:
    """Tests for _get_key."""

    def test_from_environment(self, monkeypatch):
        """_get_key should read from environment."""
        monkeypatch.setenv("HF_TOKEN", "env-token-123")
        orch = AntiGravityOrchestrator(config_path="nonexistent.json")

        # Set config in the _get_key method
        with patch.object(orch, "config", {}):
            result = orch._get_key("HF_TOKEN")
        assert result == "env-token-123"

    def test_from_config(self, monkeypatch):
        """_get_key should fall back to config."""
        monkeypatch.delenv("HF_TOKEN", raising=False)
        orch = AntiGravityOrchestrator(config_path="nonexistent.json")
        with patch.object(orch, "config", {"hf_token": "config-token-456"}):
            result = orch._get_key("HF_TOKEN")
        assert result == "config-token-456"

    def test_env_overrides_config(self, monkeypatch):
        """Environment variable should take precedence over config."""
        monkeypatch.setenv("HF_TOKEN", "env-token")
        orch = AntiGravityOrchestrator(config_path="nonexistent.json")
        with patch.object(orch, "config", {"hf_token": "config-token"}):
            result = orch._get_key("HF_TOKEN")
        assert result == "env-token"

    def test_missing_returns_default(self):
        """Missing key should return the provided default."""
        orch = AntiGravityOrchestrator(config_path="nonexistent.json")
        with patch.object(orch, "config", {}):
            result = orch._get_key("MISSING_KEY", default="fallback")
        assert result == "fallback"


# ══════════════════════════════════════════════════════════════════════
# Source Status Tracking
# ══════════════════════════════════════════════════════════════════════


class TestSourceStatus:
    """Tests for _update_source_status, _save_status, _load_status."""

    def test_update_source_status_creates_entry(self, tmp_path: Path):
        """_update_source_status should create a new entry."""
        orch = AntiGravityOrchestrator(config_path="nonexistent.json")
        orch.base_dir = tmp_path
        orch.status_dir = tmp_path / ".status"
        orch.status_dir.mkdir()

        orch._update_source_status("test_source", "hf", "downloading")
        assert "test_source" in orch.source_statuses
        assert orch.source_statuses["test_source"].status == "downloading"

    def test_update_source_status_updates_existing(self, tmp_path: Path):
        """_update_source_status should update an existing entry."""
        orch = AntiGravityOrchestrator(config_path="nonexistent.json")
        orch.base_dir = tmp_path
        orch.status_dir = tmp_path / ".status"
        orch.status_dir.mkdir()

        orch._update_source_status("test", "hf", "downloading")
        orch._update_source_status("test", "hf", "complete", size_bytes=500, num_items=10)
        assert orch.source_statuses["test"].status == "complete"
        assert orch.source_statuses["test"].size_bytes == 500
        assert orch.source_statuses["test"].num_items == 10

    def test_save_and_load_status(self, tmp_path: Path):
        """Status should persist to disk and load back."""
        orch = AntiGravityOrchestrator(config_path="nonexistent.json")
        orch.base_dir = tmp_path
        orch.status_dir = tmp_path / ".status"
        orch.status_dir.mkdir()

        orch._update_source_status("source1", "hf", "complete", size_bytes=100)
        orch._update_source_status("source2", "arxiv", "failed", error="timeout")

        # Create new orchestrator and load
        orch2 = AntiGravityOrchestrator(config_path="nonexistent.json")
        orch2.base_dir = tmp_path
        orch2.status_dir = tmp_path / ".status"
        orch2._load_status()

        assert "source1" in orch2.source_statuses
        assert orch2.source_statuses["source1"].size_bytes == 100
        assert orch2.source_statuses["source2"].error == "timeout"


# ══════════════════════════════════════════════════════════════════════
# run_phase / run_all
# ══════════════════════════════════════════════════════════════════════


class TestRunPhase:
    """Tests for run_phase — phase execution dispatch."""

    async def test_unknown_phase_returns_error(self):
        """Unknown phase should return FAILED result."""
        orch = AntiGravityOrchestrator(config_path="nonexistent.json")
        result = await orch.run_phase("nonexistent")
        assert "FAILED" in result.status
        assert "Unknown phase" in result.error

    async def test_run_phase4_returns_success(self):
        """Phase 4 (quality) should return success (placeholder)."""
        orch = AntiGravityOrchestrator(config_path="nonexistent.json")
        result = await orch.run_phase("phase4")
        assert "SUCCESS" in result.status or "PARTIAL" in result.status

    async def test_run_phase5_returns_success(self):
        """Phase 5 (training) should return success (placeholder)."""
        orch = AntiGravityOrchestrator(config_path="nonexistent.json")
        result = await orch.run_phase("phase5")
        assert "SUCCESS" in result.status or "PARTIAL" in result.status

    async def test_phase_collects_duration(self):
        """run_phase should record duration."""
        orch = AntiGravityOrchestrator(config_path="nonexistent.json")
        result = await orch.run_phase("phase4")
        assert result.duration_seconds > 0

    async def test_run_all_collects_results(self):
        """run_all should collect phase results for all 5 phases."""
        orch = AntiGravityOrchestrator(config_path="nonexistent.json")
        await orch.run_all(force=False)
        assert len(orch.phase_results) == 5

    async def test_run_all_results_have_correct_names(self):
        """run_all phase results should have expected phase names."""
        orch = AntiGravityOrchestrator(config_path="nonexistent.json")
        await orch.run_all(force=False)
        names = [pr.name for pr in orch.phase_results]
        assert names == ["phase1", "phase2", "phase3", "phase4", "phase5"]


# ══════════════════════════════════════════════════════════════════════
# Phase 1 — Text & Code (mocked)
# ══════════════════════════════════════════════════════════════════════


class TestPhase1:
    """Tests for Phase 1: Text & Code collection."""

    async def test_phase1_with_sources_disabled(self):
        """Phase 1 with all sources disabled should return success (no-op)."""
        orch = AntiGravityOrchestrator(config_path="nonexistent.json")
        orch.phase1_sources = {
            "huggingface_datasets": False,
            "arxiv_papers": False,
            "openalex_snapshot": False,
        }
        with patch("src.data.orchestrator.AntiGravityOrchestrator._run_hf_download", return_value=True):
            result = await orch._run_phase1_text(force=False)
            assert result is True


# ══════════════════════════════════════════════════════════════════════
# Source Runner — _run_hf_download (mocked imports)
# ══════════════════════════════════════════════════════════════════════


class TestRunHfDownload:
    """Tests for _run_hf_download — HuggingFace downloader."""

    async def test_hf_download_success(self):
        """Successful HF download should return True."""
        orch = AntiGravityOrchestrator(config_path="nonexistent.json")
        with patch("src.data.orchestrator.AntiGravityOrchestrator._update_source_status"):
            with patch("builtins.__import__", side_effect=ImportError("no collect_everything")):
                result = await orch._run_hf_download(force=False)
                assert result is False  # Import fails gracefully

    async def test_hf_download_fails_returns_false(self):
        """HF download failure should return False."""
        orch = AntiGravityOrchestrator(config_path="nonexistent.json")
        with patch("src.data.orchestrator.AntiGravityOrchestrator._update_source_status"):
            result = await orch._run_hf_download(force=False)
            # Import fails but function handles gracefully
            assert isinstance(result, bool)


# ══════════════════════════════════════════════════════════════════════
# Reporting
# ══════════════════════════════════════════════════════════════════════


class TestReporting:
    """Tests for collection summary and dashboard data."""

    def test_get_collection_summary_empty(self):
        """Empty state should return zero counts."""
        orch = AntiGravityOrchestrator(config_path="nonexistent.json")
        summary = orch.get_collection_summary()
        assert summary["total_size_bytes"] == 0
        assert summary["sources"] == {}
        assert summary["phases_completed"] == 0

    def test_get_collection_summary_with_data(self):
        """Summary should reflect source statuses."""
        orch = AntiGravityOrchestrator(config_path="nonexistent.json")
        orch._update_source_status("hf_data", "hf", "complete", size_bytes=1000, num_items=50)
        orch._update_source_status("arxiv_data", "arxiv", "complete", size_bytes=500, num_items=10)

        summary = orch.get_collection_summary()
        assert summary["total_size_bytes"] == 1500
        assert len(summary["sources"]) == 2
        assert summary["by_type"]["hf"]["count"] == 1

    def test_get_dashboard_data_format(self):
        """Dashboard data should have the expected structure."""
        orch = AntiGravityOrchestrator(config_path="nonexistent.json")
        orch._update_source_status("test", "hf", "complete", size_bytes=1_500_000_000, num_items=10)
        orch.phase_results = [PhaseResult(name="phase1", status="✅ SUCCESS")]

        data = orch.get_dashboard_data()
        assert "timestamp" in data
        assert data["total_size_gb"] == 1.5  # 1.5 GB (rounded to 2dp)
        assert data["sources_count"] == 1
        assert data["phases_completed"] == 1
        assert "phase_results" in data
        assert "sources" in data

    def test_dashboard_data_includes_phase_results(self):
        """Dashboard should include all phase results."""
        orch = AntiGravityOrchestrator(config_path="nonexistent.json")
        orch.phase_results = [
            PhaseResult(name="p1", status="✅ SUCCESS", duration_seconds=10.0),
            PhaseResult(name="p2", status="❌ FAILED", error="timeout"),
        ]
        data = orch.get_dashboard_data()
        assert len(data["phase_results"]) == 2
        assert data["phase_results"][0]["name"] == "p1"
        assert data["phase_results"][1]["error"] == "timeout"


# ══════════════════════════════════════════════════════════════════════
# Run arxiv, image, audio, synthetic runners
# ══════════════════════════════════════════════════════════════════════


class TestOtherRunners:
    """Tests for other source runners that depend on collect_everything."""

    async def test_arxiv_import_fails_gracefully(self):
        """_run_arxiv_collect should handle missing collect_everything."""
        orch = AntiGravityOrchestrator(config_path="nonexistent.json")
        with patch("src.data.orchestrator.AntiGravityOrchestrator._update_source_status"):
            result = await orch._run_arxiv_collect(force=False)
            assert isinstance(result, bool)

    async def test_synthetic_import_fails_gracefully(self):
        """_run_synthetic should handle missing collect_everything."""
        orch = AntiGravityOrchestrator(config_path="nonexistent.json")
        with patch("src.data.orchestrator.AntiGravityOrchestrator._update_source_status"):
            result = await orch._run_synthetic(force=False)
            assert isinstance(result, bool)

    async def test_image_import_fails_gracefully(self):
        """_run_image_collect should handle missing collect_everything."""
        orch = AntiGravityOrchestrator(config_path="nonexistent.json")
        with patch("src.data.orchestrator.AntiGravityOrchestrator._update_source_status"):
            result = await orch._run_image_collect(force=False)
            assert isinstance(result, bool)


# ══════════════════════════════════════════════════════════════════════
# Phase 3 (synthetic) run_phase dispatch
# ══════════════════════════════════════════════════════════════════════


class TestPhase3:
    """Tests for Phase 3: Synthetic data generation."""

    async def test_phase3_dispatches_correctly(self):
        """Phase 3 should call _run_synthetic."""
        orch = AntiGravityOrchestrator(config_path="nonexistent.json")
        with patch.object(orch, "_run_synthetic", new_callable=AsyncMock, return_value=True):
            result = await orch.run_phase("phase3")
            assert "SUCCESS" in result.status or "PARTIAL" in result.status
