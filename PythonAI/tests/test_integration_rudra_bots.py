"""
Rudra-bots Bridge — Unit Tests
===============================

Tests for the bridge module (src.integration.rudra_bots_bridge).

Covers:
  - get_rudra_bots_url() with/without env var
  - send_metrics() (mock the HTTP call — success, failure, connect error)
  - check_health() (mock — healthy, degraded, unreachable)
  - send_acceptance_rate()
  - send_training_run()
  - send_capture_stats()
  - sync_all_to_dashboard()
"""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

# ---------------------------------------------------------------------------
# All tests use mocked HTTP so they never contact a real server.
# The default Rudra-bots URL is http://localhost:7000 — tests override via
# environment variable or directly mock the httpx calls.
# ---------------------------------------------------------------------------


class TestGetRudraBotsURL(unittest.TestCase):
    """Test URL resolution (env var vs default)."""

    def setUp(self):
        # Clear any existing env var before each test
        self._env_patcher = patch.dict("os.environ", {}, clear=True)
        self._env_patcher.start()

    def tearDown(self):
        self._env_patcher.stop()

    def test_default_url(self):
        """Test default URL when env var is not set."""
        from src.integration.rudra_bots_bridge import get_rudra_bots_url

        url = get_rudra_bots_url()
        self.assertEqual(url, "http://localhost:7000")

    def test_env_var_url(self):
        """Test URL from environment variable."""
        import os

        os.environ["RUDRA_BOTS_URL"] = "http://custom:8080"
        # Re-import or reload to pick up the env var
        from src.integration.rudra_bots_bridge import get_rudra_bots_url

        url = get_rudra_bots_url()
        self.assertEqual(url, "http://custom:8080")


class TestCheckHealth(unittest.TestCase):
    """Test the check_health async function."""

    def setUp(self):
        self._env_patcher = patch.dict("os.environ", {"RUDRA_BOTS_URL": "http://test:7000"}, clear=True)
        self._env_patcher.start()

    def tearDown(self):
        self._env_patcher.stop()

    async def _run(self, mock_status, mock_exception=None):
        from src.integration.rudra_bots_bridge import check_health

        if mock_exception:
            client_mock = AsyncMock()
            client_mock.__aenter__.return_value.get = AsyncMock(side_effect=mock_exception)
        else:
            response_mock = AsyncMock()
            response_mock.status_code = mock_status
            client_mock = AsyncMock()
            client_mock.__aenter__.return_value.get = AsyncMock(return_value=response_mock)

        with patch("httpx.AsyncClient", return_value=client_mock):
            return await check_health()

    def test_healthy(self):
        import asyncio

        result = asyncio.run(self._run(200))
        self.assertTrue(result["running"])
        self.assertEqual(result["status"], "healthy")

    def test_degraded(self):
        import asyncio

        result = asyncio.run(self._run(503))
        self.assertTrue(result["running"])
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["code"], 503)

    def test_unreachable(self):
        import asyncio
        import httpx

        result = asyncio.run(self._run(None, httpx.ConnectError("Connection refused")))
        self.assertFalse(result["running"])
        self.assertEqual(result["status"], "unreachable")

    def test_generic_error(self):
        import asyncio

        result = asyncio.run(self._run(None, ValueError("Something broke")))
        self.assertFalse(result["running"])
        self.assertEqual(result["status"], "error")
        self.assertIn("error", result)


class TestSendMetrics(unittest.TestCase):
    """Test the send_metrics async function."""

    def setUp(self):
        self._env_patcher = patch.dict("os.environ", {"RUDRA_BOTS_URL": "http://test:7000"}, clear=True)
        self._env_patcher.start()

    def tearDown(self):
        self._env_patcher.stop()

    async def _run(self, mock_status, mock_exception=None):
        from src.integration.rudra_bots_bridge import send_metrics

        if mock_exception:
            client_mock = AsyncMock()
            client_mock.__aenter__.return_value.post = AsyncMock(side_effect=mock_exception)
        else:
            response_mock = AsyncMock()
            response_mock.status_code = mock_status
            client_mock = AsyncMock()
            client_mock.__aenter__.return_value.post = AsyncMock(return_value=response_mock)

        with patch("httpx.AsyncClient", return_value=client_mock):
            return await send_metrics({"type": "test", "value": 42})

    def test_send_success_200(self):
        import asyncio

        result = asyncio.run(self._run(200))
        self.assertTrue(result)

    def test_send_success_201(self):
        import asyncio

        result = asyncio.run(self._run(201))
        self.assertTrue(result)

    def test_send_failure_400(self):
        import asyncio

        result = asyncio.run(self._run(400))
        self.assertFalse(result)

    def test_send_connect_error(self):
        import asyncio
        import httpx

        result = asyncio.run(self._run(None, httpx.ConnectError("refused")))
        self.assertFalse(result)

    def test_send_generic_error(self):
        import asyncio

        result = asyncio.run(self._run(None, TimeoutError("timed out")))
        self.assertFalse(result)


