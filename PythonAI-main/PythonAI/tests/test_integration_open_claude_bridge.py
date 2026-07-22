"""
Open-Claude Bridge — Unit Tests
================================

Tests for the open-claude bridge module (src.integration.open_claude_bridge).

Covers:
  - is_open_claude_available() (installed, not installed, via npx)
  - get_open_claude_version() (found, not found)
  - configure_open_claude_for_forgeai() (success, not installed, timeout)
  - query_forgeai_chat() (success, connect error, timeout, API error)
  - get_cli_status() (installed, not installed)
  - send_to_cli()
"""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch


class TestIsOpenClaudeAvailable(unittest.TestCase):
    """Test is_open_claude_available()."""

    @patch("subprocess.run")
    def test_available_direct(self, mock_run):
        """Should detect open-claude installed directly in PATH."""
        from src.integration.open_claude_bridge import is_open_claude_available

        mock_run.return_value = MagicMock(returncode=0)
        result = is_open_claude_available()
        self.assertTrue(result)
        mock_run.assert_called()

    @patch("subprocess.run")
    def test_not_available(self, mock_run):
        """Should return False when open-claude is not installed."""
        from src.integration.open_claude_bridge import is_open_claude_available

        mock_run.side_effect = FileNotFoundError()
        result = is_open_claude_available()
        self.assertFalse(result)

    @patch("subprocess.run")
    def test_not_available_then_npx(self, mock_run):
        """Should fall back to npx when direct command fails."""
        from src.integration.open_claude_bridge import is_open_claude_available

        # First call fails, second (npx) succeeds
        mock_run.side_effect = [
            MagicMock(returncode=1),
            MagicMock(returncode=0),
        ]
        result = is_open_claude_available()
        self.assertTrue(result)
        self.assertEqual(mock_run.call_count, 2)

    @patch("subprocess.run")
    def test_not_available_via_either(self, mock_run):
        """Should return False when both direct and npx fail."""
        from src.integration.open_claude_bridge import is_open_claude_available

        mock_run.side_effect = FileNotFoundError()
        result = is_open_claude_available()
        self.assertFalse(result)


class TestGetOpenClaudeVersion(unittest.TestCase):
    """Test get_open_claude_version()."""

    @patch("subprocess.run")
    def test_version_found(self, mock_run):
        from src.integration.open_claude_bridge import get_open_claude_version

        mock_run.return_value = MagicMock(
            returncode=0, stdout="open-claude v1.2.3\n"
        )
        result = get_open_claude_version()
        self.assertEqual(result, "open-claude v1.2.3")

    @patch("subprocess.run")
    def test_version_not_found(self, mock_run):
        from src.integration.open_claude_bridge import get_open_claude_version

        mock_run.side_effect = FileNotFoundError()
        result = get_open_claude_version()
        self.assertEqual(result, "not found")


class TestConfigureOpenClaude(unittest.TestCase):
    """Test configure_open_claude_for_forgeai()."""

    @patch("src.integration.open_claude_bridge.is_open_claude_available", return_value=False)
    def test_not_installed(self, mock_avail):
        from src.integration.open_claude_bridge import configure_open_claude_for_forgeai

        result = configure_open_claude_for_forgeai()
        self.assertFalse(result["success"])
        self.assertIn("not installed", result["error"])

    @patch("src.integration.open_claude_bridge.is_open_claude_available", return_value=True)
    @patch("subprocess.run")
    def test_config_success(self, mock_run, mock_avail):
        from src.integration.open_claude_bridge import configure_open_claude_for_forgeai

        mock_run.return_value = MagicMock(returncode=0, stdout="Provider added\n")
        result = configure_open_claude_for_forgeai(api_port=7337)
        self.assertTrue(result["success"])
        self.assertEqual(result["provider"], "forgeai")
        self.assertEqual(result["base_url"], "http://localhost:7337")

    @patch("src.integration.open_claude_bridge.is_open_claude_available", return_value=True)
    @patch("subprocess.run")
    def test_config_failure(self, mock_run, mock_avail):
        from src.integration.open_claude_bridge import configure_open_claude_for_forgeai

        mock_run.return_value = MagicMock(returncode=1, stderr="Error: invalid args\n")
        result = configure_open_claude_for_forgeai()
        self.assertFalse(result["success"])

    @patch("src.integration.open_claude_bridge.is_open_claude_available", return_value=True)
    @patch("subprocess.run")
    def test_config_timeout(self, mock_run, mock_avail):
        from src.integration.open_claude_bridge import configure_open_claude_for_forgeai

        mock_run.side_effect = TimeoutError("timed out")
        result = configure_open_claude_for_forgeai()
        self.assertFalse(result["success"])
        self.assertIn("timed out", result["error"])

    @patch("src.integration.open_claude_bridge.is_open_claude_available", return_value=True)
    @patch("subprocess.run")
    def test_config_file_not_found(self, mock_run, mock_avail):
        from src.integration.open_claude_bridge import configure_open_claude_for_forgeai

        mock_run.side_effect = FileNotFoundError("openclaude not found in PATH")
        result = configure_open_claude_for_forgeai()
        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"])


