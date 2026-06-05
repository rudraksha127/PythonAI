"""
Ollama model registry for the RAG engine.

Manages available models, their metadata, and resolution logic.
Supports CLI (list / add / remove) and programmatic usage.
"""

from __future__ import annotations

import json
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any


# ═══════════════════════════════════════
#  File & model metadata
# ═══════════════════════════════════════

CONFIG_DIR = Path.home() / ".pythonai"
MODELS_FILE = CONFIG_DIR / "models.json"

DEFAULT_MODEL = "qwen2.5-coder:14b"

# Pre-defined recommended models with metadata
RECOMMENDED_MODELS: dict[str, dict[str, str]] = {
    "qwen2.5-coder:14b": {
        "description": "Qwen 2.5 Coder 14B — best for Python (default)",
        "size": "~9 GB",
        "tags": "python, coding, recommended",
    },
    "qwen2.5-coder:7b": {
        "description": "Qwen 2.5 Coder 7B — faster, lighter",
        "size": "~4.5 GB",
        "tags": "python, coding, fast",
    },
    "qwen2.5-coder:1.5b": {
        "description": "Qwen 2.5 Coder 1.5B — quick responses",
        "size": "~1 GB",
        "tags": "python, coding, tiny",
    },
    "deepseek-coder:6.7b": {
        "description": "DeepSeek Coder 6.7B — strong coding model",
        "size": "~4 GB",
        "tags": "coding, alternative",
    },
    "codellama:7b": {
        "description": "Code Llama 7B — Meta's code-focused model",
        "size": "~4 GB",
        "tags": "coding, meta",
    },
    "llama3.2:3b": {
        "description": "Llama 3.2 3B — fast general purpose",
        "size": "~2 GB",
        "tags": "general, fast",
    },
    "mistral:7b": {
        "description": "Mistral 7B — strong general model",
        "size": "~4.5 GB",
        "tags": "general, alternative",
    },
}


# ═══════════════════════════════════════
#  I/O helpers
# ═══════════════════════════════════════

def _ensure_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _load() -> dict[str, dict[str, str]]:
    """Return {model_name: metadata_dict}."""
    if not MODELS_FILE.exists():
        return {}
    try:
        with MODELS_FILE.open("r", encoding="utf-8") as f:
            data: dict[str, dict[str, str]] = json.load(f)
            return data
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict[str, dict[str, str]]) -> None:
    _ensure_dir()
    tmp = MODELS_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    try:
        tmp.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    tmp.replace(MODELS_FILE)


# ═══════════════════════════════════════
#  Public API
# ═══════════════════════════════════════

def list_configured_models() -> dict[str, dict[str, str]]:
    """Return {model_name: metadata} for all configured models.

    Merges user-added models from config with hardcoded RECOMMENDED_MODELS.
    User config overrides descriptions for same model name.
    """
    configured = _load()
    merged = dict(RECOMMENDED_MODELS)
    merged.update(configured)
    return merged


def list_ollama_models() -> list[str]:
    """Return list of models currently available in local Ollama."""
    if not shutil.which("ollama"):
        return []
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=20,
        )
        if result.returncode != 0:
            return []
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        models = []
        for line in lines[1:]:  # Skip header
            parts = line.split()
            if parts:
                models.append(parts[0])
        return models
    except (subprocess.TimeoutExpired, OSError):
        return []


def get_ollama_model_info(model_name: str) -> dict[str, Any] | None:
    """Get detailed info about an Ollama model via `ollama show`."""
    if not shutil.which("ollama"):
        return None
    try:
        result = subprocess.run(
            ["ollama", "show", model_name],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return None
        info = {"name": model_name}
        for line in result.stdout.splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                info[key.strip().lower()] = val.strip()
        return info
    except (subprocess.TimeoutExpired, OSError):
        return None


def is_model_available(model_name: str) -> bool:
    """Check if a model is available in local Ollama."""
    available = list_ollama_models()
    return model_name in available


def add_model(model_name: str, description: str = "", tags: str = "") -> dict[str, Any]:
    """Register a model in the config. Returns result dict."""
    model_name = model_name.strip()
    if not model_name:
        return {"success": False, "error": "Model name cannot be empty."}

    data = _load()
    entry: dict[str, str] = {}
    if description:
        entry["description"] = description
    if tags:
        entry["tags"] = tags
    if not entry:
        entry = {"description": model_name}
    data[model_name] = entry
    _save(data)
    return {"success": True, "model": model_name}


def remove_model(model_name: str) -> dict[str, Any]:
    """Remove a model from config. Returns result dict."""
    model_name = model_name.strip()
    data = _load()
    if model_name not in data:
        return {"success": False, "error": f"Model '{model_name}' not found in config."}
    del data[model_name]
    _save(data)
    return {"success": True, "model": model_name}


def get_model_info(model_name: str) -> dict[str, str]:
    """Get metadata for a model from config or recommended list."""
    merged = list_configured_models()
    return merged.get(model_name, {"description": model_name, "tags": ""})


def resolve_model(
    model_name: str,
    available: list[str] | None = None,
) -> str:
    """Resolve a model name to an available model with fallback.

    Priority:
      1. Requested model if available in Ollama
      2. Attempt to pull the requested model
      3. Fall back to DEFAULT_MODEL
      4. Fall back to first available model
      5. Return DEFAULT_MODEL as-is (ollama will error if not found)
    """
    if available is None:
        available = list_ollama_models()

    # 1. Requested model available
    if model_name in available:
        return model_name

    # 2. Try to pull the model
    if shutil.which("ollama"):
        try:
            result = subprocess.run(
                ["ollama", "pull", model_name],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                return model_name
        except (subprocess.TimeoutExpired, OSError):
            pass

    # 3. Fall back to default
    if DEFAULT_MODEL in available:
        return DEFAULT_MODEL

    # 4. Fall back to first available
    if available:
        return available[0]

    # 5. Return requested (ollama will handle the error)
    return model_name
