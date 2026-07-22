"""
Full End-to-End Integration Test
=================================
Exercises the complete ForgeAI backend pipeline:

  1. Server health check          — GET /health
  2. Event capture (HTTP API)     — POST /api/events (accept, reject, edit, pr_merge)
  3. Capture statistics           — GET /stats
  4. Acceptance rate time-series  — GET /api/metrics/acceptance-rate
  5. Training status              — GET /api/training/status
  6. Training schedule management — GET/PUT /api/training/schedule
  7. SEAL Phase 3 cycle (dry run) — POST /api/seal/cycle?dry_run=true
  8. SEAL Phase 3 status          — GET /api/seal/status
  9. Dashboard ecosystem metrics  — GET /api/forgeai/ecosystem-metrics
  10. Model improvement heatmap   — GET /api/metrics/improvement-heatmap
  11. Signal pattern analysis     — GET /api/metrics/signal-patterns
  12. Project CRUD                — CRUD /api/projects
  13. Memory endpoints            — POST/GET /api/memory/*
  14. TTS pipeline status         — GET /api/tts/status
  15. Test-Time Scaling config    — PUT /api/tts/config
  16. RAG stats                   — GET /api/rag/stats
  17. Rate limiter resilience     — Verify 429 handling
  18. Encrypted DB verification   — Confirm data persists encrypted

Uses FastAPI's TestClient with a real CaptureEngine backed by a temp file.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    """Create a TestClient with the real ForgeAI server app.

    The server's lifespan initializes the CaptureEngine, scheduler,
    TTS pipeline, etc. Tests must patch globals for custom behavior.
    """
    from src.api.server import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def capture_db() -> str:
    """Create a temp file for the capture engine database."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    yield tmp.name
    try:
        os.unlink(tmp.name)
        # Also clean up any encrypted blob or temp files
        for suffix in (".encrypted", ".tmp.enc"):
            p = tmp.name + suffix
            if os.path.exists(p):
                os.unlink(p)
    except OSError:
        pass


def _make_real_engine(db_path: str):
    """Create a real CaptureEngine backed by the given temp file."""
    from src.learning.capture_engine import CaptureEngine

    return CaptureEngine(db_path=db_path)


def _patch_rate_limiter() -> MagicMock:
    """Return a mock rate limiter that always allows."""
    mock = MagicMock()
    mock.allow.return_value = True
    return mock


# ── Test Class ───────────────────────────────────────────────────


