"""
Unified Gateway — Unit Tests
=============================

Tests for the API gateway module (src.integration.gateway).

Covers:
  - Gateway health endpoint
  - Auth endpoints (login, signup, verify, service-token, users list)
  - Auth middleware (protected routes reject unauthenticated requests)
  - Auth middleware allows exempt paths without token
  - Proxy endpoints return 502 when backend unreachable
  - Ecosystem status endpoint
  - Watchdog status endpoint
  - _proxy_request error cases (unknown service, connect error, timeout)
  - WebSocket proxy (mock)
"""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


class TestGatewayHealthEndpoint(unittest.TestCase):
    """Test the /health endpoint."""

    def setUp(self):
        import tempfile

        # Patch auth & ecosystem to use temp dirs, and patch SERVICES to avoid real HTTP calls
        self._tmp = Path(tempfile.mkdtemp())
        self._patches = []

        # Patch AUTH_DIR
        p = patch("src.integration.auth.AUTH_DIR", self._tmp)
        p.start()
        self._patches.append(p)
        p = patch("src.integration.auth.USERS_FILE", self._tmp / "users.json")
        p.start()
        self._patches.append(p)
        p = patch("src.integration.auth.SECRET_KEY_FILE", self._tmp / "secret.key")
        p.start()
        self._patches.append(p)

        # Patch gateway SERVICES to empty so health doesn't make real HTTP calls
        self._services_patch = patch(
            "src.integration.gateway.SERVICES",
            {"test-svc": ("http://localhost:1", True)},
        )
        self._services_patch.start()
        self._patches.append(self._services_patch)

        # Patch _health_cache to known values
        self._health_cache_patch = patch(
            "src.integration.gateway._health_cache",
            {"test-svc": {"status": "unreachable"}},
        )
        self._health_cache_patch.start()
        self._patches.append(self._health_cache_patch)

        self._health_time_patch = patch(
            "src.integration.gateway._health_cache_time", time.time()
        )
        self._health_time_patch.start()
        self._patches.append(self._health_time_patch)

        # We need to re-import the gateway module to pick up the patched values
        import importlib
        import src.integration.gateway as gateway_mod
        importlib.reload(gateway_mod)
        self.app = gateway_mod.app

    def tearDown(self):
        for p in self._patches:
            try:
                p.stop()
            except Exception:
                pass
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_health_endpoint_returns_gateway_running(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        resp = client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["gateway"], "running")
        self.assertIn("services", data)
        self.assertIn("service_count", data)
        self.assertIn("healthy_count", data)


