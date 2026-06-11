from __future__ import annotations

import json
import stat
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".pythonai"
CONFIG_FILE = CONFIG_DIR / "config.json"


def _default_config() -> dict[str, Any]:
    return {
        "user": None,
        "settings": {
            "offline_mode": False,
            "default_model": "qwen2.5-coder:14b",
        },
    }


class AuthConfig:
    """Manages reading/writing the auth config file at ~/.pythonai/config.json."""

    def __init__(self, config_path: Path = CONFIG_FILE) -> None:
        self.config_path = config_path

    def load(self) -> dict[str, Any]:
        """Load config from disk, returning defaults if missing."""
        if not self.config_path.exists():
            return _default_config()
        try:
            with self.config_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return _default_config()

    def save(self, data: dict[str, Any]) -> None:
        """Save config to disk with restricted permissions."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.config_path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        # Restrict to owner-only read/write
        try:
            tmp.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass
        tmp.replace(self.config_path)

    def get_user(self) -> dict[str, Any] | None:
        """Return user data dict or None if not logged in."""
        return self.load().get("user")

    def set_user(self, user_data: dict[str, Any]) -> None:
        """Set user data and save."""
        config = self.load()
        config["user"] = user_data
        self.save(config)

    def clear_user(self) -> None:
        """Remove user data from config."""
        config = self.load()
        config["user"] = None
        self.save(config)

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting value."""
        return self.load().get("settings", {}).get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        """Set a setting value and save."""
        config = self.load()
        config.setdefault("settings", {})[key] = value
        self.save(config)

    def is_logged_in(self) -> bool:
        """Check if a user is currently logged in with a valid token."""
        user = self.get_user()
        if user is None:
            return False
        token = user.get("token", "")
        return bool(token and len(token) > 8)
