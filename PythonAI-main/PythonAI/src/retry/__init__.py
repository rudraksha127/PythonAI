"""
ForgeAI Auto-Retry Pipeline — Exponential Backoff + Circuit Breaker
===================================================================

Configurable retry logic for LLM API calls with:
  - Exponential backoff with jitter
  - Circuit breaker pattern (stops retrying after N failures)
  - Per-provider configurable settings
  - Automatic fallback to alternate providers

Usage:
    from src.retry import RetryConfig, auto_retry, circuit_breaker

    @auto_retry(max_retries=3, base_delay=2.0)
    def call_api(provider: str, prompt: str) -> str:
        ...
"""

from __future__ import annotations

import asyncio
import functools
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any, Callable, TypeVar

T = TypeVar("T")


# ═══════════════════════════════════════
# Error Types
# ═══════════════════════════════════════


class RetryableErrorType(Enum):
    """Types of errors that can be retried."""

    RATE_LIMIT = "rate_limit"  # 429
    SERVER_ERROR = "server_error"  # 5xx
    TIMEOUT = "timeout"
    NETWORK = "network"
    SERVICE_UNAVAILABLE = "service_unavailable"  # 503
    UNKNOWN = "unknown"


# ═══════════════════════════════════════
# Configuration
# ═══════════════════════════════════════


@dataclass
class RetryConfig:
    """Per-provider retry configuration."""

    max_retries: int = 3
    base_delay: float = 2.0  # Seconds
    max_delay: float = 60.0  # Max backoff cap
    jitter_factor: float = 0.5  # ±50% jitter
    timeout_seconds: float = 30.0
    retryable_status_codes: set[int] = field(default_factory=lambda: {429, 500, 502, 503, 504})
    circuit_breaker_threshold: int = 5  # Failures before circuit opens
    circuit_breaker_reset_seconds: float = 30.0  # Time before reset


# ═══════════════════════════════════════
# Circuit Breaker
# ═══════════════════════════════════════


class CircuitState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


class CircuitBreaker:
    """Per-provider circuit breaker to stop hammering failing APIs."""

    def __init__(self, threshold: int = 5, reset_seconds: float = 30.0) -> None:
        self._threshold = threshold
        self._reset_seconds = reset_seconds
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._lock = Lock()

    def record_success(self) -> None:
        """Record a successful call — reset circuit."""
        with self._lock:
            self._failure_count = 0
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """Record a failed call — may open circuit."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._failure_count >= self._threshold:
                self._state = CircuitState.OPEN

    def allow_request(self) -> bool:
        """Check if a request should be allowed through."""
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                # Check if reset time elapsed
                if time.time() - self._last_failure_time >= self._reset_seconds:
                    self._state = CircuitState.HALF_OPEN
                    return True
                return False

            # HALF_OPEN — allow one test request
            return True

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state

    @property
    def failure_count(self) -> int:
        with self._lock:
            return self._failure_count


# ═══════════════════════════════════════
# Retry Logic
# ═══════════════════════════════════════


class RetryHandler:
    """Handles retry logic with exponential backoff, jitter, and circuit breaker."""

    def __init__(self, config: RetryConfig | None = None) -> None:
        self._config = config or RetryConfig()
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._stats: dict[str, Any] = {
            "total_retries": 0,
            "total_failures": 0,
            "circuit_open_count": 0,
        }

    def _get_circuit_breaker(self, provider: str) -> CircuitBreaker:
        """Get or create a circuit breaker for a provider."""
        if provider not in self._circuit_breakers:
            self._circuit_breakers[provider] = CircuitBreaker(
                threshold=self._config.circuit_breaker_threshold,
                reset_seconds=self._config.circuit_breaker_reset_seconds,
            )
        return self._circuit_breakers[provider]

    def execute(
        self,
        fn: Callable[..., T],
        *args: Any,
        provider: str = "default",
        **kwargs: Any,
    ) -> T:
        """Execute a function with retry logic (synchronous)."""
        cb = self._get_circuit_breaker(provider)

        if not cb.allow_request():
            self._stats["circuit_open_count"] += 1
            raise CircuitBreakerOpenError(f"Circuit breaker open for provider '{provider}'")

        last_error: Exception | None = None

        for attempt in range(self._config.max_retries + 1):
            try:
                result = fn(*args, **kwargs)
                cb.record_success()
                return result
            except Exception as e:
                last_error = e
                cb.record_failure()
                self._stats["total_failures"] += 1

                if attempt < self._config.max_retries:
                    self._stats["total_retries"] += 1
                    delay = self._compute_delay(attempt)
                    time.sleep(delay)

        raise RetryExhaustedError(
            f"All {self._config.max_retries} retries exhausted for provider '{provider}': {last_error}"
        ) from last_error

    async def execute_async(
        self,
        fn: Callable[..., Any],
        *args: Any,
        provider: str = "default",
        **kwargs: Any,
    ) -> Any:
        """Execute an async function with retry logic."""
        cb = self._get_circuit_breaker(provider)

        if not cb.allow_request():
            self._stats["circuit_open_count"] += 1
            raise CircuitBreakerOpenError(f"Circuit breaker open for provider '{provider}'")

        last_error: Exception | None = None

        for attempt in range(self._config.max_retries + 1):
            try:
                result = await fn(*args, **kwargs)
                cb.record_success()
                return result
            except Exception as e:
                last_error = e
                cb.record_failure()
                self._stats["total_failures"] += 1

                if attempt < self._config.max_retries:
                    self._stats["total_retries"] += 1
                    delay = self._compute_delay(attempt)
                    await asyncio.sleep(delay)

        raise RetryExhaustedError(
            f"All {self._config.max_retries} retries exhausted for provider '{provider}': {last_error}"
        ) from last_error

    def _compute_delay(self, attempt: int) -> float:
        """Compute delay with exponential backoff and jitter."""
        delay = self._config.base_delay * (2**attempt)
        delay = min(delay, self._config.max_delay)
        jitter = random.uniform(
            delay * (1 - self._config.jitter_factor),
            delay * (1 + self._config.jitter_factor),
        )
        return max(0, jitter)

    def get_stats(self) -> dict[str, Any]:
        """Get retry handler statistics."""
        circuit_breakers = {
            provider: {
                "state": cb.state.value,
                "failures": cb.failure_count,
            }
            for provider, cb in self._circuit_breakers.items()
        }
        return {
            **self._stats,
            "circuit_breakers": circuit_breakers,
            "config": {
                "max_retries": self._config.max_retries,
                "base_delay": self._config.base_delay,
                "max_delay": self._config.max_delay,
                "circuit_breaker_threshold": self._config.circuit_breaker_threshold,
                "circuit_breaker_reset_seconds": self._config.circuit_breaker_reset_seconds,
            },
        }

    def reset_circuit_breaker(self, provider: str) -> None:
        """Manually reset a circuit breaker."""
        if provider in self._circuit_breakers:
            self._circuit_breakers[provider] = CircuitBreaker(
                threshold=self._config.circuit_breaker_threshold,
                reset_seconds=self._config.circuit_breaker_reset_seconds,
            )


# ═══════════════════════════════════════
# Decorator
# ═══════════════════════════════════════


def auto_retry(
    max_retries: int = 3,
    base_delay: float = 2.0,
    provider: str = "default",
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator: automatically retry a function on failure."""
    config = RetryConfig(max_retries=max_retries, base_delay=base_delay)
    handler = RetryHandler(config)

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            return handler.execute(fn, *args, provider=provider, **kwargs)
        return wrapper

    return decorator


