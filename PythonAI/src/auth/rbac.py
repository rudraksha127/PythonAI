"""
ForgeAI RBAC — Role-Based Access Control + Multi-Tenancy
=========================================================

Provides role-based access control for ForgeAI with:
  - Built-in roles: admin, manager, developer
  - Per-project access isolation
  - Permission checking for API endpoints
  - Decorator-based route protection

Usage:
    from src.auth.rbac import rbac, require_role, require_project_access

    @require_role("admin")
    async def admin_only_endpoint():
        ...

    @require_project_access
    async def project_endpoint(project_id: str):
        ...
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import HTTPException


# ═══════════════════════════════════════
# Roles & Permissions
# ═══════════════════════════════════════

ROLES = {
    "admin": {
        "description": "Full system access",
        "permissions": [
            "projects:create", "projects:read", "projects:update", "projects:delete",
            "projects:list",
            "training:trigger", "training:configure", "training:view",
            "users:manage", "users:invite",
            "settings:read", "settings:write",
            "analytics:view", "analytics:export",
            "logs:view", "logs:export",
        ],
    },
    "manager": {
        "description": "Project management access",
        "permissions": [
            "projects:create", "projects:read", "projects:update",
            "projects:list",
            "training:trigger", "training:view",
            "analytics:view",
            "settings:read",
        ],
    },
    "developer": {
        "description": "Basic developer access",
        "permissions": [
            "projects:read",
            "projects:list",
            "training:view",
            "analytics:view",
        ],
    },
}

DEFAULT_ROLE = "developer"


# ═══════════════════════════════════════
# RBAC Manager
# ═══════════════════════════════════════


@dataclass
class UserRole:
    """A user with role and project access."""

    username: str
    role: str = DEFAULT_ROLE
    projects: list[str] = field(default_factory=list)  # Project IDs this user can access
    created_at: float = 0.0
    is_active: bool = True


class RBACManager:
    """Manages user roles and permissions with file-based persistence."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self._data_dir = Path(data_dir) if data_dir else Path.home() / ".forgeai" / "auth"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._users_path = self._data_dir / "users.json"
        self._users: dict[str, UserRole] = {}
        self._load()

    def has_permission(self, username: str, permission: str) -> bool:
        """Check if a user has a specific permission based on their role."""
        user = self._users.get(username)
        if user is None or not user.is_active:
            return False

        role_perms = ROLES.get(user.role, ROLES[DEFAULT_ROLE])["permissions"]
        return permission in role_perms

    def has_project_access(self, username: str, project_id: str) -> bool:
        """Check if a user has access to a specific project."""
        user = self._users.get(username)
        if user is None or not user.is_active:
            return False

        # Admin can access all projects
        if user.role == "admin":
            return True

        return project_id in user.projects

    def assign_role(self, username: str, role: str) -> bool:
        """Assign a role to a user. Creates user if not exists."""
        if role not in ROLES:
            return False

        if username not in self._users:
            self._users[username] = UserRole(
                username=username,
                role=role,
                created_at=time.time(),
            )
        else:
            self._users[username].role = role

        self._save()
        return True

    def grant_project_access(self, username: str, project_id: str) -> bool:
        """Grant a user access to a project."""
        if username not in self._users:
            return False

        user = self._users[username]
        if project_id not in user.projects:
            user.projects.append(project_id)
            self._save()

        return True

    def revoke_project_access(self, username: str, project_id: str) -> bool:
        """Revoke a user's access to a project."""
        if username not in self._users:
            return False

        user = self._users[username]
        if project_id in user.projects:
            user.projects.remove(project_id)
            self._save()

        return True

    def get_user(self, username: str) -> dict[str, Any] | None:
        """Get user details."""
        user = self._users.get(username)
        if user is None:
            return None
        return {
            "username": user.username,
            "role": user.role,
            "projects": user.projects,
            "created_at": user.created_at,
            "is_active": user.is_active,
        }

    def list_users(self) -> list[dict[str, Any]]:
        """List all users."""
        return [
            {
                "username": u.username,
                "role": u.role,
                "projects": u.projects,
                "created_at": u.created_at,
                "is_active": u.is_active,
            }
            for u in self._users.values()
        ]

    def get_role_permissions(self, role: str) -> list[str]:
        """Get permissions for a role."""
        role_info = ROLES.get(role)
        if role_info is None:
            return []
        return role_info["permissions"]

    # ─── Persistence ──────────────────────────────────────────────

    def _save(self) -> None:
        data = {
            "users": {
                username: {
                    "username": u.username,
                    "role": u.role,
                    "projects": u.projects,
                    "created_at": u.created_at,
                    "is_active": u.is_active,
                }
                for username, u in self._users.items()
            },
            "updated_at": time.time(),
        }
        self._users_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load(self) -> None:
        if not self._users_path.exists():
            return
        try:
            data = json.loads(self._users_path.read_text(encoding="utf-8"))
            for username, u_data in data.get("users", {}).items():
                self._users[username] = UserRole(
                    username=u_data["username"],
                    role=u_data.get("role", DEFAULT_ROLE),
                    projects=u_data.get("projects", []),
                    created_at=u_data.get("created_at", 0.0),
                    is_active=u_data.get("is_active", True),
                )
        except (json.JSONDecodeError, KeyError):
            pass


# ═══════════════════════════════════════
# FastAPI Dependency Helpers
# ═══════════════════════════════════════

def require_role(required_role: str):
    """Decorator factory: require a specific role to access an endpoint.

    Usage:
        @router.get("/admin")
        @require_role("admin")
        async def admin_only():
            return {"message": "admin only"}
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Extract username from request context (set by auth middleware)
            request = kwargs.get("request")
            username = getattr(request, "user", None) if request else None

            if not username:
                raise HTTPException(status_code=401, detail="Not authenticated")

            manager = RBACManager()
            user = manager.get_user(username)
            if user is None:
                raise HTTPException(status_code=403, detail="User not found")

            role_perms = ROLES.get(required_role, ROLES[DEFAULT_ROLE])["permissions"]
            for perm in role_perms:
                if manager.has_permission(username, perm):
                    return await func(*args, **kwargs)

            raise HTTPException(
                status_code=403,
                detail=f"Requires role: {required_role}",
            )
        return wrapper
    return decorator


_rbac_manager: RBACManager | None = None


def get_rbac_manager() -> RBACManager:
    """Get or create the global RBAC manager."""
    global _rbac_manager
    if _rbac_manager is None:
        _rbac_manager = RBACManager()
    return _rbac_manager


__all__ = [
    "RBACManager",
    "UserRole",
    "ROLES",
    "get_rbac_manager",
    "require_role",
]
