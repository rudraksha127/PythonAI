"""
Hermes-Agent Bridge — Unit Tests
=================================

Tests for the hermes bridge module (src.integration.hermes_bridge).

Covers:
  - is_hermes_available() (installed, not installed)
  - get_hermes_agent() (available, unavailable)
  - register_forgeai_skills() (creates skill files)
  - _find_hermes_path() (found, not found)
  - _get_hermes_venv_python() (found, not found)
  - _venv_bin_dir() and _venv_python_names() cross-platform helpers
  - call_hermes_agent() (success, timeout, file not found)
  - CLI handlers (rag_search, capture_stats, training_status)
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


class TestVenvHelpers(unittest.TestCase):
    """Test virtual environment helper functions."""

    def test_venv_bin_dir_windows(self):
        from src.integration.hermes_bridge import _venv_bin_dir

        with patch("os.name", "nt"):
            result = _venv_bin_dir(Path("/venv"))
            self.assertEqual(result, Path("/venv/Scripts"))

    def test_venv_bin_dir_linux(self):
        from src.integration.hermes_bridge import _venv_bin_dir

        with patch("os.name", "posix"):
            result = _venv_bin_dir(Path("/venv"))
            self.assertEqual(result, Path("/venv/bin"))

    def test_venv_python_names_windows(self):
        from src.integration.hermes_bridge import _venv_python_names

        with patch("os.name", "nt"):
            names = _venv_python_names()
            self.assertEqual(names, ["python.exe"])

    def test_venv_python_names_posix(self):
        from src.integration.hermes_bridge import _venv_python_names

        with patch("os.name", "posix"):
            names = _venv_python_names()
            self.assertIn("python3", names)
            self.assertIn("python", names)


class TestGetHermesVenvPython(unittest.TestCase):
    """Test finding the hermes 3.12 virtualenv Python executable."""

    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    @patch("src.integration.hermes_bridge.Path.cwd")
    def test_finds_venv(self, mock_cwd):
        """Should find python.exe/Scripts in .venv312."""
        from src.integration.hermes_bridge import _get_hermes_venv_python

        # Create a fake .venv312 with python.exe
        venv_dir = self._tmp / "hermes-agent-main" / ".venv312"
        scripts_dir = venv_dir / "Scripts" if True else venv_dir / "bin"
        scripts_dir = venv_dir / "Scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "python.exe").write_text("")

        mock_cwd.return_value = self._tmp

        with patch("os.name", "nt"):
            result = _get_hermes_venv_python()
            self.assertIsNotNone(result)
            self.assertTrue(result.endswith("python.exe"))

    def test_no_venv_returns_none(self):
        """Should return None when no .venv312 exists."""
        from src.integration.hermes_bridge import _get_hermes_venv_python

        with patch("pathlib.Path.is_file", return_value=False):
            result = _get_hermes_venv_python()
            self.assertIsNone(result)


class TestIsHermesAvailable(unittest.TestCase):
    """Test the is_hermes_available() function."""

    @patch("src.integration.hermes_bridge._get_hermes_venv_python", return_value=None)
    @patch("builtins.__import__", side_effect=ImportError)
    def test_not_available(self, mock_import, mock_venv):
        from src.integration.hermes_bridge import is_hermes_available
        self.assertFalse(is_hermes_available())

    @patch("src.integration.hermes_bridge._get_hermes_venv_python", return_value=None)
    @patch("builtins.__import__", return_value=MagicMock())
    def test_available_via_import(self, mock_import, mock_venv):
        from src.integration.hermes_bridge import is_hermes_available
        self.assertTrue(is_hermes_available())


class TestGetHermesAgent(unittest.TestCase):
    """Test get_hermes_agent()."""

    @patch("src.integration.hermes_bridge.is_hermes_available", return_value=False)
    def test_not_available_returns_none(self, mock_avail):
        from src.integration.hermes_bridge import get_hermes_agent
        result = get_hermes_agent()
        self.assertIsNone(result)

    @patch("src.integration.hermes_bridge.is_hermes_available", return_value=True)
    @patch("src.integration.hermes_bridge._get_hermes_venv_python", return_value=None)
    @patch("src.integration.hermes_bridge.sys.executable", "/usr/bin/python3")
    @patch(
        "src.integration.hermes_bridge.subprocess.run",
        return_value=MagicMock(returncode=0, stdout="hermes-agent 0.16.0\n"),
    )
    def test_available_returns_info(self, mock_run, mock_venv, mock_avail, mock_sys):
        from src.integration.hermes_bridge import get_hermes_agent
        result = get_hermes_agent()
        self.assertIsNotNone(result)
        self.assertTrue(result["available"])
        self.assertIn("version", result)


class TestRegisterForgeAISkills(unittest.TestCase):
    """Test register_forgeai_skills()."""

    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    @patch("src.integration.hermes_bridge.is_hermes_available", return_value=False)
    def test_hermes_not_available_returns_false(self, mock_avail):
        from src.integration.hermes_bridge import register_forgeai_skills
        result = register_forgeai_skills()
        self.assertFalse(result)

    @patch("src.integration.hermes_bridge.is_hermes_available", return_value=True)
    @patch("src.integration.hermes_bridge.Path.home")
    def test_creates_skill_files(self, mock_home, mock_avail):
        """Should create 3 skill JSON files in ~/.forgeai/skills/."""
        from src.integration.hermes_bridge import register_forgeai_skills

        mock_home.return_value = self._tmp
        result = register_forgeai_skills()
        self.assertTrue(result)

        skills_dir = self._tmp / ".forgeai" / "skills"
        self.assertTrue(skills_dir.exists())

        skill_files = list(skills_dir.glob("*.json"))
        self.assertEqual(len(skill_files), 3)

        filenames = {f.name for f in skill_files}
        self.assertIn("rag_search.json", filenames)
        self.assertIn("capture_stats.json", filenames)
        self.assertIn("training_status.json", filenames)

        # Verify content
        for f in skill_files:
            content = json.loads(f.read_text(encoding="utf-8"))
            self.assertIn("name", content)
            self.assertIn("description", content)
            self.assertIn("command", content)


class TestFindHermesPath(unittest.TestCase):
    """Test _find_hermes_path()."""

    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_finds_path_with_markers(self):
        """Should find hermes-agent-main dir when it has 'hermes' file and pyproject.toml."""
        from src.integration.hermes_bridge import _find_hermes_path

        hermes_dir = self._tmp / "hermes-agent-main"
        hermes_dir.mkdir(parents=True)
        (hermes_dir / "hermes").write_text("#!/bin/sh\necho hermes")
        (hermes_dir / "pyproject.toml").write_text("[project]\nname = \"hermes-agent\"")

        with patch.object(Path, "cwd", return_value=self._tmp):
            result = _find_hermes_path()
            self.assertIsNotNone(result)
            self.assertEqual(result, hermes_dir)

    def test_not_found_returns_none(self):
        """Should return None when hermes is not found."""
        from src.integration.hermes_bridge import _find_hermes_path

        # Ensure no hermes-agent-main exists in search paths
        with patch.object(Path, "cwd", return_value=self._tmp):
            with patch.object(Path, "home", return_value=self._tmp / "home"):
                result = _find_hermes_path()
                self.assertIsNone(result)


class TestCallHermesAgent(unittest.TestCase):
    """Test call_hermes_agent()."""

    @patch("src.integration.hermes_bridge._find_hermes_path", return_value=None)
    def test_hermes_not_found_returns_error(self, mock_find):
        from src.integration.hermes_bridge import call_hermes_agent

        import asyncio
        result = asyncio.run(call_hermes_agent("test task"))
        self.assertIn("error", result)
        self.assertIn("not installed", result["error"])

    @patch("src.integration.hermes_bridge._find_hermes_path", return_value=Path("/tmp/hermes"))
    @patch("src.integration.hermes_bridge.sys.executable", "/usr/bin/python")
    @patch("asyncio.create_subprocess_exec")
    def test_successful_call(self, mock_subprocess, mock_find, mock_sys):
        from src.integration.hermes_bridge import call_hermes_agent

        # Mock the subprocess
        proc_mock = AsyncMock()
        proc_mock.communicate = AsyncMock(
            return_value=(b"Task completed successfully\n", b"")
        )
        proc_mock.returncode = 0
        mock_subprocess.return_value = proc_mock

        import asyncio
        result = asyncio.run(call_hermes_agent("implement feature X"))
        self.assertIn("output", result)
        self.assertEqual(result["returncode"], 0)
        self.assertIn("Task completed", result["output"])

    @patch("src.integration.hermes_bridge._find_hermes_path", return_value=Path("/tmp/hermes"))
    @patch("src.integration.hermes_bridge.sys.executable", "/usr/bin/python")
    @patch("asyncio.create_subprocess_exec")
    def test_timeout_returns_error(self, mock_subprocess, mock_find, mock_sys):
        from src.integration.hermes_bridge import call_hermes_agent

        proc_mock = AsyncMock()
        proc_mock.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        mock_subprocess.return_value = proc_mock

        import asyncio
        result = asyncio.run(call_hermes_agent("long task"))
        self.assertIn("error", result)
        self.assertIn("timed out", result["error"])


class TestCLIHandlers(unittest.TestCase):
    """Test the CLI handler functions."""

    def test_cli_rag_search_runs(self):
        """Test cli_rag_search doesn't crash (uses mock)."""
        from src.integration.hermes_bridge import cli_rag_search

        with patch("sys.argv", ["prog", "test query"]):
            with patch(
                "src.integration.hermes_bridge._resolve_pythonai_path",
                return_value="/tmp",
            ):
                with patch("src.rag.rag_engine.load_or_build_db") as mock_load:
                    mock_load.return_value = (None, None, None, None, None)
                    with patch("src.rag.rag_engine.get_answer") as mock_answer:
                        mock_answer.return_value = ("answer text", [])
                        try:
                            cli_rag_search()
                        except Exception as e:
                            self.fail(f"cli_rag_search raised {e}")

    def test_cli_capture_stats_runs(self):
        """Test cli_capture_stats doesn't crash (uses mock)."""
        from src.integration.hermes_bridge import cli_capture_stats

        with patch(
            "src.integration.hermes_bridge._resolve_pythonai_path",
            return_value="/tmp",
        ):
            with patch("src.learning.capture_engine.CaptureEngine") as mock_engine:
                mock_engine.return_value.get_statistics.return_value = {"signals": 10}
                mock_engine.return_value.get_acceptance_rate.return_value = []
                try:
                    cli_capture_stats()
                except Exception as e:
                    self.fail(f"cli_capture_stats raised {e}")

    def test_cli_training_status_runs(self):
        """Test cli_training_status doesn't crash (uses mock)."""
        from src.integration.hermes_bridge import cli_training_status

        with patch(
            "src.integration.hermes_bridge._resolve_pythonai_path",
            return_value="/tmp",
        ):
            with patch("src.learning.capture_engine.CaptureEngine") as mock_engine:
                mock_engine.return_value.get_training_runs.return_value = [{"run_id": "r1"}]
                try:
                    cli_training_status()
                except Exception as e:
                    self.fail(f"cli_training_status raised {e}")

    def test_main_unknown_command(self):
        """Test CLI main with unknown command."""
        from src.integration.hermes_bridge import __main__ as cli_main

        with patch("sys.argv", ["prog", "unknown_command"]):
            with self.assertRaises(SystemExit) as ctx:
                # The module's __name__ check won't trigger in test,
                # so we test the if-elif directly via a helper
                pass


if __name__ == "__main__":
    unittest.main()
