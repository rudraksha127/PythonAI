from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.auth.auth import (
    check_auth,
    generate_token,
    hash_password,
    login,
    logout,
    verify_password,
)
from src.auth.config import AuthConfig
from src.auth.decorators import requires_auth


@pytest.fixture
def temp_config(tmp_path: Path) -> AuthConfig:
    """Create a temporary config file for testing."""
    config_path = tmp_path / ".pythonai" / "config.json"
    return AuthConfig(config_path)


class TestPasswordHashing:
    def test_hash_and_verify(self) -> None:
        password = "my_secret_password_123"
        salt, hashed = hash_password(password)
        assert len(salt) == 32  # 16 bytes = 32 hex chars
        assert len(hashed) > 0
        assert verify_password(password, salt, hashed)

    def test_wrong_password_fails(self) -> None:
        password = "correct_password"
        salt, hashed = hash_password(password)
        assert not verify_password("wrong_password", salt, hashed)

    def test_different_salts(self) -> None:
        password = "same_password"
        salt1, hash1 = hash_password(password)
        salt2, hash2 = hash_password(password)
        assert salt1 != salt2
        assert hash1 != hash2

    def test_empty_password(self) -> None:
        salt, hashed = hash_password("")
        assert verify_password("", salt, hashed)


class TestTokenGeneration:
    def test_token_length(self) -> None:
        token = generate_token(16)
        assert len(token) == 16

    def test_token_uniqueness(self) -> None:
        tokens = {generate_token() for _ in range(100)}
        assert len(tokens) == 100

    def test_token_alphanumeric(self) -> None:
        token = generate_token()
        assert token.isalnum()


class TestAuthConfig:
    def test_default_config(self, temp_config: AuthConfig) -> None:
        config = temp_config.load()
        assert config["user"] is None
        assert config["settings"]["default_model"] == "qwen2.5-coder:14b"

    def test_save_and_load(self, temp_config: AuthConfig) -> None:
        data = {
            "user": {"username": "testuser", "token": "abc123"},
            "settings": {"offline_mode": True},
        }
        temp_config.save(data)
        loaded = temp_config.load()
        assert loaded == data

    def test_set_user(self, temp_config: AuthConfig) -> None:
        user_data = {"username": "john", "token": "tok_123"}
        temp_config.set_user(user_data)
        assert temp_config.get_user() == user_data

    def test_clear_user(self, temp_config: AuthConfig) -> None:
        temp_config.set_user({"username": "john", "token": "tok"})
        temp_config.clear_user()
        assert temp_config.get_user() is None

    def test_is_logged_in_no_user(self, temp_config: AuthConfig) -> None:
        assert not temp_config.is_logged_in()

    def test_is_logged_in_valid(self, temp_config: AuthConfig) -> None:
        temp_config.set_user({"username": "john", "token": "x" * 16})
        assert temp_config.is_logged_in()

    def test_is_logged_in_short_token(self, temp_config: AuthConfig) -> None:
        temp_config.set_user({"username": "john", "token": "short"})
        assert not temp_config.is_logged_in()

    def test_corrupted_json(self, temp_config: AuthConfig) -> None:
        temp_config.config_path.parent.mkdir(parents=True, exist_ok=True)
        temp_config.config_path.write_text("{invalid json}", encoding="utf-8")
        config = temp_config.load()
        assert config["user"] is None


class TestLoginFlow:
    def test_first_time_login(self, temp_config: AuthConfig) -> None:
        result = login("alice", "password123", temp_config)
        assert result["success"]
        assert result["username"] == "alice"
        assert len(result["token"]) > 8

    def test_relogin_correct_password(self, temp_config: AuthConfig) -> None:
        login("bob", "secret", temp_config)
        result = login("bob", "secret", temp_config)
        assert result["success"]

    def test_relogin_wrong_password(self, temp_config: AuthConfig) -> None:
        login("bob", "secret", temp_config)
        result = login("bob", "wrong_password", temp_config)
        assert not result["success"]
        assert "Invalid password" in result["error"]

    def test_logout(self, temp_config: AuthConfig) -> None:
        login("charlie", "pass", temp_config)
        result = logout(temp_config)
        assert result["success"]
        assert temp_config.get_user() is None

    def test_check_auth_authenticated(self, temp_config: AuthConfig) -> None:
        login("dave", "pass", temp_config)
        status = check_auth(temp_config)
        assert status["authenticated"]
        assert status["username"] == "dave"

    def test_check_auth_not_authenticated(self, temp_config: AuthConfig) -> None:
        status = check_auth(temp_config)
        assert not status["authenticated"]


class TestDecorator:
    def test_requires_auth_not_logged_in(self) -> None:
        """Test that requires_auth blocks when not logged in."""

        @requires_auth
        def sample_func(args: object) -> int:
            return 0

        class FakeArgs:
            no_auth = False

        with patch("src.auth.decorators.AuthConfig.is_logged_in", return_value=False):
            result = sample_func(FakeArgs())
        assert result == 1  # Not authenticated

    def test_requires_auth_logged_in(self) -> None:
        """Test that requires_auth allows when logged in."""

        @requires_auth
        def sample_func(args: object) -> int:
            return 42

        class FakeArgs:
            no_auth = False

        with patch("src.auth.decorators.AuthConfig.is_logged_in", return_value=True):
            result = sample_func(FakeArgs())
        assert result == 42  # Authenticated

    def test_requires_auth_with_no_auth_flag(self) -> None:
        """Test that --no-auth skips the auth check."""

        @requires_auth
        def sample_func(args: object) -> int:
            return 42

        class FakeArgs:
            no_auth = True

        result = sample_func(FakeArgs())
        assert result == 42  # Skipped auth check