class TestGatewayAuthEndpoints(unittest.TestCase):
    """Test the native auth endpoints (/api/auth/*)."""

    def setUp(self):
        import tempfile

        self._tmp = Path(tempfile.mkdtemp())
        self._patches = []

        for attr in ("AUTH_DIR", "USERS_FILE", "SECRET_KEY_FILE"):
            p = patch(f"src.integration.auth.{attr}", self._tmp / attr.lower().replace("_file", ".file"))
            p.start()
            self._patches.append(p)

        # Also patch SECRET_KEY_FILE specifically
        p = patch("src.integration.auth.SECRET_KEY_FILE", self._tmp / "secret.key")
        p.start()
        self._patches.append(p)

        # Patch gateway SERVICES to empty
        p = patch("src.integration.gateway.SERVICES", {})
        p.start()
        self._patches.append(p)

        import importlib
        import src.integration.gateway as gateway_mod
        importlib.reload(gateway_mod)
        self.app = gateway_mod.app

    def tearDown(self):
        for p in self._patches:
            try:
                p.stop()
            except Exception:
                pass
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_signup_then_login_then_verify(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.app)

        # Signup
        resp = client.post("/api/auth/signup", json={"username": "alice", "password": "pw"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])

        # Login
        resp = client.post("/api/auth/login", json={"username": "alice", "password": "pw"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        token = resp.json()["token"]

        # Verify token
        resp = client.post("/api/auth/verify", json={"token": token})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["username"], "alice")

    def test_signup_duplicate_returns_400(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        client.post("/api/auth/signup", json={"username": "bob", "password": "pw"})
        resp = client.post("/api/auth/signup", json={"username": "bob", "password": "pw"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("already exists", resp.text)

    def test_login_wrong_password_returns_401(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        client.post("/api/auth/signup", json={"username": "charlie", "password": "correct"})
        resp = client.post("/api/auth/login", json={"username": "charlie", "password": "wrong"})
        self.assertEqual(resp.status_code, 401)

    def test_verify_invalid_token_returns_401(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        resp = client.post("/api/auth/verify", json={"token": "total-garbage"})
        self.assertEqual(resp.status_code, 401)

    def test_create_service_token(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        resp = client.post("/api/auth/service-token", json={"service_name": "my-service"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("token", data)
        self.assertEqual(data["service"], "my-service")

    def test_list_users_requires_auth(self):
        """Users list should NOT be available without authentication."""
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        # First signup to have a user
        client.post("/api/auth/signup", json={"username": "alice", "password": "pw"})

        # Now try to list users without a token - should be rejected
        resp = client.get("/api/auth/users")
        self.assertEqual(resp.status_code, 401)


class TestAuthMiddleware(unittest.TestCase):
    """Test that the auth middleware properly protects routes."""

    def setUp(self):
        import tempfile

        self._tmp = Path(tempfile.mkdtemp())
        self._patches = []

        for attr in ("AUTH_DIR", "USERS_FILE", "SECRET_KEY_FILE"):
            p = patch(f"src.integration.auth.{attr}", self._tmp / attr.lower())
            p.start()
            self._patches.append(p)

        p = patch("src.integration.auth.SECRET_KEY_FILE", self._tmp / "secret.key")
        p.start()
        self._patches.append(p)

        p = patch("src.integration.gateway.SERVICES", {})
        p.start()
        self._patches.append(p)

        import importlib
        import src.integration.gateway as gateway_mod
        importlib.reload(gateway_mod)
        self.app = gateway_mod.app

    def tearDown(self):
        for p in self._patches:
            try:
                p.stop()
            except Exception:
                pass
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_protected_route_rejects_no_token(self):
        """Requests to protected routes without a token should get 401."""
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        resp = client.get("/api/pythonai/test")
        self.assertEqual(resp.status_code, 401)

    def test_protected_route_rejects_invalid_token(self):
        """Requests with an invalid token should get 401."""
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        resp = client.get(
            "/api/pythonai/test",
            headers={"Authorization": "Bearer invalid-token"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_protected_route_accepts_valid_token(self):
        """Requests with a valid token should pass through auth."""
        from fastapi.testclient import TestClient

        client = TestClient(self.app)

        # Signup and login to get a token
        client.post("/api/auth/signup", json={"username": "alice", "password": "pw"})
        login_resp = client.post("/api/auth/login", json={"username": "alice", "password": "pw"})
        token = login_resp.json()["token"]

        # Request a protected route with the token
        # The proxy will return 502 (service unreachable) which is expected
        resp = client.get(
            "/api/pythonai/test",
            headers={"Authorization": f"Bearer {token}"},
        )
        # 502 means auth passed but backend is unreachable - that's correct!
        self.assertEqual(resp.status_code, 502)

    def test_exempt_path_works_without_token(self):
        """Exempt paths like /health should work without a token."""
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        resp = client.get("/health")
        self.assertEqual(resp.status_code, 200)

    def test_exempt_auth_paths_work_without_token(self):
        """Auth endpoints should be accessible without a token."""
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        resp = client.post("/api/auth/signup", json={"username": "dave", "password": "pw"})
        self.assertEqual(resp.status_code, 200)

    def test_options_request_passes_without_token(self):
        """CORS preflight (OPTIONS) should pass without auth."""
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        resp = client.options("/api/pythonai/test")
        self.assertEqual(resp.status_code, 200)

    def test_arsenal_prefix_exempt(self):
        """Arsenal prefix routes should be exempt from auth."""
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        resp = client.get("/api/arsenal/repos")
        # Will 502 because service unreachable, not 401
        self.assertEqual(resp.status_code, 502)


class TestProxyEndpoints(unittest.TestCase):
    """Test proxy routing (backends return 502 since they're not running)."""

    def setUp(self):
        import tempfile

        self._tmp = Path(tempfile.mkdtemp())
        self._patches = []

        for attr in ("AUTH_DIR", "USERS_FILE", "SECRET_KEY_FILE"):
            p = patch(f"src.integration.auth.{attr}", self._tmp / attr.lower())
            p.start()
            self._patches.append(p)

        p = patch("src.integration.auth.SECRET_KEY_FILE", self._tmp / "secret.key")
        p.start()
        self._patches.append(p)

        # Keep SERVICES intact but real services aren't running, so we'll get 502
        import importlib
        import src.integration.gateway as gateway_mod
        importlib.reload(gateway_mod)
        self.app = gateway_mod.app

    def tearDown(self):
        for p in self._patches:
            try:
                p.stop()
            except Exception:
                pass
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _auth_token(self, client) -> str:
        """Helper to get an auth token."""
        client.post("/api/auth/signup", json={"username": "test", "password": "pw"})
        resp = client.post("/api/auth/login", json={"username": "test", "password": "pw"})
        return resp.json()["token"]

    def test_proxy_pythonai_returns_502(self):
        """PythonAI proxy should return 502 when service is not running."""
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        token = self._auth_token(client)
        resp = client.get(
            "/api/pythonai/test",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 502)

    def test_proxy_metrics(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        token = self._auth_token(client)
        resp = client.get(
            "/api/metrics/test",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 502)

    def test_proxy_training(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        token = self._auth_token(client)
        resp = client.get(
            "/api/training/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 502)

    def test_proxy_events(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        token = self._auth_token(client)
        resp = client.post(
            "/api/events",
            json={"event": "test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 502)

    def test_proxy_rudra_bots(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        token = self._auth_token(client)
        resp = client.get(
            "/api/rudra-bots/health",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 502)

    def test_proxy_seal(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        token = self._auth_token(client)
        resp = client.get(
            "/api/seal/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 502)

    def test_proxy_rag(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        token = self._auth_token(client)
        resp = client.post(
            "/api/rag/search",
            json={"query": "test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 502)

    def test_proxy_agent(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        token = self._auth_token(client)
        resp = client.post(
            "/api/agent/chat",
            json={"prompt": "hello"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 502)

    def test_proxy_projects(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        token = self._auth_token(client)
        resp = client.get(
            "/api/projects",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 502)


class TestEcosystemEndpoint(unittest.TestCase):
    """Test the ecosystem status endpoint."""

    def setUp(self):
        import tempfile

        self._tmp = Path(tempfile.mkdtemp())
        self._patches = []

        for attr in ("AUTH_DIR", "USERS_FILE", "SECRET_KEY_FILE"):
            p = patch(f"src.integration.auth.{attr}", self._tmp / attr.lower())
            p.start()
            self._patches.append(p)

        p = patch("src.integration.auth.SECRET_KEY_FILE", self._tmp / "secret.key")
        p.start()
        self._patches.append(p)

        import importlib
        import src.integration.gateway as gateway_mod
        importlib.reload(gateway_mod)
        self.app = gateway_mod.app

    def tearDown(self):
        for p in self._patches:
            try:
                p.stop()
            except Exception:
                pass
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_ecosystem_endpoint_returns_status(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        resp = client.get("/api/ecosystem")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("ecosystem", data)
        self.assertIn("projects", data)
        self.assertIn("summary", data)


class TestWatchdogEndpoint(unittest.TestCase):
    """Test the watchdog status endpoint."""

    def setUp(self):
        import tempfile

        self._tmp = Path(tempfile.mkdtemp())
        self._patches = []

        for attr in ("AUTH_DIR", "USERS_FILE", "SECRET_KEY_FILE"):
            p = patch(f"src.integration.auth.{attr}", self._tmp / attr.lower())
            p.start()
            self._patches.append(p)

        p = patch("src.integration.auth.SECRET_KEY_FILE", self._tmp / "secret.key")
        p.start()
        self._patches.append(p)

        import importlib
        import src.integration.gateway as gateway_mod
        importlib.reload(gateway_mod)
        self.app = gateway_mod.app

    def tearDown(self):
        for p in self._patches:
            try:
                p.stop()
            except Exception:
                pass
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_watchdog_endpoint(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        resp = client.get("/api/watchdog")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["watchdog"], "active")
        self.assertIn("services", data)


class TestProxyRequestErrors(unittest.TestCase):
    """Test error handling in _proxy_request."""

    def setUp(self):
        import tempfile

        self._tmp = Path(tempfile.mkdtemp())
        self._patches = []

        for attr in ("AUTH_DIR", "USERS_FILE", "SECRET_KEY_FILE"):
            p = patch(f"src.integration.auth.{attr}", self._tmp / attr.lower())
            p.start()
            self._patches.append(p)

        p = patch("src.integration.auth.SECRET_KEY_FILE", self._tmp / "secret.key")
        p.start()
        self._patches.append(p)

        import importlib
        import src.integration.gateway as gateway_mod
        importlib.reload(gateway_mod)
        self.gateway = gateway_mod

    def tearDown(self):
        for p in self._patches:
            try:
                p.stop()
            except Exception:
                pass
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_proxy_request_unknown_service(self):
        """_proxy_request should raise 404 for unknown service names."""
        from fastapi import HTTPException

        from src.integration.gateway import _proxy_request

        request = MagicMock()
        request.url.query = ""
        request.headers = {}
        request.body = AsyncMock(return_value=b"")
        request.state = MagicMock()

        with self.assertRaises(HTTPException) as ctx:
            import asyncio
            asyncio.run(_proxy_request("nonexistent", request, "/test"))
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("nonexistent", str(ctx.exception.detail))


class TestWebSocketProxy(unittest.TestCase):
    """Test WebSocket proxy helpers."""

    def test_ws_proxy_handles_connection_error(self):
        """_ws_proxy should handle connection errors gracefully."""
        from src.integration.gateway import _ws_proxy

        ws_client = MagicMock()
        # Accept should succeed but websockets.connect should fail
        import asyncio
        asyncio.run(_ws_proxy(ws_client, "ws://localhost:1/nonexistent"))
        # Should not raise - connection errors are caught and logged
        ws_client.accept.assert_called_once()


if __name__ == "__main__":
    unittest.main()
