"""
PythonAI Provider System
========================
Multi-provider routing inspired by OpenClaude's architecture.
Routes LLM requests to the best available provider based on
model capabilities, availability, cost, and user preference.

Individual provider API modules:
  openai_provider   — OpenAI/GPT models
  gemini_provider   — Google Gemini models
  deepseek_provider — DeepSeek models
  ollama_provider   — Local Ollama models
  mistral_provider  — Mistral AI models
"""

from typing import Any

from .anthropic_provider import call_anthropic
from .deepseek_provider import call_deepseek
from .discovery import (
    ProviderDiscovery,
    discover_all_local,
    discover_ollama_models,
    discover_openai_compatible_models,
)
from .gemini_provider import call_gemini
from .mistral_provider import call_mistral
from .ollama_provider import call_ollama, call_ollama_native
from .openai_provider import call_openai, call_openai_stream
from .profile import (
    DEFAULT_PROFILE_PATH,
    ProfileManager,
    ProviderProfile,
)
from .registry import (
    ALL_MODELS,
    ALL_PROVIDERS,
    ModelCapabilities,
    ModelDescriptor,
    ModelRegistry,
    ProviderDescriptor,
    find_models_by_capability,
    get_model_info,
    get_registry,
)
from .router import (
    ProviderRouter,
    RouteResult,
    RouteStrategy,
)

# All provider API call functions
PROVIDER_API_CALLS = {
    "openai": call_openai,
    "gemini": call_gemini,
    "deepseek": call_deepseek,
    "ollama": call_ollama,
    "mistral": call_mistral,
    "anthropic": call_anthropic,
    "groq": call_openai,  # Uses OpenAI-compatible API
    "xai": call_openai,  # Uses OpenAI-compatible API
    "openrouter": call_openai,  # Uses OpenAI-compatible API
    "sambanova": call_openai,  # Uses OpenAI-compatible API
    "cerebras": call_openai,  # Uses OpenAI-compatible API
    "together": call_openai,  # Uses OpenAI-compatible API
    "huggingface": call_openai,  # Uses OpenAI-compatible API
    "fireworks": call_openai,  # Uses OpenAI-compatible API
    "deepinfra": call_openai,  # Uses OpenAI-compatible API
    "novita": call_openai,  # Uses OpenAI-compatible API
}


def get_provider_api(provider_id: str) -> Any:
    """Get the API call function for a provider."""
    return PROVIDER_API_CALLS.get(provider_id, call_openai)


__all__ = [
    "ModelRegistry",
    "ModelCapabilities",
    "ModelDescriptor",
    "ProviderDescriptor",
    "ALL_MODELS",
    "ALL_PROVIDERS",
    "get_model_info",
    "find_models_by_capability",
    "get_registry",
    "ProviderRouter",
    "RouteResult",
    "RouteStrategy",
    "ProviderProfile",
    "ProfileManager",
    "DEFAULT_PROFILE_PATH",
    "ProviderDiscovery",
    "discover_ollama_models",
    "discover_openai_compatible_models",
    "discover_all_local",
    "call_openai",
    "call_openai_stream",
    "call_gemini",
    "call_deepseek",
    "call_ollama",
    "call_ollama_native",
    "call_mistral",
    "call_anthropic",
    "PROVIDER_API_CALLS",
    "get_provider_api",
]
