"""
Central API key management for dataset generation.

Stores provider API keys in ~/.pythonai/apikeys.json with restricted file
permissions.  Supports CLI (set / list / delete / export) and programmatic
usage so the generator, the CLI, and the Web UI all read from the same store.
"""

from __future__ import annotations

import json
import os
import stat
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

# ═══════════════════════════════════════
#  File & provider metadata
# ═══════════════════════════════════════

CONFIG_DIR = Path.home() / ".pythonai"
KEYS_FILE = CONFIG_DIR / "apikeys.json"

# ---------------------------------------------------------------------------
# Provider registry — maps provider keys to environment variable names.
# These are the canonical keys used throughout the system.
# ---------------------------------------------------------------------------

ALL_PROVIDERS: dict[str, str] = {
    # OpenAI-compatible inference providers
    "groq": "GROQ_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
    "sambanova": "SAMBANOVA_API_KEY",
    "together": "TOGETHER_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "huggingface": "HF_TOKEN",
    "mistral": "MISTRAL_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
    "novita": "NOVITA_API_KEY",
    "deepinfra": "DEEPINFRA_API_KEY",
    # NVIDIA NIM inference — individual model keys
    "nvidia": "NVIDIA_API_KEY",
    "nvidia_llama": "NVIDIA_LLAMA_KEY",
    "nvidia_nemotron": "NVIDIA_NEMOTRON_KEY",
    "nvidia_mavarik": "NVIDIA_MAVARIK_KEY",
    "nvidia_qwen": "NVIDIA_QWEN_KEY",
    "nvidia_moonshot": "NVIDIA_MOONSHOT_KEY",
    # Premium frontier model providers
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "xai": "XAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "cohere": "COHERE_API_KEY",
}

# Provider capability classification — used by the MultiAgentKeyManager
# to decide which provider to use for which task type.
PROVIDER_TIERS: dict[str, str] = {
    "anthropic": "premium",
    "openai": "premium",
    "google": "premium",
    "xai": "premium",
    "deepseek": "premium",
    "cohere": "premium",
    "mistral": "standard",
    "groq": "standard",
    "cerebras": "standard",
    "sambanova": "standard",
    "together": "standard",
    "openrouter": "standard",
    "fireworks": "standard",
    "novita": "standard",
    "deepinfra": "standard",
    "nvidia": "standard",
    "nvidia_llama": "standard",
    "nvidia_nemotron": "standard",
    "nvidia_mavarik": "standard",
    "nvidia_qwen": "standard",
    "nvidia_moonshot": "standard",
    "huggingface": "standard",
}

# Maximum concurrency per provider (safe ceiling to avoid 429s)
PROVIDER_MAX_CONCURRENCY: dict[str, int] = {
    "anthropic": 5,
    "openai": 10,
    "google": 10,
    "xai": 5,
    "deepseek": 5,
    "cohere": 5,
    "mistral": 5,
    "groq": 10,
    "cerebras": 5,
    "sambanova": 5,
    "together": 5,
    "openrouter": 5,
    "fireworks": 5,
    "novita": 5,
    "deepinfra": 5,
    "nvidia": 10,
    "nvidia_llama": 10,
    "nvidia_nemotron": 10,
    "nvidia_mavarik": 10,
    "nvidia_qwen": 10,
    "nvidia_moonshot": 10,
    "huggingface": 5,
}

# Friendly display names
PROVIDER_LABELS: dict[str, str] = {
    "groq": "Groq",
    "cerebras": "Cerebras",
    "sambanova": "SambaNova",
    "together": "Together AI",
    "openrouter": "OpenRouter",
    "huggingface": "HuggingFace",
    "mistral": "Mistral AI",
    "fireworks": "Fireworks AI",
    "novita": "Novita AI",
    "deepinfra": "DeepInfra",
    "nvidia": "NVIDIA NIM",
    "nvidia_llama": "NVIDIA Llama",
    "nvidia_nemotron": "NVIDIA Nemotron",
    "nvidia_mavarik": "NVIDIA Maverick",
    "nvidia_qwen": "NVIDIA Qwen",
    "nvidia_moonshot": "NVIDIA Moonshot",
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "google": "Google Gemini",
    "xai": "xAI Grok",
    "deepseek": "DeepSeek",
    "cohere": "Cohere",
}


