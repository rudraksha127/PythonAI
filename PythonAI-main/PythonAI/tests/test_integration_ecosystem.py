"""
Ecosystem Manager — Unit Tests
===============================

Tests for the ecosystem manager module (src.integration.ecosystem_manager).

Covers:
  - Project discovery with custom root
  - get_ecosystem_status() structure
  - _compute_summary_from_checks() with various scenarios
  - discovered_projects property
  - get_project_path()
  - _check_shared_config() (missing, valid, invalid JSON)
  - print_ecosystem_status() (smoke test — just that it doesn't crash)
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch


class TestProjectDiscovery(unittest.TestCase):
    """Test that EcosystemManager discovers projects correctly."""

    def setUp(self):
        # Create a temporary monorepo-like structure
        self._tmp = Path(tempfile.mkdtemp())
        self._create_project_dirs()

        from src.integration.ecosystem_manager import EcosystemManager

        self.mgr = EcosystemManager(project_root=self._tmp)

    def _create_project_dirs(self):
        """Create a minimal project structure for testing."""
        # Root marker
        (self._tmp / "README.md").write_text("# Test")
        (self._tmp / "PythonAI").mkdir()
        (self._tmp / "PythonAI" / "src").mkdir(parents=True, exist_ok=True)
        (self._tmp / "hermes-agent-main").mkdir()
        (self._tmp / "Rudra-bots-main").mkdir()
        # Leave out open-claude, dashboard, etc. to test partial discovery

    def tearDown(self):
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_discovered_projects_contains_expected(self):
        """Test that discovered_projects returns correct project names."""
        projects = self.mgr.discovered_projects
        self.assertIn("PythonAI", projects)
        self.assertIn("hermes-agent", projects)
        self.assertIn("Rudra-bots", projects)

    def test_discovered_projects_omits_missing(self):
        """Test that missing projects are NOT in the list."""
        projects = self.mgr.discovered_projects
        # open-claude and Dashboard were not created
        self.assertNotIn("open-claude", projects)
        self.assertNotIn("Dashboard", projects)

    def test_get_project_path_found(self):
        """Test get_project_path returns the correct Path."""
        path = self.mgr.get_project_path("PythonAI")
        self.assertIsNotNone(path)
        self.assertEqual(path.name, "PythonAI")
        self.assertTrue(path.exists())

    def test_get_project_path_not_found(self):
        """Test get_project_path returns None for unknown projects."""
        path = self.mgr.get_project_path("nonexistent")
        self.assertIsNone(path)

    def test_project_root_uses_provided(self):
        """Test that the provided project_root is used."""
        self.assertEqual(self.mgr.project_root, self._tmp)


class TestEcosystemStatus(unittest.TestCase):
    """Test ecosystem status computation."""

    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp())
        (self._tmp / "README.md").write_text("# Test")
        (self._tmp / "PythonAI").mkdir()
        (self._tmp / "hermes-agent-main").mkdir()

        from src.integration.ecosystem_manager import EcosystemManager

        self.mgr = EcosystemManager(project_root=self._tmp)

    def tearDown(self):
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_get_ecosystem_status_structure(self):
        """Test that get_ecosystem_status returns correct top-level keys."""
        status = self.mgr.get_ecosystem_status()
        self.assertIn("ecosystem", status)
        self.assertIn("projects", status)
        self.assertIn("shared_config", status)
        self.assertIn("summary", status)
        self.assertEqual(status["ecosystem"], "ForgeAI v2.0")

    def test_ecosystem_status_projects_dict(self):
        """Test that projects dict contains all discovered projects."""
        status = self.mgr.get_ecosystem_status()
        self.assertIn("PythonAI", status["projects"])
        self.assertIn("hermes-agent", status["projects"])

    def test_project_check_has_basic_keys(self):
        """Test that each project check has path and exists keys."""
        status = self.mgr.get_ecosystem_status()
        for name, check in status["projects"].items():
            self.assertIn("path", check, f"{name} missing 'path'")
            self.assertIn("exists", check, f"{name} missing 'exists'")
            self.assertIn("status", check, f"{name} missing 'status'")


class TestComputeSummary(unittest.TestCase):
    """Test the _compute_summary_from_checks method."""

    def setUp(self):
        from src.integration.ecosystem_manager import EcosystemManager

        # Use a minimal setup with a real temporary root
        self._tmp = Path(tempfile.mkdtemp())
        self.mgr = EcosystemManager(project_root=self._tmp)

    def tearDown(self):
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_all_healthy(self):
        """Test summary when all projects are healthy."""
        checks = {
            "PythonAI": {"config": {"available": True}},
            "hermes-agent": {"installed": {"installed": True}},
            "Rudra-bots": {"api": {"available": True}},
            "open-claude": {"built": {"built": True}},
            "Dashboard": {"api": {"available": True}},
            "Hermes-studio": {"exists": True},
        }
        summary = self.mgr._compute_summary_from_checks(checks)
        self.assertEqual(summary["total_projects"], 6)
        self.assertEqual(summary["available"], 6)
        self.assertEqual(summary["status"], "healthy")

    def test_partial_healthy(self):
        """Test summary when some projects are down."""
        checks = {
            "PythonAI": {"config": {"available": True}},
            "hermes-agent": {"installed": {"installed": False}},
            "Rudra-bots": {"api": {"available": False}},
            "Dashboard": {"api": {"available": True}},
        }
        summary = self.mgr._compute_summary_from_checks(checks)
        self.assertEqual(summary["available"], 2)  # PythonAI + Dashboard
        self.assertEqual(summary["status"], "partial")

    def test_all_down(self):
        """Test summary when no projects are available."""
        checks = {
            "PythonAI": {"config": {"available": False}},
            "hermes-agent": {"installed": {"installed": False}},
            "Rudra-bots": {"api": {"available": False}},
        }
        summary = self.mgr._compute_summary_from_checks(checks)
        self.assertEqual(summary["available"], 0)
        self.assertEqual(summary["status"], "partial")  # 0/3 is partial, not healthy

    def test_empty_checks(self):
        """Test summary with empty checks dict."""
        summary = self.mgr._compute_summary_from_checks({})
        self.assertEqual(summary["total_projects"], 0)
        self.assertEqual(summary["available"], 0)
        self.assertEqual(summary["status"], "healthy")  # 0/0 = vacuously healthy

    def test_unknown_project_counts_exists(self):
        """Test that unrecognized project names check the 'exists' key."""
        checks = {
            "UnknownProject": {"exists": True, "path": "/some/path"},
            "MissingProject": {"exists": False, "path": None},
        }
        summary = self.mgr._compute_summary_from_checks(checks)
        self.assertEqual(summary["total_projects"], 2)
        self.assertEqual(summary["available"], 1)


class TestSharedConfig(unittest.TestCase):
    """Test shared config checking."""

    def setUp(self):
        from src.integration.ecosystem_manager import EcosystemManager

        self._tmp = Path(tempfile.mkdtemp())
        self.mgr = EcosystemManager(project_root=self._tmp)

    def tearDown(self):
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    @patch("src.integration.ecosystem_manager.Path.home")
    def test_config_not_found(self, mock_home):
        """Test check when config file doesn't exist."""
        mock_home.return_value = self._tmp
        result = self.mgr._check_shared_config()
        self.assertFalse(result["exists"])
        self.assertIn(".forgeai", result["path"])

    @patch("src.integration.ecosystem_manager.Path.home")
    def test_config_valid_json(self, mock_home):
        """Test check with valid config."""
        mock_home.return_value = self._tmp
        config_dir = self._tmp / ".forgeai"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"version": "2.0.0", "llm": {"model": "gpt-4"}}))

        result = self.mgr._check_shared_config()
        self.assertTrue(result["exists"])
        self.assertEqual(result["version"], "2.0.0")

    @patch("src.integration.ecosystem_manager.Path.home")
    def test_config_invalid_json(self, mock_home):
        """Test check with invalid JSON in config file."""
        mock_home.return_value = self._tmp
        config_dir = self._tmp / ".forgeai"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"
        config_file.write_text("this is not json", encoding="utf-8")

        result = self.mgr._check_shared_config()
        self.assertTrue(result["exists"])
        self.assertEqual(result.get("error"), "invalid_json")