class TestQueryForgeAIChat(unittest.TestCase):
    """Test query_forgeai_chat()."""

    def setUp(self):
        self.prompt = "What is a Python decorator?"
        self.port = 7337

    @patch("httpx.AsyncClient")
    def test_successful_query(self, mock_httpx):
        from src.integration.open_claude_bridge import query_forgeai_chat

        # Mock the HTTP response
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = AsyncMock(
            return_value={"answer": "A decorator is...", "sources": [], "model": "default"}
        )

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
        mock_httpx.return_value = mock_client

        import asyncio
        result = asyncio.run(query_forgeai_chat(self.prompt))
        self.assertTrue(result["success"])
        self.assertEqual(result["answer"], "A decorator is...")

    @patch("httpx.AsyncClient")
    def test_api_error_response(self, mock_httpx):
        from src.integration.open_claude_bridge import query_forgeai_chat

        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
        mock_httpx.return_value = mock_client

        import asyncio
        result = asyncio.run(query_forgeai_chat(self.prompt))
        self.assertFalse(result["success"])
        self.assertIn("500", result["error"])

    @patch("httpx.AsyncClient")
    def test_connect_error(self, mock_httpx):
        from src.integration.open_claude_bridge import query_forgeai_chat

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.post = AsyncMock(
            side_effect=ConnectionError("Connection refused")
        )
        mock_httpx.return_value = mock_client

        import asyncio
        result = asyncio.run(query_forgeai_chat(self.prompt))
        self.assertFalse(result["success"])
        # httpx wraps connect errors differently, so check for any error
        self.assertIn("error", result)

    @patch("httpx.AsyncClient")
    def test_timeout(self, mock_httpx):
        from src.integration.open_claude_bridge import query_forgeai_chat

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.post = AsyncMock(
            side_effect=TimeoutError("Request timed out")
        )
        mock_httpx.return_value = mock_client

        import asyncio
        result = asyncio.run(query_forgeai_chat(self.prompt))
        self.assertFalse(result["success"])


class TestGetCLIStatus(unittest.TestCase):
    """Test get_cli_status()."""

    @patch("src.integration.open_claude_bridge.is_open_claude_available", return_value=True)
    @patch("src.integration.open_claude_bridge.get_open_claude_version", return_value="v1.2.3")
    def test_installed(self, mock_version, mock_avail):
        from src.integration.open_claude_bridge import get_cli_status

        result = get_cli_status()
        self.assertTrue(result["installed"])
        self.assertEqual(result["version"], "v1.2.3")
        self.assertIn("provider_configured", result)

    @patch("src.integration.open_claude_bridge.is_open_claude_available", return_value=False)
    @patch("src.integration.open_claude_bridge.get_open_claude_version", return_value="not found")
    def test_not_installed(self, mock_version, mock_avail):
        from src.integration.open_claude_bridge import get_cli_status

        result = get_cli_status()
        self.assertFalse(result["installed"])
        self.assertEqual(result["version"], "not found")


class TestSendToCLI(unittest.TestCase):
    """Test send_to_cli()."""

    @patch("subprocess.run")
    def test_send_command(self, mock_run):
        from src.integration.open_claude_bridge import send_to_cli

        mock_run.return_value = MagicMock(stdout="Command output\n", stderr="")
        result = send_to_cli("ask", {"prompt": "hello"})
        self.assertEqual(result, "Command output\n")

    @patch("subprocess.run")
    def test_timeout(self, mock_run):
        from src.integration.open_claude_bridge import send_to_cli

        mock_run.side_effect = TimeoutError("timed out")
        result = send_to_cli("ask")
        self.assertIn("TIMEOUT", result)

    @patch("subprocess.run")
    def test_not_found(self, mock_run):
        from src.integration.open_claude_bridge import send_to_cli

        mock_run.side_effect = FileNotFoundError("openclaude not found")
        result = send_to_cli("ask")
        self.assertIn("not found", result)


if __name__ == "__main__":
    unittest.main()
