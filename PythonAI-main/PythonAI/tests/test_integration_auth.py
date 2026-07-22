"""
ForgeAI Auth — Unit Tests
==========================

Tests for the shared authentication module (src.integration.auth).

Covers:
  - User creation (success, duplicate, invalid role)
  - Password hashing with scrypt (verification, wrong password, malformed hash)
  - Token creation and validation (happy path, expiry, tampered token)
  - Service tokens
  - User deactivation
  - authenticate() flow
  - list_users() and get_status()
  - create_auth_router FastAPI integration
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


class TestForgeAIUser(unittest.TestCase):
    """Test the ForgeAIUser dataclass."""

    def setUp(self):
        from src.integration.auth import ForgeAIUser

        self.user = ForgeAIUser(username="testuser", email="test@example.com", role="developer")

    def test_user_creation(self):
        self.assertEqual(self.user.username, "testuser")
        self.assertEqual(self.user.email, "test@example.com")
        self.assertEqual(self.user.role, "developer")
        self.assertTrue(self.user.is_active)
        self.assertIsNotNone(self.user.user_id)

    def test_user_to_dict(self):
        d = self.user.to_dict()
        self.assertEqual(d["username"], "testuser")
        self.assertEqual(d["email"], "test@example.com")
        self.assertEqual(d["role"], "developer")
        self.assertIn("password_hash", d)  # Hash is included (empty string by default)

    def test_user_from_dict(self):
        from src.integration.auth import ForgeAIUser

        d = {
            "username": "restored",
            "email": "r@x.com",
            "role": "admin",
            "password_hash": "aaa:bbb",
            "created_at": 1000.0,
            "is_active": False,
            "user_id": "uid-123",
        }
        user = ForgeAIUser.from_dict(d)
        self.assertEqual(user.username, "restored")
        self.assertEqual(user.role, "admin")
        self.assertFalse(user.is_active)
        self.assertEqual(user.user_id, "uid-123")


class TestForgeAIToken(unittest.TestCase):
    """Test the ForgeAIToken dataclass."""

    def setUp(self):
        from src.integration.auth import ForgeAIToken

        now = time.time()
        self.token = ForgeAIToken(
            token="abc.def",
            user_id="uid-1",
            username="testuser",
            email="t@t.com",
            role="developer",
            permissions={"can_train": True, "can_view_all": True},
            issued_at=now,
            expires_at=now + 86400,
        )

    def test_not_expired(self):
        self.assertFalse(self.token.is_expired())

    def test_expired(self):
        self.token.expires_at = time.time() - 1
        self.assertTrue(self.token.is_expired())

    def test_has_permission(self):
        self.assertTrue(self.token.has_permission("can_train"))
        self.assertFalse(self.token.has_permission("can_delete"))

    def test_to_dict(self):
        d = self.token.to_dict()
        self.assertEqual(d["username"], "testuser")
        self.assertEqual(d["role"], "developer")


class TestForgeAIAuth(unittest.TestCase):
    """Test the ForgeAIAuth class (core auth logic)."""

    def setUp(self):
        import tempfile

        # Use a temporary directory so tests never touch real ~/.forgeai
        self._tmp = Path(tempfile.mkdtemp())
        self._auth_dir_patch = patch("src.integration.auth.AUTH_DIR", self._tmp)
        self._auth_dir_patch.start()
        self._users_file_patch = patch("src.integration.auth.USERS_FILE", self._tmp / "users.json")
        self._users_file_patch.start()
        self._secret_file_patch = patch("src.integration.auth.SECRET_KEY_FILE", self._tmp / "secret.key")
        self._secret_file_patch.start()

        from src.integration.auth import ForgeAIAuth

        self.auth = ForgeAIAuth(secret_key="test-secret-key-32chr-not-for-prod!!!")

    def tearDown(self):
        self._secret_file_patch.stop()
        self._users_file_patch.stop()
        self._auth_dir_patch.stop()
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    # ── User Creation ────────────────────────────────────────────────

    def test_create_user_success(self):
        result = self.auth.create_user("alice", "secure123", "alice@x.com", "developer")
        self.assertTrue(result["success"])
        self.assertEqual(result["username"], "alice")
        self.assertEqual(result["role"], "developer")
        self.assertIn("user_id", result)

    def test_create_user_duplicate(self):
        self.auth.create_user("alice", "pw1")
        result = self.auth.create_user("alice", "pw2")
        self.assertFalse(result["success"])
        self.assertIn("already exists", result["error"])

    def test_create_user_invalid_role(self):
        result = self.auth.create_user("bob", "pw", role="superadmin")
        self.assertFalse(result["success"])
        self.assertIn("Invalid role", result["error"])

    # ── Password Hashing ─────────────────────────────────────────────

    def test_password_hash_and_verify(self):
        password = "MyS3cur3P@ss!"
        h = self.auth._hash_password(password)
        self.assertIn(":", h)  # salt:hash format

        # Verify the same password
        self.assertTrue(self.auth._verify_password(password, h))

        # Wrong password
        self.assertFalse(self.auth._verify_password("wrong", h))

    def test_verify_malformed_hash(self):
        self.assertFalse(self.auth._verify_password("pwd", "not-a-valid-format"))
        self.assertFalse(self.auth._verify_password("pwd", ""))
        self.assertFalse(self.auth._verify_password("pwd", "abc"))  # no colon

    # ── Token Lifecycle ──────────────────────────────────────────────

    def test_create_and_validate_token(self):
        self.auth.create_user("alice", "pw", role="admin")
        token = self.auth.create_token("alice", "admin")
        self.assertIsNotNone(token)
        self.assertEqual(token.username, "alice")
        self.assertEqual(token.role, "admin")
        self.assertTrue(token.permissions.get("can_manage_users"))

        # Validate round-trip
        validated = self.auth.validate_token(token.token)
        self.assertIsNotNone(validated)
        self.assertEqual(validated.username, "alice")
        self.assertEqual(validated.role, "admin")

    def test_validate_tampered_token(self):
        self.auth.create_user("alice", "pw")
        token = self.auth.create_token("alice")
        tampered = token.token + "x"
        self.assertIsNone(self.auth.validate_token(tampered))

        # Bad format
        self.assertIsNone(self.auth.validate_token("not-a-token"))

    def test_validate_expired_token(self):
        self.auth.create_user("alice", "pw")
        token = self.auth.create_token("alice", expires_in_days=0)  # expires immediately-ish
        # Actually 0 days still gives some time; let's force expiry
        # by patching time
        from src.integration.auth import time as auth_time_module

        with patch.object(auth_time_module, "time", return_value=time.time() + 86401):
            validated = self.auth.validate_token(token.token)
            self.assertIsNone(validated)

    # ── Authenticate flow ────────────────────────────────────────────

    def test_authenticate_success(self):
        self.auth.create_user("alice", "password")
        result = self.auth.authenticate("alice", "password")
        self.assertTrue(result["success"])
        self.assertIn("token", result)
        self.assertEqual(result["user"]["username"], "alice")

    def test_authenticate_wrong_password(self):
        self.auth.create_user("alice", "correct")
        result = self.auth.authenticate("alice", "wrong")
        self.assertFalse(result["success"])
        self.assertIn("Invalid password", result["error"])

    def test_authenticate_user_not_found(self):
        result = self.auth.authenticate("nonexistent", "pw")
        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"])

    def test_authenticate_deactivated_user(self):
        self.auth.create_user("alice", "pw")
        # Manually deactivate
        self.auth._users["alice"].is_active = False
        result = self.auth.authenticate("alice", "pw")
        self.assertFalse(result["success"])
        self.assertIn("deactivated", result["error"])

    # ── Service Tokens ───────────────────────────────────────────────

    def test_create_service_token(self):
        token = self.auth.create_service_token("pythonai-rudra")
        self.assertIsNotNone(token)
        self.assertTrue(token.is_service_token)
        self.assertEqual(token.role, "api")
        self.assertIn("service:", token.username)

    def test_validate_service_token(self):
        token = self.auth.create_service_token("dashboard")
        validated = self.auth.validate_token(token.token)
        self.assertIsNotNone(validated)
        self.assertTrue(validated.is_service_token)

    # ── List & Status ────────────────────────────────────────────────

    def test_list_users(self):
        self.auth.create_user("u1", "p1", role="admin")
        self.auth.create_user("u2", "p2", role="viewer")
        users = self.auth.list_users()
        self.assertEqual(len(users), 2)
        usernames = {u["username"] for u in users}
        self.assertIn("u1", usernames)
        self.assertIn("u2", usernames)
        # No password hashes in list
        for u in users:
            self.assertNotIn("password_hash", u)

    def test_get_status(self):
        self.auth.create_user("u1", "p1")
        status = self.auth.get_status()
        self.assertTrue(status["enabled"])
        self.assertEqual(status["users_count"], 1)
        self.assertEqual(len(status["users"]), 1)

    # ── Deactivation Token Invalidation ──────────────────────────────

    def test_token_invalid_after_user_deactivated(self):
        self.auth.create_user("alice", "pw")
        token = self.auth.create_token("alice")
        self.auth._users["alice"].is_active = False
        validated = self.auth.validate_token(token.token)
        self.assertIsNone(validated)

    # ── Custom secret key ────────────────────────────────────────────

    def test_custom_secret_key(self):
        from src.integration.auth import ForgeAIAuth

        auth1 = ForgeAIAuth(secret_key="my-custom-key")
        auth1.create_user("u1", "pw")
        t1 = auth1.create_token("u1")

        # Different key should not validate the same token
        auth2 = ForgeAIAuth(secret_key="different-key")
        # auth2 has no users — validate will check signature first
        validated = auth2.validate_token(t1.token)
        # Different keys produce different signatures, so validation fails
        self.assertIsNone(validated)


class TestCreateAuthRouter(unittest.TestCase):
    """Test the FastAPI router created by create_auth_router()."""

    def setUp(self):
        import tempfile

        self._tmp = Path(tempfile.mkdtemp())
        self._auth_dir_patch = patch("src.integration.auth.AUTH_DIR", self._tmp)
        self._auth_dir_patch.start()
        self._users_file_patch = patch("src.integration.auth.USERS_FILE", self._tmp / "users.json")
        self._users_file_patch.start()
        self._secret_file_patch = patch("src.integration.auth.SECRET_KEY_FILE", self._tmp / "secret.key")
        self._secret_file_patch.start()

        from src.integration.auth import ForgeAIAuth, create_auth_router
        from fastapi import FastAPI

        self.auth = ForgeAIAuth(secret_key="test-key")
        self.router = create_auth_router(self.auth)

        self.app = FastAPI()
        self.app.include_router(self.router)

    def tearDown(self):
        self._secret_file_patch.stop()
        self._users_file_patch.stop()
        self._auth_dir_patch.stop()
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_router_has_routes(self):
        routes = [r.path for r in self.router.routes]
        self.assertIn("/api/auth/login", routes)
        self.assertIn("/api/auth/signup", routes)
        self.assertIn("/api/auth/status", routes)
        self.assertIn("/api/auth/verify", routes)

    def test_signup_then_login_via_httpx_testclient(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.app)

        # Signup
        resp = client.post("/api/auth/signup", json={"username": "alice", "password": "pw"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])

        # Login
        resp = client.post("/api/auth/login", json={"username": "alice", "password": "pw"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("token", data)

        # Verify token
        token = data["token"]
        resp = client.post("/api/auth/verify", json={"token": token})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["username"], "alice")

    def test_signup_duplicate(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        client.post("/api/auth/signup", json={"username": "alice", "password": "pw"})
        resp = client.post("/api/auth/signup", json={"username": "alice", "password": "pw"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("already exists", resp.text)

    def test_login_wrong_password(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        client.post("/api/auth/signup", json={"username": "alice", "password": "pw"})
        resp = client.post("/api/auth/login", json={"username": "alice", "password": "wrong"})
        self.assertEqual(resp.status_code, 401)

    def test_verify_invalid_token(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        resp = client.post("/api/auth/verify", json={"token": "invalid"})
        self.assertEqual(resp.status_code, 401)

    def test_status_endpoint(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        resp = client.get("/api/auth/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["enabled"])

    def test_invalid_role_signup(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.app)
        resp = client.post(
            "/api/auth/signup", json={"username": "bob", "password": "pw", "role": "superadmin"}
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid role", resp.text)


if __name__ == "__main__":
    unittest.main()
