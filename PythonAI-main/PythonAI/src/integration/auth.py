"""
ForgeAI Shared Authentication — Ek JWT Token, Sab Projects Mein
================================================================

Central authentication hub that provides:

  1. JWT token generation & validation (shared across all projects)
  2. User management (stored in ~/.forgeai/auth/users.json)
  3. API key management for service-to-service calls
  4. Role-based access control (admin, developer, viewer)

Architecture:
  ┌──────────────┐     ┌──────────────────┐
  │  PythonAI    │────▶│  Auth Hub        │
  │  (Core)      │     │  ~/.forgeai/auth/ │
  └──────────────┘     └────────┬─────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
       ┌────────────┐   ┌────────────┐   ┌────────────┐
       │ Rudra-bots │   │ Dashboard  │   │open-claude │
       └────────────┘   └────────────┘   └────────────┘

Usage:
    from src.integration.auth import ForgeAIAuth

    auth = ForgeAIAuth()
    token = auth.create_token("user@example.com", "developer")
    user = auth.validate_token(token)
"""

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("forgeai.integration.auth")

AUTH_DIR = Path.home() / ".forgeai" / "auth"
USERS_FILE = AUTH_DIR / "users.json"
TOKENS_FILE = AUTH_DIR / "tokens.json"
SECRET_KEY_FILE = AUTH_DIR / "secret.key"

# Default roles and their permissions
ROLES = {
    "admin": {"can_train": True, "can_manage_users": True, "can_view_all": True, "can_delete": True},
    "developer": {"can_train": True, "can_manage_users": False, "can_view_all": True, "can_delete": False},
    "viewer": {"can_train": False, "can_manage_users": False, "can_view_all": True, "can_delete": False},
    "api": {"can_train": False, "can_manage_users": False, "can_view_all": False, "can_delete": False},
}


@dataclass
class ForgeAIUser:
    """A user in the ForgeAI ecosystem."""

    username: str
    email: str
    role: str = "developer"
    password_hash: str = ""
    created_at: float = field(default_factory=time.time)
    is_active: bool = True
    user_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "password_hash": self.password_hash,
            "created_at": self.created_at,
            "is_active": self.is_active,
            "user_id": self.user_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ForgeAIUser:
        return cls(
            username=data["username"],
            email=data.get("email", ""),
            role=data.get("role", "developer"),
            password_hash=data.get("password_hash", ""),
            created_at=data.get("created_at", time.time()),
            is_active=data.get("is_active", True),
            user_id=data.get("user_id", str(uuid.uuid4())),
        )


@dataclass
class ForgeAIToken:
    """A JWT-like token for cross-project authentication."""

    token: str
    user_id: str
    username: str
    email: str
    role: str
    permissions: dict[str, bool]
    issued_at: float
    expires_at: float
    is_service_token: bool = False

    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def has_permission(self, permission: str) -> bool:
        return self.permissions.get(permission, False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "permissions": self.permissions,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "is_service_token": self.is_service_token,
        }


