"""pytest configuration for PythonAI tests."""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register custom pytest markers to eliminate warnings."""
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests (requires real providers/MCP). "
        "These tests are run alongside unit tests by default but can be filtered "
        "with `-m integration` or excluded with `-m 'not integration'`.",
    )