class TestSendAcceptanceRate(unittest.TestCase):
    """Test the send_acceptance_rate helper."""

    def setUp(self):
        self._env_patcher = patch.dict("os.environ", {"RUDRA_BOTS_URL": "http://test:7000"}, clear=True)
        self._env_patcher.start()

    def tearDown(self):
        self._env_patcher.stop()

    def test_sends_correct_payload(self):
        import asyncio

        from src.integration.rudra_bots_bridge import send_acceptance_rate

        # Mock send_metrics to capture what it would send
        with patch("src.integration.rudra_bots_bridge.send_metrics", new_callable=AsyncMock) as mock_send:
            asyncio.run(send_acceptance_rate("2026-06-12", 75.0, 10, 3, edits=2))

            mock_send.assert_called_once()
            args = mock_send.call_args[0][0]
            self.assertEqual(args["type"], "acceptance_rate")
            self.assertEqual(args["date"], "2026-06-12")
            self.assertEqual(args["rate"], 75.0)
            self.assertEqual(args["accepts"], 10)
            self.assertEqual(args["rejects"], 3)
            self.assertEqual(args["edits"], 2)
            self.assertEqual(args["source"], "PythonAI")
            self.assertIn("timestamp", args)


class TestSendTrainingRun(unittest.TestCase):
    """Test the send_training_run helper."""

    def test_sends_correct_payload(self):
        import asyncio

        from src.integration.rudra_bots_bridge import send_training_run

        with patch("src.integration.rudra_bots_bridge.send_metrics", new_callable=AsyncMock) as mock_send:
            asyncio.run(
                send_training_run(
                    {
                        "run_id": "run-001",
                        "model_name": "test-model",
                        "signals_used": 100,
                        "acceptance_rate_before": 60.0,
                        "acceptance_rate_after": 72.5,
                    }
                )
            )

            mock_send.assert_called_once()
            args = mock_send.call_args[0][0]
            self.assertEqual(args["type"], "training_run")
            self.assertEqual(args["source"], "PythonAI")
            self.assertEqual(args["run_id"], "run-001")
            self.assertEqual(args["model_name"], "test-model")
            self.assertEqual(args["acceptance_rate_after"], 72.5)


class TestSendCaptureStats(unittest.TestCase):
    """Test the send_capture_stats helper."""

    def test_sends_correct_payload(self):
        import asyncio

        from src.integration.rudra_bots_bridge import send_capture_stats

        with patch("src.integration.rudra_bots_bridge.send_metrics", new_callable=AsyncMock) as mock_send:
            stats = {"signals_by_type": {"accept": 50, "reject": 10}, "total_sessions": 30}
            asyncio.run(send_capture_stats(stats))

            mock_send.assert_called_once()
            args = mock_send.call_args[0][0]
            self.assertEqual(args["type"], "capture_stats")
            self.assertEqual(args["source"], "PythonAI")
            self.assertEqual(args["data"]["signals_by_type"]["accept"], 50)


class TestSyncAllToDashboard(unittest.TestCase):
    """Test the sync_all_to_dashboard function."""

    def test_sync_creates_correct_payload(self):
        import asyncio

        from src.integration.rudra_bots_bridge import sync_all_to_dashboard

        with patch("src.integration.rudra_bots_bridge.send_metrics", new_callable=AsyncMock) as mock_send:
            # Mock CaptureEngine at its actual import location (it's imported
            # inside sync_all_to_dashboard via `from src.learning.capture_engine import CaptureEngine`)
            with patch(
                "src.learning.capture_engine.CaptureEngine"
            ) as mock_engine_cls:
                mock_engine = mock_engine_cls.return_value
                mock_engine.get_statistics.return_value = {"signals_by_type": {"accept": 10}, "overall_acceptance_rate": 80.0}
                mock_engine.get_acceptance_rate.return_value = [{"date": "2026-06-12", "rate": 80.0}]
                mock_engine.get_training_runs.return_value = [{"run_id": "r1", "model_name": "m1"}]

                asyncio.run(sync_all_to_dashboard())

                mock_send.assert_called_once()
                args = mock_send.call_args[0][0]
                self.assertEqual(args["type"], "forgeai_sync")
                self.assertEqual(args["source"], "PythonAI")
                self.assertIn("statistics", args["data"])
                self.assertIn("acceptance_rates", args["data"])
                self.assertIn("training_runs", args["data"])

    def test_sync_returns_false_on_error(self):
        import asyncio

        from src.integration.rudra_bots_bridge import sync_all_to_dashboard

        with patch("src.learning.capture_engine.CaptureEngine") as mock_engine_cls:
            mock_engine_cls.side_effect = RuntimeError("DB not available")

            result = asyncio.run(sync_all_to_dashboard())
            self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