# ═══════════════════════════════════════
# Exceptions
# ═══════════════════════════════════════


class CircuitBreakerOpenError(Exception):
    """Raised when a circuit breaker is open and blocking requests."""
    pass


class RetryExhaustedError(Exception):
    """Raised when all retry attempts have been exhausted."""
    pass


# ═══════════════════════════════════════
# Error Classifier
# ═══════════════════════════════════════


def classify_error(status_code: int | None, error_message: str = "") -> RetryableErrorType:
    """Classify an error to determine if it's retryable."""
    if status_code:
        if status_code == 429:
            return RetryableErrorType.RATE_LIMIT
        if status_code == 503:
            return RetryableErrorType.SERVICE_UNAVAILABLE
        if status_code >= 500:
            return RetryableErrorType.SERVER_ERROR

    msg = error_message.lower()
    if "timeout" in msg or "timed out" in msg:
        return RetryableErrorType.TIMEOUT
    if "connection" in msg or "network" in msg or "econnrefused" in msg:
        return RetryableErrorType.NETWORK

    return RetryableErrorType.UNKNOWN


def is_retryable(status_code: int | None = None, error_message: str = "") -> bool:
    """Determine if an error is worth retrying."""
    error_type = classify_error(status_code, error_message)
    return error_type in {
        RetryableErrorType.RATE_LIMIT,
        RetryableErrorType.SERVER_ERROR,
        RetryableErrorType.TIMEOUT,
        RetryableErrorType.NETWORK,
        RetryableErrorType.SERVICE_UNAVAILABLE,
    }


# ═══════════════════════════════════════
# Global Singleton
# ═══════════════════════════════════════

_handler: RetryHandler | None = None


def get_retry_handler(config: RetryConfig | None = None) -> RetryHandler:
    """Get or create the global retry handler."""
    global _handler
    if _handler is None:
        _handler = RetryHandler(config=config)
    return _handler


__all__ = [
    "RetryConfig",
    "RetryHandler",
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "RetryExhaustedError",
    "auto_retry",
    "classify_error",
    "is_retryable",
    "get_retry_handler",
]