# ═══════════════════════════════════════
#  I/O helpers
# ═══════════════════════════════════════

def _ensure_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _load() -> dict[str, dict[str, str]]:
    """Return {provider_name: {"key": "..."}}."""
    if not KEYS_FILE.exists():
        return {}
    try:
        with KEYS_FILE.open("r", encoding="utf-8") as f:
            data: dict[str, dict[str, str]] = json.load(f)
            return data
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict[str, dict[str, str]]) -> None:
    _ensure_dir()
    tmp = KEYS_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    try:
        tmp.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    tmp.replace(KEYS_FILE)


# ═══════════════════════════════════════
#  Public API
# ═══════════════════════════════════════

def get_keys() -> dict[str, str]:
    """Return {provider: key} for all currently *stored* keys."""
    raw = _load()
    return {k: v["key"] for k, v in raw.items() if v.get("key")}


def get_key(provider: str) -> str | None:
    """Return a single provider's stored key, or None."""
    raw = _load()
    entry = raw.get(provider)
    return entry["key"] if entry and entry.get("key") else None


def set_key(provider: str, key: str) -> dict[str, Any]:
    """Store an API key for *provider*.  Returns a result dict."""
    provider = provider.strip().lower()
    if provider not in ALL_PROVIDERS:
        return {"success": False, "error": f"Unknown provider '{provider}'. Valid: {list(ALL_PROVIDERS)}"}
    key = key.strip()
    if len(key) < 8:
        return {"success": False, "error": "Key too short (min 8 characters)."}

    data = _load()
    data[provider] = {"key": key}
    _save(data)
    return {"success": True, "provider": provider, "env_var": ALL_PROVIDERS[provider]}


def delete_key(provider: str) -> dict[str, Any]:
    """Remove a stored API key.  Returns a result dict."""
    provider = provider.strip().lower()
    data = _load()
    if provider not in data:
        return {"success": False, "error": f"No key stored for '{provider}'."}
    del data[provider]
    _save(data)
    return {"success": True, "provider": provider}


def list_keys(masked: bool = True) -> dict[str, str]:
    """
    Return {provider: masked_key_or_status}.
    If *masked* is True, show only first 6 + last 4 chars of each key,
    otherwise return the full key.
    """
    raw = _load()
    result: dict[str, str] = {}
    for prov, entry in raw.items():
        k = entry.get("key", "")
        if k and masked and len(k) > 12:
            result[prov] = f"{k[:6]}...{k[-4:]}"
        elif k and masked:
            result[prov] = f"{k[:4]}..."
        else:
            result[prov] = k if k else "[empty]"
    # Also list known providers that have no stored key
    for prov in ALL_PROVIDERS:
        if prov not in result:
            result[prov] = "[not set]"
    return result


def active_providers() -> list[str]:
    """Return providers that have a valid-looking stored key."""
    raw = _load()
    active: list[str] = []
    for prov, entry in raw.items():
        k = entry.get("key", "")
        if k and len(k) >= 8 and prov in ALL_PROVIDERS:
            active.append(prov)
    return sorted(active)


def export_dotenv(path: str | Path | None = None) -> dict[str, Any]:
    """
    Write a .env file with all stored keys.
    Default path is project-root /.env.
    """
    data = _load()
    if not data:
        return {"success": False, "error": "No API keys stored to export."}

    # Find project root by walking up from this file
    root = Path(__file__).resolve().parent.parent.parent
    dest = Path(path) if path else root / ".env"

    lines: list[str] = []
    for prov, entry in data.items():
        env_name = ALL_PROVIDERS.get(prov)
        if env_name and entry.get("key"):
            lines.append(f'{env_name}="{entry["key"]}"')

    if not lines:
        return {"success": False, "error": "No exportable keys found."}

    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"success": True, "path": str(dest), "count": len(lines)}


def resolve_key(provider: str) -> str | None:
    """
    Resolve a provider's API key with this priority:
      1. Stored file (~/.pythonai/apikeys.json)
      2. Environment variable (e.g. GROQ_API_KEY)
      3. Falls back to None
    """
    # 1. Stored
    stored = get_key(provider)
    if stored:
        return stored
    # 2. Env var
    env_name = ALL_PROVIDERS.get(provider)
    if env_name:
        env_val = os.getenv(env_name, "").strip()
        if env_val and len(env_val) >= 8:
            return env_val
    return None


