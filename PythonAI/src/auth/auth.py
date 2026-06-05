from __future__ import annotations

import getpass
import hashlib
import os
import secrets
import string
import time
from typing import Any

from src.auth.config import AuthConfig


SALT_LENGTH = 16
TOKEN_LENGTH = 32
HASH_ALGO = "sha256"


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Hash a password with SHA-256 + salt.

    Returns (salt, hash_string).
    """
    if salt is None:
        salt = secrets.token_hex(SALT_LENGTH)
    hashed = hashlib.pbkdf2_hmac(
        HASH_ALGO,
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations=100_000,
    )
    return salt, hashed.hex()


def verify_password(password: str, salt: str, stored_hash: str) -> bool:
    """Verify a password against the stored salt + hash."""
    _, computed = hash_password(password, salt)
    return secrets.compare_digest(computed, stored_hash)


def generate_token(length: int = TOKEN_LENGTH) -> str:
    """Generate a cryptographically secure random token."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def login(username: str, password: str, config: AuthConfig | None = None) -> dict[str, Any]:
    """Authenticate a user and store session in config.

    First-time login for a username creates the account automatically.
    Subsequent logins verify against stored credentials.

    Returns a dict with success/error info.
    """
    cfg = config or AuthConfig()
    existing = cfg.get_user()

    if existing and existing.get("username") == username:
        # Existing user — verify password
        stored_salt = existing.get("password_salt", "")
        stored_hash = existing.get("password_hash", "")
        if not stored_salt or not stored_hash:
            return {"success": False, "error": "Corrupted credentials. Logout and try again."}
        if not verify_password(password, stored_salt, stored_hash):
            return {"success": False, "error": "Invalid password."}

    # New user or re-login: hash password and store
    salt, hashed = hash_password(password)
    token = generate_token()
    user_data = {
        "username": username,
        "password_salt": salt,
        "password_hash": hashed,
        "token": token,
        "logged_in_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    cfg.set_user(user_data)
    return {"success": True, "username": username, "token": token}


def logout(config: AuthConfig | None = None) -> dict[str, Any]:
    """Clear the current user session."""
    cfg = config or AuthConfig()
    username = cfg.get_user().get("username", "unknown") if cfg.get_user() else "unknown"
    cfg.clear_user()
    return {"success": True, "message": f"User '{username}' logged out."}


def check_auth(config: AuthConfig | None = None) -> dict[str, Any]:
    """Check authentication status."""
    cfg = config or AuthConfig()
    user = cfg.get_user()
    if user is None:
        return {"authenticated": False, "username": None}
    token = user.get("token", "")
    if not token or len(token) <= 8:
        return {"authenticated": False, "username": user.get("username")}
    return {
        "authenticated": True,
        "username": user.get("username"),
        "logged_in_at": user.get("logged_in_at", ""),
    }


def interactive_login(config: AuthConfig | None = None) -> dict[str, Any]:
    """Run an interactive login prompt in the terminal."""
    cfg = config or AuthConfig()
    print("\n🔐 Login to PythonAI")
    print("─" * 40)

    username = input("Username/Email: ").strip()
    if not username:
        return {"success": False, "error": "Username cannot be empty."}

    password = getpass.getpass("Password: ")
    if not password:
        return {"success": False, "error": "Password cannot be empty."}

    return login(username, password, cfg)
