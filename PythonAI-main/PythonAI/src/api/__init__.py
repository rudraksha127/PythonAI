"""
PythonAI API Server — Phase 9 Deployment & Serving.

Usage:
    python -m src.cli serve --port 8765
    uvicorn src.api.server:app --host 0.0.0.0 --port 8765
"""

from src.api.server import app  # noqa: F401

__all__ = ["app"]
