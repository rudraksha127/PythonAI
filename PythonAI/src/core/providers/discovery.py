"""
Provider Discovery — Find Available Local Models
=================================================
Inspired by OpenClaude's providerDiscovery.ts.
Discovers:
- Ollama models installed locally
- OpenAI-compatible endpoints (LM Studio, LocalAI, vLLM, etc.)
- Atomic Chat models
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

# ═══════════════════════════════════════
#  Ollama Discovery
# ═══════════════════════════════════════

@dataclass
class OllamaModelInfo:
    """Information about an installed Ollama model."""
    name: str
    size_bytes: int = 0
    parameter_size: str = ""
    quantization: str = ""
    modified_at: str = ""


def discover_ollama_models(ollama_host: str = "http://localhost:11434") -> list[dict[str, Any]]:
    """
    Discover installed Ollama models via ollama CLI or API.

    Returns list of model dicts with name, size, parameter_size, etc.
    """
    models = []

    # Method 1: Try ollama CLI
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            for line in lines[1:]:  # Skip header
                parts = line.split()
                if parts:
                    name = parts[0]
                    size_str = parts[-1] if len(parts) > 1 else ""
                    models.append({
                        "name": name,
                        "size": size_str,
                        "source": "ollama_cli",
                    })
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # Method 2: Try Ollama API
    if not models:
        try:
            req = Request(f"{ollama_host}/api/tags", method="GET")
            resp = urlopen(req, timeout=5)
            data = json.loads(resp.read().decode())
            for m in data.get("models", []):
                models.append({
                    "name": m.get("name", "unknown"),
                    "size_bytes": m.get("size", 0),
                    "parameter_size": m.get("details", {}).get("parameter_size", ""),
                    "quantization": m.get("details", {}).get("quantization_level", ""),
                    "source": "ollama_api",
                })
        except (URLError, json.JSONDecodeError, OSError):
            pass

    return models


# ═══════════════════════════════════════
#  OpenAI-Compatible Endpoint Discovery
# ═══════════════════════════════════════

@dataclass
class OpenAICompatibleEndpoint:
    """Information about an OpenAI-compatible endpoint."""
    base_url: str
    label: str
    source: str  # "env", "lm_studio", "ollama", "localai", "vllm", "custom"


def discover_openai_compatible_models(
    base_url: str = "",
    api_key: str = "",
) -> list[dict[str, Any]]:
    """
    Discover models from an OpenAI-compatible endpoint's /models endpoint.

    Returns list of model dicts with id, owned_by, etc.
    """
    url = base_url or os.environ.get("OPENAI_BASE_URL", "")
    if not url:
        return []

    # Normalize URL
    url = url.rstrip("/")
    if not url.endswith("/models"):
        url = f"{url}/models"

    key = api_key or os.environ.get("OPENAI_API_KEY", "")

    try:
        req = Request(url, method="GET")
        if key:
            req.add_header("Authorization", f"Bearer {key}")
        req.add_header("Content-Type", "application/json")

        resp = urlopen(req, timeout=5)
        data = json.loads(resp.read().decode())

        models = []
        for m in data.get("data", []):
            models.append({
                "id": m.get("id", "unknown"),
                "object": m.get("object", "model"),
                "owned_by": m.get("owned_by", ""),
            })
        return models

    except (URLError, json.JSONDecodeError, OSError, ValueError):
        return []


# ═══════════════════════════════════════
#  Combined Discovery
# ═══════════════════════════════════════

def discover_all_local() -> dict[str, list[dict[str, Any]]]:
    """
    Discover all locally available models from all sources.

    Returns:
        {
            "ollama": [...],
            "openai_compatible": [...],
        }
    """
    result: dict[str, list[dict[str, Any]]] = {
        "ollama": [],
        "openai_compatible": [],
    }

    # Discover Ollama
    result["ollama"] = discover_ollama_models()

    # Discover from configured endpoints
    for env_key in ["OPENAI_BASE_URL", "LOCALAI_BASE_URL", "LM_STUDIO_BASE_URL", "VLLM_BASE_URL"]:
        base_url = os.environ.get(env_key, "")
        if base_url:
            models = discover_openai_compatible_models(base_url=base_url)
            if models:
                result["openai_compatible"].extend(models)

    return result


# ═══════════════════════════════════════
#  Local provider labels (from OpenClaude)
# ═══════════════════════════════════════

def get_local_provider_label(base_url: str) -> str:
    """Identify local provider by base URL (inspired by OpenClaude's getLocalOpenAICompatibleProviderLabel)."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(base_url)
        host = parsed.hostname or ""
        port = parsed.port
        path = parsed.path.lower()

        if port == 1234 or "lmstudio" in host or "lm-studio" in host:
            return "LM Studio"
        if port == 11434 or "ollama" in host:
            return "Ollama"
        if "localai" in host or "localai" in path:
            return "LocalAI"
        if "jan" in host or "jan" in path:
            return "Jan"
        if "kobold" in host or "kobold" in path:
            return "KoboldCpp"
        if "vllm" in host or "vllm" in path:
            return "vLLM"
        if "open-webui" in host or "openwebui" in path:
            return "Open WebUI"
        return "OpenAI-compatible"
    except Exception:
        return "OpenAI-compatible"


class ProviderDiscovery:
    """
    Discovers available local and remote providers.

    Combines:
    - Ollama model discovery
    - OpenAI-compatible endpoint discovery
    - Known cloud provider status
    """

    def __init__(self):
        pass

    def discover_all(self) -> dict[str, list[dict[str, Any]]]:
        """Discover all models from all sources."""
        return discover_all_local()

    def discover_ollama(self) -> list[dict[str, Any]]:
        return discover_ollama_models()

    def discover_endpoint(self, base_url: str, api_key: str = "") -> list[dict[str, Any]]:
        return discover_openai_compatible_models(base_url=base_url, api_key=api_key)

    def detect_local_endpoints(self) -> list[dict[str, Any]]:
        """Detect common local endpoints."""
        endpoints = []

        # Common local endpoints
        candidates = [
            ("http://localhost:11434/v1", "Ollama"),
            ("http://localhost:1234/v1", "LM Studio"),
            ("http://localhost:8080/v1", "LocalAI / vLLM"),
            ("http://127.0.0.1:1337/v1", "Atomic Chat"),
        ]

        for base_url, label in candidates:
            try:
                req = Request(f"{base_url}/models", method="GET")
                req.add_header("Content-Type", "application/json")
                resp = urlopen(req, timeout=2)
                if resp.status == 200:
                    endpoints.append({
                        "base_url": base_url,
                        "label": label,
                        "reachable": True,
                    })
            except (URLError, OSError):
                continue

        return endpoints
