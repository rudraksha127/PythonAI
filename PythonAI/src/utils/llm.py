"""
ANTI-GRAVITY GOD MODE — Multi-Provider LLM Engine
═══════════════════════════════════════════════════
Parallel multi-API key rotation with automatic failover.
Every agent picks the fastest available provider.
"""

import os
import asyncio
import time
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
from dataclasses import dataclass, field
from loguru import logger

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests
from src.utils.cost_tracker import tracker

@dataclass
class ProviderConfig:
    name: str
    api_key_env: str
    base_url: str
    model: str
    max_tokens: int = 4096
    temperature: float = 0.2
    priority: int = 1  # lower = higher priority
    rate_limit_cooldown: float = 0
    last_error_time: float = 0
    consecutive_errors: int = 0
    extra_payload: dict = field(default_factory=dict)

PROVIDERS: dict[str, ProviderConfig] = {
    # ── NVIDIA NIM FLEET (Priority 1 - Fastest & Highest Quality) ──
    "nvidia_llama": ProviderConfig(
        name="nvidia_llama",
        api_key_env="NVIDIA_LLAMA_KEY",
        base_url="https://integrate.api.nvidia.com/v1/chat/completions",
        model="meta/llama-3.1-70b-instruct",
        priority=1,
    ),
    "nvidia_nemotron": ProviderConfig(
        name="nvidia_nemotron",
        api_key_env="NVIDIA_NEMOTRON_KEY",
        base_url="https://integrate.api.nvidia.com/v1/chat/completions",
        model="nvidia/nemotron-mini-4b-instruct",
        max_tokens=512,  # Small model with 4096 total context limit
        priority=1,
    ),
    "nvidia_mavarik": ProviderConfig(
        name="nvidia_mavarik",
        api_key_env="NVIDIA_MAVARIK_KEY",
        base_url="https://integrate.api.nvidia.com/v1/chat/completions",
        model="meta/llama-4-maverick-17b-128e-instruct",
        priority=1,
    ),
    "nvidia_qwen": ProviderConfig(
        name="nvidia_qwen",
        api_key_env="NVIDIA_QWEN_KEY",
        base_url="https://integrate.api.nvidia.com/v1/chat/completions",
        model="qwen/qwen3-next-80b-a3b-instruct",
        priority=1,
    ),
    "nvidia_moonshot": ProviderConfig(
        name="nvidia_moonshot",
        api_key_env="NVIDIA_MOONSHOT_KEY",
        base_url="https://integrate.api.nvidia.com/v1/chat/completions",
        model="moonshotai/kimi-k2.6",
        max_tokens=16384,
        temperature=1.0,
        priority=1,
        extra_payload={"chat_template_kwargs": {"thinking": True}}
    ),

    # ── OPENAI & GROQ (Priority 1) ──
    "openai": ProviderConfig(
        name="openai",
        api_key_env="OPENAI_API_KEY",
        base_url="https://api.openai.com/v1/chat/completions",
        model="gpt-4o",
        priority=1,
    ),
    "groq": ProviderConfig(
        name="groq",
        api_key_env="GROQ_API_KEY",
        base_url="https://api.groq.com/openai/v1/chat/completions",
        model="llama-3.3-70b-versatile",
        priority=1,
    ),

    # ── FREE / MID-TIER FALLBACKS (Priority 2) ──
    "mistral": ProviderConfig(
        name="mistral",
        api_key_env="MISTRAL_API_KEY",
        base_url="https://api.mistral.ai/v1/chat/completions",
        model="mistral-small-latest",
        priority=2,
    ),
    "cerebras": ProviderConfig(
        name="cerebras",
        api_key_env="CEREBRAS_API_KEY",
        base_url="https://api.cerebras.ai/v1/chat/completions",
        model="llama-4-scout-17b-16e-instruct",
        priority=2,
    ),
    "sambanova": ProviderConfig(
        name="sambanova",
        api_key_env="SAMBANOVA_API_KEY",
        base_url="https://api.sambanova.ai/v1/chat/completions",
        model="Meta-Llama-3.3-70B-Instruct",
        priority=2,
    ),
    "openrouter": ProviderConfig(
        name="openrouter",
        api_key_env="OPENROUTER_API_KEY",
        base_url="https://openrouter.ai/api/v1/chat/completions",
        model="meta-llama/llama-3.3-70b-instruct:free",
        priority=2,
    ),

    # ── LOCAL FALLBACK (always available, priority 99) ──
    "local": ProviderConfig(
        name="local",
        api_key_env="",
        base_url="",
        model="qwen2.5-coder:14b",
        priority=99,
    ),
}

_provider_lock = threading.Lock()

def _get_api_key(provider: ProviderConfig) -> Optional[str]:
    if not provider.api_key_env:
        return None
    return os.environ.get(provider.api_key_env, "")

def _is_provider_available(provider: ProviderConfig) -> bool:
    if provider.name == "local": return True
    if not _get_api_key(provider): return False
    if provider.rate_limit_cooldown > 0:
        if time.time() - provider.last_error_time < provider.rate_limit_cooldown:
            return False
        with _provider_lock:
            provider.rate_limit_cooldown = 0
            provider.consecutive_errors = 0
    return True

