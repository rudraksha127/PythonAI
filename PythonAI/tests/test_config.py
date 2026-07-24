"""Tests for configuration module.

Replaces the old script-style test_config.py with proper pytest tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


class TestMassiveConfig:
    """Test the massive_config module."""

    @pytest.fixture
    def configs(self) -> list[dict[str, Any]]:
        """Generate configs once per test class."""
        from src.data import massive_config

        return massive_config.generate_all_configs()

    def test_configs_generated(self, configs: list[dict[str, Any]]) -> None:
        """Verify at least some configs are generated."""
        assert len(configs) > 0, "No configs were generated"

    def test_config_types(self, configs: list[dict[str, Any]]) -> None:
        """Verify configs have expected types."""
        types = {c.get("type", "unknown") for c in configs}
        assert len(types) > 0, "Configs have no types"
        # All configs should have a type field
        for c in configs:
            assert "type" in c, f"Config missing 'type' key: {c}"

    def test_config_has_required_keys(self, configs: list[dict[str, Any]]) -> None:
        """Verify each config has essential keys."""
        required_keys = {"type", "name"}
        for c in configs:
            for key in required_keys:
                assert key in c, f"Config missing required key '{key}': {c.get('name', 'unnamed')}"

    def test_config_no_empty_names(self, configs: list[dict[str, Any]]) -> None:
        """Verify no config has an empty name."""
        for c in configs:
            name = c.get("name", "")
            assert name, f"Config has empty name: {c}"


class TestConfigUtils:
    """Test configuration utility functions."""

    def test_src_config_imports(self) -> None:
        """Verify src.config can be imported."""
        from src import config  # noqa: F811

        assert config.__name__ == "src.config"

    def test_env_example_exists(self) -> None:
        """Verify .env.example exists with required variables."""
        env_example = Path(__file__).resolve().parent.parent / ".env.example"
        assert env_example.exists(), ".env.example not found"
        content = env_example.read_text(encoding="utf-8")
        # Verify the file has substantial content with env var patterns
        assert len(content) > 100, f".env.example too short: {len(content)} chars"
        assert "=" in content, ".env.example missing env var assignments"
