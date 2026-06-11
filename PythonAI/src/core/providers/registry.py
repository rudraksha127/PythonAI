"""
Provider Registry — Model and Provider Descriptors
===================================================
Inspired by OpenClaude's integrations/models/*.ts and define.ts.
Defines models with their capabilities, context windows, and provider info.

Examples:
    # Find a model with specific capabilities
    model = get_model_info("gpt-4o")
    coding_models = find_models_by_capability(coding=True, streaming=True)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ═══════════════════════════════════════
#  Capabilities descriptor
# ═══════════════════════════════════════

@dataclass
class ModelCapabilities:
    """Capabilities a model supports."""
    vision: bool = False
    streaming: bool = True
    function_calling: bool = True
    json_mode: bool = True
    reasoning: bool = False
    precise_token_count: bool = False
    parallel_tool_calls: bool = True


# ═══════════════════════════════════════
#  Model descriptor
# ═══════════════════════════════════════

@dataclass
class ModelDescriptor:
    """Describes an LLM model and its properties."""
    id: str
    label: str
    provider: str               # "openai", "anthropic", "gemini", "deepseek", "ollama", etc.
    capabilities: ModelCapabilities
    context_window: int = 128_000
    max_output_tokens: int = 16_384
    classification: list[str] = field(default_factory=lambda: ["chat", "coding"])
    default_model: bool = False
    pricing_per_million_input: float = 0.0    # USD (0 = unknown / local)
    pricing_per_million_output: float = 0.0


# ═══════════════════════════════════════
#  Provider descriptor
# ═══════════════════════════════════════

@dataclass
class ProviderDescriptor:
    """Describes an LLM provider."""
    id: str
    label: str
    base_url: str
    env_key: str                       # Environment variable for API key
    api_type: str = "openai"           # "openai", "anthropic", "gemini"
    default_model: str = ""
    is_local: bool = False
    requires_key: bool = True
    priority: int = 5                  # 1=highest, 99=lowest


# ═══════════════════════════════════════
#  Model Registry
# ═══════════════════════════════════════

class ModelRegistry:
    """Registry of all known models and their capabilities."""

    def __init__(self):
        self._models: dict[str, ModelDescriptor] = {}
        self._providers: dict[str, ProviderDescriptor] = {}

    # ── Registration ────────────────────────────────────────

    def register_model(self, model: ModelDescriptor) -> None:
        self._models[model.id] = model

    def register_models(self, models: list[ModelDescriptor]) -> None:
        for m in models:
            self._models[m.id] = m

    def register_provider(self, provider: ProviderDescriptor) -> None:
        self._providers[provider.id] = provider

    def register_providers(self, providers: list[ProviderDescriptor]) -> None:
        for p in providers:
            self._providers[p.id] = p

    # ── Queries ─────────────────────────────────────────────

    def get_model(self, model_id: str) -> ModelDescriptor | None:
        return self._models.get(model_id)

    def get_provider(self, provider_id: str) -> ProviderDescriptor | None:
        return self._providers.get(provider_id)

    def list_models(self, provider: str | None = None) -> list[ModelDescriptor]:
        if provider:
            return [m for m in self._models.values() if m.provider == provider]
        return list(self._models.values())

    def list_providers(self) -> list[ProviderDescriptor]:
        return list(self._providers.values())

    def find_models_by_capability(
        self,
        vision: bool | None = None,
        streaming: bool | None = None,
        function_calling: bool | None = None,
        reasoning: bool | None = None,
        coding: bool | None = None,
        min_context: int | None = None,
        provider: str | None = None,
    ) -> list[ModelDescriptor]:
        """Find models matching specific capability requirements."""
        results = []
        for model in self._models.values():
            if provider and model.provider != provider:
                continue
            caps = model.capabilities
            if vision is not None and caps.vision != vision:
                continue
            if streaming is not None and caps.streaming != streaming:
                continue
            if function_calling is not None and caps.function_calling != function_calling:
                continue
            if reasoning is not None and caps.reasoning != reasoning:
                continue
            if min_context and model.context_window < min_context:
                continue
            if coding is not None:
                is_coding = "coding" in model.classification
                if is_coding != coding:
                    continue
            results.append(model)
        return results

    def get_default_model(self, provider: str) -> ModelDescriptor | None:
        """Get the default model for a provider."""
        for model in self._models.values():
            if model.provider == provider and model.default_model:
                return model
        return None

    def suggest_model(
        self,
        task: str = "coding",
        prefer_reasoning: bool = False,
        prefer_local: bool = False,
    ) -> ModelDescriptor | None:
        """Suggest the best model for a task type."""
        candidates = []

        for model in self._models.values():
            if prefer_local and model.provider not in ("ollama", "local"):
                continue

            # Filter by task
            if task == "coding" and "coding" not in model.classification:
                continue
            if task == "chat" and "chat" not in model.classification:
                continue
            if task == "reasoning" and "reasoning" not in model.classification:
                continue

            if prefer_reasoning and not model.capabilities.reasoning:
                continue

            candidates.append(model)

        # Score by priority: default > context > cost
        def score(m: ModelDescriptor) -> float:
            s = 0.0
            if m.default_model:
                s += 50
            s += min(m.context_window / 100_000, 20)
            if m.pricing_per_million_input == 0:
                s += 10  # Local / free
            else:
                s -= m.pricing_per_million_input * 2
            return s

        candidates.sort(key=score, reverse=True)
        return candidates[0] if candidates else None

    @property
    def model_count(self) -> int:
        return len(self._models)

    @property
    def provider_count(self) -> int:
        return len(self._providers)


# ═══════════════════════════════════════
#  Built-in Model Definitions
# ═══════════════════════════════════════

def _build_default_registry() -> ModelRegistry:
    """Build the default registry with all known models and providers."""
    reg = ModelRegistry()

    # ── Providers ───────────────────────────────────────────────
    providers = [
        ProviderDescriptor("openai", "OpenAI", "https://api.openai.com/v1", "OPENAI_API_KEY",
                           default_model="gpt-4o", priority=1),
        ProviderDescriptor("gemini", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY",
                           default_model="gemini-2.5-flash", api_type="gemini", priority=2),
        ProviderDescriptor("deepseek", "DeepSeek", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY",
                           default_model="deepseek-chat", priority=2),
        ProviderDescriptor("mistral", "Mistral AI", "https://api.mistral.ai/v1", "MISTRAL_API_KEY",
                           default_model="mistral-small-latest", priority=3),
        ProviderDescriptor("groq", "Groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY",
                           default_model="llama-3.3-70b-versatile", priority=3),
        ProviderDescriptor("anthropic", "Anthropic", "https://api.anthropic.com/v1", "ANTHROPIC_API_KEY",
                           default_model="claude-sonnet-4", api_type="anthropic", priority=1),
        ProviderDescriptor("ollama", "Ollama", "http://localhost:11434/v1", "",
                           default_model="qwen2.5-coder:14b", is_local=True, requires_key=False, priority=99),
        ProviderDescriptor("xai", "xAI Grok", "https://api.x.ai/v1", "XAI_API_KEY",
                           default_model="grok-2", priority=2),
        ProviderDescriptor("openrouter", "OpenRouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY",
                           default_model="meta-llama/llama-3.3-70b-instruct", priority=4),
        ProviderDescriptor("sambanova", "SambaNova", "https://api.sambanova.ai/v1", "SAMBANOVA_API_KEY",
                           default_model="Meta-Llama-3.3-70B-Instruct", priority=4),
        ProviderDescriptor("cerebras", "Cerebras", "https://api.cerebras.ai/v1", "CEREBRAS_API_KEY",
                           default_model="llama-3.1-8b", priority=3),
        ProviderDescriptor("together", "Together AI", "https://api.together.xyz/v1", "TOGETHER_API_KEY",
                           default_model="mistralai/Mixtral-8x22B-Instruct-v0.1", priority=4),
        ProviderDescriptor("huggingface", "HuggingFace Inference", "https://api-inference.huggingface.co/v1", "HF_TOKEN",
                           default_model="Qwen/Qwen2.5-Coder-32B-Instruct", priority=5),
        ProviderDescriptor("fireworks", "Fireworks AI", "https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY",
                           default_model="accounts/fireworks/models/llama-v3p3-70b-instruct", priority=4),
        ProviderDescriptor("deepinfra", "DeepInfra", "https://api.deepinfra.com/v1/openai", "DEEPINFRA_API_KEY",
                           default_model="meta-llama/Llama-3.3-70B-Instruct", priority=4),
        ProviderDescriptor("novita", "Novita AI", "https://api.novita.ai/v3/openai", "NOVITA_API_KEY",
                           default_model="meta-llama/llama-3.1-8b-instruct", priority=5),
    ]
    reg.register_providers(providers)

    GPT_CAPS = ModelCapabilities(vision=True, streaming=True, function_calling=True,
                                  json_mode=True, reasoning=False, precise_token_count=True)
    GPT_R_CAPS = ModelCapabilities(vision=True, streaming=True, function_calling=True,
                                    json_mode=True, reasoning=True, precise_token_count=True)

    # ── OpenAI Models ───────────────────────────────────────────
    reg.register_models([
        ModelDescriptor("gpt-4o", "GPT-4o", "openai", GPT_CAPS, 128_000, 16_384,
                        ["chat", "vision", "coding"], True, 2.50, 10.0),
        ModelDescriptor("gpt-4o-mini", "GPT-4o Mini", "openai", GPT_CAPS, 128_000, 16_384,
                        ["chat", "vision", "coding"], False, 0.15, 0.60),
        ModelDescriptor("gpt-4-turbo", "GPT-4 Turbo", "openai", GPT_CAPS, 128_000, 4_096,
                        ["chat", "coding"], False, 10.0, 30.0),
        ModelDescriptor("gpt-4.1", "GPT-4.1", "openai", GPT_CAPS, 1_047_576, 32_768,
                        ["chat", "coding"], False, 2.0, 8.0),
        ModelDescriptor("gpt-4.1-mini", "GPT-4.1 Mini", "openai", GPT_CAPS, 1_047_576, 32_768,
                        ["chat", "coding"], False, 0.40, 1.60),
        ModelDescriptor("o1", "o1", "openai", GPT_R_CAPS, 200_000, 100_000,
                        ["chat", "reasoning", "coding"], False, 15.0, 60.0),
        ModelDescriptor("o3-mini", "o3 Mini", "openai", GPT_R_CAPS, 200_000, 100_000,
                        ["chat", "reasoning", "coding"], False, 1.10, 4.40),
        ModelDescriptor("o4-mini", "o4 Mini", "openai", GPT_R_CAPS, 200_000, 100_000,
                        ["chat", "reasoning", "coding"], False, 1.10, 4.40),
    ])

    # ── Gemini Models ───────────────────────────────────────────
    GEMINI_CAPS = ModelCapabilities(vision=True, streaming=True, function_calling=True,
                                     json_mode=True, reasoning=True, precise_token_count=False)
    reg.register_models([
        ModelDescriptor("gemini-2.5-flash", "Gemini 2.5 Flash", "gemini", GEMINI_CAPS, 1_048_576, 65_536,
                        ["chat", "reasoning", "vision", "coding"], True, 0.15, 0.60),
        ModelDescriptor("gemini-2.5-pro", "Gemini 2.5 Pro", "gemini", GEMINI_CAPS, 1_048_576, 65_536,
                        ["chat", "reasoning", "vision", "coding"], False, 1.25, 10.0),
        ModelDescriptor("gemini-2.0-flash", "Gemini 2.0 Flash", "gemini", GEMINI_CAPS, 1_048_576, 8_192,
                        ["chat", "vision", "coding"], False, 0.10, 0.40),
    ])

    # ── DeepSeek Models ─────────────────────────────────────────
    DS_CAPS = ModelCapabilities(vision=False, streaming=True, function_calling=True,
                                 json_mode=True, reasoning=False, precise_token_count=False)
    DS_R_CAPS = ModelCapabilities(vision=False, streaming=True, function_calling=True,
                                   json_mode=True, reasoning=True, precise_token_count=False)
    reg.register_models([
        ModelDescriptor("deepseek-chat", "DeepSeek Chat", "deepseek", DS_CAPS, 128_000, 8_192,
                        ["chat", "coding"], True, 0.27, 1.10),
        ModelDescriptor("deepseek-reasoner", "DeepSeek Reasoner", "deepseek", DS_R_CAPS, 128_000, 65_536,
                        ["chat", "reasoning", "coding"], False, 0.55, 2.19),
        ModelDescriptor("deepseek-v4-flash", "DeepSeek V4 Flash", "deepseek", DS_CAPS, 1_048_576, 65_536,
                        ["chat", "coding"], False, 0.0, 0.0),
        ModelDescriptor("deepseek-v4-pro", "DeepSeek V4 Pro", "deepseek", DS_R_CAPS, 1_048_576, 65_536,
                        ["chat", "reasoning", "coding"], False, 0.0, 0.0),
    ])

    # ── Mistral Models ──────────────────────────────────────────
    MISTRAL_CAPS = ModelCapabilities(vision=False, streaming=True, function_calling=True,
                                      json_mode=True, reasoning=False, precise_token_count=False)
    reg.register_models([
        ModelDescriptor("mistral-large-latest", "Mistral Large", "mistral", MISTRAL_CAPS, 256_000, 32_768,
                        ["chat", "coding"], False, 2.0, 6.0),
        ModelDescriptor("mistral-small-latest", "Mistral Small", "mistral", MISTRAL_CAPS, 256_000, 32_768,
                        ["chat", "coding"], True, 0.20, 0.60),
        ModelDescriptor("codestral", "Codestral", "mistral", MISTRAL_CAPS, 32_768, 8_192,
                        ["chat", "coding"], False, 0.0, 0.0),
    ])

    # ── Groq Models ─────────────────────────────────────────────
    GROQ_CAPS = ModelCapabilities(vision=False, streaming=True, function_calling=True,
                                   json_mode=True, reasoning=False, precise_token_count=False)
    reg.register_models([
        ModelDescriptor("llama-3.3-70b-versatile", "Llama 3.3 70B", "groq", GROQ_CAPS, 128_000, 32_768,
                        ["chat", "coding"], True, 0.0, 0.0),
        ModelDescriptor("llama-3.1-8b-instant", "Llama 3.1 8B", "groq", GROQ_CAPS, 128_000, 8_192,
                        ["chat", "coding"], False, 0.0, 0.0),
        ModelDescriptor("mixtral-8x7b-32768", "Mixtral 8x7B", "groq", GROQ_CAPS, 32_768, 32_768,
                        ["chat", "coding"], False, 0.0, 0.0),
    ])

    # ── Anthropic Models ────────────────────────────────────────
    ANTH_CAPS = ModelCapabilities(vision=True, streaming=True, function_calling=True,
                                   json_mode=True, reasoning=False, precise_token_count=False)
    ANTH_R_CAPS = ModelCapabilities(vision=True, streaming=True, function_calling=True,
                                     json_mode=True, reasoning=True, precise_token_count=False)
    reg.register_models([
        ModelDescriptor("claude-sonnet-4", "Claude Sonnet 4", "anthropic", ANTH_CAPS, 200_000, 32_000,
                        ["chat", "vision", "coding"], True, 3.0, 15.0),
        ModelDescriptor("claude-haiku-4", "Claude Haiku 4", "anthropic", ANTH_CAPS, 200_000, 64_000,
                        ["chat", "vision", "coding"], False, 0.80, 4.0),
        ModelDescriptor("claude-opus-4", "Claude Opus 4", "anthropic", ANTH_R_CAPS, 200_000, 32_000,
                        ["chat", "reasoning", "vision", "coding"], False, 15.0, 75.0),
    ])

    # ── Ollama / Local Models ───────────────────────────────────
    LOCAL_CAPS = ModelCapabilities(vision=False, streaming=True, function_calling=True,
                                    json_mode=True, reasoning=False, precise_token_count=False)
    LOCAL_R_CAPS = ModelCapabilities(vision=False, streaming=True, function_calling=True,
                                      json_mode=True, reasoning=True, precise_token_count=False)
    reg.register_models([
        ModelDescriptor("qwen2.5-coder:14b", "Qwen 2.5 Coder 14B", "ollama", LOCAL_CAPS, 32_768, 8_192,
                        ["chat", "coding"], True),
        ModelDescriptor("qwen2.5-coder:7b", "Qwen 2.5 Coder 7B", "ollama", LOCAL_CAPS, 32_768, 8_192,
                        ["chat", "coding"], False),
        ModelDescriptor("deepseek-coder-v2:16b", "DeepSeek Coder V2 16B", "ollama", LOCAL_CAPS, 163_840, 8_192,
                        ["chat", "coding"], False),
        ModelDescriptor("llama3.1:8b", "Llama 3.1 8B", "ollama", LOCAL_CAPS, 128_000, 8_192,
                        ["chat", "coding"], False),
        ModelDescriptor("deepseek-r1:14b", "DeepSeek R1 14B", "ollama", LOCAL_R_CAPS, 65_536, 8_192,
                        ["chat", "reasoning", "coding"], False),
        ModelDescriptor("phi4:14b", "Phi-4 14B", "ollama", LOCAL_CAPS, 16_384, 4_096,
                        ["chat", "coding"], False),
    ])

    # ── xAI Models ──────────────────────────────────────────────
    XAI_CAPS = ModelCapabilities(vision=True, streaming=True, function_calling=True,
                                  json_mode=True, reasoning=False, precise_token_count=False)
    reg.register_models([
        ModelDescriptor("grok-2", "Grok 2", "xai", XAI_CAPS, 128_000, 8_192,
                        ["chat", "vision", "coding"], True, 2.0, 10.0),
        ModelDescriptor("grok-2-vision", "Grok 2 Vision", "xai", XAI_CAPS, 32_768, 8_192,
                        ["chat", "vision"], False, 5.0, 15.0),
    ])

    # ── SambaNova Models ────────────────────────────────────────
    SAMBA_CAPS = ModelCapabilities(vision=False, streaming=True, function_calling=True,
                                    json_mode=True, reasoning=False, precise_token_count=False)
    reg.register_models([
        ModelDescriptor("Meta-Llama-3.3-70B-Instruct", "Llama 3.3 70B", "sambanova", SAMBA_CAPS, 128_000, 2_048,
                        ["chat", "coding"], True, 0.0, 0.0),
        ModelDescriptor("Meta-Llama-3.1-405B-Instruct", "Llama 3.1 405B", "sambanova", SAMBA_CAPS, 128_000, 2_048,
                        ["chat", "coding"], False, 0.0, 0.0),
    ])

    # ── Cerebras Models ─────────────────────────────────────────
    CEREBRAS_CAPS = ModelCapabilities(vision=False, streaming=True, function_calling=True,
                                       json_mode=True, reasoning=False, precise_token_count=False)
    reg.register_models([
        ModelDescriptor("llama-3.1-8b", "Llama 3.1 8B", "cerebras", CEREBRAS_CAPS, 8_192, 8_192,
                        ["chat", "coding"], True, 0.0, 0.0),
        ModelDescriptor("llama-4-scout-17b-16e-instruct", "Llama 4 Scout 17B", "cerebras", CEREBRAS_CAPS, 256_000, 8_192,
                        ["chat", "coding"], False, 0.0, 0.0),
    ])

    return reg


# Singleton
ALL_PROVIDERS: list[ProviderDescriptor] = []
ALL_MODELS: list[ModelDescriptor] = []
_default_registry: ModelRegistry | None = None


def _ensure_registry() -> ModelRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = _build_default_registry()
        # Populate module-level convenience lists
        global ALL_PROVIDERS, ALL_MODELS
        ALL_PROVIDERS = _default_registry.list_providers()
        ALL_MODELS = _default_registry.list_models()
    return _default_registry


def get_model_info(model_id: str) -> ModelDescriptor | None:
    """Get model descriptor by ID."""
    return _ensure_registry().get_model(model_id)


def find_models_by_capability(**kwargs: Any) -> list[ModelDescriptor]:
    """Find models matching specific capabilities."""
    return _ensure_registry().find_models_by_capability(**kwargs)


def get_registry() -> ModelRegistry:
    """Get or create the default model registry singleton."""
    return _ensure_registry()