def resolve_all() -> dict[str, str]:
    """
    Resolve all provider keys (stored > env var).
    Returns {provider: key} for every provider that has a usable key.
    """
    resolved: dict[str, str] = {}
    for prov in ALL_PROVIDERS:
        key = resolve_key(prov)
        if key:
            resolved[prov] = key
    return resolved


def get_available_providers(min_tier: str = "standard") -> list[str]:
    """
    Return sorted list of providers that have a key available,
    optionally filtered by a minimum tier.

    Tiers: premium > standard
    """
    resolved = resolve_all()
    available = []
    for prov in resolved:
        tier = PROVIDER_TIERS.get(prov, "standard")
        if min_tier == "premium" and tier != "premium":
            continue
        available.append(prov)
    return sorted(available, key=lambda p: (PROVIDER_TIERS.get(p, "standard") != "premium", p))


def get_provider_info(provider: str) -> dict[str, Any]:
    """Return metadata about a provider."""
    resolved = resolve_all()
    return {
        "name": provider,
        "label": PROVIDER_LABELS.get(provider, provider.title()),
        "env_var": ALL_PROVIDERS.get(provider),
        "has_key": provider in resolved,
        "tier": PROVIDER_TIERS.get(provider, "standard"),
        "max_concurrency": PROVIDER_MAX_CONCURRENCY.get(provider, 5),
    }


# ═══════════════════════════════════════
#  Multi-Agent Key Manager
# ═══════════════════════════════════════

class RateLimitState:
    """Tracks rate-limit backoff for a single provider."""

    def __init__(self) -> None:
        self.backoff_until: float = 0.0
        self.consecutive_429s: int = 0
        self.last_reset: float = time.time()
        self.minute_calls: int = 0

    def is_rate_limited(self) -> bool:
        """Check if we're currently in a backoff window."""
        now = time.time()
        # Reset minute counter every 60s
        if now - self.last_reset >= 60:
            self.minute_calls = 0
            self.last_reset = now
        return now < self.backoff_until

    def record_success(self) -> None:
        """Record a successful call, reducing backoff if any."""
        self.minute_calls += 1
        self.consecutive_429s = max(0, self.consecutive_429s - 1)

    def record_429(self) -> None:
        """Record a 429, increasing backoff exponentially."""
        self.consecutive_429s += 1
        backoff = min(2 ** self.consecutive_429s, 120)  # Max 2 min
        self.backoff_until = time.time() + backoff