class TestFullPipelineE2E:
    """Complete end-to-end pipeline verification."""

    # ═══════════════════════════════════════════════════════════
    # 1. Server Health
    # ═══════════════════════════════════════════════════════════

    def test_health_check(self, client: TestClient):
        """Server should report healthy with version info."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "uptime_seconds" in data
        assert "scheduler" in data
        assert data["inference_connected"] is True

    def test_security_headers(self, client: TestClient):
        """Every response should include security headers."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"
        assert "X-Request-ID" in response.headers

    # ═══════════════════════════════════════════════════════════
    # 2. Event Capture → Stats → Dashboard
    # ═══════════════════════════════════════════════════════════

    def test_capture_accept_reject_edit_and_verify_stats(
        self, client: TestClient, capture_db: str
    ):
        """Full pipeline: capture events → stats reflect them → dashboard shows them."""
        limiter = _patch_rate_limiter()
        engine = _make_real_engine(capture_db)

        with patch("src.api.server._rate_limiter", limiter):
            with patch("src.api.server._capture_engine", engine):

                # --- 2a. Capture 8 accepts ---
                for i in range(8):
                    resp = client.post("/api/events", json={
                        "event_type": "accept",
                        "session_id": f"e2e-session-{i}",
                        "project_id": "e2e-test",
                        "file_path": f"src/app{i}.py",
                        "line_number": 10 + i,
                        "language": "python",
                        "project_type": "web",
                        "suggestion": f"def handler_{i}(): pass" * 20,
                        "context_before": "import os",
                        "context_after": "    pass",
                    })
                    assert resp.status_code == 200, f"Accept {i}: {resp.text[:200]}"
                    body = resp.json()
                    assert body["captured"] is True
                    assert "event_id" in body

                # --- 2b. Capture 3 rejects ---
                for i in range(3):
                    resp = client.post("/api/events", json={
                        "event_type": "reject",
                        "session_id": f"e2e-reject-{i}",
                        "project_id": "e2e-test",
                        "file_path": f"src/bad{i}.py",
                        "line_number": 5 + i,
                        "language": "python",
                        "project_type": "web",
                        "suggestion": f"bad_code_{i}" * 30,
                        "context_before": "def foo():",
                        "context_after": "    pass",
                    })
                    assert resp.status_code == 200, f"Reject {i}: {resp.text[:200]}"
                    assert resp.json()["captured"] is True

                # --- 2c. Capture 2 edits ---
                for i in range(2):
                    resp = client.post("/api/events", json={
                        "event_type": "edit",
                        "session_id": f"e2e-edit-{i}",
                        "project_id": "e2e-test",
                        "file_path": f"src/edit{i}.py",
                        "line_number": 15 + i,
                        "language": "python",
                        "project_type": "web",
                        "suggestion": f"original_{i}" * 30,
                        "final_code": f"edited_{i}" * 30,
                        "context_before": "def baz():",
                        "context_after": "    pass",
                    })
                    assert resp.status_code == 200, f"Edit {i}: {resp.text[:200]}"
                    assert resp.json()["captured"] is True

                # --- 2d. Capture 1 PR merge ---
                resp = client.post("/api/events", json={
                    "event_type": "pr_merge",
                    "session_id": "e2e-pr-1",
                    "project_id": "e2e-test",
                    "file_path": "src/feature.py",
                    "line_number": 1,
                    "language": "python",
                    "project_type": "web",
                    "suggestion": "def new_feature(): return 42" * 20,
                    "suggestion_metadata": {"pr_number": 42, "branch": "feature/new-thing", "git_sha": "abc123"},
                    "context_before": "import sys",
                    "context_after": "    return 42",
                })
                assert resp.status_code == 200, f"PR merge: {resp.text[:200]}"
                assert resp.json()["captured"] is True

                # --- 2e. Verify /stats ---
                stats_resp = client.get("/stats")
                assert stats_resp.status_code == 200
                stats = stats_resp.json()

                assert stats["signals_by_type"].get("accept", 0) == 8
                assert stats["signals_by_type"].get("reject", 0) == 3
                assert stats["signals_by_type"].get("edit", 0) == 2
                # pr_merge counts as accept signal in acceptance rate
                assert stats["total_sessions"] > 0
                assert stats["overall_acceptance_rate"] > 0

                # Acceptance rate: (8 accepts + 1 pr_merge) / (9 + 3 rejects) = 9/12 = 75%
                # Edits are not counted in accept/reject rate
                total_positive = 8 + 1  # accepts + pr_merge
                total_negative = 3     # rejects
                expected_rate = round(total_positive / (total_positive + total_negative) * 100, 1)
                actual = stats["overall_acceptance_rate"]
                assert abs(actual - expected_rate) < 1.0, (
                    f"Expected ~{expected_rate}%, got {actual}%"
                )

                # --- 2f. Verify /api/metrics/acceptance-rate ---
                rate_resp = client.get("/api/metrics/acceptance-rate")
                assert rate_resp.status_code == 200
                rate_data = rate_resp.json()
                assert "data" in rate_data
                assert len(rate_data["data"]) > 0
                latest = rate_data["data"][-1]
                assert latest["accepts"] >= 8
                assert latest["rejects"] >= 3

                # --- 2g. Store a training run ---
                engine.store_training_run(
                    run_id="e2e-run-001",
                    model_name="Qwen/Qwen2.5-Coder-7B-Instruct",
                    signals_used=14,
                    acceptance_rate_before=0.50,
                    acceptance_rate_after=0.65,
                    train_loss=0.45,
                    eval_loss=1.02,
                    adapter_path="/tmp/e2e-adapter",
                )

                # --- 2h. Verify /api/training/status ---
                train_resp = client.get("/api/training/status")
                assert train_resp.status_code == 200
                train_data = train_resp.json()
                assert len(train_data["history"]) == 1
                run = train_data["history"][0]
                assert run["run_id"] == "e2e-run-001"
                assert abs(run["acceptance_delta"] - 0.15) < 1e-6
                assert run["signals_used"] == 14

                # --- 2i. Verify /api/forgeai/ecosystem-metrics ---
                eco_resp = client.get("/api/forgeai/ecosystem-metrics")
                assert eco_resp.status_code == 200
                eco = eco_resp.json()
                assert eco["statistics"]["overall_acceptance_rate"] > 0
                assert len(eco["acceptance_rates"]) > 0
                assert eco["training"]["history"][0]["run_id"] == "e2e-run-001"
                assert eco["server"]["status"] == "healthy"
                assert eco["health"]["status"] == "ok"
                # Signal distribution should have accept/reject/edit
                dist = {s["name"]: s for s in eco["signal_distribution"]}
                assert "Accept" in dist
                assert dist["Accept"]["value"] >= 8

    # ═══════════════════════════════════════════════════════════
    # 3. SEAL Phase 3 Cycle and Status
    # ═══════════════════════════════════════════════════════════

    def test_seal_dry_run_cycle(self, client: TestClient, capture_db: str):
        """Trigger a SEAL cycle in dry_run mode and verify the response."""
        engine = _make_real_engine(capture_db)

        # Seed some signals so SEAL has data to analyze
        for i in range(5):
            engine.capture_accept(
                suggestion=f"def f{i}(): pass",
                file_path=f"src/f{i}.py",
                line_number=1 + i,
                language="python",
                project_type="web",
            )

        limiter = _patch_rate_limiter()
        with patch("src.api.server._rate_limiter", limiter):
            with patch("src.api.server._capture_engine", engine):
                # Trigger SEAL cycle with dry_run=True (no actual training)
                seal_resp = client.post("/api/seal/cycle?dry_run=true")
                assert seal_resp.status_code == 200
                seal_data = seal_resp.json()
                assert "seal" in seal_data
                assert "cycle" in seal_data["seal"]
                assert "action" in seal_data["seal"]
                # SelfEditAction.to_dict() uses key "action" for action_type.value
                assert seal_data["seal"]["action"]["action"] is not None

    def test_seal_status(self, client: TestClient, capture_db: str):
        """SEAL status endpoint should return system status."""
        engine = _make_real_engine(capture_db)

        limiter = _patch_rate_limiter()
        with patch("src.api.server._rate_limiter", limiter):
            with patch("src.api.server._capture_engine", engine):
                status_resp = client.get("/api/seal/status")
                assert status_resp.status_code == 200
                status_data = status_resp.json()
                assert "status" in status_data

    # ═══════════════════════════════════════════════════════════
    # 4. Project CRUD
    # ═══════════════════════════════════════════════════════════

    def test_project_crud(self, client: TestClient):
        """Full CRUD lifecycle for projects."""
        limiter = _patch_rate_limiter()

        with patch("src.api.server._rate_limiter", limiter):
            # Create
            create_resp = client.post("/api/projects", json={
                "name": "E2E Test Project",
                "repo_path": "/tmp/e2e-test-repo",
                "languages": ["python", "typescript"],
                "training_schedule": "weekly",
            })
            assert create_resp.status_code == 201
            project = create_resp.json()
            project_id = project["id"]
            assert project["name"] == "E2E Test Project"
            assert "python" in project["languages"]
            assert project["training_schedule"] == "weekly"
            assert project["training_phase"] == 1

            # List
            list_resp = client.get("/api/projects")
            assert list_resp.status_code == 200
            projects = list_resp.json()
            ids = [p["id"] for p in projects]
            assert project_id in ids

            # Get by ID
            get_resp = client.get(f"/api/projects/{project_id}")
            assert get_resp.status_code == 200
            assert get_resp.json()["name"] == "E2E Test Project"

            # Update
            update_resp = client.put(f"/api/projects/{project_id}", json={
                "name": "E2E Updated",
                "training_phase": 2,
            })
            assert update_resp.status_code == 200
            assert update_resp.json()["name"] == "E2E Updated"
            assert update_resp.json()["training_phase"] == 2

            # Delete
            delete_resp = client.delete(f"/api/projects/{project_id}")
            assert delete_resp.status_code == 204

    # ═══════════════════════════════════════════════════════════
    # 5. Training Schedule
    # ═══════════════════════════════════════════════════════════

    def test_training_schedule_lifecycle(self, client: TestClient):
        """Update and query the training schedule."""
        limiter = _patch_rate_limiter()

        mock_scheduler = MagicMock()
        mock_scheduler.running = True

        with patch("src.api.server._rate_limiter", limiter):
            with patch("src.api.server._scheduler", mock_scheduler):
                # GET current schedule
                get_resp = client.get("/api/training/schedule")
                assert get_resp.status_code == 200
                schedule = get_resp.json()
                assert "enabled" in schedule
                assert "cron" in schedule
                assert "description" in schedule
                assert "next_run" in schedule

                # PUT update cron to Sunday 3AM
                put_resp = client.put("/api/training/schedule", json={
                    "cron": "0 3 * * 0",
                })
                assert put_resp.status_code == 200
                updated = put_resp.json()
                assert updated["cron"] == "0 3 * * 0"
                assert "Sunday" in updated["description"] or "sunday" in updated["description"]
                assert "updated" in updated["message"]

    # ═══════════════════════════════════════════════════════════
    # 6. Improvement Heatmap & Signal Patterns
    # ═══════════════════════════════════════════════════════════

    def test_improvement_heatmap_with_real_engine(self, client: TestClient, capture_db: str):
        """Improvement heatmap should return structured data with real engine."""
        engine = _make_real_engine(capture_db)
        for i in range(10):
            engine.capture_accept(
                suggestion=f"code_{i}",
                file_path=f"f{i}.py",
                line_number=i,
                language="python",
                project_type="web",
            )

        limiter = _patch_rate_limiter()
        with patch("src.api.server._rate_limiter", limiter):
            with patch("src.api.server._capture_engine", engine):
                resp = client.get("/api/metrics/improvement-heatmap")
                assert resp.status_code == 200
                data = resp.json()
                assert "languages" in data
                assert "patterns" in data
                assert "slots" in data
                assert "weekly_data" in data
                assert data["slots"]["total_signals_used"] >= 10

    def test_signal_patterns_with_real_engine(self, client: TestClient, capture_db: str):
        """Signal patterns should return per-language and per-type breakdowns."""
        engine = _make_real_engine(capture_db)
        for lang in ["python", "typescript", "rust"]:
            for _ in range(5):
                engine.capture_accept(
                    suggestion=f"fn test() -> {lang}",
                    file_path=f"test.{'py' if lang == 'python' else 'ts' if lang == 'typescript' else 'rs'}",
                    line_number=1,
                    language=lang,
                    project_type="web",
                )

        limiter = _patch_rate_limiter()
        with patch("src.api.server._rate_limiter", limiter):
            with patch("src.api.server._capture_engine", engine):
                resp = client.get("/api/metrics/signal-patterns")
                assert resp.status_code == 200
                data = resp.json()
                assert "signal_types" in data
                assert "language_rates" in data
                assert "overall" in data
                # Should have 3 languages
                assert len(data["language_rates"]) == 3
                assert data["overall"]["languages_count"] == 3

    # ═══════════════════════════════════════════════════════════
    # 7. Memory Endpoints
    # ═══════════════════════════════════════════════════════════

    def test_memory_endpoints_handle_unavailable(self, client: TestClient):
        """Memory endpoints gracefully handle uninitialized memory."""
        limiter = _patch_rate_limiter()

        with patch("src.api.server._rate_limiter", limiter):
            with patch("src.api.server._forgeai_memory", None):
                add_resp = client.post("/api/memory/add", json={
                    "message": "test memory",
                    "user_id": "test-user",
                })
                assert add_resp.status_code == 200
                assert add_resp.json()["success"] is False

                search_resp = client.post("/api/memory/search", json={
                    "query": "test",
                    "user_id": "test-user",
                })
                assert search_resp.status_code == 200
                assert search_resp.json()["success"] is False

    # ═══════════════════════════════════════════════════════════
    # 8. TTS Pipeline
    # ═══════════════════════════════════════════════════════════

    def test_tts_status_and_config(self, client: TestClient):
        """TTS pipeline should report status and accept config updates."""
        limiter = _patch_rate_limiter()

        with patch("src.api.server._rate_limiter", limiter):
            # GET status
            status_resp = client.get("/api/tts/status")
            assert status_resp.status_code == 200
            tts = status_resp.json()
            assert "enabled" in tts
            assert "pipeline_initialized" in tts
            assert "config" in tts
            assert tts["config"]["complexity_threshold"] == 0.7

            # PUT config
            config_resp = client.put("/api/tts/config", json={
                "complexity_threshold": 0.85,
                "num_initial_rollouts": 3,
            })
            assert config_resp.status_code == 200
            cfg = config_resp.json()
            assert cfg["config"]["complexity_threshold"] == 0.85
            assert cfg["config"]["num_initial_rollouts"] == 3

            # Reset stats
            reset_resp = client.post("/api/tts/reset-stats")
            assert reset_resp.status_code == 200

    # ═══════════════════════════════════════════════════════════
    # 9. RAG Backend & Stats
    # ═══════════════════════════════════════════════════════════

    def test_rag_backend_and_stats(self, client: TestClient):
        """RAG stats should return backend info even without data."""
        limiter = _patch_rate_limiter()

        with patch("src.api.server._rate_limiter", limiter):
            # Backend info
            backend_resp = client.get("/api/rag/backend")
            assert backend_resp.status_code == 200
            backend = backend_resp.json()
            assert "backend" in backend
            assert "chroma_available" in backend
            assert "lightrag_available" in backend

            # Stats (may be unavailable if no DB, but should return gracefully)
            stats_resp = client.get("/api/rag/stats")
            assert stats_resp.status_code == 200
            stats = stats_resp.json()
            assert "status" in stats
            assert "backend" in stats

    # ═══════════════════════════════════════════════════════════
    # 10. Event Validation & Error Handling
    # ═══════════════════════════════════════════════════════════

    def test_invalid_event_types_rejected(self, client: TestClient):
        """Invalid event_type should return 422 validation error."""
        limiter = _patch_rate_limiter()

        with patch("src.api.server._rate_limiter", limiter):
            resp = client.post("/api/events", json={
                "event_type": "invalid_type",
                "session_id": "test",
                "project_id": "test",
                "file_path": "test.py",
                "line_number": 1,
                "language": "python",
                "project_type": "web",
                "suggestion": "code",
            })
            assert resp.status_code == 422

    def test_edit_without_final_code_rejected(self, client: TestClient):
        """Edit events without final_code should return 400."""
        engine = _make_real_engine(tempfile.NamedTemporaryFile(suffix=".db", delete=False).name)
        limiter = _patch_rate_limiter()

        with patch("src.api.server._rate_limiter", limiter):
            with patch("src.api.server._capture_engine", engine):
                resp = client.post("/api/events", json={
                    "event_type": "edit",
                    "session_id": "test",
                    "project_id": "test",
                    "file_path": "test.py",
                    "line_number": 1,
                    "language": "python",
                    "project_type": "web",
                    "suggestion": "original code",
                    # No final_code
                })
                assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text[:200]}"

    # ═══════════════════════════════════════════════════════════
    # 11. Encrypted DB Persistence
    # ═══════════════════════════════════════════════════════════

    def test_data_persists_across_sessions_with_encryption(self, client: TestClient, capture_db: str):
        """Data captured in one session should be readable in another via encrypted storage."""
        from src.learning.capture_engine import CaptureEngine
        from src.utils.encrypted_db import create_encrypted_db

        # Session 1: capture data through the real engine
        engine1 = CaptureEngine(db_path=capture_db, prefer_sqlcipher=False)
        for i in range(4):
            engine1.capture_accept(
                suggestion=f"def persist_{i}(): pass",
                file_path=f"test_{i}.py",
                line_number=i,
                language="python",
                project_type="web",
            )

        # Force close the encrypted DB to flush data to encrypted blob
        engine1._db.close()

        # Session 2: read back through API
        engine2 = CaptureEngine(db_path=capture_db, prefer_sqlcipher=False)
        limiter = _patch_rate_limiter()

        with patch("src.api.server._rate_limiter", limiter):
            with patch("src.api.server._capture_engine", engine2):
                stats_resp = client.get("/stats")
                assert stats_resp.status_code == 200
                stats = stats_resp.json()
                assert stats["signals_by_type"].get("accept", 0) >= 4

        # Verify the encrypted blob exists
        encrypted_path = Path(capture_db).with_suffix(Path(capture_db).suffix + ".encrypted")
        assert encrypted_path.exists(), "Encrypted blob should exist"

    # ═══════════════════════════════════════════════════════════
    # 12. Rate Limiter Resilience
    # ═══════════════════════════════════════════════════════════

    def test_rate_limiter_returns_429(self, client: TestClient):
        """Rate limiter should block requests after capacity exhausted."""
        limiter = MagicMock()
        limiter.allow.return_value = False
        limiter.retry_after.return_value = 5.0

        with patch("src.api.server._rate_limiter", limiter):
            resp = client.get("/health")
            assert resp.status_code == 429
            data = resp.json()
            assert "Rate limit exceeded" in data["error"]
            assert "retry_after" in data
            assert "Retry-After" in resp.headers