class ForgeAIAuth:
    """Central authentication for the ForgeAI ecosystem.

    Manages users, issues JWT-style tokens, and validates
    authentication across all ecosystem projects.
    """

    def __init__(self, secret_key: str | None = None):
        AUTH_DIR.mkdir(parents=True, exist_ok=True)

        if secret_key:
            self.secret_key = secret_key
        else:
            self.secret_key = self._load_or_generate_secret()

        self._users: dict[str, ForgeAIUser] = {}
        self._load_users()

    def _load_or_generate_secret(self) -> str:
        """Load existing secret key or generate a new one."""
        if SECRET_KEY_FILE.exists():
            return SECRET_KEY_FILE.read_text(encoding="utf-8").strip()
        secret = os.urandom(32).hex()
        SECRET_KEY_FILE.write_text(secret, encoding="utf-8")
        logger.info(f"Generated new auth secret at {SECRET_KEY_FILE}")
        return secret

    def _load_users(self):
        """Load users from disk."""
        if USERS_FILE.exists():
            try:
                data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
                self._users = {name: ForgeAIUser.from_dict(u) for name, u in data.items()}
            except Exception as e:
                logger.warning(f"Failed to load users: {e}")
                self._users = {}

    def _save_users(self):
        """Save users to disk."""
        USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {name: user.to_dict() for name, user in self._users.items()}
        USERS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _hash_password(self, password: str) -> str:
        """Hash a password using hashlib.scrypt (memory-hard, brute-force resistant)."""
        salt = os.urandom(16)
        key = hashlib.scrypt(
            password.encode(),
            salt=salt,
            n=16384,  # CPU/memory cost
            r=8,      # block size
            p=1,      # parallelization
            dklen=32, # output length
        )
        return f"{salt.hex()}:{key.hex()}"

    def _verify_password(self, password: str, stored_hash: str) -> bool:
        """Verify a password against its stored hash."""
        try:
            salt_hex, key_hex = stored_hash.split(":")
            salt = bytes.fromhex(salt_hex)
            expected = hashlib.scrypt(
                password.encode(),
                salt=salt,
                n=16384,
                r=8,
                p=1,
                dklen=32,
            )
            return hmac.compare_digest(expected.hex(), key_hex)
        except (ValueError, AttributeError, TypeError):
            return False

    def _generate_token_id(self) -> str:
        """Generate a unique token ID."""
        return hashlib.sha256(os.urandom(32)).hexdigest()[:32]

    def _sign_token(self, payload: dict[str, Any]) -> str:
        """Sign a token payload with HMAC-SHA256."""
        payload_str = json.dumps(payload, sort_keys=True)
        signature = hmac.new(
            self.secret_key.encode(),
            payload_str.encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"{payload_str}.{signature}"

    def _verify_token_signature(self, token_str: str) -> dict[str, Any] | None:
        """Verify a token's signature and return the payload."""
        try:
            payload_str, signature = token_str.rsplit(".", 1)
            expected = hmac.new(
                self.secret_key.encode(),
                payload_str.encode(),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(expected, signature):
                return None
            return json.loads(payload_str)
        except (ValueError, json.JSONDecodeError, AttributeError):
            return None

    # ── User Management ────────────────────────────────────────────

    def create_user(
        self,
        username: str,
        password: str,
        email: str = "",
        role: str = "developer",
    ) -> dict[str, Any]:
        """Create a new user in the ecosystem."""
        if username in self._users:
            return {"success": False, "error": "User already exists"}

        if role not in ROLES:
            return {"success": False, "error": f"Invalid role: {role}. Valid: {list(ROLES.keys())}"}

        user = ForgeAIUser(
            username=username,
            email=email,
            role=role,
            password_hash=self._hash_password(password),
        )
        self._users[username] = user
        self._save_users()

        logger.info(f"User created: {username} ({role})")
        return {"success": True, "user_id": user.user_id, "username": username, "role": role}

    def authenticate(self, username: str, password: str) -> dict[str, Any]:
        """Authenticate a user and return a token."""
        user = self._users.get(username)
        if not user:
            return {"success": False, "error": "User not found"}
        if not user.is_active:
            return {"success": False, "error": "User is deactivated"}
        if not self._verify_password(password, user.password_hash):
            return {"success": False, "error": "Invalid password"}

        token = self.create_token(username, user.role)
        return {"success": True, "token": token.token, "user": {"username": username, "role": user.role, "email": user.email}}

    def create_token(self, username: str, role: str = "developer", expires_in_days: int = 30) -> ForgeAIToken:
        """Create a signed token for a user."""
        permissions = ROLES.get(role, ROLES["developer"])
        now = time.time()

        payload = {
            "token_id": self._generate_token_id(),
            "username": username,
            "role": role,
            "permissions": permissions,
            "issued_at": now,
            "expires_at": now + (expires_in_days * 86400),
            "is_service_token": role == "api",
        }

        token_str = self._sign_token(payload)

        user_obj = self._users.get(username)
        user_email = user_obj.email if user_obj else ""
        return ForgeAIToken(
            token=token_str,
            user_id=payload["token_id"],
            username=username,
            email=user_email,
            role=role,
            permissions=permissions,
            issued_at=now,
            expires_at=payload["expires_at"],
            is_service_token=role == "api",
        )

    def validate_token(self, token_str: str) -> ForgeAIToken | None:
        """Validate a token and return its data.

        Returns None if invalid or expired.
        """
        payload = self._verify_token_signature(token_str)
        if payload is None:
            return None

        now = time.time()
        if now > payload.get("expires_at", 0):
            logger.debug(f"Token expired for user: {payload.get('username', 'unknown')}")
            return None

        # Check if user still exists and is active
        username = payload.get("username", "")
        user = self._users.get(username)
        if user and not user.is_active:
            logger.warning(f"Token used for deactivated user: {username}")
            return None

        return ForgeAIToken(
            token=token_str,
            user_id=payload.get("token_id", ""),
            username=username,
            email=user.email if user else "",
            role=payload.get("role", "viewer"),
            permissions=payload.get("permissions", ROLES["viewer"]),
            issued_at=payload.get("issued_at", now),
            expires_at=payload.get("expires_at", now),
            is_service_token=payload.get("is_service_token", False),
        )

    def create_service_token(self, service_name: str, expires_in_days: int = 365) -> ForgeAIToken:
        """Create a service-to-service API token.

        These tokens are used for inter-project communication
        (e.g., PythonAI → Rudra-bots, Dashboard → PythonAI).
        """
        now = time.time()
        permissions = {
            "can_read_metrics": True,
            "can_write_events": True,
            "can_trigger_training": True,
            "can_read_projects": True,
        }

        payload = {
            "token_id": self._generate_token_id(),
            "username": f"service:{service_name}",
            "role": "api",
            "permissions": permissions,
            "issued_at": now,
            "expires_at": now + (expires_in_days * 86400),
            "is_service_token": True,
        }

        token_str = self._sign_token(payload)

        return ForgeAIToken(
            token=token_str,
            user_id=payload["token_id"],
            username=f"service:{service_name}",
            email="",
            role="api",
            permissions=permissions,
            issued_at=now,
            expires_at=payload["expires_at"],
            is_service_token=True,
        )

    def list_users(self) -> list[dict[str, Any]]:
        """List all registered users (without password hashes)."""
        return [
            {
                "username": u.username,
                "email": u.email,
                "role": u.role,
                "is_active": u.is_active,
                "created_at": u.created_at,
                "user_id": u.user_id,
            }
            for u in self._users.values()
        ]

    def get_status(self) -> dict[str, Any]:
        """Get authentication system status."""
        return {
            "enabled": True,
            "users_count": len(self._users),
            "users": self.list_users(),
            "auth_dir": str(AUTH_DIR),
            "secret_key_exists": SECRET_KEY_FILE.exists(),
        }


# ── FastAPI Integration ─────────────────────────────────────────


def create_auth_router(auth_instance: ForgeAIAuth):
    """Create a FastAPI router with auth endpoints.

    Usage:
        from src.integration.auth import ForgeAIAuth, create_auth_router
        auth = ForgeAIAuth()
        app.include_router(create_auth_router(auth))

    Note: auth_instance is required — each call uses the SAME instance
    so that user state is shared across all routes.
    """
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel

    router = APIRouter(prefix="/api/auth", tags=["ForgeAI Auth"])
    auth = auth_instance

    class LoginRequest(BaseModel):
        username: str
        password: str

    class SignupRequest(BaseModel):
        username: str
        password: str
        email: str = ""
        role: str = "developer"

    class VerifyRequest(BaseModel):
        token: str

    @router.post("/login")
    async def login(body: LoginRequest):
        result = auth.authenticate(body.username, body.password)
        if not result["success"]:
            raise HTTPException(status_code=401, detail=result["error"])
        return result

    @router.post("/signup")
    async def signup(body: SignupRequest):
        result = auth.create_user(body.username, body.password, body.email, body.role)
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    @router.get("/status")
    async def auth_status():
        return auth.get_status()

    @router.post("/verify")
    async def verify_token(body: VerifyRequest):
        result = auth.validate_token(body.token)
        if result is None:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return result.to_dict()

    return router


# ── CLI Interface ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ForgeAI Authentication Manager")
    subparsers = parser.add_subparsers(dest="command")

    create_parser = subparsers.add_parser("create-user", help="Create a new user")
    create_parser.add_argument("username")
    create_parser.add_argument("password")
    create_parser.add_argument("--email", default="")
    create_parser.add_argument("--role", default="developer", choices=list(ROLES.keys()))

    token_parser = subparsers.add_parser("create-token", help="Create a token for a user")
    token_parser.add_argument("username")
    token_parser.add_argument("--days", type=int, default=30)

    verify_parser = subparsers.add_parser("verify", help="Verify a token")
    verify_parser.add_argument("token")

    svc_parser = subparsers.add_parser("service-token", help="Create a service token")
    svc_parser.add_argument("service_name")

    list_parser = subparsers.add_parser("list-users", help="List all users")

    args = parser.parse_args()
    auth = ForgeAIAuth()

    if args.command == "create-user":
        result = auth.create_user(args.username, args.password, args.email, args.role)
        if result["success"]:
            print(f"✅ User created: {args.username} ({args.role})")
        else:
            print(f"❌ {result['error']}")

    elif args.command == "create-token":
        token = auth.create_token(args.username, expires_in_days=args.days)
        print(f"Token: {token.token}")
        print(f"Expires: {datetime.fromtimestamp(token.expires_at, tz=timezone.utc).isoformat()}")
        print(f"Role: {token.role}")

    elif args.command == "verify":
        result = auth.validate_token(args.token)
        if result:
            print(f"✅ Valid token")
            print(f"  User: {result.username}")
            print(f"  Role: {result.role}")
            print(f"  Expires: {datetime.fromtimestamp(result.expires_at, tz=timezone.utc).isoformat()}")
        else:
            print("❌ Invalid or expired token")

    elif args.command == "service-token":
        token = auth.create_service_token(args.service_name)
        print(f"Service Token ({args.service_name}):")
        print(f"  Token: {token.token}")
        print(f"  Expires: {datetime.fromtimestamp(token.expires_at, tz=timezone.utc).isoformat()}")

    elif args.command == "list-users":
        users = auth.list_users()
        if not users:
            print("No users registered.")
        else:
            print(f"Users ({len(users)}):")
            for u in users:
                print(f"  - {u['username']} ({u['role']}) {'✓' if u['is_active'] else '✗'}")

    else:
        parser.print_help()