class MultiAgentKeyManager:
    """
    Thread-safe concurrent key pool for multi-agent parallel execution.

    Manages API keys across multiple providers, tracks rate limits,
    provides fair scheduling, and distributes work across all available
    providers for maximum throughput.

    Features:
    - Concurrent key borrowing/returning via semaphore per provider
    - Automatic rate-limit detection with exponential backoff
    - Provider tier awareness (premium vs standard)
    - Usage statistics per provider
    - Round-robin scheduling across equally-tiered providers
    """

    def __init__(self, providers: dict[str, str] | None = None) -> None:
        """
        Initialize with a dict of {provider_name: api_key}.
        If None, resolves all available keys automatically.
        """
        self._providers: dict[str, str] = providers if providers is not None else resolve_all()
        self._lock = threading.RLock()
        self._rate_states: dict[str, RateLimitState] = {
            p: RateLimitState() for p in self._providers
        }
        self._semaphores: dict[str, threading.BoundedSemaphore] = {
            p: threading.BoundedSemaphore(PROVIDER_MAX_CONCURRENCY.get(p, 5))
            for p in self._providers
        }
        self._usage: dict[str, dict[str, int]] = {
            p: {"calls": 0, "429s": 0, "errors": 0, "tokens": 0}
            for p in self._providers
        }
        self._openai_rr_idx: int = 0

    # ── Properties ──────────────────────────────────────────────

    @property
    def active_providers(self) -> list[str]:
        """Return list of provider names that have keys loaded."""
        with self._lock:
            return list(self._providers.keys())

    @property
    def premium_providers(self) -> list[str]:
        """Return premium-tier providers with keys."""
        with self._lock:
            return [p for p in self._providers if PROVIDER_TIERS.get(p) == "premium"]

    @property
    def standard_providers(self) -> list[str]:
        """Return standard-tier providers with keys."""
        with self._lock:
            return [p for p in self._providers if PROVIDER_TIERS.get(p, "standard") == "standard"]

    def count(self) -> int:
        """Number of providers with keys."""
        return len(self._providers)

    # ── Key Management ─────────────────────────────────────────

    def get_key(self, provider: str) -> str | None:
        """Get the API key for a provider."""
        return self._providers.get(provider)

    def add_key(self, provider: str, key: str) -> None:
        """Add or update a provider's key at runtime."""
        with self._lock:
            self._providers[provider] = key
            if provider not in self._rate_states:
                self._rate_states[provider] = RateLimitState()
            if provider not in self._semaphores:
                self._semaphores[provider] = threading.BoundedSemaphore(
                    PROVIDER_MAX_CONCURRENCY.get(provider, 5)
                )
            if provider not in self._usage:
                self._usage[provider] = {"calls": 0, "429s": 0, "errors": 0, "tokens": 0}

    def remove_key(self, provider: str) -> None:
        """Remove a provider from the pool."""
        with self._lock:
            self._providers.pop(provider, None)
            self._rate_states.pop(provider, None)
            self._semaphores.pop(provider, None)
            self._usage.pop(provider, None)

    # ── Concurrent Borrow / Return ─────────────────────────────

    def acquire(self, provider: str, timeout: float = 30.0) -> bool:
        """
        Acquire the semaphore for a provider.
        Returns True if acquired, False if timeout or rate-limited.
        """
        if provider not in self._semaphores:
            return False

        state = self._rate_states.get(provider)
        if state and state.is_rate_limited():
            return False

        sem = self._semaphores[provider]
        try:
            acquired = sem.acquire(timeout=timeout)
            return acquired
        except Exception:
            return False

    def release(self, provider: str) -> None:
        """Release a provider's semaphore slot."""
        sem = self._semaphores.get(provider)
        if sem:
            try:
                sem.release()
            except ValueError:
                pass  # Released too many times

    # ── Rate Limit Tracking ────────────────────────────────────

    def record_success(self, provider: str, tokens_used: int = 0) -> None:
        """Record a successful API call."""
        state = self._rate_states.get(provider)
        if state:
            state.record_success()
        usage = self._usage.get(provider)
        if usage:
            usage["calls"] += 1
            usage["tokens"] += tokens_used

    def record_429(self, provider: str) -> None:
        """Record a rate-limit response."""
        state = self._rate_states.get(provider)
        if state:
            state.record_429()
        usage = self._usage.get(provider)
        if usage:
            usage["429s"] += 1

    def record_error(self, provider: str) -> None:
        """Record a non-rate-limit error."""
        usage = self._usage.get(provider)
        if usage:
            usage["errors"] += 1

    # ── Provider Selection ─────────────────────────────────────

    def select_providers(
        self,
        n: int = 1,
        preferred_tier: str = "any",
        exclude: set[str] | None = None,
    ) -> list[str]:
        """
        Select the best N providers for a task, considering rate limits.

        Args:
            n: Number of providers to select.
            preferred_tier: "premium", "standard", or "any".
            exclude: Set of provider names to exclude.

        Returns:
            List of provider names, length <= n.
        """
        with self._lock:
            exclude = exclude or set()
            candidates = []

            for prov in self._providers:
                if prov in exclude:
                    continue
                state = self._rate_states.get(prov)
                if state and state.is_rate_limited():
                    continue
                tier = PROVIDER_TIERS.get(prov, "standard")
                if preferred_tier == "premium" and tier != "premium":
                    continue
                # Prefer providers with fewer calls (fair scheduling)
                weight = self._usage.get(prov, {}).get("calls", 0)
                candidates.append((weight, tier, prov))

            # Sort: premium first (if tier allows), then by fewest calls
            def sort_key(item):
                w, tier, prov = item
                tier_rank = 0 if tier == "premium" else 1
                return (tier_rank, w)

            candidates.sort(key=sort_key)
            return [prov for _, _, prov in candidates[:n]]

    def next_openai_compatible(self) -> str | None:
        """
        Round-robin through OpenAI-compatible providers.
        Returns the next available provider name or None.
        """
        with self._lock:
            compatible = [
                p for p in self._providers
                if p not in ("anthropic", "google")  # These have different APIs
                and not (self._rate_states.get(p, RateLimitState()).is_rate_limited())
            ]
            if not compatible:
                return None

            idx = self._openai_rr_idx % len(compatible)
            self._openai_rr_idx = (self._openai_rr_idx + 1) % len(compatible)
            return compatible[idx]

    # ── Stats ──────────────────────────────────────────────────

    def get_usage_report(self) -> dict[str, Any]:
        """Return a full usage report across all providers."""
        with self._lock:
            report: dict[str, Any] = {
                "total_providers": len(self._providers),
                "providers": {},
                "summary": {"total_calls": 0, "total_429s": 0, "total_errors": 0},
            }
            for prov, usage in sorted(self._usage.items()):
                state = self._rate_states.get(prov)
                is_limited = state and state.is_rate_limited()
                report["providers"][prov] = {
                    **usage,
                    "tier": PROVIDER_TIERS.get(prov, "standard"),
                    "label": PROVIDER_LABELS.get(prov, prov.title()),
                    "rate_limited": is_limited,
                    "backoff_remaining": max(0, (state.backoff_until - time.time())) if state else 0,
                }
                report["summary"]["total_calls"] += usage["calls"]
                report["summary"]["total_429s"] += usage["429s"]
                report["summary"]["total_errors"] += usage["errors"]
            return report

    def print_report(self) -> None:
        """Print a formatted usage report to stdout."""
        report = self.get_usage_report()
        print("=" * 60)
        print("  Multi-Agent Key Manager — Usage Report")
        print(f"  {report['summary']['total_calls']} total calls | "
              f"{report['summary']['total_429s']} rate limits | "
              f"{report['summary']['total_errors']} errors")
        print(f"  {report['total_providers']} providers active")
        print("=" * 60)
        for prov, info in report["providers"].items():
            rl = " 🔴 RATE LIMITED" if info["rate_limited"] else ""
            print(f"  {info['label']:14s} | calls={info['calls']:4d} | "
                  f"429s={info['429s']:2d} | errs={info['errors']:2d} | "
                  f"tokens={info['tokens']:7d}{rl}")
        print("=" * 60)

    # ── Context Manager for parallel execution ─────────────────

    def parallel_map(
        self,
        tasks: list[Any],
        worker_fn: Callable[[str, Any], Any],
        preferred_tier: str = "any",
        max_workers: int | None = None,
        timeout: float = 120.0,
    ) -> list[Any]:
        """
        Execute tasks in parallel, distributing across all available providers.

        Args:
            tasks: List of task data items to process.
            worker_fn: Callable(provider_name, task_data) -> result.
            preferred_tier: "premium", "standard", or "any".
            max_workers: Max parallel workers (default: 2x number of providers).
            timeout: Per-task timeout in seconds.

        Returns:
            List of results, same order as tasks.
        """
        n_providers = len(self._providers)
        max_workers = max_workers or (n_providers * 2)

        results: list[Any] = []

        def worker_wrapper(task_data: Any) -> Any:
            # Select a provider for this task
            provider = self.select_providers(n=1, preferred_tier=preferred_tier)
            if not provider:
                return None
            prov = provider[0]

            acquired = self.acquire(prov, timeout=10)
            if not acquired:
                return None

            try:
                result = worker_fn(prov, task_data)
                self.record_success(prov)
                return result
            except Exception as exc:
                exc_str = str(exc).lower()
                if "429" in exc_str or "rate limit" in exc_str:
                    self.record_429(prov)
                else:
                    self.record_error(prov)
                return None
            finally:
                self.release(prov)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(worker_wrapper, t): i for i, t in enumerate(tasks)}
            ordered = [None] * len(tasks)
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    ordered[idx] = future.result(timeout=timeout)
                except Exception:
                    ordered[idx] = None

        return ordered

    def __repr__(self) -> str:
        return f"MultiAgentKeyManager({self.count()} providers: {', '.join(self.active_providers)})"
