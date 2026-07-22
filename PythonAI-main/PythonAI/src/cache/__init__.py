"""
ForgeAI Smart Cache — Semantic + Exact Match LLM Response Caching
==================================================================

Caches LLM responses for both exact and semantic matches to reduce
cost and latency. Uses embedding similarity for semantic matching.

Features:
  - Exact match (MD5 hash) for identical queries
  - Semantic match (cosine similarity > threshold) for similar queries
  - TTL-based expiry per entry
  - LRU eviction when cache is full
  - Multi-backend: in-memory, Redis (optional)

Usage:
    from src.cache import SmartCache, CacheConfig

    cache = SmartCache(config=CacheConfig(similarity_threshold=0.92))
    cache.set("user query", {"response": "..."}, provider="openai")
    result = cache.get("user query", provider="openai")  # exact match
    result = cache.semantic_get("similar query", provider="openai")  # semantic match
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np


# ═══════════════════════════════════════
# Configuration
# ═══════════════════════════════════════


@dataclass
class CacheConfig:
    """Smart Cache configuration."""

    enabled: bool = True
    max_size: int = 512  # Max cached entries (LRU eviction)
    ttl_seconds: int = 300  # 5 minutes default TTL
    similarity_threshold: float = 0.92  # Cosine similarity for semantic matching
    embedding_dim: int = 384  # Embedding dimension (all-MiniLM-L6-v2 default)
    enable_semantic: bool = True  # Enable semantic matching
    persist_path: str | None = None  # Path to persist cache to disk


# ═══════════════════════════════════════
# Cache Entry
# ═══════════════════════════════════════


@dataclass
class _CacheEntry:
    """A single cache entry."""

    key_hash: str
    query: str
    response: Any
    embedding: list[float] | None
    provider: str
    model: str
    created_at: float
    expires_at: float
    hit_count: int = 0
    token_savings: int = 0  # Estimated tokens saved


# ═══════════════════════════════════════
# Embedding Provider
# ═══════════════════════════════════════


class _SimpleEmbedder:
    """Simple embedding provider using sentence-transformers or fallback."""

    def __init__(self, dim: int = 384) -> None:
        self._dim = dim
        self._model = None
        self._available = False
        self._init_model()

    def _init_model(self) -> None:
        """Try to load sentence-transformers, fall back to hashing."""
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
            self._available = True
            self._dim = self._model.get_sentence_embedding_dimension() or self._dim
        except ImportError:
            self._available = False

    def embed(self, text: str) -> list[float]:
        """Embed text. Falls back to random projection if model unavailable."""
        if self._available and self._model is not None:
            emb = self._model.encode(text, normalize_embeddings=True)
            return emb.tolist()

        # Fallback: deterministic hash-based embedding (not great but better than nothing)
        np.random.seed(abs(hash(text)) % (2**31))
        return np.random.randn(self._dim).tolist()

    @property
    def available(self) -> bool:
        return self._available

    @property
    def dim(self) -> int:
        return self._dim


# ═══════════════════════════════════════
# Smart Cache
# ═══════════════════════════════════════


class SmartCache:
    """LLM response cache with exact and semantic matching."""

    def __init__(self, config: CacheConfig | None = None) -> None:
        self._config = config or CacheConfig()
        self._lock = Lock()
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._embedder = _SimpleEmbedder(dim=self._config.embedding_dim)
        self._stats: dict[str, Any] = {
            "hits_exact": 0,
            "hits_semantic": 0,
            "misses": 0,
            "evictions": 0,
            "total_entries_saved": 0,
        }

        # Load persisted cache if available
        if self._config.persist_path:
            self._load_from_disk()

    # ─── Public API ───────────────────────────────────────────────

    def get(self, query: str, provider: str = "default", model: str = "") -> Any | None:
        """Get cached response by exact match (hash-based)."""
        if not self._config.enabled:
            return None

        key = self._make_key(query, provider, model)
        with self._lock:
            if key not in self._cache:
                self._stats["misses"] += 1
                return None

            entry = self._cache[key]
            if time.time() > entry.expires_at:
                del self._cache[key]
                self._stats["misses"] += 1
                return None

            # Move to end (LRU)
            self._cache.move_to_end(key)
            entry.hit_count += 1
            self._stats["hits_exact"] += 1
            return entry.response

    def semantic_get(self, query: str, provider: str = "default", model: str = "") -> Any | None:
        """Get cached response by semantic similarity.

        Returns the response with the highest similarity above threshold.
        """
        if not self._config.enabled or not self._config.enable_semantic:
            return None

        query_emb = self._embedder.embed(query)
        best_match: tuple[float, _CacheEntry | None] = (0.0, None)

        with self._lock:
            now = time.time()
            expired_keys: list[str] = []

            for key, entry in self._cache.items():
                if now > entry.expires_at:
                    expired_keys.append(key)
                    continue

                if entry.provider != provider:
                    continue

                if entry.embedding is not None:
                    sim = self._cosine_similarity(query_emb, entry.embedding)
                    if sim > best_match[0] and sim >= self._config.similarity_threshold:
                        best_match = (sim, entry)

            # Clean expired
            for k in expired_keys:
                del self._cache[k]

        entry = best_match[1]
        if entry is not None:
            with self._lock:
                self._cache.move_to_end(entry.key_hash)
                entry.hit_count += 1
                self._stats["hits_semantic"] += 1
            return entry.response

        with self._lock:
            self._stats["misses"] += 1
        return None

    def set(
        self,
        query: str,
        response: Any,
        provider: str = "default",
        model: str = "",
        token_count: int = 0,
        ttl: int | None = None,
    ) -> None:
        """Cache a response for future exact and semantic lookups."""
        if not self._config.enabled:
            return

        key = self._make_key(query, provider, model)
        now = time.time()
        expires_at = now + (ttl or self._config.ttl_seconds)

        with self._lock:
            # Evict if at capacity
            if key not in self._cache and len(self._cache) >= self._config.max_size:
                self._cache.popitem(last=False)
                self._stats["evictions"] += 1

            entry = _CacheEntry(
                key_hash=key,
                query=query,
                response=response,
                embedding=self._embedder.embed(query) if self._config.enable_semantic else None,
                provider=provider,
                model=model,
                created_at=now,
                expires_at=expires_at,
                token_savings=token_count,
            )
            self._cache[key] = entry
            self._cache.move_to_end(key)
            self._stats["total_entries_saved"] += 1

    def invalidate(self, query: str, provider: str = "default") -> bool:
        """Remove a specific entry from cache."""
        key = self._make_key(query, provider)
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
        return False

    def clear(self) -> int:
        """Clear all cache entries. Returns count of cleared entries."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
        return count

    # ─── Stats ────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total_hits = self._stats["hits_exact"] + self._stats["hits_semantic"]
            total_requests = total_hits + self._stats["misses"]
            hit_rate = (total_hits / max(1, total_requests)) * 100

            total_entries = len(self._cache)
            total_tokens_saved = sum(
                e.token_savings for e in self._cache.values()
            )

            return {
                "enabled": self._config.enabled,
                "semantic_enabled": self._config.enable_semantic,
                "max_size": self._config.max_size,
                "ttl_seconds": self._config.ttl_seconds,
                "similarity_threshold": self._config.similarity_threshold,
                "entries": total_entries,
                "hits_exact": self._stats["hits_exact"],
                "hits_semantic": self._stats["hits_semantic"],
                "misses": self._stats["misses"],
                "total_requests": total_requests,
                "hit_rate_percent": round(hit_rate, 2),
                "evictions": self._stats["evictions"],
                "total_tokens_saved": total_tokens_saved,
                "embedder_available": self._embedder.available,
            }

    def clear_stats(self) -> None:
        """Reset statistics."""
        with self._lock:
            self._stats = {
                "hits_exact": 0,
                "hits_semantic": 0,
                "misses": 0,
                "evictions": 0,
                "total_entries_saved": 0,
            }

    # ─── Persistence ──────────────────────────────────────────────

    def save_to_disk(self) -> None:
        """Persist cache to disk."""
        if not self._config.persist_path:
            return

        with self._lock:
            data = {
                "config": {
                    "max_size": self._config.max_size,
                    "ttl_seconds": self._config.ttl_seconds,
                    "similarity_threshold": self._config.similarity_threshold,
                },
                "entries": [
                    {
                        "key_hash": e.key_hash,
                        "query": e.query,
                        "response": e.response,
                        "embedding": e.embedding,
                        "provider": e.provider,
                        "model": e.model,
                        "created_at": e.created_at,
                        "expires_at": e.expires_at,
                        "hit_count": e.hit_count,
                        "token_savings": e.token_savings,
                    }
                    for e in self._cache.values()
                ],
                "stats": self._stats,
            }

            path = self._config.persist_path
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

    def _load_from_disk(self) -> None:
        """Load persisted cache from disk."""
        if not self._config.persist_path:
            return

        path = self._config.persist_path
        if not path or not Path(path).exists():
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            now = time.time()
            for entry_data in data.get("entries", []):
                if now > entry_data.get("expires_at", 0):
                    continue

                entry = _CacheEntry(
                    key_hash=entry_data["key_hash"],
                    query=entry_data["query"],
                    response=entry_data["response"],
                    embedding=entry_data.get("embedding"),
                    provider=entry_data.get("provider", "default"),
                    model=entry_data.get("model", ""),
                    created_at=entry_data["created_at"],
                    expires_at=entry_data["expires_at"],
                    hit_count=entry_data.get("hit_count", 0),
                    token_savings=entry_data.get("token_savings", 0),
                )
                self._cache[entry.key_hash] = entry

            self._stats = data.get("stats", self._stats)
        except (json.JSONDecodeError, KeyError, FileNotFoundError):
            pass

    # ─── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _make_key(query: str, provider: str, model: str = "") -> str:
        """Create a deterministic hash key from query + provider + model."""
        raw = f"{query}:::{provider}:::{model}"
        return hashlib.md5(raw.encode()).hexdigest()

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        arr_a = np.array(a, dtype=np.float32)
        arr_b = np.array(b, dtype=np.float32)
        norm_a = np.linalg.norm(arr_a)
        norm_b = np.linalg.norm(arr_b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(arr_a, arr_b) / (norm_a * norm_b))


# ═══════════════════════════════════════
# Global Singleton
# ═══════════════════════════════════════

_cache: SmartCache | None = None


def get_cache(config: CacheConfig | None = None) -> SmartCache:
    """Get or create the global smart cache."""
    global _cache
    if _cache is None:
        _cache = SmartCache(config=config)
    return _cache


__all__ = [
    "SmartCache",
    "CacheConfig",
    "get_cache",
]