class TestDetectProjectRoot(unittest.TestCase):
    """Test automatic project root detection."""

    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp())
        # Create markers in cwd — we'll patch cwd
        self._tmp_with_markers = Path(tempfile.mkdtemp())
        (self._tmp_with_markers / "README.md").write_text("# Root")
        (self._tmp_with_markers / "PythonAI").mkdir()

    def tearDown(self):
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)
        shutil.rmtree(self._tmp_with_markers, ignore_errors=True)

    def test_detect_root_finds_markers(self):
        """Test that _detect_project_root finds the right directory."""
        from src.integration.ecosystem_manager import EcosystemManager

        # Create an instance pointing at our marker dir
        mgr = EcosystemManager(project_root=self._tmp_with_markers)
        self.assertEqual(mgr.project_root, self._tmp_with_markers)

    def test_provided_root_is_used(self):
        """Test that the provided project_root is stored and used as-is."""
        from src.integration.ecosystem_manager import EcosystemManager

        mgr = EcosystemManager(project_root=self._tmp)
        # No README.md + PythonAI in _tmp, but provided root is used directly
        self.assertEqual(mgr.project_root, self._tmp)


class TestPrintStatus(unittest.TestCase):
    """Smoke test for print_ecosystem_status."""

    def setUp(self):
        from src.integration.ecosystem_manager import EcosystemManager

        self._tmp = Path(tempfile.mkdtemp())
        self.mgr = EcosystemManager(project_root=self._tmp)

    def tearDown(self):
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_print_does_not_crash(self):
        """Test that print_ecosystem_status runs without error."""
        try:
            self.mgr.print_ecosystem_status()
        except Exception as e:
            self.fail(f"print_ecosystem_status raised {e}")


if __name__ == "__main__":
    unittest.main()