def _call_api_provider(provider: ProviderConfig, prompt: str, system_prompt: str = "") -> str:
    key = _get_api_key(provider)
    if not key: raise ValueError(f"No API key for {provider.name}")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if provider.name == "openrouter":
        headers["HTTP-Referer"] = "https://anti-gravity-god-mode.local"

    payload = {
        "model": provider.model,
        "messages": messages,
        "temperature": provider.temperature,
        "max_tokens": provider.max_tokens,
        **provider.extra_payload
    }

    start = time.time()
    response = requests.post(provider.base_url, headers=headers, json=payload, timeout=90)
    elapsed = time.time() - start

    if response.status_code == 429:
        with _provider_lock:
            provider.consecutive_errors += 1
            provider.rate_limit_cooldown = min(60 * (2 ** provider.consecutive_errors), 300)
            provider.last_error_time = time.time()
        raise ConnectionError(f"{provider.name} rate limited (429). Cooldown: {provider.rate_limit_cooldown}s")

    if response.status_code != 200:
        with _provider_lock: provider.consecutive_errors += 1
        raise ConnectionError(f"{provider.name} returned {response.status_code}: {response.text[:200]}")

    with _provider_lock:
        provider.consecutive_errors = 0
        provider.rate_limit_cooldown = 0

    try:
        text = response.json()["choices"][0]["message"]["content"]
    except KeyError:
        raise ValueError(f"Unexpected response format from {provider.name}: {response.text[:200]}")

    tracker.log_call(provider.name, prompt, text)
    logger.debug(f"[LLM] {provider.name} responded in {elapsed:.2f}s ({len(text)} chars)")
    return text

def _call_local(prompt: str, system_prompt: str = "") -> str:
    try:
        import ollama
        messages = []
        if system_prompt: messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        r = ollama.chat(model="qwen2.5-coder:14b", messages=messages, options={"temperature": 0.2})
        return r["message"]["content"]
    except Exception as e:
        return f"[Local Ollama Failed]: {e}"

def generate_with_provider(prompt: str, provider: str = "auto", system_prompt: str = "") -> str:
    if provider == "auto": return generate_auto(prompt, system_prompt)
    if provider == "local": return _call_local(prompt, system_prompt)
    cfg = PROVIDERS.get(provider)
    if not cfg or not _is_provider_available(cfg): return generate_auto(prompt, system_prompt)
    try:
        return _call_api_provider(cfg, prompt, system_prompt)
    except Exception as e:
        logger.warning(f"{provider} failed: {e}. Falling back to auto.")
        return generate_auto(prompt, system_prompt)

def generate_auto(prompt: str, system_prompt: str = "") -> str:
    available = sorted([p for p in PROVIDERS.values() if _is_provider_available(p)], key=lambda p: p.priority)
    for cfg in available:
        if cfg.name == "local": continue
        try: return _call_api_provider(cfg, prompt, system_prompt)
        except Exception: continue
    return _call_local(prompt, system_prompt)

def generate_parallel(prompt: str, providers: list[str] = None, system_prompt: str = "") -> str:
    """Fire all high-priority APIs simultaneously, first one to respond wins."""
    if providers is None:
        # Get all available Priority 1 APIs
        available = [p for p in PROVIDERS.values() if _is_provider_available(p) and p.priority == 1]
        providers = [p.name for p in available]

    if not providers:
        return _call_local(prompt, system_prompt)

    logger.info(f"[LLM PARALLEL] Racing providers: {providers}")

    with ThreadPoolExecutor(max_workers=len(providers)) as executor:
        futures = {}
        for name in providers:
            cfg = PROVIDERS.get(name)
            if cfg and _is_provider_available(cfg):
                future = executor.submit(_call_api_provider, cfg, prompt, system_prompt)
                futures[future] = name

        for future in as_completed(futures, timeout=90):
            name = futures[future]
            try:
                result = future.result()
                logger.success(f"[LLM PARALLEL] Winner: {name}")
                return result
            except Exception as e:
                logger.warning(f"[LLM PARALLEL] {name} failed: {e}")
                continue

    return _call_local(prompt, system_prompt)

def get_provider_status() -> list[dict]:
    statuses = []
    for name, cfg in PROVIDERS.items():
        statuses.append({
            "name": name, "model": cfg.model, "priority": cfg.priority,
            "has_key": bool(_get_api_key(cfg)) if cfg.name != "local" else True,
            "available": _is_provider_available(cfg),
            "cooldown_remaining": max(0, cfg.rate_limit_cooldown - (time.time() - cfg.last_error_time)) if cfg.rate_limit_cooldown > 0 else 0,
            "consecutive_errors": cfg.consecutive_errors,
        })
    return sorted(statuses, key=lambda s: (not s["available"], PROVIDERS[s["name"]].priority))

async def generate_async(prompt: str, provider: str = "auto", system_prompt: str = "") -> str:
    """Async wrapper for generate_with_provider using run_in_executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        generate_with_provider,
        prompt,
        provider,
        system_prompt
    )

async def generate_parallel_async(prompt: str, providers: list[str] = None, system_prompt: str = "") -> str:
    """Async wrapper for generate_parallel using run_in_executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        generate_parallel,
        prompt,
        providers,
        system_prompt
    )

