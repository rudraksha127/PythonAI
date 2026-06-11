"""
Provider Profile — Persist & Manage Provider Selection
=======================================================
Inspired by OpenClaude's providerProfile.ts system.
Saves provider selection to a JSON file so the user's
choice persists across sessions.

Profile file: ~/.pythonai/provider-profile.json
"""

from __future__ import annotations

import json
import os
import stat
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_PROFILE_PATH = Path.home() / ".pythonai" / "provider-profile.json"
CONFIG_DIR = Path.home() / ".pythonai"


@dataclass
class ProviderProfile:
    """Saved provider profile."""
    provider: str                         # "openai", "deepseek", "ollama", etc.
    model: str = ""                       # Specific model, empty = default
    label: str = ""                       # User-friendly label
    base_url: str = ""                    # Custom base URL
    api_key_to_check: str = ""            # Last 4 chars of key for identification
    strategy: str = "auto"                # RouteStrategy
    updated_at: str = ""                  # ISO timestamp
    goal: str = "coding"                  # "coding", "latency", "balanced"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProviderProfile:
        return cls(
            provider=data.get("provider", "auto"),
            model=data.get("model", ""),
            label=data.get("label", ""),
            base_url=data.get("base_url", ""),
            api_key_to_check=data.get("api_key_to_check", ""),
            strategy=data.get("strategy", "auto"),
            updated_at=data.get("updated_at", ""),
            goal=data.get("goal", "coding"),
        )


class ProfileManager:
    """
    Manages provider profile persistence.

    Features:
    - Save current provider selection to file
    - Load saved selection at startup
    - List available profiles
    - Switch between providers
    """

    def __init__(self, profile_path: Path | str | None = None):
        self._profile_path = Path(profile_path) if profile_path else DEFAULT_PROFILE_PATH
        self._ensure_config_dir()

    # ── Path Helpers ────────────────────────────────────────

    @staticmethod
    def _ensure_config_dir() -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def profile_path(self) -> Path:
        return self._profile_path

    # ── Load / Save ─────────────────────────────────────────

    def load(self) -> ProviderProfile | None:
        """Load the saved provider profile, or None if not set."""
        if not self._profile_path.exists():
            return None

        try:
            data = json.loads(self._profile_path.read_text(encoding="utf-8"))
            return ProviderProfile.from_dict(data)
        except (json.JSONDecodeError, OSError):
            return None

    def save(self, profile: ProviderProfile) -> Path:
        """Save a provider profile to disk."""
        self._ensure_config_dir()
        # Update timestamp
        profile.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Write atomically
        tmp = self._profile_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(profile.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        try:
            tmp.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        tmp.replace(self._profile_path)

        return self._profile_path

    def delete(self) -> bool:
        """Delete the saved profile."""
        if self._profile_path.exists():
            self._profile_path.unlink()
            return True
        return False

    def exists(self) -> bool:
        """Check if a profile has been saved."""
        return self._profile_path.exists()

    # ── Convenience ─────────────────────────────────────────

    def set_provider(
        self,
        provider: str,
        model: str = "",
        base_url: str = "",
        strategy: str = "auto",
        goal: str = "coding",
    ) -> ProviderProfile:
        """Set and save a provider profile."""
        # Try to determine the last 4 chars of the API key for identification
        api_key_suffix = ""
        provider_env_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "mistral": "MISTRAL_API_KEY",
            "groq": "GROQ_API_KEY",
            "xai": "XAI_API_KEY",
        }
        env_key = provider_env_map.get(provider)
        if env_key:
            key = os.environ.get(env_key, "")
            if len(key) > 8:
                api_key_suffix = f"...{key[-4:]}"

        # Also check apikeys storage
        if not api_key_suffix:
            try:
                from src.data.apikeys import get_key
                key = get_key(provider)
                if key and len(key) > 8:
                    api_key_suffix = f"...{key[-4:]}"
            except ImportError:
                pass

        # Get label from registry
        label = provider.upper() if len(provider) <= 4 else provider.capitalize()
        try:
            from .registry import get_registry
            provider_info = get_registry().get_provider(provider)
            if provider_info:
                label = provider_info.label
        except ImportError:
            pass

        profile = ProviderProfile(
            provider=provider,
            model=model,
            label=label,
            base_url=base_url,
            api_key_to_check=api_key_suffix,
            strategy=strategy,
            goal=goal,
        )
        self.save(profile)
        return profile

    def get_current(self) -> dict[str, Any]:
        """Get current profile info for display."""
        profile = self.load()
        if not profile:
            return {
                "provider": "auto",
                "model": "",
                "label": "Automatic",
                "is_saved": False,
            }

        return {
            "provider": profile.provider,
            "model": profile.model,
            "label": profile.label or profile.provider.capitalize(),
            "base_url": profile.base_url,
            "strategy": profile.strategy,
            "goal": profile.goal,
            "updated_at": profile.updated_at,
            "is_saved": True,
        }
